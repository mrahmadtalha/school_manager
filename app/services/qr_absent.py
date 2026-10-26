"""QR attendance phase 3: mark students Absent after the cutoff time.

How a day works
---------------
1. At the cutoff time (default 10:00) students with *no* attendance record for
   today are the "not arrived" list.  Anyone on Leave, Present, Late or already
   Absent has a record, so they are never touched.
2. **Approval mode** - the list waits on the QR Attendance page.  An admin
   approves (students are marked Absent) or rejects (nobody is marked).
3. **Automatic mode** - students are marked Absent straight away, with one
   safety rule: when fewer than ``absent_min_scan_percent`` % of the students
   have arrived, the check falls back to approval mode.  That situation almost
   always means a dead phone / Wi-Fi / app, not 400 absent children.
4. The absent message to the guardian is held back for
   ``absent_message_delay_minutes`` so a mistake can still be fixed.
5. A student who scans *after* being marked Absent is corrected by
   ``qr_attendance._mark_student`` (see ``handle_arrival_after_absent``): a
   message that was not sent yet is cancelled, one that already went out is
   followed by a short correction message.

Only one check runs per school day (``QrAbsentRun.run_date`` is unique).
"""

import logging
from datetime import date, datetime, timedelta

from app.database import db
from app.models import AttendanceModel, MessageQueue, StudentModel
from app.models.qr_config import QrAbsentRun, QrConfig

logger = logging.getLogger(__name__)

MODE_AUTO = 'auto'
MODE_APPROVAL = 'approval'
ATTENDED = ('Present', 'Late')
# Message states that mean "the guardian may already have read it".
_SENT_STATES = ('sending', 'sending_auto', 'sent')
_WAITING_STATES = ('pending', 'approved')


# -- settings ---------------------------------------------------------------

def parse_cutoff(value):
    """'10:00' -> datetime.time (falls back to 10:00 for bad text)."""
    try:
        return datetime.strptime((value or '').strip()[:5], '%H:%M').time()
    except ValueError:
        return datetime.strptime('10:00', '%H:%M').time()


def clean_settings(form):
    """Validate the settings form; returns (values, error_message_or_None)."""
    cutoff = (form.get('absent_cutoff_time') or '').strip()
    try:
        datetime.strptime(cutoff, '%H:%M')
    except ValueError:
        return None, 'Enter the cutoff time like 10:00.'
    mode = form.get('absent_mode')
    if mode not in (MODE_AUTO, MODE_APPROVAL):
        mode = MODE_APPROVAL
    try:
        percent = int(form.get('absent_min_scan_percent', 20))
        delay = int(form.get('absent_message_delay_minutes', 30))
    except (TypeError, ValueError):
        return None, 'Minimum arrivals and message delay must be whole numbers.'
    if not 0 <= percent <= 100:
        return None, 'Minimum arrivals must be between 0 and 100 percent.'
    if not 0 <= delay <= 720:
        return None, 'Message delay must be between 0 and 720 minutes.'
    return {
        'auto_absent_enabled': form.get('auto_absent_enabled') == 'on',
        'absent_cutoff_time': cutoff,
        'absent_mode': mode,
        'absent_min_scan_percent': percent,
        'absent_message_delay_minutes': delay,
        'late_correction_enabled': form.get('late_correction_enabled') == 'on',
    }, None


# -- helpers ----------------------------------------------------------------

def _enrolled_students():
    return [s for s in StudentModel.query.filter_by(is_active=True).all()
            if (s.status or 'enrolled') == 'enrolled']


def _records_today(day):
    return {r.target_id: r for r in AttendanceModel.query.filter_by(
        target_type='student', date=day).all()}


def _split(day):
    """Return (students, attended_count, not_arrived_students) for ``day``."""
    students = _enrolled_students()
    records = _records_today(day)
    attended = sum(1 for s in students
                   if s.id in records and records[s.id].status in ATTENDED)
    missing = [s for s in students if s.id not in records]
    return students, attended, missing


def preview(day):
    """Who would be marked Absent right now (for the approval screen)."""
    students, attended, missing = _split(day)
    return {'total': len(students), 'attended': attended, 'students': missing}


def _license_allows_writes():
    try:
        from app.license_guard import get_manager
        return not get_manager().status().read_only
    except Exception:       # no manager (tests / plain scripts): allow
        return True


def _utc_after(minutes, now):
    """UTC send time for a local ``now`` plus ``minutes`` (queue times are UTC)."""
    if not minutes:
        return None
    local_offset = datetime.now() - datetime.utcnow()
    return (now - local_offset) + timedelta(minutes=minutes)


# -- the daily check --------------------------------------------------------

def run_auto_absent(now=None):
    """Run today's check if it is due.  Safe to call every minute.

    Returns ``None`` when nothing was due, otherwise a small dict
    ``{'ran': True, 'status': ..., 'marked': n}``.
    """
    from app.services.qr_attendance import _SCAN_LOCK, qr_feature_enabled
    from app.services.teacher_payroll import is_school_day

    now = (now or datetime.now()).replace(microsecond=0)
    today = now.date()
    config = QrConfig.get()
    if not (config.auto_absent_enabled and qr_feature_enabled()):
        return None
    if now.time() < parse_cutoff(config.absent_cutoff_time):
        return None
    if not is_school_day(today) or not _license_allows_writes():
        return None
    if QrAbsentRun.query.filter_by(run_date=today).first() is not None:
        return None

    with _SCAN_LOCK:      # never race a guard scan
        students, attended, missing = _split(today)
        if not students:
            return None
        percent = attended * 100.0 / len(students)
        mode = config.absent_mode if config.absent_mode in (MODE_AUTO, MODE_APPROVAL) else MODE_APPROVAL
        reason = None
        if mode == MODE_AUTO and percent < config.absent_min_scan_percent:
            mode = MODE_APPROVAL
            reason = (f'Only {attended} of {len(students)} students ({percent:.0f}%) arrived '
                      f'by the cutoff - below the {config.absent_min_scan_percent}% safety limit. '
                      'Please check the list before marking anyone absent.')
        run = QrAbsentRun(run_date=today, mode_used=mode, reason=reason,
                          total_students=len(students), attended_count=attended,
                          candidate_count=len(missing),
                          status='applied' if mode == MODE_AUTO else 'pending')
        db.session.add(run)
        try:
            db.session.flush()
        except Exception:    # a second process got there first
            db.session.rollback()
            return None
        marked = 0
        if mode == MODE_AUTO:
            marked = _apply(run, missing, now, config, decided_by='automatic')
        db.session.commit()
    logger.info('Auto-absent %s: %s candidate(s), %s marked', run.status, len(missing), marked)
    return {'ran': True, 'status': run.status, 'marked': marked, 'mode': mode,
            'candidates': len(missing)}


def _apply(run, students, now, config, decided_by):
    """Mark ``students`` Absent and queue their (delayed) messages."""
    from app.services.whatsapp_automation import queue_automation_message

    today = run.run_date
    send_after = _utc_after(config.absent_message_delay_minutes, now)
    locked_classes = {row.class_id for row in AttendanceModel.query.filter_by(
        target_type='student', date=today, is_locked=True).all()}
    marked = 0
    for student in students:
        db.session.add(AttendanceModel(
            target_type='student', target_id=student.id, class_id=student.class_id,
            date=today, status='Absent', is_locked=student.class_id in locked_classes))
        marked += 1
    run.marked_count = marked
    run.decided_at = datetime.utcnow()
    run.decided_by = decided_by
    run.status = 'applied'
    db.session.commit()        # the attendance is safe before any message is attempted

    for student in students:
        try:
            queue_automation_message(
                student, 'attendance_absent',
                {'student_name': student.student_name, 'date': today.isoformat()},
                send_after=send_after)
        except Exception:      # a WhatsApp problem must never undo the attendance
            db.session.rollback()
            logger.exception('Could not queue the absent message for student %s', student.id)
    return marked


# -- approval ---------------------------------------------------------------

def approve_run(run_id, user_name='admin', now=None):
    """Admin approved the list: mark everyone who *still* has no record Absent.

    Students who scanned in while the list was waiting are skipped, because
    the list is rebuilt now rather than reused from the cutoff moment.
    """
    from app.services.qr_attendance import _SCAN_LOCK

    now = (now or datetime.now()).replace(microsecond=0)
    run = db.session.get(QrAbsentRun, run_id)
    if run is None or run.status != 'pending':
        return None
    with _SCAN_LOCK:
        run = db.session.get(QrAbsentRun, run_id)
        if run.status != 'pending':
            return None
        _students, _attended, missing = _split(run.run_date)
        marked = _apply(run, missing, now, QrConfig.get(), decided_by=user_name)
    return {'marked': marked, 'skipped': max(0, run.candidate_count - marked)}


def reject_run(run_id, user_name='admin'):
    """Admin turned the list down: nobody is marked Absent today."""
    run = db.session.get(QrAbsentRun, run_id)
    if run is None or run.status != 'pending':
        return False
    run.status = 'rejected'
    run.decided_at = datetime.utcnow()
    run.decided_by = user_name
    db.session.commit()
    return True


def pending_run(day):
    return QrAbsentRun.query.filter_by(run_date=day, status='pending').first()


# -- a student arrives after being marked Absent -----------------------------

def handle_arrival_after_absent(student, day, status, checkin, late_minutes):
    """Fix the guardian's messages after an Absent student scans in.

    Returns ``True`` when a correction message was queued, so the caller can
    skip the ordinary "arrived late" message (the correction already says so).
    A waiting absent message is cancelled instead; the guardian then gets the
    normal late / nothing message as usual.
    """
    from app.services.whatsapp_automation import queue_automation_message

    messages = MessageQueue.query.filter_by(
        student_id=student.id, trigger='attendance_absent', ref_date=day).all()
    if not messages:
        return False

    already_sent = False
    for message in messages:
        if message.status in _WAITING_STATES:
            message.status = 'rejected'
            message.error_msg = 'Cancelled: the student arrived after being marked absent.'
        elif message.status in _SENT_STATES:
            already_sent = True
    db.session.commit()

    if not (already_sent and QrConfig.get().late_correction_enabled):
        return False
    try:
        queue_automation_message(student, 'attendance_correction', {
            'student_name': student.student_name, 'date': day.isoformat(),
            'late_time': checkin, 'late_minutes': late_minutes})
        return True
    except Exception:
        db.session.rollback()
        logger.exception('Could not queue the correction message for student %s', student.id)
        return False

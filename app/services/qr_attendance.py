"""QR attendance: signed student QR tokens, guard scans and the daily report.

Everything is saved in the existing ``attendance`` table (target_type
``student``), so the normal attendance summaries and exports keep working.

Token format printed on the ID card:  ``SMQR1.<student_id>.<signature>``
The signature is an HMAC with a per-school secret, so a QR code cannot be
guessed or made up.  (Roll numbers are only unique inside a class, so they
cannot identify a student school-wide - the database id can.)
"""

import hashlib
import hmac
import logging
import socket
import threading
from datetime import date, datetime

from app.database import db
from app.models import AttendanceModel, ClassModel, StudentModel
from app.models.qr_config import QrConfig

logger = logging.getLogger(__name__)

TOKEN_PREFIX = 'SMQR1'
FEATURE_KEY = 'qr_attendance'

# One scan is processed at a time, so two phones scanning the same card at
# the same moment can never create two attendance rows.
_SCAN_LOCK = threading.Lock()


# -- tokens (pure functions, no database) ---------------------------------

def _signature(secret, student_id):
    message = f'student:{int(student_id)}'.encode('ascii')
    digest = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return digest[:20]


def make_token(secret, student_id):
    return f'{TOKEN_PREFIX}.{int(student_id)}.{_signature(secret, student_id)}'


def parse_token(secret, raw):
    """Return the student id inside a valid token, otherwise ``None``."""
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split('.')
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None
    number = parts[1]
    if not (number.isascii() and number.isdigit()) or len(number) > 9:
        return None
    student_id = int(number)
    expected = _signature(secret, student_id)
    if not hmac.compare_digest(parts[2].strip().lower(), expected):
        return None
    return student_id


# -- settings / feature ----------------------------------------------------

def ensure_qr_config():
    """Create the settings row at start-up (writes are blocked later if the license is read-only)."""
    try:
        QrConfig.get()
    except Exception:  # never stop the app from starting
        db.session.rollback()
        logger.exception('Could not prepare the QR attendance settings')


def get_secret():
    return QrConfig.get().secret


def qr_feature_enabled():
    """True when this school's license includes QR attendance."""
    try:
        from app.license_guard import get_manager
        return bool(get_manager().status().feature_enabled(FEATURE_KEY))
    except Exception:
        return True


def lan_access_wanted():
    """True when guard phones should be able to reach this computer."""
    try:
        return bool(QrConfig.get().lan_access) and qr_feature_enabled()
    except Exception:
        return False


def student_qr_payload(student):
    """The text printed as the QR code on a student's ID card."""
    if qr_feature_enabled():
        return make_token(get_secret(), student.id)
    return f'STUDENT|{student.roll_number}|{student.student_name}'


def local_ip_addresses():
    """This computer's likely Wi-Fi / LAN addresses (best first)."""
    found = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('10.255.255.255', 1))   # no packet is sent
            found.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        found.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    result = []
    for ip in found:
        if ip and not ip.startswith(('127.', '169.254.', '0.')) and ip not in result:
            result.append(ip)
    return result


# -- scanning --------------------------------------------------------------

MESSAGES = {
    'invalid_qr': ('Invalid QR code. This is not a School Manager ID card.',
                   'غلط QR کوڈ۔ یہ اسکول کا شناختی کارڈ نہیں ہے۔'),
    'old_card': ('Old ID card. Please print a new ID card for this student.',
                 'پرانا کارڈ ہے۔ طالب علم کا نیا شناختی کارڈ پرنٹ کریں۔'),
    'unknown_student': ('Student not found, or no longer enrolled.',
                        'طالب علم نہیں ملا یا اب داخل نہیں ہے۔'),
    'school_closed': ('School is closed today, so attendance was not marked.',
                      'آج اسکول بند ہے، حاضری نہیں لگی۔'),
    'on_leave': ('This student is on leave today. Attendance was not changed.',
                 'طالب علم آج چھٹی پر ہے۔ حاضری نہیں بدلی۔'),
    'already_marked': ('Attendance is already marked.',
                       'حاضری پہلے سے لگ چکی ہے۔'),
    'marked_present': ('Marked PRESENT.', 'حاضر لگ گئی۔'),
    'marked_late': ('Marked LATE.', 'لیٹ لگ گیا۔'),
}


def _hhmm(value):
    return (value or '')[:5]


def _result(code, message_key=None, student=None, **extra):
    english, urdu = MESSAGES[message_key or code]
    result = {
        'ok': code in ('marked', 'already_marked'),
        'code': code,
        'message': english,
        'message_ur': urdu,
        'student': student,
        'status': None,
        'time': '',
        'late_minutes': None,
        'previous_status': None,
    }
    result.update(extra)
    return result


def student_info(student):
    class_name = student.class_info.name if student.class_info else ''
    section = student.section_info.name if student.section_info else ''
    photo_url = ''
    if student.photo_filename:
        photo_url = f'/api/qr/photo/{student.id}?v={student.photo_filename}'
    return {
        'id': student.id,
        'name': student.student_name,
        'father_name': student.father_name,
        'roll_number': student.roll_number,
        'class_name': class_name,
        'section': section,
        'photo_url': photo_url,
    }


def process_scan(raw_token, now=None):
    """Handle one scanned QR code and return the result dictionary."""
    now = (now or datetime.now()).replace(microsecond=0)
    raw = raw_token.strip() if isinstance(raw_token, str) else ''
    if raw.upper().startswith('STUDENT|'):
        return _result('old_card')
    student_id = parse_token(get_secret(), raw)
    if student_id is None:
        return _result('invalid_qr')
    with _SCAN_LOCK:
        return _mark_student(student_id, now)


def _mark_student(student_id, now):
    from app.services.attendance_service import evaluate_checkin_attendance
    from app.services.teacher_payroll import is_school_day
    from app.services.whatsapp_automation import queue_automation_message

    student = db.session.get(StudentModel, student_id)
    if student is None or not student.is_active or (student.status or 'enrolled') != 'enrolled':
        return _result('unknown_student')

    info = student_info(student)
    today = now.date()
    if not is_school_day(today):
        return _result('school_closed', student=info)

    record = AttendanceModel.query.filter_by(
        target_type='student', target_id=student.id, date=today).first()
    previous_status = None
    if record is not None:
        if record.status in ('Present', 'Late'):
            return _result('already_marked', student=info, status=record.status,
                           time=_hhmm(record.late_time),
                           late_minutes=record.late_minutes)
        if record.status != 'Absent':
            return _result('on_leave', student=info, status=record.status)
        previous_status = record.status      # Absent -> the student did come

    status, checkin, late_minutes = evaluate_checkin_attendance(
        'Present', now.time().isoformat(timespec='seconds'))

    if record is None:
        class_is_locked = AttendanceModel.query.filter_by(
            target_type='student', class_id=student.class_id, date=today,
            is_locked=True).first() is not None
        record = AttendanceModel(
            target_type='student', target_id=student.id, class_id=student.class_id,
            date=today, status=status, late_time=checkin, late_minutes=late_minutes,
            qr_time=checkin, is_locked=class_is_locked)
        db.session.add(record)
    else:
        record.status = status
        record.class_id = student.class_id
        record.late_time = checkin
        record.late_minutes = late_minutes
        record.qr_time = checkin
    db.session.commit()

    corrected = False
    if previous_status == 'Absent':
        try:
            from app.services.qr_absent import handle_arrival_after_absent
            corrected = handle_arrival_after_absent(student, today, status, checkin, late_minutes)
        except Exception:    # never undo the attendance because of a message problem
            db.session.rollback()
            logger.exception('Could not fix the absent message for student %s', student.id)

    if status == 'Late' and not corrected:
        try:
            queue_automation_message(student, 'attendance_late', {
                'student_name': student.student_name, 'date': today.isoformat(),
                'late_time': checkin, 'late_minutes': late_minutes})
        except Exception:    # a WhatsApp problem must never undo the attendance
            db.session.rollback()
            logger.exception('Could not queue the late message for student %s', student.id)

    return _result('marked', message_key='marked_late' if status == 'Late' else 'marked_present',
                   student=info, status=status, time=_hhmm(checkin),
                   late_minutes=late_minutes, previous_status=previous_status)


# -- daily report ----------------------------------------------------------

def build_daily_report(day, class_id=None):
    """Present / late / absent lists for one day (admin report and app header)."""
    from app.services.teacher_payroll import is_school_day

    query = StudentModel.query.filter_by(is_active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)
    students = query.order_by(StudentModel.class_id, StudentModel.roll_number).all()
    class_names = {c.id: c.name for c in ClassModel.query.all()}

    records = {}
    for record in AttendanceModel.query.filter_by(target_type='student', date=day).all():
        records.setdefault(record.target_id, record)

    present, late, absent, leave = [], [], [], []
    for student in students:
        record = records.get(student.id)
        row = {
            'student': student,
            'class_name': class_names.get(student.class_id, ''),
            'time': _hhmm(record.late_time) if record else '',
            'qr_time': _hhmm(record.qr_time) if record else '',
            'late_minutes': record.late_minutes if record else None,
            'status': record.status if record else None,
        }
        if record is None:
            row['label'] = 'Not marked yet'
            absent.append(row)
        elif record.status == 'Present':
            present.append(row)
        elif record.status == 'Late':
            late.append(row)
        elif record.status == 'Leave':
            leave.append(row)
        else:
            row['label'] = 'Absent'
            absent.append(row)

    from app.services.attendance_service import late_counts_as_present
    counts_late = late_counts_as_present()
    total = len(students)
    attended = len(present) + (len(late) if counts_late else 0)
    return {
        'date': day,
        'is_school_day': is_school_day(day),
        'total': total,
        'present': present,
        'late': late,
        'absent': absent,
        'leave': leave,
        'counts': {
            'total': total,
            'present': len(present),
            'late': len(late),
            'absent': len(absent),
            'leave': len(leave),
            'attended': attended,
        },
        'percentage': round(attended * 100.0 / total, 1) if total else 0.0,
        'late_counts_as_present': counts_late,
    }


# -- connecting a guard phone by QR code -----------------------------------------

def pairing_addresses(port):
    """Addresses of this computer the phone should try (best first, at most 3)."""
    return [f'http://{ip}:{port}' for ip in local_ip_addresses()][:3]


def pairing_info(guard, port):
    """What the page needs to draw the connection QR for one guard account.

    ``None`` when this computer has no network address to put in the code.
    """
    from app.services import qr_pairing

    addresses = pairing_addresses(port)
    if not addresses:
        return None
    token = qr_pairing.make_pair_token(get_secret(), guard.id)
    return {
        'payload': qr_pairing.build_pair_payload(addresses, token),
        'addresses': addresses,
        'username': guard.username,
        'expires_in': qr_pairing.PAIR_LIFETIME_SECONDS,
    }


# -- the QR tab of the merged attendance page --------------------------------

def qr_tab_context(day, class_id, port):
    """Everything the QR tab needs (daily report, guard connection, auto-absent)."""
    from app.models import ROLE_GUARD, AdminUser
    from app.models.qr_config import QrAbsentRun
    from app.services import qr_absent

    report = build_daily_report(day, class_id)
    config = QrConfig.get()
    run = QrAbsentRun.query.filter_by(run_date=day).first()
    absent_preview = qr_absent.preview(day) if (run is not None and run.status == 'pending') else None
    addresses = [f'http://{ip}:{port}' for ip in local_ip_addresses()]

    # The connection QR lets a phone sign in as a guard, so only an admin gets it.
    from flask_login import current_user
    is_admin = getattr(current_user, 'role', None) == 'admin'
    guards = (AdminUser.query.filter_by(role=ROLE_GUARD, is_active=True)
              .order_by(AdminUser.username).all()) if is_admin else []
    pair = pairing_info(guards[0], port) if (guards and config.lan_access) else None
    return {
        'guards': guards,
        'pair': pair,
        'report': report,
        'qr_day': day.strftime('%Y-%m-%d'),
        'qr_class_id': class_id,
        'addresses': addresses,
        'lan_access': config.lan_access,
        'qr_cfg': config,
        'absent_run': run,
        'absent_preview': absent_preview,
        'guard_count': AdminUser.query.filter_by(role=ROLE_GUARD, is_active=True).count(),
    }

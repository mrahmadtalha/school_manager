"""Stages: teacher remarks, teaching load, timetable, QR attendance and the WhatsApp queue."""

import json
from datetime import datetime, timedelta

from app.database import db
from app.models import (AttendanceModel, AutomationSettings, DeliveryLog, MessageQueue, QrAbsentRun,
                        QrConfig, StudentMarkModel, StudentModel, StudentRemark, SubjectModel,
                        TeacherModel, TeachingAssignment, TermExam, TestModel, TimetableCell,
                        TimetableRow)
from app.models.settings import get_timetable_structure
from app.services.automation_events import EVENT_TEMPLATES

from .data import REMARK_TEXT
from .helpers import _today


def _stage_remarks(rng, cfg, progress):
    """A teacher's remark for most students on every published term exam."""
    exams = TermExam.query.order_by(TermExam.id).all()
    count = 0
    for e_index, exam in enumerate(exams):
        averages = dict(
            db.session.query(StudentMarkModel.student_id, db.func.avg(StudentMarkModel.percentage))
            .join(TestModel, StudentMarkModel.test_id == TestModel.id)
            .filter(TestModel.term_exam_id == exam.id, StudentMarkModel.is_absent.is_(False))
            .group_by(StudentMarkModel.student_id).all())
        for student_id, average in averages.items():
            if rng.random() > 0.7:
                continue
            bucket = 'excellent' if (average or 0) >= 75 else ('good' if (average or 0) >= 55 else 'weak')
            db.session.add(StudentRemark(student_id=student_id, class_id=exam.class_id,
                                         test_type=exam.exam_type, session=exam.session_label,
                                         remarks=rng.choice(REMARK_TEXT[bucket])))
            count += 1
        db.session.commit()
        progress.report('remarks', (e_index + 1) / max(1, len(exams)))
    progress.report('remarks', 1.0)
    return count


def _stage_teaching_and_timetable(rng, classes):
    """Teaching load per subject and a one-page timetable (no teacher in two rooms at once)."""
    assignments = 0
    for subject in SubjectModel.query.filter(SubjectModel.teacher_id.isnot(None),
                                             SubjectModel.library_id.isnot(None)).all():
        exists = TeachingAssignment.query.filter_by(
            teacher_id=subject.teacher_id, library_id=subject.library_id,
            class_id=subject.class_id, section_id=None).first()
        if exists is None:
            db.session.add(TeachingAssignment(
                teacher_id=subject.teacher_id, library_id=subject.library_id,
                class_id=subject.class_id, section_id=None,
                periods_per_week=rng.choice([4, 5, 5, 6]), is_active=True))
            assignments += 1
    db.session.flush()

    rows = 0
    if TimetableRow.query.count() == 0:
        periods = int(get_timetable_structure().get('periods_per_day', 8))
        teachers_by_class = {}
        for subject in SubjectModel.query.filter(SubjectModel.teacher_id.isnot(None)).all():
            teachers_by_class.setdefault(subject.class_id, []).append(subject.teacher_id)
        active = [t.id for t in TeacherModel.query.filter_by(is_active=True).order_by(TeacherModel.id)]
        row_objects = []
        for order, class_obj in enumerate(classes):
            row = TimetableRow(sort_order=order, class_ids=json.dumps([class_obj.id]))
            db.session.add(row)
            row_objects.append((row, class_obj.id))
        db.session.flush()
        for period in range(1, periods + 1):
            busy = set()
            for row, class_id in row_objects:
                preferred = [t for t in teachers_by_class.get(class_id, []) if t not in busy]
                pool = preferred or [t for t in active if t not in busy]
                teacher_id = rng.choice(pool) if pool else None
                if teacher_id:
                    busy.add(teacher_id)
                db.session.add(TimetableCell(row_id=row.id, period_no=period, teacher_id=teacher_id))
        rows = len(row_objects)
    db.session.flush()
    return assignments, rows


def _qr_history(rng, today):
    """Auto-absent settings and the last few school days' runs (applied, rejected, waiting)."""
    from app.services.teacher_payroll import is_school_day

    config = QrConfig.get()
    config.auto_absent_enabled = True
    config.absent_mode = 'approval'
    config.absent_cutoff_time = '10:00'
    config.absent_min_scan_percent = 20
    config.absent_message_delay_minutes = 30
    config.late_correction_enabled = True
    db.session.flush()

    runs = 0
    day, seen = today, 0
    while seen < 6 and (today - day).days < 30:
        if is_school_day(day) and QrAbsentRun.query.filter_by(run_date=day).first() is None:
            total = StudentModel.query.filter(StudentModel.is_active.is_(True)).count()
            absent = AttendanceModel.query.filter_by(date=day, target_type='student',
                                                     status='Absent').count()
            attended = max(0, total - absent)
            status = 'pending' if seen == 0 else rng.choice(['applied', 'applied', 'applied', 'rejected'])
            decided = None if status == 'pending' else datetime.combine(day, datetime.min.time()) \
                + timedelta(hours=10, minutes=rng.randint(5, 40))
            db.session.add(QrAbsentRun(
                run_date=day, status=status, mode_used='approval',
                reason=None if status != 'rejected' else 'Guard phone was offline for a while',
                total_students=total, attended_count=attended, candidate_count=absent,
                marked_count=absent if status == 'applied' else 0,
                created_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=10),
                decided_at=decided, decided_by=None if status == 'pending' else 'admin'))
            runs += 1
            seen += 1
        day -= timedelta(days=1)
    return runs


def _whatsapp_history(rng, today):
    """WhatsApp settings and a queue showing every message state (sent, waiting, failed...)."""
    settings = AutomationSettings.get()
    settings.enabled = True
    settings.mode = 'approval'
    settings.notify_absent = True
    settings.notify_late = True
    settings.notify_results = True
    settings.notify_fee_reminders = True
    settings.notify_fee_receipts = True
    settings.wa_status = 'connected'
    settings.last_successful_send_at = datetime.now() - timedelta(hours=3)
    db.session.flush()

    queued = 0
    absences = (AttendanceModel.query.filter_by(target_type='student', status='Absent')
                .filter(AttendanceModel.date >= today - timedelta(days=21))
                .order_by(AttendanceModel.date.desc()).limit(40).all())
    pool = [('attendance_absent', a.target_id, a.date) for a in absences]
    pool += [('attendance_late', a.target_id, a.date) for a in
             (AttendanceModel.query.filter_by(target_type='student', status='Late')
              .filter(AttendanceModel.date >= today - timedelta(days=14)).limit(10).all())]
    for student in StudentModel.query.filter_by(is_active=True).limit(12).all():
        pool.append(('fee_reminder', student.id, today))

    statuses = ['sent'] * 6 + ['pending'] * 2 + ['approved', 'failed', 'rejected']
    for trigger, student_id, day in pool:
        student = db.session.get(StudentModel, student_id)
        if student is None or not student.guardian_phone:
            continue
        values = {'student_name': student.student_name, 'date_value': day.strftime('%d %b %Y'),
                  'late_at': '', 'month_year': day.strftime('%B %Y'), 'amount_due': 'Rs. 2,500'}
        status = rng.choice(statuses)
        sent_at = (datetime.combine(day, datetime.min.time()) + timedelta(hours=11, minutes=rng.randint(0, 50))
                   if status in ('sent', 'failed') else None)
        message = MessageQueue(
            phone=''.join(ch for ch in student.guardian_phone if ch.isdigit() or ch == '+'),
            message=EVENT_TEMPLATES[trigger].format(**values), status=status, trigger=trigger,
            student_id=student.id, ref_date=day, retry_count=2 if status == 'failed' else 0,
            created_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=10, minutes=30),
            sent_at=sent_at if status == 'sent' else None,
            error_msg='WhatsApp session was disconnected' if status == 'failed' else None)
        db.session.add(message)
        db.session.flush()
        if status in ('sent', 'failed'):
            db.session.add(DeliveryLog(message_id=message.id, status=status,
                                       error_msg=message.error_msg,
                                       details='Delivered to WhatsApp' if status == 'sent' else None,
                                       created_at=sent_at))
        queued += 1
    return queued


def _stage_school_life(rng, cfg, progress, classes):
    today = _today()
    assignments, timetable_rows = _stage_teaching_and_timetable(rng, classes)
    progress.report('school_life', 0.4)
    qr_runs = _qr_history(rng, today)
    progress.report('school_life', 0.7)
    messages = 0 if MessageQueue.query.first() is not None else _whatsapp_history(rng, today)
    db.session.commit()
    progress.report('school_life', 1.0)
    return {'teaching_assignments': assignments, 'timetable_rows': timetable_rows,
            'qr_absent_runs': qr_runs, 'whatsapp_messages': messages}

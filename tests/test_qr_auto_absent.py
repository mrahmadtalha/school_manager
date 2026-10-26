"""QR attendance phase 3: auto-absent at the cutoff, approval, safety rule, messages."""

from datetime import date, datetime, timedelta

import pytest

from app.database import db
from app.models import (AttendanceModel, AutomationSettings, MessageQueue,
                        SchoolSettings, StudentModel)
from app.models.qr_config import QrAbsentRun, QrConfig
from app.services import qr_absent
from app.services import qr_attendance as qr
from tests.conftest import ADMIN_PASSWORD, login

MONDAY = date(2026, 10, 19)
SUNDAY = date(2026, 10, 18)


def _at(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute)


@pytest.fixture(autouse=True)
def _school(app):
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    for name in ('saturday_off', 'sunday_off'):
        if hasattr(settings, name):
            setattr(settings, name, True)
    db.session.commit()


def _configure(**values):
    config = QrConfig.get()
    config.auto_absent_enabled = True
    config.absent_cutoff_time = '10:00'
    config.absent_mode = 'auto'
    config.absent_min_scan_percent = 20
    config.absent_message_delay_minutes = 30
    config.late_correction_enabled = True
    for name, value in values.items():
        setattr(config, name, value)
    db.session.commit()
    return config


def _whatsapp(mode='auto'):
    settings = AutomationSettings.get()
    settings.enabled = True
    settings.mode = mode
    db.session.commit()


def _add_students(seed, count):
    ids = []
    for index in range(count):
        student = StudentModel(
            roll_number=2000 + index, student_name=f'Extra {index}', father_name='Father',
            guardian_phone=f'0300555{index:04d}', address='Street',
            class_id=seed['class_id'], section_id=seed['section_id'], monthly_fee=1000.0)
        db.session.add(student)
        db.session.flush()
        ids.append(student.id)
    db.session.commit()
    return ids


def _scan(student_id, now):
    return qr.process_scan(qr.make_token(qr.get_secret(), student_id), now=now)


def _record(student_id, day=MONDAY):
    return AttendanceModel.query.filter_by(
        target_type='student', target_id=student_id, date=day).first()


# -- when the check runs ----------------------------------------------------

def test_nothing_happens_when_switched_off(app, seed):
    _configure(auto_absent_enabled=False)
    assert qr_absent.run_auto_absent(now=_at(MONDAY, 11)) is None
    assert _record(seed['student_id']) is None


def test_nothing_happens_before_the_cutoff(app, seed):
    _configure()
    assert qr_absent.run_auto_absent(now=_at(MONDAY, 9, 59)) is None
    assert QrAbsentRun.query.count() == 0


def test_closed_days_are_skipped(app, seed):
    _configure()
    assert qr_absent.run_auto_absent(now=_at(SUNDAY, 11)) is None
    assert AttendanceModel.query.count() == 0


def test_auto_mode_marks_only_students_without_a_record(app, seed):
    _configure(absent_min_scan_percent=0)
    _scan(seed['student_id'], _at(MONDAY, 8, 10))                   # Present
    outcome = qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    assert outcome['status'] == 'applied' and outcome['marked'] == 1
    assert _record(seed['student_id']).status == 'Present'          # untouched
    other = _record(seed['other_student_id'])
    assert other.status == 'Absent' and other.class_id == seed['class_id']


def test_leave_and_existing_absent_are_never_changed(app, seed):
    _configure(absent_min_scan_percent=0)
    db.session.add(AttendanceModel(target_type='student', target_id=seed['student_id'],
                                   class_id=seed['class_id'], date=MONDAY, status='Leave'))
    db.session.commit()
    outcome = qr_absent.run_auto_absent(now=_at(MONDAY, 10, 5))
    assert outcome['marked'] == 1
    assert _record(seed['student_id']).status == 'Leave'
    assert AttendanceModel.query.filter_by(target_id=seed['student_id']).count() == 1


def test_it_runs_only_once_per_day(app, seed):
    _configure(absent_min_scan_percent=0)
    assert qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))['ran']
    assert qr_absent.run_auto_absent(now=_at(MONDAY, 10, 1)) is None
    assert QrAbsentRun.query.count() == 1


def test_running_late_in_the_day_still_does_the_check_once(app, seed):
    """Opening School Manager at noon (after the cutoff) still runs today's check."""
    _configure(absent_min_scan_percent=0)
    assert qr_absent.run_auto_absent(now=_at(MONDAY, 12, 30))['ran']


# -- safety rule ------------------------------------------------------------

def test_too_few_scans_forces_approval_in_auto_mode(app, seed):
    _configure(absent_min_scan_percent=20)
    ids = _add_students(seed, 8)                       # 10 students, nobody scanned
    outcome = qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    assert outcome['status'] == 'pending' and outcome['mode'] == 'approval'
    assert outcome['marked'] == 0
    assert AttendanceModel.query.count() == 0           # nobody was marked
    run = QrAbsentRun.query.one()
    assert 'safety limit' in run.reason and run.candidate_count == 10


def test_enough_scans_lets_automatic_mode_continue(app, seed):
    _configure(absent_min_scan_percent=20)
    ids = _add_students(seed, 8)
    _scan(seed['student_id'], _at(MONDAY, 8, 0))
    _scan(ids[0], _at(MONDAY, 8, 5))                     # 2 of 10 = 20%
    outcome = qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    assert outcome['status'] == 'applied' and outcome['marked'] == 8


# -- approval mode ----------------------------------------------------------

def test_approval_mode_waits_then_marks_on_approve(app, seed):
    _configure(absent_mode='approval')
    outcome = qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    assert outcome['status'] == 'pending'
    assert AttendanceModel.query.count() == 0
    run = QrAbsentRun.query.one()

    # one student scans in while the list is waiting - they must be skipped
    _scan(seed['student_id'], _at(MONDAY, 10, 20))
    result = qr_absent.approve_run(run.id, user_name='admin', now=_at(MONDAY, 10, 30))
    assert result['marked'] == 1 and result['skipped'] == 1
    assert _record(seed['student_id']).status == 'Late'
    assert _record(seed['other_student_id']).status == 'Absent'
    assert db.session.get(QrAbsentRun, run.id).status == 'applied'
    assert qr_absent.approve_run(run.id) is None          # cannot be approved twice


def test_reject_marks_nobody(app, seed):
    _configure(absent_mode='approval')
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    run = QrAbsentRun.query.one()
    assert qr_absent.reject_run(run.id, user_name='admin') is True
    assert AttendanceModel.query.count() == 0
    assert db.session.get(QrAbsentRun, run.id).status == 'rejected'
    assert qr_absent.approve_run(run.id) is None
    assert qr_absent.run_auto_absent(now=_at(MONDAY, 11, 0)) is None   # no second check


# -- messages ---------------------------------------------------------------

def test_absent_messages_are_delayed(app, seed):
    _configure(absent_min_scan_percent=0, absent_message_delay_minutes=30)
    _whatsapp('auto')
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    messages = MessageQueue.query.filter_by(trigger='attendance_absent').all()
    assert len(messages) == 2
    for message in messages:
        assert message.send_after is not None
        assert message.status == 'approved'


def test_pending_endpoint_holds_messages_until_their_time(app, seed):
    _whatsapp('auto')
    due = MessageQueue(phone='923001234567', message='due', status='approved',
                       trigger='attendance_absent', send_after=datetime.utcnow() - timedelta(minutes=1))
    held = MessageQueue(phone='923007654321', message='held', status='approved',
                        trigger='attendance_absent', send_after=datetime.utcnow() + timedelta(hours=1))
    plain = MessageQueue(phone='923001112222', message='plain', status='approved', trigger='result')
    db.session.add_all([due, held, plain])
    db.session.commit()

    app.config['WHATSAPP_BRIDGE_TOKEN'] = 'absent-test-token'
    response = app.test_client().get('/api/whatsapp/pending',
                                     headers={'X-Bridge-Token': 'absent-test-token'})
    assert response.status_code == 200
    sent = {item['message'] for item in response.get_json()['items']}
    assert sent == {'due', 'plain'}
    assert db.session.get(MessageQueue, held.id).status == 'approved'


def test_arrival_before_the_absent_message_is_sent_cancels_it(app, seed):
    _configure(absent_min_scan_percent=0)
    _whatsapp('auto')
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    result = _scan(seed['student_id'], _at(MONDAY, 10, 20))
    assert result['status'] == 'Late' and result['previous_status'] == 'Absent'
    absent = MessageQueue.query.filter_by(
        student_id=seed['student_id'], trigger='attendance_absent').one()
    assert absent.status == 'rejected'
    assert MessageQueue.query.filter_by(trigger='attendance_correction').count() == 0
    # the guardian still gets the normal "arrived late" message
    assert MessageQueue.query.filter_by(
        student_id=seed['student_id'], trigger='attendance_late').count() == 1


def test_arrival_after_the_absent_message_went_out_sends_a_correction(app, seed):
    _configure(absent_min_scan_percent=0)
    _whatsapp('auto')
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    absent = MessageQueue.query.filter_by(
        student_id=seed['student_id'], trigger='attendance_absent').one()
    absent.status = 'sent'
    db.session.commit()

    _scan(seed['student_id'], _at(MONDAY, 10, 50))
    correction = MessageQueue.query.filter_by(
        student_id=seed['student_id'], trigger='attendance_correction').one()
    assert 'ABSENT' in correction.message and '10:50 AM' in correction.message
    assert db.session.get(MessageQueue, absent.id).status == 'sent'      # history untouched
    # the correction replaces the late message, so the guardian gets one message, not two
    assert MessageQueue.query.filter_by(
        student_id=seed['student_id'], trigger='attendance_late').count() == 0


def test_correction_can_be_switched_off(app, seed):
    _configure(absent_min_scan_percent=0, late_correction_enabled=False)
    _whatsapp('auto')
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    MessageQueue.query.filter_by(student_id=seed['student_id'],
                                 trigger='attendance_absent').one().status = 'sent'
    db.session.commit()
    _scan(seed['student_id'], _at(MONDAY, 10, 50))
    assert MessageQueue.query.filter_by(trigger='attendance_correction').count() == 0
    assert _record(seed['student_id']).status == 'Late'


def test_whatsapp_off_still_marks_attendance(app, seed):
    _configure(absent_min_scan_percent=0)
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    assert MessageQueue.query.count() == 0
    assert _record(seed['student_id']).status == 'Absent'


# -- settings form + pages --------------------------------------------------

def test_settings_validation():
    values, error = qr_absent.clean_settings({
        'auto_absent_enabled': 'on', 'absent_cutoff_time': '09:45', 'absent_mode': 'auto',
        'absent_min_scan_percent': '25', 'absent_message_delay_minutes': '15'})
    assert error is None
    assert values['auto_absent_enabled'] and values['absent_cutoff_time'] == '09:45'
    assert values['late_correction_enabled'] is False        # unchecked box
    assert qr_absent.clean_settings({'absent_cutoff_time': '25:99'})[1]
    assert qr_absent.clean_settings({'absent_cutoff_time': '10:00',
                                     'absent_min_scan_percent': '150'})[1]
    assert qr_absent.clean_settings({'absent_cutoff_time': '10:00',
                                     'absent_min_scan_percent': 'abc'})[1]
    values, _ = qr_absent.clean_settings({'absent_cutoff_time': '10:00', 'absent_mode': 'weird'})
    assert values['absent_mode'] == 'approval'


def test_admin_can_save_settings_and_decide_from_the_page(app, seed, client):
    login(client, 'admin', ADMIN_PASSWORD)
    saved = client.post('/attendance/qr/auto-absent/settings', data={
        'auto_absent_enabled': 'on', 'absent_cutoff_time': '09:30', 'absent_mode': 'approval',
        'absent_min_scan_percent': '30', 'absent_message_delay_minutes': '10',
        'late_correction_enabled': 'on'})
    assert saved.status_code == 302
    config = QrConfig.get()
    assert config.auto_absent_enabled and config.absent_cutoff_time == '09:30'
    assert config.absent_min_scan_percent == 30 and config.absent_message_delay_minutes == 10

    qr_absent.run_auto_absent(now=_at(MONDAY, 9, 45))
    run = QrAbsentRun.query.one()
    page = client.get('/attendance/students?tab=qr&date=2026-10-19')
    assert page.status_code == 200
    assert b'waiting for approval' in page.data and b'Approve' in page.data

    approved = client.post(f'/attendance/qr/auto-absent/{run.id}/approve')
    assert approved.status_code == 302
    assert db.session.get(QrAbsentRun, run.id).status == 'applied'
    assert _record(seed['student_id']).status == 'Absent'


def test_bad_settings_are_refused(app, seed, client):
    login(client, 'admin', ADMIN_PASSWORD)
    client.post('/attendance/qr/auto-absent/settings',
                data={'absent_cutoff_time': 'later', 'absent_mode': 'auto'})
    assert QrConfig.get().auto_absent_enabled is False


def test_teacher_cannot_change_settings_or_approve(app, seed, teacher_client):
    denied = teacher_client.post('/attendance/qr/auto-absent/settings',
                                 data={'auto_absent_enabled': 'on', 'absent_cutoff_time': '10:00'})
    assert denied.status_code in (302, 403)
    assert QrConfig.get().auto_absent_enabled is False
    _configure(absent_mode='approval')
    qr_absent.run_auto_absent(now=_at(MONDAY, 10, 0))
    run = QrAbsentRun.query.one()
    teacher_client.post(f'/attendance/qr/auto-absent/{run.id}/approve')
    assert db.session.get(QrAbsentRun, run.id).status == 'pending'

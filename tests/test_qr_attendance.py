"""QR attendance (phase 1): tokens, scanning rules, guard API, role limits, report."""

from datetime import date, datetime

import pytest

from app.database import db
from app.models import (ROLE_GUARD, AdminUser, AttendanceModel, SchoolSettings,
                        StudentModel)
from app.services import qr_attendance as qr
from app.services.id_documents import student_card_payload
from tests.conftest import login

GUARD_PASSWORD = 'guardpass123'
MONDAY = date(2026, 10, 19)
SUNDAY = date(2026, 10, 18)


def _at(day, hour, minute, second=0):
    return datetime(day.year, day.month, day.day, hour, minute, second)


def _settings():
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    for name in ('saturday_off', 'sunday_off'):
        if hasattr(settings, name):
            setattr(settings, name, True)
    db.session.commit()
    return settings


def _token(student_id):
    return qr.make_token(qr.get_secret(), student_id)


def _rows(student_id, day=MONDAY):
    return AttendanceModel.query.filter_by(
        target_type='student', target_id=student_id, date=day).all()


@pytest.fixture()
def guard_client(app, client):
    guard = AdminUser(username='guard', role=ROLE_GUARD, full_name='Gate Guard')
    guard.set_password(GUARD_PASSWORD)
    db.session.add(guard)
    db.session.commit()
    return client


# -- tokens ---------------------------------------------------------------

def test_token_round_trip_and_tampering():
    token = qr.make_token('secret-one', 42)
    assert token.startswith('SMQR1.42.')
    assert qr.parse_token('secret-one', token) == 42
    assert qr.parse_token('secret-one', f'  {token}\n') == 42
    assert qr.parse_token('another-secret', token) is None          # wrong school
    assert qr.parse_token('secret-one', token.replace('.42.', '.43.')) is None
    assert qr.parse_token('secret-one', 'SMQR1.42') is None
    assert qr.parse_token('secret-one', 'hello') is None
    assert qr.parse_token('secret-one', None) is None


def test_id_card_qr_is_the_signed_token(app, seed):
    student = db.session.get(StudentModel, seed['student_id'])
    payload = student_card_payload(student)
    assert payload['qr'] == _token(seed['student_id'])


# -- scan rules -----------------------------------------------------------

def test_on_time_scan_marks_present_in_the_normal_attendance_table(app, seed):
    _settings()
    result = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 20))
    assert result['ok'] and result['code'] == 'marked'
    assert result['status'] == 'Present'
    assert result['student']['name'] == 'Ali Khan'
    assert result['student']['class_name'] == 'Class 1'
    rows = _rows(seed['student_id'])
    assert len(rows) == 1
    assert rows[0].status == 'Present'
    assert rows[0].class_id == seed['class_id']
    assert rows[0].late_time.startswith('08:20')


def test_scan_after_start_time_marks_late_with_minutes(app, seed):
    _settings()
    result = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 50))
    assert result['status'] == 'Late'
    assert result['late_minutes'] == 20
    assert _rows(seed['student_id'])[0].status == 'Late'


def test_second_scan_never_creates_a_second_record(app, seed):
    _settings()
    first = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 10))
    again = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 45))
    assert first['code'] == 'marked'
    assert again['code'] == 'already_marked' and again['ok']
    assert again['status'] == 'Present'            # the earlier result stands
    assert again['time'] == '08:10'
    assert len(_rows(seed['student_id'])) == 1


def test_absent_student_who_arrives_later_becomes_late(app, seed):
    _settings()
    db.session.add(AttendanceModel(
        target_type='student', target_id=seed['student_id'], class_id=seed['class_id'],
        date=MONDAY, status='Absent', is_locked=True))
    db.session.commit()
    result = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 10, 30))
    assert result['code'] == 'marked'
    assert result['status'] == 'Late'
    assert result['late_minutes'] == 120
    assert result['previous_status'] == 'Absent'
    rows = _rows(seed['student_id'])
    assert len(rows) == 1 and rows[0].status == 'Late'


def test_leave_is_not_changed_by_a_scan(app, seed):
    _settings()
    db.session.add(AttendanceModel(
        target_type='student', target_id=seed['student_id'], class_id=seed['class_id'],
        date=MONDAY, status='Leave'))
    db.session.commit()
    result = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 0))
    assert result['code'] == 'on_leave' and not result['ok']
    assert _rows(seed['student_id'])[0].status == 'Leave'


def test_new_record_in_a_locked_class_is_locked_too(app, seed):
    _settings()
    db.session.add(AttendanceModel(
        target_type='student', target_id=seed['other_student_id'], class_id=seed['class_id'],
        date=MONDAY, status='Present', is_locked=True))
    db.session.commit()
    qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 0))
    assert _rows(seed['student_id'])[0].is_locked is True


def test_school_closed_day_is_refused(app, seed):
    _settings()
    result = qr.process_scan(_token(seed['student_id']), now=_at(SUNDAY, 8, 0))
    assert result['code'] == 'school_closed' and not result['ok']
    assert result['student']['name'] == 'Ali Khan'
    assert _rows(seed['student_id'], SUNDAY) == []


def test_bad_codes_give_clear_codes_and_save_nothing(app, seed):
    _settings()
    assert qr.process_scan('hello', now=_at(MONDAY, 8, 0))['code'] == 'invalid_qr'
    assert qr.process_scan('', now=_at(MONDAY, 8, 0))['code'] == 'invalid_qr'
    assert qr.process_scan(None, now=_at(MONDAY, 8, 0))['code'] == 'invalid_qr'
    assert qr.process_scan('STUDENT|1001|Ali Khan', now=_at(MONDAY, 8, 0))['code'] == 'old_card'
    assert qr.process_scan(_token(999999), now=_at(MONDAY, 8, 0))['code'] == 'unknown_student'
    assert AttendanceModel.query.count() == 0


def test_archived_student_is_unknown(app, seed):
    _settings()
    student = db.session.get(StudentModel, seed['student_id'])
    student.is_active = False
    student.status = 'struck_off'
    db.session.commit()
    result = qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 0))
    assert result['code'] == 'unknown_student'


# -- report ---------------------------------------------------------------

def test_daily_report_splits_present_late_and_absent(app, seed):
    _settings()
    qr.process_scan(_token(seed['student_id']), now=_at(MONDAY, 8, 50))
    report = qr.build_daily_report(MONDAY)
    assert report['counts']['total'] == 2
    assert report['counts']['late'] == 1
    assert report['counts']['present'] == 0
    assert report['counts']['absent'] == 1
    assert report['absent'][0]['label'] == 'Not marked yet'
    assert report['percentage'] == 50.0


# -- guard API ------------------------------------------------------------

def test_guard_can_sign_in_and_scan(app, seed, guard_client, monkeypatch):
    _settings()
    monkeypatch.setattr('app.services.teacher_payroll.is_school_day', lambda day, settings=None: True)
    bad = guard_client.post('/api/qr/login', json={'username': 'guard', 'password': 'nope'})
    assert bad.status_code == 401

    ok = guard_client.post('/api/qr/login', json={'username': 'guard', 'password': GUARD_PASSWORD})
    assert ok.status_code == 200 and ok.get_json()['user']['role'] == 'guard'

    ping = guard_client.get('/api/qr/ping')
    assert ping.status_code == 200 and ping.get_json()['today']['total'] == 2

    scan = guard_client.post('/api/qr/scan', json={'token': _token(seed['student_id'])})
    body = scan.get_json()
    assert scan.status_code == 200 and body['ok'] and body['code'] == 'marked'
    assert body['student']['name'] == 'Ali Khan'
    assert body['today']['attended'] == 1

    junk = guard_client.post('/api/qr/scan', json={'token': 'junk'})
    assert junk.status_code == 200 and junk.get_json()['code'] == 'invalid_qr'
    empty = guard_client.post('/api/qr/scan', json={})
    assert empty.status_code == 400


def test_scan_requires_sign_in(app, seed, client):
    response = client.post('/api/qr/scan', json={'token': _token(seed['student_id'])})
    assert response.status_code == 401


def test_guard_account_reaches_only_the_guard_api(app, guard_client):
    guard_client.post('/api/qr/login', json={'username': 'guard', 'password': GUARD_PASSWORD})
    for path in ('/students', '/fees', '/attendance/qr', '/attendance/students', '/users'):
        assert guard_client.get(path).status_code == 403, path
    assert guard_client.get('/api/qr/ping').status_code == 200


def test_guard_web_login_lands_on_the_guard_page(app, guard_client):
    response = login(guard_client, 'guard', GUARD_PASSWORD)
    assert response.status_code == 302 and '/guard' in response.location
    assert guard_client.get('/guard').status_code == 200


def test_teacher_cannot_use_the_scan_api(app, seed, teacher_client):
    response = teacher_client.post('/api/qr/scan', json={'token': _token(seed['student_id'])})
    assert response.status_code == 403


def test_non_guard_account_cannot_sign_in_to_the_app(app, client):
    response = client.post('/api/qr/login', json={'username': 'teacher', 'password': 'teacherpass123'})
    assert response.status_code == 403
    assert response.get_json()['error'] == 'role_not_allowed'


def test_photo_endpoint_404_without_a_photo(app, seed, guard_client):
    guard_client.post('/api/qr/login', json={'username': 'guard', 'password': GUARD_PASSWORD})
    assert guard_client.get(f"/api/qr/photo/{seed['student_id']}").status_code == 404


# -- admin page and network limits ------------------------------------------

def test_admin_and_teacher_can_open_the_report(app, seed, admin_client):
    # QR attendance is a tab of the attendance page now
    page = admin_client.get('/attendance/students?tab=qr')
    assert page.status_code == 200
    assert 'QR Scans' in page.get_data(as_text=True)
    assert admin_client.get('/attendance/students?tab=qr&date=2026-10-19&class_id=%d' % seed['class_id']).status_code == 200
    assert admin_client.get('/attendance/students?tab=qr&date=not-a-date').status_code == 200
    # the old address still works and lands on the tab
    old = admin_client.get('/attendance/qr?date=2026-10-19')
    assert old.status_code == 302 and 'tab=qr' in old.location and 'date=2026-10-19' in old.location


def test_teacher_can_view_but_not_change_guard_network_setting(app, teacher_client):
    assert teacher_client.get('/attendance/students?tab=qr').status_code == 200
    assert teacher_client.post('/attendance/qr/settings', data={'lan_access': 'on'}).status_code == 403


def test_admin_can_switch_guard_phone_access(app, admin_client):
    from app.models.qr_config import QrConfig
    admin_client.post('/attendance/qr/settings', data={'lan_access': 'on'})
    db.session.expire_all()
    assert QrConfig.get().lan_access is True
    admin_client.post('/attendance/qr/settings', data={})
    db.session.expire_all()
    assert QrConfig.get().lan_access is False


def test_other_devices_can_reach_only_the_guard_api(app, client):
    remote = {'environ_overrides': {'REMOTE_ADDR': '192.168.1.50'}}
    assert client.get('/login', **remote).status_code == 403
    assert client.get('/students', **remote).status_code == 403
    assert client.get('/api/whatsapp/pending', **remote).status_code == 403
    assert client.post('/api/qr/login', json={}, **remote).status_code == 400   # reached the route


def test_guard_role_is_in_the_license_catalog():
    from app.services import features
    assert 'qr_attendance' in features.ALL_FEATURES
    assert 'guard' in features.ALL_ROLES
    assert features.normalize_roles(['guard'])[-1] == 'guard'

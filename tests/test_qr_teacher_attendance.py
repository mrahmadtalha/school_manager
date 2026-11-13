"""QR attendance for teachers: signed staff-card tokens, scan rules, guard API,
QR tab, teacher sheet and ID card.

Teachers are saved in the same ``attendance`` table as students
(``target_type='teacher'``), so the teacher sheet, summaries and exports keep
working without any change.
"""

from datetime import date, datetime

import pytest

from app.database import db
from app.models import (ROLE_GUARD, AdminUser, AttendanceModel, MessageQueue,
                        SchoolSettings, TeacherModel)
from app.services import qr_attendance as qr
from app.services.attendance_service import (
    build_teacher_attendance_summary, save_teacher_attendance)
from app.services.id_documents import teacher_card_payload

MONDAY = date(2026, 10, 19)
SUNDAY = date(2026, 10, 18)
QR_URL = '/attendance/students?tab=qr&date=2026-10-19'


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


def _teacher(code='T001', name='Sara Ahmed', **extra):
    teacher = TeacherModel(teacher_id_str=code, teacher_name=name,
                           qualification='MA', **extra)
    db.session.add(teacher)
    db.session.commit()
    return teacher


def _token(teacher_id):
    return qr.make_teacher_token(qr.get_secret(), teacher_id)


def _rows(teacher_id, day=MONDAY):
    return AttendanceModel.query.filter_by(
        target_type='teacher', target_id=teacher_id, date=day).all()


@pytest.fixture()
def guard_client(app, client):
    guard = AdminUser(username='guard', role=ROLE_GUARD, full_name='Gate Guard')
    guard.set_password('guardpass123')
    db.session.add(guard)
    db.session.commit()
    return client


# -- tokens ---------------------------------------------------------------

def test_teacher_token_round_trip_and_tampering():
    token = qr.make_teacher_token('secret-one', 7)
    assert token.startswith('SMQT1.7.')
    assert qr.parse_teacher_token('secret-one', token) == 7
    assert qr.parse_teacher_token('secret-one', f'  {token}\n') == 7
    assert qr.parse_teacher_token('another-secret', token) is None        # wrong school
    assert qr.parse_teacher_token('secret-one', token.replace('.7.', '.8.')) is None
    assert qr.parse_teacher_token('secret-one', 'SMQT1.7') is None
    assert qr.parse_teacher_token('secret-one', 'hello') is None
    assert qr.parse_teacher_token('secret-one', None) is None
    assert qr.parse_teacher_token('secret-one', 'SMQT1.%s.abc' % ('9' * 12)) is None


def test_student_and_teacher_tokens_are_never_mixed_up():
    student_token = qr.make_token('secret-one', 5)
    teacher_token = qr.make_teacher_token('secret-one', 5)
    assert student_token != teacher_token
    assert qr.parse_teacher_token('secret-one', student_token) is None
    assert qr.parse_token('secret-one', teacher_token) is None
    # even a teacher code dressed up with the student prefix has the wrong signature
    forged = teacher_token.replace('SMQT1', 'SMQR1', 1)
    assert qr.parse_token('secret-one', forged) is None


def test_staff_card_qr_is_the_signed_token(app):
    teacher = _teacher()
    payload = teacher_card_payload(teacher)
    assert payload['qr'] == _token(teacher.id)
    assert payload['qr'].startswith('SMQT1.')


def test_staff_card_keeps_the_old_text_when_qr_is_not_in_the_license(app, monkeypatch):
    teacher = _teacher()
    monkeypatch.setattr(qr, 'qr_feature_enabled', lambda: False)
    assert teacher_card_payload(teacher)['qr'] == 'TEACHER|T001|Sara Ahmed'


def test_teacher_id_card_pdf_still_downloads(app, admin_client):
    teacher = _teacher()
    response = admin_client.get(f'/documents/id-cards/teachers.pdf?teacher_id={teacher.id}')
    assert response.status_code == 200
    assert response.data[:4] == b'%PDF'


# -- scan rules -----------------------------------------------------------

def test_on_time_scan_marks_teacher_present_in_the_normal_attendance_table(app):
    _settings()
    teacher = _teacher(designation='Senior Teacher')
    result = qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 20))
    assert result['ok'] and result['code'] == 'marked'
    assert result['status'] == 'Present'
    assert result['person_type'] == 'teacher'
    assert result['person']['name'] == 'Sara Ahmed'
    assert result['person']['roll_number'] == 'T001'
    assert result['person']['class_name'] == 'Senior Teacher'
    assert result['student'] == result['person']        # an older guard app still sees the name
    rows = _rows(teacher.id)
    assert len(rows) == 1
    assert rows[0].status == 'Present'
    assert rows[0].class_id is None
    assert rows[0].late_time.startswith('08:20') and rows[0].qr_time.startswith('08:20')


def test_teacher_scan_after_start_time_is_late_with_minutes(app):
    _settings()
    teacher = _teacher()
    result = qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 50))
    assert result['status'] == 'Late' and result['late_minutes'] == 20
    assert 'LATE' in result['message']
    assert _rows(teacher.id)[0].status == 'Late'


def test_second_teacher_scan_never_creates_a_second_record(app):
    _settings()
    teacher = _teacher()
    first = qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 10))
    again = qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 45))
    assert first['code'] == 'marked'
    assert again['code'] == 'already_marked' and again['ok']
    assert again['status'] == 'Present' and again['time'] == '08:10'
    assert len(_rows(teacher.id)) == 1


def test_absent_teacher_who_arrives_later_is_corrected(app):
    _settings()
    teacher = _teacher()
    db.session.add(AttendanceModel(
        target_type='teacher', target_id=teacher.id, date=MONDAY, status='Absent'))
    db.session.commit()
    result = qr.process_scan(_token(teacher.id), now=_at(MONDAY, 10, 30))
    assert result['code'] == 'marked' and result['status'] == 'Late'
    assert result['late_minutes'] == 120 and result['previous_status'] == 'Absent'
    rows = _rows(teacher.id)
    assert len(rows) == 1 and rows[0].status == 'Late'


def test_teacher_on_leave_is_not_changed_by_a_scan(app):
    _settings()
    teacher = _teacher()
    db.session.add(AttendanceModel(
        target_type='teacher', target_id=teacher.id, date=MONDAY, status='Leave'))
    db.session.commit()
    result = qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 0))
    assert result['code'] == 'on_leave' and not result['ok']
    assert 'teacher' in result['message'].lower()
    assert _rows(teacher.id)[0].status == 'Leave'


def test_teacher_scan_on_a_closed_day_is_refused(app):
    _settings()
    teacher = _teacher()
    result = qr.process_scan(_token(teacher.id), now=_at(SUNDAY, 8, 0))
    assert result['code'] == 'school_closed' and not result['ok']
    assert result['person']['name'] == 'Sara Ahmed'
    assert _rows(teacher.id, SUNDAY) == []


def test_inactive_or_unknown_teacher_is_refused_and_nothing_is_saved(app):
    _settings()
    teacher = _teacher()
    teacher.is_active = False
    db.session.commit()
    assert qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 0))['code'] == 'unknown_teacher'
    assert qr.process_scan(_token(999999), now=_at(MONDAY, 8, 0))['code'] == 'unknown_teacher'
    assert AttendanceModel.query.count() == 0


def test_bad_and_old_teacher_codes_give_clear_answers(app):
    _settings()
    teacher = _teacher()
    forged = _token(teacher.id)[:-3] + 'abc'
    assert qr.process_scan(forged, now=_at(MONDAY, 8, 0))['code'] == 'invalid_qr'
    assert qr.process_scan('SMQT1.x.y', now=_at(MONDAY, 8, 0))['code'] == 'invalid_qr'
    old = qr.process_scan('TEACHER|T001|Sara Ahmed', now=_at(MONDAY, 8, 0))
    assert old['code'] == 'old_card' and not old['ok']
    assert 'teacher' in old['message'].lower() and old['person_type'] == 'teacher'
    assert AttendanceModel.query.count() == 0


def test_teacher_scan_sends_no_whatsapp_message(app):
    _settings()
    teacher = _teacher()
    qr.process_scan(_token(teacher.id), now=_at(MONDAY, 9, 45))      # very late
    assert MessageQueue.query.count() == 0


def test_student_scan_is_unchanged_and_teachers_stay_out_of_student_numbers(app, seed):
    _settings()
    teacher = _teacher()
    qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 0))
    student = qr.process_scan(qr.make_token(qr.get_secret(), seed['student_id']),
                              now=_at(MONDAY, 8, 5))
    assert student['code'] == 'marked' and student['person_type'] == 'student'
    assert student['person']['name'] == 'Ali Khan' and student['student'] == student['person']
    students = qr.build_daily_report(MONDAY)
    assert students['counts']['total'] == 2 and students['counts']['present'] == 1
    assert AttendanceModel.query.filter_by(target_type='student').count() == 1
    assert AttendanceModel.query.filter_by(target_type='teacher').count() == 1


# -- the teachers' daily report -------------------------------------------

def test_teacher_daily_report_splits_present_late_leave_and_not_arrived(app):
    _settings()
    on_time = _teacher('T001', 'Aaliya')
    late = _teacher('T002', 'Bilal')
    leave = _teacher('T003', 'Chand')
    _teacher('T004', 'Danish')
    gone = _teacher('T005', 'Gone Teacher')
    gone.is_active = False
    db.session.add(AttendanceModel(
        target_type='teacher', target_id=leave.id, date=MONDAY, status='Leave'))
    db.session.commit()
    qr.process_scan(_token(on_time.id), now=_at(MONDAY, 8, 10))
    qr.process_scan(_token(late.id), now=_at(MONDAY, 9, 0))

    report = qr.build_teacher_daily_report(MONDAY)
    assert report['counts'] == {'total': 4, 'present': 1, 'late': 1, 'absent': 1,
                                'leave': 1, 'attended': 2}
    assert report['absent'][0]['label'] == 'Not marked yet'
    assert report['present'][0]['teacher'].id == on_time.id
    assert report['present'][0]['qr_time'] == '08:10'
    assert report['late'][0]['late_minutes'] == 30


def test_teacher_scan_shows_in_the_teacher_summary(app):
    _settings()
    teacher = _teacher()
    qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 50))
    summary = build_teacher_attendance_summary(MONDAY, MONDAY)
    row = next(row for row in summary['matrix_data'] if row['teacher'].id == teacher.id)
    assert row['daily_status'][MONDAY] == 'Late'
    assert row['total_late_minutes'] == 20


# -- guard API ------------------------------------------------------------

def test_guard_phone_can_scan_a_teacher_card(app, guard_client, monkeypatch):
    _settings()
    monkeypatch.setattr('app.services.teacher_payroll.is_school_day',
                        lambda day, settings=None: True)
    teacher = _teacher()
    guard_client.post('/api/qr/login', json={'username': 'guard', 'password': 'guardpass123'})

    ping = guard_client.get('/api/qr/ping').get_json()
    assert ping['today']['teachers']['total'] == 1
    assert ping['today']['teachers']['attended'] == 0

    scan = guard_client.post('/api/qr/scan', json={'token': _token(teacher.id)})
    body = scan.get_json()
    assert scan.status_code == 200 and body['ok'] and body['code'] == 'marked'
    assert body['person_type'] == 'teacher' and body['person']['name'] == 'Sara Ahmed'
    assert body['today']['teachers']['attended'] == 1
    assert body['today']['attended'] == 0          # the student numbers are not touched

    again = guard_client.post('/api/qr/scan', json={'token': _token(teacher.id)}).get_json()
    assert again['code'] == 'already_marked'


def test_teacher_scan_needs_a_signed_in_guard(app, client):
    teacher = _teacher()
    response = client.post('/api/qr/scan', json={'token': _token(teacher.id)})
    assert response.status_code == 401


def test_teacher_photo_endpoint_404_without_a_photo(app, guard_client):
    teacher = _teacher()
    guard_client.post('/api/qr/login', json={'username': 'guard', 'password': 'guardpass123'})
    assert guard_client.get(f'/api/qr/teacher-photo/{teacher.id}').status_code == 404
    assert guard_client.get('/api/qr/teacher-photo/999999').status_code == 404


def test_other_devices_can_reach_the_teacher_photo_api_only_through_the_guard_api(app, client):
    remote = {'environ_overrides': {'REMOTE_ADDR': '192.168.1.50'}}
    # it is inside /api/qr/, so the network rule lets it reach the route (which then wants a sign-in)
    assert client.get('/api/qr/teacher-photo/1', **remote).status_code in (401, 404)


# -- QR tab ---------------------------------------------------------------

def test_qr_tab_lists_teachers_and_their_scan_time(app, seed, admin_client):
    _settings()
    scanned = _teacher('T001', 'Aaliya Scanned')
    _teacher('T002', 'Bilal Waiting')
    qr.process_scan(_token(scanned.id), now=_at(MONDAY, 8, 20))
    html = admin_client.get(QR_URL).get_data(as_text=True)
    assert 'id="qaTeachers"' in html
    assert 'Teachers on this day' in html
    assert 'Aaliya Scanned' in html and 'Bilal Waiting' in html and '08:20' in html
    assert html.index('Bilal Waiting') < html.index('Aaliya Scanned')      # not arrived come first
    # the student list is separate: its rows and counts are not changed by teachers
    assert html.count('class="qa-row" data-group="absent"') == 2
    assert html.count('class="qa-row" data-group="present"') == 0


def test_qr_tab_has_no_teacher_card_when_there_are_no_teachers(app, seed, admin_client):
    html = admin_client.get(QR_URL).get_data(as_text=True)
    assert 'id="qaTeachers"' not in html


def test_qr_tab_live_refresh_also_swaps_the_teacher_card(app, seed, admin_client):
    html = admin_client.get(QR_URL).get_data(as_text=True)
    assert "'qaTeachers'" in html


# -- teacher sheet --------------------------------------------------------

def test_teacher_sheet_shows_the_gate_scan_time(app, admin_client):
    _settings()
    teacher = _teacher()
    qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 20))
    html = admin_client.get('/attendance/teachers?date=2026-10-19').get_data(as_text=True)
    assert 'QR 08:20' in html


def test_teacher_sheet_without_a_scan_has_no_qr_tag(app, admin_client):
    _settings()
    _teacher()
    html = admin_client.get('/attendance/teachers?date=2026-10-19').get_data(as_text=True)
    assert 'ta-tag ta-tag-qr' not in html


def test_manual_teacher_save_never_loses_the_qr_scan_time(app):
    _settings()
    teacher = _teacher()
    qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 20))
    # the sheet is saved with the time box left empty
    save_teacher_attendance(MONDAY, {f'status_{teacher.id}': 'Present',
                                     f'checkin_time_{teacher.id}': ''}, [teacher])
    row = _rows(teacher.id)[0]
    assert row.qr_time.startswith('08:20') and row.late_time.startswith('08:20')
    assert row.status == 'Present'
    # marking Absent by hand keeps the scan time on record
    save_teacher_attendance(MONDAY, {f'status_{teacher.id}': 'Absent'}, [teacher])
    row = _rows(teacher.id)[0]
    assert row.status == 'Absent' and row.qr_time.startswith('08:20')


def test_manual_teacher_time_still_wins_over_the_scan_time(app):
    _settings()
    teacher = _teacher()
    qr.process_scan(_token(teacher.id), now=_at(MONDAY, 8, 20))
    save_teacher_attendance(MONDAY, {f'status_{teacher.id}': 'Present',
                                     f'checkin_time_{teacher.id}': '09:00'}, [teacher])
    row = _rows(teacher.id)[0]
    assert row.status == 'Late' and row.late_time == '09:00' and row.late_minutes == 30
    assert row.qr_time.startswith('08:20')

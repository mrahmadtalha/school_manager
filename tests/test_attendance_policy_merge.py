"""Attendance policy, merged attendance page and QR-time protection."""

from datetime import date, datetime

from app.database import db
from app.models import AttendanceModel, SchoolSettings, StudentModel
from app.services import qr_attendance as qr
from app.services.attendance_service import (
    attended_statuses, build_student_attendance_summary, save_student_attendance)

MONDAY = date(2026, 10, 19)


def _at(hour, minute):
    return datetime(MONDAY.year, MONDAY.month, MONDAY.day, hour, minute)


def _settings(**flags):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    for name, value in flags.items():
        setattr(settings, name, value)
    db.session.commit()
    return settings


def _token(student_id):
    return qr.make_token(qr.get_secret(), student_id)


def _row(student_id):
    return AttendanceModel.query.filter_by(
        target_type='student', target_id=student_id, date=MONDAY).one()


def test_late_after_cutoff_is_the_default(app, seed):
    _settings()
    result = qr.process_scan(_token(seed['student_id']), now=_at(10, 45))
    assert result['status'] == 'Late'


def test_school_can_keep_late_arrivals_as_present(app, seed):
    _settings(late_after_cutoff=False)
    result = qr.process_scan(_token(seed['student_id']), now=_at(10, 45))
    assert result['status'] == 'Present'
    row = _row(seed['student_id'])
    assert row.status == 'Present' and row.late_time.startswith('10:45')
    assert row.late_minutes is None and row.qr_time.startswith('10:45')


def test_teacher_can_still_choose_late_by_hand(app, seed):
    _settings(late_after_cutoff=False)
    class_obj = StudentModel.query.get(seed['student_id']).class_info
    save_student_attendance(class_obj.id, MONDAY, {
        f"status_{seed['student_id']}": 'Late',
        f"checkin_time_{seed['student_id']}": '09:00'}, [class_obj])
    assert _row(seed['student_id']).status == 'Late'


def test_percentage_follows_the_school_setting(app, seed):
    _settings(late_counts_as_present=True)
    assert attended_statuses() == ('Present', 'Late')
    qr.process_scan(_token(seed['student_id']), now=_at(10, 45))            # Late
    both = qr.build_daily_report(MONDAY)['percentage']
    summary = build_student_attendance_summary(seed['class_id'], MONDAY, MONDAY)
    row = [r for r in summary['matrix_data'] if r['student'].id == seed['student_id']][0]
    assert row['percentage'] == 100.0 and both == 50.0

    _settings(late_counts_as_present=False)
    assert attended_statuses() == ('Present',)
    assert qr.build_daily_report(MONDAY)['percentage'] == 0.0
    summary = build_student_attendance_summary(seed['class_id'], MONDAY, MONDAY)
    row = [r for r in summary['matrix_data'] if r['student'].id == seed['student_id']][0]
    assert row['percentage'] == 0


def test_manual_save_never_overwrites_the_qr_scan_time(app, seed):
    _settings()
    qr.process_scan(_token(seed['student_id']), now=_at(8, 20))
    class_obj = StudentModel.query.get(seed['student_id']).class_info
    # the teacher saves the sheet with the time box left empty
    save_student_attendance(class_obj.id, MONDAY, {
        f"status_{seed['student_id']}": 'Present',
        f"checkin_time_{seed['student_id']}": ''}, [class_obj])
    row = _row(seed['student_id'])
    assert row.qr_time.startswith('08:20') and row.late_time.startswith('08:20')
    # even marking Absent by hand keeps the scan time on record
    save_student_attendance(class_obj.id, MONDAY, {
        f"status_{seed['student_id']}": 'Absent'}, [class_obj])
    assert _row(seed['student_id']).qr_time.startswith('08:20')


def test_sheet_page_has_both_tabs_and_shows_qr_time(admin_client, app, seed):
    _settings()
    qr.process_scan(_token(seed['student_id']), now=_at(8, 20))
    page = admin_client.get(
        f"/attendance/students?class_id={seed['class_id']}&date=2026-10-19").get_data(as_text=True)
    assert 'Attendance Sheet' in page and 'QR Scans' in page and 'QR 08:20' in page
    for status in ('Present', 'Absent', 'Late', 'Leave'):      # the full set for teachers
        assert f'value="{status}"' in page
    nav = admin_client.get('/').get_data(as_text=True)
    assert 'QR Attendance</span>' not in nav


def test_policy_is_saved_from_school_settings(admin_client, app):
    _settings()
    admin_client.post('/settings', data={
        'action': 'save_academic_settings', 'attendance_grace_minutes': '5',
        'late_display': 'present', 'percent_basis': 'present_only'})
    db.session.expire_all()
    settings = SchoolSettings.query.first()
    assert settings.late_after_cutoff is False
    assert settings.late_counts_as_present is False


def test_sheet_flags_unmarked_students_and_hides_zero_minutes(admin_client, app, seed):
    _settings()
    qr.process_scan(_token(seed['student_id']), now=_at(8, 20))      # one student scanned
    page = admin_client.get(
        f"/attendance/students?class_id={seed['class_id']}&date=2026-10-19").get_data(as_text=True)
    assert 'attendance not marked yet' in page and 'Not marked yet' in page
    assert 'toggleUnmarkedOnly()' in page
    row = AttendanceModel.query.filter_by(target_id=seed['student_id'], date=MONDAY).one()
    row.status, row.late_minutes, row.is_locked = 'Late', 0, True
    db.session.commit()
    locked = admin_client.get(
        f"/attendance/students?class_id={seed['class_id']}&date=2026-10-19").get_data(as_text=True)
    assert '· 0 min' not in locked          # the badge only; the grace line also says "0 minute(s)"
    assert 'Late' in locked

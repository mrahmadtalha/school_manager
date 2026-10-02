from datetime import date

from app.database import db
from app.models import (
    AttendanceModel, ClassModel, SchoolSettings, StudentModel, TeacherModel,
)
from app.services.attendance_service import (
    build_student_attendance_summary,
    build_teacher_attendance_summary,
    evaluate_checkin_attendance,
    save_student_attendance,
    save_teacher_attendance,
)


ATTENDANCE_DATE = date(2026, 9, 21)


def _school_settings():
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
        db.session.flush()
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 5
    return settings


def test_checkin_evaluator_observes_start_and_grace_boundary(app):
    with app.app_context():
        settings = _school_settings()
        assert evaluate_checkin_attendance('Present', '08:35', settings) == (
            'Present', '08:35', None)
        assert evaluate_checkin_attendance('Present', '08:35:00', settings) == (
            'Present', '08:35', None)
        assert evaluate_checkin_attendance('Present', '08:35:01', settings) == (
            'Late', '08:35:01', 6)
        assert evaluate_checkin_attendance('Present', '08:36', settings) == (
            'Late', '08:36', 6)
        assert evaluate_checkin_attendance('Late', '08:33', settings) == (
            'Late', '08:33', 3)
        assert evaluate_checkin_attendance('Absent', '09:00', settings) == (
            'Absent', None, None)


def test_student_checkin_is_auto_marked_and_summarized(admin_client, app, seed):
    entry_page = admin_client.get(
        f'/attendance/students?class_id={seed["class_id"]}&date={ATTENDANCE_DATE}')
    assert f'name="checkin_time_{seed["student_id"]}"' in entry_page.get_data(as_text=True)

    with app.app_context():
        settings = _school_settings()
        db.session.commit()
        class_obj = db.session.get(ClassModel, seed['class_id'])
        students = StudentModel.query.filter_by(class_id=class_obj.id, is_active=True).all()
        target = students[0]

        save_student_attendance(
            class_obj.id,
            ATTENDANCE_DATE,
            {
                f'status_{target.id}': 'Present',
                f'checkin_time_{target.id}': '08:47',
            },
            [class_obj],
        )

        record = AttendanceModel.query.filter_by(
            target_type='student', target_id=target.id, date=ATTENDANCE_DATE).one()
        assert record.status == 'Late'
        assert record.late_time == '08:47'
        assert record.late_minutes == 17

        summary = build_student_attendance_summary(
            class_obj.id, ATTENDANCE_DATE, ATTENDANCE_DATE)
        row = next(row for row in summary['matrix_data'] if row['student'].id == target.id)
        assert row['daily_status'][ATTENDANCE_DATE] == 'Late'
        assert row['daily_late_minutes'][ATTENDANCE_DATE] == 17
        assert row['total_late_minutes'] == 17

    daily_page = admin_client.get(
        f'/attendance/students?class_id={seed["class_id"]}&date={ATTENDANCE_DATE}')
    monthly_page = admin_client.get(
        f'/attendance/summary?class_id={seed["class_id"]}&start_date={ATTENDANCE_DATE}&end_date={ATTENDANCE_DATE}')
    assert 'Late · 17 min' in daily_page.get_data(as_text=True)
    assert 'L · 17m' in monthly_page.get_data(as_text=True)


def test_teacher_checkin_is_auto_marked_and_summarized(admin_client, app):
    with app.app_context():
        _school_settings()
        teacher = TeacherModel(
            teacher_id_str='T-LATE-1', teacher_name='Late Teacher',
            qualification='B.Ed', contact_number='03001234567',
        )
        db.session.add(teacher)
        db.session.commit()

        save_teacher_attendance(ATTENDANCE_DATE, {
            f'status_{teacher.id}': 'Present',
            f'checkin_time_{teacher.id}': '08:42',
        }, [teacher])

        record = AttendanceModel.query.filter_by(
            target_type='teacher', target_id=teacher.id, date=ATTENDANCE_DATE).one()
        assert record.status == 'Late'
        assert record.late_time == '08:42'
        assert record.late_minutes == 12

        summary = build_teacher_attendance_summary(ATTENDANCE_DATE, ATTENDANCE_DATE)
        row = next(row for row in summary['matrix_data'] if row['teacher'].id == teacher.id)
        assert row['daily_late_minutes'][ATTENDANCE_DATE] == 12
        assert row['total_late_minutes'] == 12

    daily_page = admin_client.get(f'/attendance/teachers?date={ATTENDANCE_DATE}')
    monthly_page = admin_client.get(
        f'/attendance/teachers/summary?start_date={ATTENDANCE_DATE}&end_date={ATTENDANCE_DATE}')
    assert 'Late · 12 min' in daily_page.get_data(as_text=True)
    assert f'name="checkin_time_{teacher.id}"' in daily_page.get_data(as_text=True)
    assert 'Late · 12m' in monthly_page.get_data(as_text=True)


def test_academic_settings_form_exposes_and_saves_grace_period(admin_client, app):
    page = admin_client.get('/settings?tab=academic').get_data(as_text=True)
    assert 'Late arrival grace period' in page
    assert 'name="attendance_grace_minutes"' in page

    response = admin_client.post('/settings', data={
        'action': 'save_academic_settings',
        'academic_session': '2026-2027',
        'school_start_time': '08:10',
        'school_end_time': '14:30',
        'attendance_grace_minutes': '12',
        'weekend_off': 'on',
    })
    assert response.status_code == 302
    with app.app_context():
        settings = SchoolSettings.query.first()
        assert settings.school_start_time == '08:10'
        assert settings.attendance_grace_minutes == 12


def test_existing_database_migrates_late_minutes_and_grace_settings(fresh_app_factory, tmp_path):
    import sqlite3

    database_path = tmp_path / 'old-attendance.db'
    connection = sqlite3.connect(database_path)
    connection.execute('''
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            target_type VARCHAR(20) NOT NULL,
            target_id INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL,
            class_id INTEGER,
            is_locked BOOLEAN DEFAULT 0,
            late_time VARCHAR(10)
        )
    ''')
    connection.execute('''
        CREATE TABLE school_settings (
            id INTEGER PRIMARY KEY,
            school_name VARCHAR(200),
            tagline VARCHAR(200),
            logo_filename VARCHAR(200),
            address VARCHAR(300),
            phone VARCHAR(50),
            email VARCHAR(100),
            academic_session VARCHAR(50),
            result_announcement_date VARCHAR(20),
            school_start_time VARCHAR(10) DEFAULT '08:30',
            school_end_time VARCHAR(10) DEFAULT '15:00',
            weekend_off BOOLEAN DEFAULT 1,
            custom_off_days VARCHAR(200) DEFAULT '',
            primary_color VARCHAR(20) DEFAULT '#0d6efd',
            secondary_color VARCHAR(20) DEFAULT '#6c757d'
        )
    ''')
    connection.commit()
    connection.close()

    migrated_app = fresh_app_factory(tmp_path, 'old-attendance.db')
    with migrated_app.app_context():
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        attendance_columns = {column['name'] for column in inspector.get_columns('attendance')}
        school_columns = {column['name'] for column in inspector.get_columns('school_settings')}
        assert 'late_minutes' in attendance_columns
        assert 'attendance_grace_minutes' in school_columns

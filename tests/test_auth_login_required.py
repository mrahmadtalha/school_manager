"""Authentication, session handling and the original regression intents."""

from datetime import date

from app.database import db
from app.models import (
    AttendanceModel, ClassModel, FeeRecordModel, SchoolSettings, SectionModel,
    StudentMarkModel, StudentModel, SubjectModel, TeacherModel, TestModel,
)
from tests.conftest import ADMIN_PASSWORD, login, logout


def test_dashboard_requires_login(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.location


def test_protected_page_requires_login(client):
    response = client.get('/students')
    assert response.status_code == 302
    assert '/login' in response.location


def test_login_with_wrong_password_is_rejected(client):
    response = login(client, 'admin', 'wrong-password')
    assert response.status_code == 200
    assert b'Incorrect username or password' in response.data


def test_login_success_redirects_to_dashboard(client):
    response = login(client, 'admin', ADMIN_PASSWORD)
    assert response.status_code == 302
    assert response.location.endswith('/')


def test_logout_invalidates_session(client):
    login(client, 'admin', ADMIN_PASSWORD)
    assert client.get('/').status_code == 200

    logout(client)
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.location


def test_login_lockout_after_repeated_failures(client, app):
    max_attempts = app.config['LOGIN_MAX_ATTEMPTS']
    for _ in range(max_attempts):
        login(client, 'admin', 'nope')

    response = client.post('/login', data={'username': 'admin', 'password': ADMIN_PASSWORD})
    assert response.status_code == 429


def _wait_for_seed_job(client, timeout=180):
    """Wait until the background demo-data job started by the wizard ends."""
    import time

    from app.seed_progress import get_seed_job

    with client.session_transaction() as sess:
        token = sess.get('seed_job_token')
    assert token, 'wizard should register a seed job token in the session'
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_seed_job(token)
        assert job is not None, 'seed job disappeared'
        if job['state'] != 'running':
            return job
        time.sleep(0.2)
    raise AssertionError('demo-data job did not finish in time')


def test_first_run_setup_creates_admin_settings_and_demo_data(monkeypatch, fresh_app_factory):
    monkeypatch.delenv('INITIAL_ADMIN_USERNAME', raising=False)
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)

    import pathlib
    import tempfile
    base = pathlib.Path(tempfile.mkdtemp(prefix='setup-wizard-'))

    application = fresh_app_factory(base, 'setup.db')
    with application.app_context():
        db.drop_all()
        db.create_all()

    client = application.test_client()
    response = client.post('/setup-admin', data={
        'username': 'schooladmin',
        'password': 'StrongPass123',
        'confirm_password': 'StrongPass123',
        'school_name': 'Bright Future Academy',
        'tagline': 'Quality Education',
        'address': 'Main Road, Sargodha',
        'phone': '+923001234567',
        'email': 'info@brightfuture.edu',
        'dummy_data': 'on',
        'dummy_period_months': '1',
        'dummy_attendance': 'off', 'dummy_fees': 'off', 'dummy_expenses': 'off',
        'dummy_tests': 'off', 'dummy_term_exams': 'off', 'dummy_payroll': 'off',
    }, follow_redirects=False)

    # The wizard now redirects to the live progress screen while a background
    # thread generates the demo data.
    assert response.status_code == 302
    assert '/setup-progress' in response.location
    job = _wait_for_seed_job(client)
    assert job['state'] == 'done', job.get('error')

    with application.app_context():
        from app.models import AdminUser
        admin = AdminUser.query.filter_by(username='schooladmin').first()
        assert admin is not None
        assert admin.role == 'admin'

        school = SchoolSettings.query.first()
        assert school is not None
        assert school.school_name == 'Bright Future Academy'
        assert school.email == 'info@brightfuture.edu'
        assert ClassModel.query.count() > 0


def test_first_run_setup_honours_demo_counts_and_fee(monkeypatch, fresh_app_factory):
    monkeypatch.delenv('INITIAL_ADMIN_USERNAME', raising=False)
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)

    import pathlib
    import tempfile
    base = pathlib.Path(tempfile.mkdtemp(prefix='setup-wizard-'))

    application = fresh_app_factory(base, 'setup2.db')
    with application.app_context():
        db.drop_all()
        db.create_all()

    client = application.test_client()
    response = client.post('/setup-admin', data={
        'username': 'demoadmin',
        'password': 'StrongPass123',
        'confirm_password': 'StrongPass123',
        'school_name': 'Demo Academy',
        'dummy_data': 'on',
        'dummy_student_count': '100',
        'dummy_teacher_count': '12',
        'dummy_fee': '2200',
        'dummy_period_months': '1',
        'dummy_attendance': 'off', 'dummy_fees': 'off', 'dummy_expenses': 'off',
        'dummy_tests': 'off', 'dummy_term_exams': 'off', 'dummy_payroll': 'off',
    }, follow_redirects=False)

    assert response.status_code == 302
    job = _wait_for_seed_job(client)
    assert job['state'] == 'done', job.get('error')

    with application.app_context():
        assert StudentModel.query.count() == 100
        assert TeacherModel.query.count() == 12
        # Fees anchor to the entered base fee and rise slightly with class
        # level (plus small jitter), so every fee stays in a realistic band.
        fees = [s.monthly_fee for s in StudentModel.query.all()]
        assert all(2000 <= fee <= 3200 for fee in fees)


def test_import_templates_are_available(admin_client):
    student_response = admin_client.get('/students/template/excel')
    assert student_response.status_code == 200
    assert 'spreadsheetml' in student_response.mimetype

    teacher_response = admin_client.get('/teachers/template/excel')
    assert teacher_response.status_code == 200
    assert 'spreadsheetml' in teacher_response.mimetype


def test_class_fee_bulk_update_and_individual_override(admin_client, app, seed):
    response = admin_client.post('/fees/class-bulk-update', data={
        'class_id': str(seed['class_id']),
        'monthly_fee': '2500',
        'confirm_bulk_update': 'yes',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        students = StudentModel.query.filter_by(class_id=seed['class_id']).all()
        assert len(students) == 2
        assert all(s.monthly_fee == 2500.0 for s in students)

        student = StudentModel.query.filter_by(roll_number=1001).first()
        student.monthly_fee = 3200.0
        db.session.commit()
        assert StudentModel.query.filter_by(roll_number=1001).first().monthly_fee == 3200.0


def test_permanent_delete_routes_are_removed(admin_client, app, seed):
    with app.app_context():
        student = StudentModel.query.get(seed['student_id'])
        student.is_active = False
        db.session.add(StudentMarkModel(test_id=1, student_id=student.id, marks_obtained=80.0,
                                        percentage=80.0, grade='A'))
        db.session.add(FeeRecordModel(student_id=student.id, month_year='September 2026',
                                      amount_due=2000.0, amount_paid=0.0, status='Pending'))
        db.session.commit()
        archived_id = student.id

    # Permanent deletion has been removed from the app entirely.
    assert admin_client.post('/students/delete-all-permanent',
                             follow_redirects=False).status_code == 404
    assert admin_client.post('/students/permanent-delete/%d' % archived_id,
                             follow_redirects=False).status_code == 404

    with app.app_context():
        # The archived student and every related record must survive.
        assert StudentModel.query.get(archived_id) is not None
        assert StudentModel.query.count() == 2
        assert FeeRecordModel.query.filter_by(student_id=archived_id).count() == 1
        assert StudentMarkModel.query.filter_by(student_id=archived_id).count() == 1


def test_classes_page_shows_active_student_total(admin_client, app, seed):
    with app.app_context():
        student = StudentModel.query.get(seed['other_student_id'])
        student.is_active = False
        db.session.commit()

    response = admin_client.get('/classes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'summary-card is-students' in html
    num_block = html.split('summary-card is-students', 1)[1].split('summary-num">', 1)[1]
    assert num_block.split('<', 1)[0] == '1'


def test_reports_overview_dashboard_renders(admin_client, app, seed):
    with app.app_context():
        db.session.add(TeacherModel(
            teacher_id_str='T001', teacher_name='Ayesha', joining_date=date(2024, 1, 1),
            qualification='M.Ed', salary=50000, assigned_class='Class 1',
        ))
        db.session.commit()

    response = admin_client.get('/reports/hub?module=overview', follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Total Outstanding Dues' in body
    assert 'id="hubAttendanceChart"' in body


def test_student_detailed_report_renders_attendance_and_marks(admin_client, app, seed):
    with app.app_context():
        class_id = seed['class_id']
        subject_id = seed['subject_id']
        student_id = seed['student_id']

        test1 = TestModel(test_title='Monthly Test 1', test_date=date(2026, 9, 2),
                          test_type='Monthly', class_id=class_id, subject_id=subject_id,
                          total_marks=100)
        test2 = TestModel(test_title='Monthly Test 2', test_date=date(2026, 9, 16),
                          test_type='Monthly', class_id=class_id, subject_id=subject_id,
                          total_marks=100)
        db.session.add_all([test1, test2])
        db.session.flush()

        db.session.add_all([
            StudentMarkModel(test_id=test1.id, student_id=student_id, marks_obtained=82,
                             percentage=82.0, grade='A'),
            StudentMarkModel(test_id=test2.id, student_id=student_id, marks_obtained=76,
                             percentage=76.0, grade='B'),
            AttendanceModel(date=date(2026, 9, 1), target_type='student', target_id=student_id,
                            status='Absent', class_id=class_id),
            AttendanceModel(date=date(2026, 9, 2), target_type='student', target_id=student_id,
                            status='Late', class_id=class_id, late_time='08:45'),
            AttendanceModel(date=date(2026, 9, 3), target_type='student', target_id=student_id,
                            status='Leave', class_id=class_id),
            AttendanceModel(date=date(2026, 9, 4), target_type='student', target_id=student_id,
                            status='Present', class_id=class_id),
        ])
        db.session.commit()

    response = admin_client.get(f'/students/{seed["student_id"]}/report')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Attendance History' in body
    assert 'Absent' in body
    assert 'Late' in body
    assert 'Result Card' in body

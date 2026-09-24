import os
import unittest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')

from app import create_app
from app.database import db
from app.models import AdminUser, SchoolSettings, ClassModel, StudentModel, SectionModel, SubjectModel, TeacherModel, AttendanceModel, TestModel, StudentMarkModel, FeeRecordModel


class AuthLoginRequiredTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(AdminUser(username='admin', password_hash='hashed-password'))
            db.session.commit()

    def test_dashboard_requires_login(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)

    def test_first_time_setup_creates_school_settings_and_demo_data(self):
        os.environ.pop('INITIAL_ADMIN_USERNAME', None)
        os.environ.pop('INITIAL_ADMIN_PASSWORD', None)

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post('/setup-admin', data={
            'username': 'schooladmin',
            'password': 'StrongPass123',
            'confirm_password': 'StrongPass123',
            'school_name': 'Bright Future Academy',
            'tagline': 'Quality Education',
            'address': 'Main Road, Sargodha',
            'phone': '+923001234567',
            'email': 'info@brightfuture.edu',
            'dummy_data': 'on',
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            admin = AdminUser.query.filter_by(username='schooladmin').first()
            self.assertIsNotNone(admin)

            school = SchoolSettings.query.first()
            self.assertIsNotNone(school)
            self.assertEqual(school.school_name, 'Bright Future Academy')
            self.assertEqual(school.email, 'info@brightfuture.edu')
            self.assertGreater(ClassModel.query.count(), 0)

    def test_first_time_setup_accepts_demo_data_counts_and_fee(self):
        os.environ.pop('INITIAL_ADMIN_USERNAME', None)
        os.environ.pop('INITIAL_ADMIN_PASSWORD', None)

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

        response = self.client.post('/setup-admin', data={
            'username': 'demoadmin',
            'password': 'StrongPass123',
            'confirm_password': 'StrongPass123',
            'school_name': 'Demo Academy',
            'tagline': 'Demo setup',
            'address': 'Street 1',
            'phone': '+923001234567',
            'email': 'demo@example.com',
            'dummy_data': 'on',
            'dummy_student_count': '100',
            'dummy_teacher_count': '12',
            'dummy_fee': '2200',
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertEqual(StudentModel.query.count(), 100)
            self.assertEqual(TeacherModel.query.count(), 12)
            self.assertTrue(all(student.monthly_fee == 2200.0 for student in StudentModel.query.all()))

    def test_class_fee_bulk_update_and_individual_override(self):
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            class_a = ClassModel(name='Class 1')
            db.session.add(class_a)
            db.session.flush()

            s1 = StudentModel(
                roll_number='R1', student_name='Ali', father_name='Ahmad',
                guardian_phone='03001234567', address='Address', monthly_fee=1000.0,
                class_id=class_a.id
            )
            s2 = StudentModel(
                roll_number='R2', student_name='Bay', father_name='Bashir',
                guardian_phone='03001234568', address='Address', monthly_fee=1500.0,
                class_id=class_a.id
            )
            db.session.add_all([s1, s2])
            db.session.commit()

        response = self.client.post('/fees/class-bulk-update', data={
            'class_id': str(class_a.id),
            'monthly_fee': '2500'
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertEqual(StudentModel.query.filter_by(class_id=class_a.id).count(), 2)
            self.assertEqual(StudentModel.query.filter_by(class_id=class_a.id, roll_number='R1').first().monthly_fee, 2500.0)
            self.assertEqual(StudentModel.query.filter_by(class_id=class_a.id, roll_number='R2').first().monthly_fee, 2500.0)

            student = StudentModel.query.filter_by(roll_number='R1').first()
            student.monthly_fee = 3200.0
            db.session.commit()
            self.assertEqual(StudentModel.query.filter_by(roll_number='R1').first().monthly_fee, 3200.0)

    def test_import_templates_are_available(self):
        self.client.post('/login', data={'username': 'admin', 'password': 'strongpass123'}, follow_redirects=False)

        student_response = self.client.get('/students/template/excel')
        self.assertEqual(student_response.status_code, 200)
        self.assertIn('spreadsheetml', student_response.mimetype)

        teacher_response = self.client.get('/teachers/template/excel')
        self.assertEqual(teacher_response.status_code, 200)
        self.assertIn('spreadsheetml', teacher_response.mimetype)

    def test_bulk_delete_permanent_student_removes_related_records(self):
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            class_obj = ClassModel(name='Class 1')
            db.session.add(class_obj)
            db.session.flush()

            student = StudentModel(
                roll_number='S-100', student_name='Ali', father_name='Ahmad',
                guardian_phone='03000000001', address='Street', class_id=class_obj.id, is_active=False,
            )
            db.session.add(student)
            db.session.flush()

            db.session.add_all([
                StudentMarkModel(test_id=1, student_id=student.id, marks_obtained=80.0, percentage=80.0, grade='A'),
                FeeRecordModel(student_id=student.id, month_year='September 2026', amount_due=2000.0, amount_paid=0.0, status='Pending'),
            ])
            db.session.commit()

        login_response = self.client.post('/login', data={'username': 'admin', 'password': 'adminpass123'}, follow_redirects=False)
        self.assertEqual(login_response.status_code, 302)

        response = self.client.post('/students/delete-all-permanent', follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertEqual(StudentModel.query.count(), 0)
            self.assertEqual(FeeRecordModel.query.count(), 0)
            self.assertEqual(StudentMarkModel.query.count(), 0)

    def test_classes_page_shows_active_student_total(self):
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            class_obj = ClassModel(name='Class 1')
            db.session.add(class_obj)
            db.session.flush()
            db.session.add_all([
                SectionModel(name='A', class_id=class_obj.id),
                SubjectModel(name='English', class_id=class_obj.id),
            ])
            db.session.add_all([
                StudentModel(
                    roll_number='S1', student_name='Ali', father_name='Ahmad',
                    guardian_phone='03000000001', address='Street', class_id=class_obj.id, is_active=True
                ),
                StudentModel(
                    roll_number='S2', student_name='Hassan', father_name='Hassan',
                    guardian_phone='03000000002', address='Street', class_id=class_obj.id, is_active=False
                ),
            ])
            db.session.commit()

        response = self.client.get('/classes')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text-success">1</div>', response.get_data(as_text=True))

    def test_reports_overview_dashboard_renders(self):
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            class_obj = ClassModel(name='Class 1')
            db.session.add(class_obj)
            db.session.flush()
            db.session.add_all([
                StudentModel(
                    roll_number='S1', student_name='Ali', father_name='Ahmad',
                    guardian_phone='03000000001', address='Street', class_id=class_obj.id, is_active=True, monthly_fee=2000.0
                ),
                StudentModel(
                    roll_number='S2', student_name='Hassan', father_name='Hassan',
                    guardian_phone='03000000002', address='Street', class_id=class_obj.id, is_active=True, monthly_fee=1500.0
                )
            ])
            db.session.add(TeacherModel(
                teacher_id_str='T001', teacher_name='Ayesha', joining_date='2024-01-01', qualification='M.Ed', salary=50000,
                assigned_class='Class 1'
            ))
            db.session.commit()

        response = self.client.get('/reports/hub?module=overview')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Total Students', response.get_data(as_text=True))
        self.assertIn('School Overview', response.get_data(as_text=True))

    def test_student_detailed_report_renders_attendance_and_marks(self):
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            class_obj = ClassModel(name='Class 1')
            db.session.add(class_obj)
            db.session.flush()
            math = SubjectModel(name='Mathematics', class_id=class_obj.id)
            db.session.add(math)
            db.session.flush()

            student = StudentModel(
                roll_number='R-101', student_name='Ali Khan', father_name='Ahmad Khan',
                guardian_phone='03001234567', address='Main Road', class_id=class_obj.id, monthly_fee=2500.0
            )
            db.session.add(student)
            db.session.flush()

            test1 = TestModel(test_title='Monthly Test 1', test_date='2026-09-02', test_type='Monthly', class_id=class_obj.id, subject_id=math.id, total_marks=100)
            test2 = TestModel(test_title='Monthly Test 2', test_date='2026-09-16', test_type='Monthly', class_id=class_obj.id, subject_id=math.id, total_marks=100)
            db.session.add_all([test1, test2])
            db.session.flush()

            db.session.add_all([
                StudentMarkModel(test_id=test1.id, student_id=student.id, marks_obtained=82, percentage=82.0, grade='A'),
                StudentMarkModel(test_id=test2.id, student_id=student.id, marks_obtained=76, percentage=76.0, grade='B'),
                AttendanceModel(date='2026-09-01', target_type='student', target_id=student.id, status='Absent', class_id=class_obj.id),
                AttendanceModel(date='2026-09-02', target_type='student', target_id=student.id, status='Late', class_id=class_obj.id, late_time='08:45'),
                AttendanceModel(date='2026-09-03', target_type='student', target_id=student.id, status='Leave', class_id=class_obj.id),
                AttendanceModel(date='2026-09-04', target_type='student', target_id=student.id, status='Present', class_id=class_obj.id)
            ])
            db.session.commit()

        response = self.client.get(f'/students/{student.id}/report')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Attendance History', response.get_data(as_text=True))
        self.assertIn('Absent', response.get_data(as_text=True))
        self.assertIn('Late', response.get_data(as_text=True))
        self.assertIn('Result Card', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()

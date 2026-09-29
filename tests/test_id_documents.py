import os
import unittest
from datetime import date

from werkzeug.security import generate_password_hash

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')

from app import create_app
from app.database import db
from app.models import AdminUser, ClassModel, SchoolSettings, StudentModel, TeacherModel
from app.services.id_documents import academic_session, certificate_body, school_branding


class IdDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(AdminUser(
                username='admin',
                password_hash=generate_password_hash('adminpass123'),
            ))
            db.session.add(SchoolSettings(
                school_name='Test Academy',
                tagline='Learn well',
                address='Main Road',
                phone='03001234567',
            ))
            class_obj = ClassModel(name='Class 5')
            db.session.add(class_obj)
            db.session.flush()
            db.session.add(StudentModel(
                roll_number=1001,
                student_name='Ali Khan',
                father_name='Imran Khan',
                guardian_phone='03001111111',
                address='Street 1',
                class_id=class_obj.id,
            ))
            db.session.add(TeacherModel(
                teacher_id_str='T001',
                teacher_name='Sara Ahmed',
                qualification='M.Ed',
                salary=40000,
                monthly_salary=40000,
                assigned_class='Class 5',
                joining_date=date(2024, 4, 1),
            ))
            db.session.commit()
            self.class_id = class_obj.id
            self.student_id = StudentModel.query.filter_by(roll_number=1001).first().id
            self.teacher_id = TeacherModel.query.filter_by(teacher_id_str='T001').first().id

        self.client.post('/login', data={'username': 'admin', 'password': 'adminpass123'})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_documents_hub_renders(self):
        response = self.client.get('/documents')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ID Cards', response.data)
        self.assertIn(b'Certificates', response.data)

    def test_student_id_card_pdf(self):
        response = self.client.get(f'/documents/id-cards/students.pdf?student_id={self.student_id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertTrue(response.data.startswith(b'%PDF'))

    def test_teacher_id_card_pdf(self):
        response = self.client.get(f'/documents/id-cards/teachers.pdf?teacher_id={self.teacher_id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertTrue(response.data.startswith(b'%PDF'))

    def test_certificate_pdf_requires_target(self):
        response = self.client.get('/documents/certificates.pdf', follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    def test_certificate_pdf(self):
        response = self.client.get(
            f'/documents/certificates.pdf?cert_type=character&student_id={self.student_id}&session=2026-2027'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertTrue(response.data.startswith(b'%PDF'))

    def test_certificate_body_includes_student(self):
        with self.app.app_context():
            student = StudentModel.query.filter_by(id=self.student_id).first()
            school = school_branding()
            body = certificate_body('bonafide', student, school, '2026-2027', date.today(), '')
            self.assertIn('Ali Khan', body)
            self.assertIn('1001', body)
            self.assertIn('Test Academy', body)

    def test_academic_session_format(self):
        session = academic_session(date(2026, 9, 27))
        self.assertEqual(session, '2026-2027')

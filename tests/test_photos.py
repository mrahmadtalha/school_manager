"""Optional student / teacher profile pictures."""
import io
import os
import tempfile
import unittest
from datetime import date

from werkzeug.security import generate_password_hash

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')

from PIL import Image

from app import create_app
from app.database import db
from app.models import AdminUser, ClassModel, SchoolSettings, StudentModel, TeacherModel


def _png_bytes(color=(200, 30, 30), size=(120, 160)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.upload_dir = tempfile.mkdtemp(prefix='photo-tests-')
        self.app = create_app({'TESTING': True, 'PHOTO_UPLOAD_DIR': self.upload_dir})
        self.client = self.app.test_client()
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(AdminUser(username='admin',
                                     password_hash=generate_password_hash('adminpass123')))
            db.session.add(SchoolSettings(school_name='Test Academy'))
            klass = ClassModel(name='Class 5')
            db.session.add(klass)
            db.session.commit()
            self.class_id = klass.id
        self.client.post('/login', data={'username': 'admin', 'password': 'adminpass123'})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ---- helpers
    def _student_form(self, roll='1001', **extra):
        data = {'roll_number': roll, 'student_name': 'Ali Khan', 'father_name': 'Imran Khan',
                'guardian_phone': '03001111111', 'address': 'Street 1',
                'class_id': str(self.class_id), 'sponsor_type': 'Father'}
        data.update(extra)
        return data

    def _teacher_form(self, **extra):
        data = {'teacher_id_str': 'T001', 'teacher_name': 'Sara Ahmed',
                'qualification': 'M.Ed', 'salary_type': 'monthly', 'monthly_salary': '40000',
                'joining_date': '2024-04-01'}
        data.update(extra)
        return data

    def _student(self):
        with self.app.app_context():
            return StudentModel.query.first()

    def _teacher(self):
        with self.app.app_context():
            return TeacherModel.query.first()

    def _files_on_disk(self, kind):
        folder = os.path.join(self.upload_dir, kind + 's')
        return os.listdir(folder) if os.path.isdir(folder) else []

    # ---- students
    def test_student_saved_without_photo(self):
        self.client.post('/students/add', data=self._student_form(), follow_redirects=True)
        student = self._student()
        self.assertIsNotNone(student)
        self.assertIsNone(student.photo_filename)
        self.assertEqual(self.client.get(f'/students/{student.id}/photo').status_code, 404)
        self.assertEqual(self.client.get('/students').status_code, 200)
        self.assertEqual(self.client.get(f'/students/{student.id}/report').status_code, 200)
        pdf = self.client.get(f'/documents/id-cards/students.pdf?student_id={student.id}')
        self.assertTrue(pdf.data.startswith(b'%PDF'))

    def test_student_add_edit_remove_photo(self):
        self.client.post('/students/add', content_type='multipart/form-data',
                         data=self._student_form(photo=(_png_bytes(), 'me.png')))
        student = self._student()
        self.assertTrue(student.photo_filename)
        self.assertEqual(len(self._files_on_disk('student')), 1)
        served = self.client.get(f'/students/{student.id}/photo')
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.mimetype, 'image/jpeg')
        served.close()  # release the file handle so a later edit can delete it

        # Photo appears on list, profile, ID card, report PDF, transcript.
        self.assertIn(b'/photo?v=', self.client.get('/students').data)
        self.assertIn(b'/photo?v=', self.client.get(f'/students/{student.id}/report').data)
        for url in (f'/documents/id-cards/students.pdf?student_id={student.id}',
                    f'/students/{student.id}/report/pdf',
                    f'/students/{student.id}/transcript.pdf'):
            self.assertTrue(self.client.get(url).data.startswith(b'%PDF'), url)

        # Edit without touching the photo keeps it.
        old = student.photo_filename
        self.client.post(f'/students/edit/{student.id}', content_type='multipart/form-data',
                         data=self._student_form(student_name='Ali K'))
        self.assertEqual(self._student().photo_filename, old)

        # Change it: old file is deleted, new one stored.
        self.client.post(f'/students/edit/{student.id}', content_type='multipart/form-data',
                         data=self._student_form(photo=(_png_bytes((0, 0, 255)), 'new.png')))
        changed = self._student().photo_filename
        self.assertNotEqual(changed, old)
        self.assertEqual(self._files_on_disk('student'), [changed])

        # Remove it.
        self.client.post(f'/students/edit/{student.id}', content_type='multipart/form-data',
                         data=self._student_form(remove_photo='1'))
        self.assertIsNone(self._student().photo_filename)
        self.assertEqual(self._files_on_disk('student'), [])

    def test_invalid_photo_does_not_block_student(self):
        self.client.post('/students/add', content_type='multipart/form-data',
                         data=self._student_form(photo=(io.BytesIO(b'not an image'), 'x.png')))
        student = self._student()
        self.assertIsNotNone(student)
        self.assertIsNone(student.photo_filename)

    def test_photo_survives_roll_conflict_confirmation(self):
        self.client.post('/students/add', data=self._student_form(roll='1001'))
        response = self.client.post(
            '/students/add', content_type='multipart/form-data',
            data=self._student_form(roll='1001', student_name='Bilal',
                                    photo=(_png_bytes(), 'b.png')))
        self.assertEqual(response.status_code, 200)       # confirmation preview
        self.assertIn(b'photo_token', response.data)
        import re
        token = re.search(rb'name="photo_token" value="([0-9a-f]{32})"', response.data).group(1).decode()
        self.client.post('/students/add', data=self._student_form(
            roll='1001', student_name='Bilal', photo_token=token, confirm_cascade='1'))
        with self.app.app_context():
            bilal = StudentModel.query.filter_by(student_name='Bilal').first()
            self.assertTrue(bilal.photo_filename)

    # ---- teachers
    def test_teacher_saved_without_photo(self):
        self.client.post('/teachers/add', data=self._teacher_form())
        teacher = self._teacher()
        self.assertIsNotNone(teacher)
        self.assertIsNone(teacher.photo_filename)
        self.assertEqual(self.client.get(f'/teachers/{teacher.id}/photo').status_code, 404)
        self.assertEqual(self.client.get('/teachers').status_code, 200)
        self.assertEqual(self.client.get(f'/teachers/{teacher.id}').status_code, 200)
        pdf = self.client.get(f'/documents/id-cards/teachers.pdf?teacher_id={teacher.id}')
        self.assertTrue(pdf.data.startswith(b'%PDF'))

    def test_teacher_add_edit_remove_photo(self):
        self.client.post('/teachers/add', content_type='multipart/form-data',
                         data=self._teacher_form(photo=(_png_bytes(), 't.png')))
        teacher = self._teacher()
        self.assertTrue(teacher.photo_filename)
        self.assertEqual(self.client.get(f'/teachers/{teacher.id}/photo').status_code, 200)
        self.assertIn(b'/photo?v=', self.client.get('/teachers').data)
        self.assertIn(b'/photo?v=', self.client.get(f'/teachers/{teacher.id}').data)
        self.assertTrue(self.client.get(
            f'/documents/id-cards/teachers.pdf?teacher_id={teacher.id}').data.startswith(b'%PDF'))

        old = teacher.photo_filename
        self.client.post(f'/teachers/edit/{teacher.id}', content_type='multipart/form-data',
                         data=self._teacher_form(teacher_name='Sara A'))
        self.assertEqual(self._teacher().photo_filename, old)

        self.client.post(f'/teachers/edit/{teacher.id}', content_type='multipart/form-data',
                         data=self._teacher_form(remove_photo='1'))
        self.assertIsNone(self._teacher().photo_filename)
        self.assertEqual(self._files_on_disk('teacher'), [])

    def test_photo_routes_require_login(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get('/students/1/photo').status_code, 302)
        self.assertEqual(anonymous.get('/teachers/1/photo').status_code, 302)


if __name__ == '__main__':
    unittest.main()

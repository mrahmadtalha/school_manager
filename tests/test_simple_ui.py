"""Phase 5B: the simpler Inventory / Other Income / Admission pages still render."""
import os
import unittest

from werkzeug.security import generate_password_hash

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')

from app import create_app
from app.database import db
from app.models import AdminUser, ClassModel, SchoolSettings, StudentModel


class SimpleUiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(AdminUser(
                username='admin',
                password_hash=generate_password_hash('adminpass123')))
            db.session.add(SchoolSettings(school_name='Test Academy'))
            klass = ClassModel(name='Class 5')
            db.session.add(klass)
            db.session.flush()
            db.session.add(StudentModel(
                roll_number=1001, student_name='Ali Khan', father_name='Imran',
                guardian_phone='0300', address='X', class_id=klass.id))
            db.session.commit()
            self.student_id = StudentModel.query.first().id
        self.client.post('/login', data={'username': 'admin',
                                         'password': 'adminpass123'})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_inventory_has_everyday_buttons_and_tabs(self):
        page = self.client.get('/inventory')
        self.assertEqual(page.status_code, 200)
        for text in (b'Sell an item', b'Buy stock', b'New item', b'id="invTabs"',
                     b'id="recordSale"', b'id="recordPurchase"',
                     b'id="addProduct"', b'Setup checklist', b'id="studentStock"'):
            self.assertIn(text, page.data, text)
        # The supplier-dues card (and its id) only exists when something is owed.
        self.assertNotIn(b'id="supplierDues"', page.data)

    def test_other_income_page_is_simple(self):
        page = self.client.get('/other-income')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Add money received', page.data)
        self.assertIn(b'Nothing received', page.data)

    def test_admission_register_and_student_pages_render(self):
        page = self.client.get('/admission-fees?status=pending')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Still to collect', page.data)
        self.assertIn(b'/admission-fees/export/pdf?status=pending', page.data)
        student = self.client.get('/admission-fees/student/%d' % self.student_id)
        self.assertEqual(student.status_code, 200)
        self.assertIn(b'No admission fee is on record', student.data)
        self.assertIn(b'Set admission fee', student.data)


if __name__ == '__main__':
    unittest.main()

"""Phase 5: fees, receipts and duplicates for ID cards and certificates."""
import os
import unittest
from datetime import date

from werkzeug.security import generate_password_hash

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')

from app import create_app
from app.database import db
from app.models import (AdminUser, ClassModel, IssuedDocument, OtherIncome,
                        ROLE_TEACHER, SchoolSettings, StudentModel)
from app.services import document_fees


class DocumentFeesTests(unittest.TestCase):
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
                password_hash=generate_password_hash('adminpass123')))
            db.session.add(AdminUser(
                username='teach', role=ROLE_TEACHER,
                password_hash=generate_password_hash('teachpass123')))
            db.session.add(SchoolSettings(school_name='Test Academy'))
            class_obj = ClassModel(name='Class 5')
            db.session.add(class_obj)
            db.session.flush()
            db.session.add(StudentModel(
                roll_number=1001, student_name='Ali Khan',
                father_name='Imran Khan', guardian_phone='03001111111',
                address='Street 1', class_id=class_obj.id))
            db.session.commit()
            self.class_id = class_obj.id
            self.student_id = StudentModel.query.first().id
        self.client.post('/login', data={'username': 'admin',
                                         'password': 'adminpass123'})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _set_fees(self, **fees):
        data = {'id_card': '', 'id_card_dup': '', 'cert': '', 'cert_dup': ''}
        data.update(fees)
        return self.client.post('/documents/fees', data=data)

    def _issue_id_card(self, **extra):
        data = {'kind': 'id_card', 'student_id': self.student_id,
                'payment_method': 'cash'}
        data.update(extra)
        return self.client.post('/documents/issue', data=data)

    # -- nothing changes until a fee is set ------------------------------------
    def test_no_fee_set_downloads_directly_and_keeps_no_record(self):
        response = self.client.get(
            f'/documents/id-cards/students.pdf?student_id={self.student_id}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'%PDF'))
        with self.app.app_context():
            self.assertEqual(IssuedDocument.query.count(), 0)

    # -- first issue -----------------------------------------------------------
    def test_fee_set_sends_single_student_to_issue_page(self):
        self._set_fees(id_card='200')
        response = self.client.get(
            f'/documents/id-cards/students.pdf?student_id={self.student_id}')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/documents/issue', response.location)
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Rs. 200', page.data)
        self.assertIn(b'First time', page.data)

    def test_first_issue_makes_one_receipt_not_linked_to_admission(self):
        self._set_fees(id_card='200')
        response = self._issue_id_card()
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            doc = IssuedDocument.query.one()
            self.assertFalse(doc.is_duplicate)
            self.assertEqual(doc.fee_paisa, 20000)
            income = db.session.get(OtherIncome, doc.income_id)
            self.assertEqual(income.receipt_no, 'DOC-0001')
            self.assertEqual(income.amount_paisa, 20000)
            self.assertEqual(income.category.name, 'ID Cards')
            # Must never look like an admission-fee payment.
            self.assertIsNone(income.student_id)
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'DOC-0001', page.data)
        pdf = self.client.get(f'/documents/issued/{doc_id(self)}.pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b'%PDF'))

    def test_zero_fee_first_issue_is_recorded_without_receipt(self):
        # Only the duplicate has a fee, so the first print is recorded (free).
        self._set_fees(id_card='0', id_card_dup='50')
        self._issue_id_card()
        with self.app.app_context():
            doc = IssuedDocument.query.one()
            self.assertEqual(doc.fee_paisa, 0)
            self.assertIsNone(doc.income_id)
            self.assertEqual(OtherIncome.query.count(), 0)

    # -- duplicates ------------------------------------------------------------
    def test_second_issue_is_a_duplicate_and_admin_chooses_free_or_fee(self):
        self._set_fees(id_card='200', id_card_dup='100')
        self._issue_id_card()

        page = self.client.get(
            f'/documents/issue?kind=id_card&student_id={self.student_id}')
        self.assertIn(b'duplicate', page.data)
        self.assertIn(b'Rs. 100', page.data)

        self._issue_id_card(duplicate_choice='free')
        self._issue_id_card(duplicate_choice='fee')
        with self.app.app_context():
            docs = IssuedDocument.query.order_by(IssuedDocument.id).all()
            self.assertEqual([d.is_duplicate for d in docs],
                             [False, True, True])
            self.assertEqual([d.fee_paisa for d in docs], [20000, 0, 10000])
            receipts = [o.receipt_no for o in OtherIncome.query
                        .order_by(OtherIncome.id).all()]
            self.assertEqual(receipts, ['DOC-0001', 'DOC-0002'])

    def test_blank_duplicate_fee_means_same_as_first(self):
        self._set_fees(id_card='200')
        with self.app.app_context():
            self.assertEqual(document_fees.duplicate_fee_paisa('id_card'), 20000)

    # -- certificates ----------------------------------------------------------
    def test_certificate_fee_can_differ_per_type(self):
        self._set_fees(cert='300', cert_merit='0')
        with self.app.app_context():
            self.assertEqual(document_fees.first_fee_paisa('certificate', 'bonafide'), 30000)
            self.assertEqual(document_fees.first_fee_paisa('certificate', 'merit'), 0)
        response = self.client.get(
            f'/documents/certificates.pdf?cert_type=character&student_id={self.student_id}')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/documents/issue', response.location)
        self.client.post('/documents/issue', data={
            'kind': 'certificate', 'student_id': self.student_id,
            'cert_type': 'character', 'session': '2026-2027',
            'issue_date': date.today().strftime('%Y-%m-%d'),
            'payment_method': 'cash'})
        with self.app.app_context():
            doc = IssuedDocument.query.one()
            self.assertEqual(doc.cert_type, 'character')
            self.assertEqual(doc.income.category.name, 'Certificates')
        # A different certificate type is its own first issue.
        with self.app.app_context():
            student = db.session.get(StudentModel, self.student_id)
            self.assertFalse(document_fees.plan(student, 'certificate', 'bonafide')['is_duplicate'])
            self.assertTrue(document_fees.plan(student, 'certificate', 'character')['is_duplicate'])

    # -- class printing is never charged ---------------------------------------
    def test_whole_class_printing_has_no_fee_and_no_record(self):
        self._set_fees(id_card='200', cert='300')
        pdf = self.client.get(
            f'/documents/id-cards/students.pdf?class_id={self.class_id}')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b'%PDF'))
        with self.app.app_context():
            self.assertEqual(IssuedDocument.query.count(), 0)

    # -- voiding ---------------------------------------------------------------
    def test_void_removes_the_fee_and_makes_next_issue_a_first_again(self):
        self._set_fees(id_card='200')
        self._issue_id_card()
        with self.app.app_context():
            doc_pk = IssuedDocument.query.one().id
        no_reason = self.client.post(f'/documents/issued/{doc_pk}/void', data={'reason': ''})
        self.assertEqual(no_reason.status_code, 302)
        with self.app.app_context():
            self.assertFalse(IssuedDocument.query.one().is_void)
        self.client.post(f'/documents/issued/{doc_pk}/void', data={'reason': 'printed twice by mistake'})
        with self.app.app_context():
            doc = db.session.get(IssuedDocument, doc_pk)
            self.assertTrue(doc.is_void)
            self.assertTrue(doc.income.is_void)
            student = db.session.get(StudentModel, self.student_id)
            self.assertFalse(document_fees.plan(student, 'id_card')['is_duplicate'])
        self._issue_id_card()
        with self.app.app_context():
            self.assertEqual(IssuedDocument.query.filter_by(is_void=False).one().is_duplicate, False)

    # -- settings --------------------------------------------------------------
    def test_bad_fee_values_are_refused_and_nothing_is_saved(self):
        self._set_fees(id_card='200')
        self._set_fees(id_card='-5')
        self._set_fees(id_card='abc')
        with self.app.app_context():
            self.assertEqual(document_fees.first_fee_paisa('id_card'), 20000)

    def test_documents_page_shows_fee_box_to_admin(self):
        page = self.client.get('/documents')
        self.assertIn(b'Fees for ID cards', page.data)

    def test_teacher_cannot_issue_and_is_sent_back_when_a_fee_applies(self):
        self._set_fees(id_card='200')
        teacher = self.app.test_client()
        teacher.post('/login', data={'username': 'teach', 'password': 'teachpass123'})
        response = teacher.get(
            f'/documents/id-cards/students.pdf?student_id={self.student_id}')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/documents', response.location)
        self.assertNotIn('/documents/issue', response.location)
        self.assertEqual(teacher.post('/documents/fees', data={'id_card': '1'}).status_code, 403)
        self.assertEqual(teacher.get(
            f'/documents/issue?kind=id_card&student_id={self.student_id}').status_code, 403)
        with self.app.app_context():
            self.assertEqual(IssuedDocument.query.count(), 0)


def doc_id(case):
    with case.app.app_context():
        return IssuedDocument.query.order_by(IssuedDocument.id).first().id


if __name__ == '__main__':
    unittest.main()

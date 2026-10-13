"""Admission fee: settings, Add Student form, receipts, concessions, register,
roles, financial integration and the upgrade of an already-running database."""
import csv
import io
import sqlite3
from datetime import date, timedelta

import pytest
from flask import g

from app.database import db
from app.models import (AdminUser, ClassModel, OtherIncome, OtherIncomeCategory,
                        ROLE_ACCOUNTANT, ROLE_OWNER, StudentModel)
from app.services import admission_fee as adm
from app.services import other_income_service
from app.services.financial_summary import month_snapshot
from app.services.payroll_service import current_month_key
from tests.conftest import ADMIN_PASSWORD, TEACHER_PASSWORD, login


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class _RoleClient:
    """A test client for one logged-in user.

    The ``app`` fixture keeps a single app context open, so Flask-Login would
    cache the first request's user in ``g`` for every later request.  Dropping
    that cache before each call lets several roles be used in one test.
    """

    def __init__(self, client):
        self._client = client

    def _call(self, method, *args, **kwargs):
        g.pop('_login_user', None)
        return getattr(self._client, method)(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._call('get', *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._call('post', *args, **kwargs)


def _login_client(app, username, password):
    client = app.test_client()
    g.pop('_login_user', None)
    login(client, username, password)
    return _RoleClient(client)


def _user_client(app, username, role, password='Passw0rd123'):
    user = AdminUser(username=username, role=role, full_name=username.title())
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return _login_client(app, username, password)


# Own clients (not conftest's shared one) so several roles can be used in one test.
@pytest.fixture()
def admin_client(app):
    return _login_client(app, 'admin', ADMIN_PASSWORD)


@pytest.fixture()
def teacher_client(app):
    return _login_client(app, 'teacher', TEACHER_PASSWORD)


@pytest.fixture()
def accountant_client(app):
    return _user_client(app, 'acct', ROLE_ACCOUNTANT)


@pytest.fixture()
def owner_client(app):
    return _user_client(app, 'owner', ROLE_OWNER)


def _enable(default=5000, overrides=None):
    """Switch the feature on (school fee and optional per-class fees)."""
    adm.save_settings(str(default) if default is not None else '',
                      {cid: str(v) for cid, v in (overrides or {}).items()})
    db.session.commit()


def _add_student(client, seed, roll, name='New Kid', **extra):
    data = {'roll_number': str(roll), 'student_name': name, 'father_name': 'Father',
            'guardian_phone': '03001112222', 'address': 'Street',
            'class_id': str(seed['class_id']), 'monthly_fee': '2000'}
    data.update(extra)
    return client.post('/students/add', data=data, follow_redirects=False)


def _student(roll):
    return StudentModel.query.filter_by(roll_number=roll).one()


def _admission_income():
    return OtherIncome.query.filter(OtherIncome.student_id.isnot(None)).all()


# --------------------------------------------------------------------------- #
# Concession maths
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('standard, kind, value, net, concession', [
    (500000, None, None, 500000, 0),
    (500000, 'none', 10, 500000, 0),
    (500000, 'percentage', 25, 375000, 125000),
    (500000, 'percentage', 0, 500000, 0),
    (333300, 'percentage', 10, 299970, 33330),
    (500000, 'fixed', 1500, 350000, 150000),
    (500000, 'fixed', 5000, 0, 500000),
    (500000, 'waived', None, 0, 500000),
])
def test_compute_net(standard, kind, value, net, concession):
    assert adm.compute_net(standard, kind, value) == (net, concession)


@pytest.mark.parametrize('kind, value', [('percentage', 101), ('fixed', 5001),
                                         ('mystery', 5)])
def test_compute_net_rejects_bad_input(kind, value):
    with pytest.raises(ValueError):
        adm.compute_net(500000, kind, value)


# --------------------------------------------------------------------------- #
# Settings: universal fee + per class
# --------------------------------------------------------------------------- #

def test_feature_is_off_until_a_fee_is_set(app, seed):
    assert adm.is_enabled() is False
    _enable(None, {seed['class_id']: 0})
    assert adm.is_enabled() is False          # zero everywhere = still off
    _enable(default=3000)
    assert adm.is_enabled() is True


def test_class_fee_overrides_and_zero_means_free(app, seed):
    second = ClassModel(name='Class 2')
    free = ClassModel(name='Nursery')
    db.session.add_all([second, free])
    db.session.commit()
    _enable(5000, {second.id: 7000, free.id: 0, seed['class_id']: ''})
    assert adm.effective_paisa(seed['class_id']) == 500000     # follows school fee
    assert adm.effective_paisa(second.id) == 700000
    assert adm.effective_paisa(free.id) == 0
    assert adm.fee_by_class()[str(second.id)] == 7000.0


def test_settings_are_admin_only(admin_client, teacher_client, accountant_client, app, seed):
    data = {'default_admission_fee': '4500', 'class_%d' % seed['class_id']: '6000'}
    for denied in (teacher_client, accountant_client):
        assert denied.post('/fees/admission-settings', data=data).status_code == 403
    assert adm.is_enabled() is False
    response = admin_client.post('/fees/admission-settings', data=data)
    assert response.status_code == 302
    assert adm.default_paisa() == 450000
    assert adm.effective_paisa(seed['class_id']) == 600000


def test_settings_reject_bad_values_and_leave_existing_students_alone(admin_client, app, seed):
    ali = StudentModel.query.filter_by(roll_number=1001).one()
    bad = admin_client.post('/fees/admission-settings',
                            data={'default_admission_fee': '-5'}, follow_redirects=True)
    assert b'cannot be negative' in bad.data
    assert adm.default_paisa() == 0
    admin_client.post('/fees/admission-settings', data={'default_admission_fee': '5000'})
    assert db.session.get(StudentModel, ali.id).admission_fee_net_paisa is None


def test_fees_page_shows_settings_only_to_admin(admin_client, accountant_client, app):
    assert b'Admission Fee Settings' in admin_client.get('/fees').data
    page = accountant_client.get('/fees').data
    assert b'Admission Fees' in page and b'Admission Fee Settings' not in page


# --------------------------------------------------------------------------- #
# Add Student form
# --------------------------------------------------------------------------- #

def test_nothing_changes_while_the_feature_is_off(admin_client, app, seed):
    assert b'Admission Fee (PKR)' not in admin_client.get('/students').data
    assert _add_student(admin_client, seed, 2001).status_code == 302
    student = _student(2001)
    assert student.admission_fee_net_paisa is None
    assert adm.status_for(student) == 'not_applicable'
    assert OtherIncome.query.count() == 0


def test_form_prefills_from_class_settings(admin_client, app, seed):
    _enable(5000, {seed['class_id']: 6500})
    page = admin_client.get('/students').data
    assert b'name="admission_fee"' in page and b'name="admission_received_now"' in page
    assert b'var admissionFeeByClass = {"%d": 6500.0}' % seed['class_id'] in page


def test_admin_adds_student_and_takes_the_fee_now(admin_client, app, seed):
    _enable(5000)
    response = _add_student(admin_client, seed, 2002, admission_received_now='1',
                            admission_received_amount='5000', admission_method='bank')
    assert response.status_code == 302
    student = _student(2002)
    assert student.admission_fee_net_paisa == 500000
    assert student.admission_fee_date == date.today()
    (income,) = _admission_income()
    assert income.student_id == student.id and income.amount_paisa == 500000
    assert income.receipt_no == 'ADM-0001' and income.payment_method == 'bank'
    assert income.category.name == 'Admission Fee'
    assert adm.status_for(student) == 'paid'

    page = admin_client.get('/students').data              # receipt link shown once
    assert b'ADM-0001' in page and b'Print receipt' in page
    assert b'Print receipt' not in admin_client.get('/students').data


def test_admin_can_edit_the_amount_give_a_concession_and_part_pay(admin_client, app, seed):
    _enable(5000)
    _add_student(admin_client, seed, 2003, admission_fee='6000',
                 admission_discount_type='percentage', admission_discount_value='25',
                 admission_note='Sibling', admission_received_now='1',
                 admission_received_amount='1000')
    student = _student(2003)
    assert (student.admission_fee_standard_paisa, student.admission_fee_net_paisa) == (600000, 450000)
    assert student.admission_discount_type == 'percentage'
    assert student.admission_note == 'Sibling'
    info = adm.summary(student)
    assert info['received'] == 100000 and info['balance'] == 350000
    assert info['status'] == 'partial' and info['concession'] == 150000


def test_reason_for_a_concession_is_optional(admin_client, app, seed):
    _enable(5000)
    _add_student(admin_client, seed, 2004, admission_discount_type='fixed',
                 admission_discount_value='500')
    student = _student(2004)
    assert student.admission_fee_net_paisa == 450000 and student.admission_note is None


def test_full_waiver_creates_no_income(admin_client, app, seed):
    _enable(5000)
    _add_student(admin_client, seed, 2005, admission_discount_type='waived',
                 admission_received_now='1')
    student = _student(2005)
    assert student.admission_fee_net_paisa == 0
    assert adm.status_for(student) == 'waived'
    assert OtherIncome.query.count() == 0


def test_not_received_now_stays_pending(admin_client, app, seed):
    _enable(5000)
    _add_student(admin_client, seed, 2006)                  # checkbox left unticked
    student = _student(2006)
    assert adm.status_for(student) == 'pending'
    assert OtherIncome.query.count() == 0


def test_blank_amount_uses_the_class_fee(admin_client, app, seed):
    _enable(5000, {seed['class_id']: 8000})
    _add_student(admin_client, seed, 2007, admission_fee='')
    assert _student(2007).admission_fee_standard_paisa == 800000


def test_class_with_no_admission_fee_creates_nothing(admin_client, app, seed):
    _enable(5000, {seed['class_id']: 0})
    _add_student(admin_client, seed, 2008)
    assert _student(2008).admission_fee_net_paisa is None


def test_teacher_student_gets_a_pending_standard_fee_only(teacher_client, app, seed):
    _enable(5000)
    response = _add_student(teacher_client, seed, 2009, admission_fee='1',
                            admission_discount_type='waived', admission_received_now='1',
                            admission_received_amount='5000')
    assert response.status_code == 302
    student = _student(2009)
    assert student.admission_fee_standard_paisa == 500000     # forged values ignored
    assert student.admission_fee_net_paisa == 500000
    assert student.admission_discount_type is None
    assert OtherIncome.query.count() == 0
    assert adm.status_for(student) == 'pending'
    assert b'Admission Fee (PKR)' not in teacher_client.get('/students').data


def test_bad_admission_input_saves_nothing(admin_client, app, seed):
    _enable(5000)
    _add_student(admin_client, seed, 2010, admission_fee='-1')
    assert StudentModel.query.filter_by(roll_number=2010).first() is None
    _add_student(admin_client, seed, 2011, admission_discount_type='percentage',
                 admission_discount_value='150')
    assert StudentModel.query.filter_by(roll_number=2011).first() is None
    _add_student(admin_client, seed, 2012, admission_received_now='1',
                 admission_received_amount='999999')
    assert StudentModel.query.filter_by(roll_number=2012).first() is None
    assert OtherIncome.query.count() == 0


def test_roll_conflict_preview_keeps_the_admission_fields(admin_client, app, seed):
    _enable(5000)
    form = {'roll_number': '1001', 'student_name': 'Late Joiner', 'father_name': 'Dad',
            'guardian_phone': '03001112222', 'address': 'Street',
            'class_id': str(seed['class_id']), 'monthly_fee': '2000',
            'admission_fee': '5500', 'admission_discount_type': 'fixed',
            'admission_discount_value': '500', 'admission_received_now': '1',
            'admission_received_amount': '5000'}
    preview = admin_client.post('/students/add', data=form)
    assert preview.status_code == 200
    for name in ('admission_fee', 'admission_discount_type', 'admission_received_now'):
        assert ('name="%s"' % name).encode() in preview.data
    confirmed = admin_client.post('/students/add', data=dict(form, confirm_cascade='1'))
    assert confirmed.status_code == 302
    student = StudentModel.query.filter_by(student_name='Late Joiner').one()
    assert student.admission_fee_net_paisa == 500000
    assert adm.received_paisa(student.id) == 500000


# --------------------------------------------------------------------------- #
# Receiving, receipts, voiding
# --------------------------------------------------------------------------- #

def _with_terms(seed, roll=1001, standard=5000, **terms):
    student = StudentModel.query.filter_by(roll_number=roll).one()
    adm.apply_terms(student, standard, **terms)
    db.session.commit()
    return student


def test_instalments_close_the_balance_and_get_sequential_receipts(admin_client, app, seed):
    student = _with_terms(seed)
    first = admin_client.post('/admission-fees/student/%d/receive' % student.id,
                              data={'amount': '2000', 'method': 'cash'})
    assert first.status_code == 302 and '/admission-fees/receipt/' in first.headers['Location']
    admin_client.post('/admission-fees/student/%d/receive' % student.id,
                      data={'amount': '3000', 'method': 'online'})
    receipts = [r.receipt_no for r in adm.active_payments(student.id)]
    assert receipts == ['ADM-0001', 'ADM-0002']
    assert adm.status_for(student) == 'paid'
    assert adm.summary(student)['balance'] == 0


def test_receive_validation(admin_client, app, seed):
    student = _with_terms(seed)
    url = '/admission-fees/student/%d/receive' % student.id
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for data, message in (
            ({'amount': '0'}, b'greater than zero'),
            ({'amount': '5000.01'}, b'more than the balance'),
            ({'amount': '100', 'payment_date': tomorrow}, b'cannot be in the future'),
            ({'amount': 'abc'}, b'greater than zero')):
        body = admin_client.post(url, data=data, follow_redirects=True).data
        assert message in body, data
    assert OtherIncome.query.count() == 0
    admin_client.post(url, data={'amount': '5000'})
    again = admin_client.post(url, data={'amount': '1'}, follow_redirects=True)
    assert b'already fully received' in again.data


def test_student_without_terms_cannot_receive(admin_client, app, seed):
    ali = StudentModel.query.filter_by(roll_number=1001).one()
    body = admin_client.post('/admission-fees/student/%d/receive' % ali.id,
                             data={'amount': '100'}, follow_redirects=True).data
    assert b'No admission fee is set' in body


def test_receipt_page_shows_the_numbers(admin_client, app, seed):
    student = _with_terms(seed, discount_type='percentage', discount_value=20,
                          note='Staff child')
    admin_client.post('/admission-fees/student/%d/receive' % student.id,
                      data={'amount': '1500', 'method': 'cash'})
    row = _admission_income()[0]
    body = admin_client.get('/admission-fees/receipt/%d' % row.id).data
    for text in (b'ADMISSION FEE RECEIPT', b'ADM-0001', b'Ali Khan', b'Rs. 5,000',
                 b'Rs. 4,000', b'Rs. 2,500', b'Staff child', b'Rupees Only',
                 b'PART PAID'):
        assert text in body, text


def test_reprinted_old_receipt_shows_the_balance_of_that_day(admin_client, app, seed):
    student = _with_terms(seed)
    url = '/admission-fees/student/%d/receive' % student.id
    admin_client.post(url, data={'amount': '2000'})
    admin_client.post(url, data={'amount': '3000'})
    first, second = adm.active_payments(student.id)
    assert b'Rs. 3,000' in admin_client.get('/admission-fees/receipt/%d' % first.id).data
    assert b'PAID' in admin_client.get('/admission-fees/receipt/%d' % second.id).data


def test_receipt_of_non_admission_income_is_404(admin_client, app):
    other_income_service.seed_default_categories()
    category = OtherIncomeCategory.query.first()
    row = other_income_service.record_income(category, 100, date.today())
    db.session.commit()
    assert admin_client.get('/admission-fees/receipt/%d' % row.id).status_code == 404


def test_void_needs_a_reason_and_reopens_the_balance(admin_client, accountant_client, app, seed):
    student = _with_terms(seed)
    admin_client.post('/admission-fees/student/%d/receive' % student.id,
                      data={'amount': '5000'})
    row = _admission_income()[0]
    url = '/admission-fees/receipt/%d/void' % row.id
    refused = accountant_client.post(url, data={'reason': ' '}, follow_redirects=True)
    assert b'reason is required' in refused.data
    assert adm.status_for(student) == 'paid'
    accountant_client.post(url, data={'reason': 'Entered twice'})
    assert db.session.get(OtherIncome, row.id).is_void is True
    assert adm.status_for(student) == 'pending'
    assert b'VOID' in admin_client.get('/admission-fees/receipt/%d' % row.id).data
    # the receipt number is never reused
    admin_client.post('/admission-fees/student/%d/receive' % student.id, data={'amount': '5000'})
    assert sorted(r.receipt_no for r in _admission_income()) == ['ADM-0001', 'ADM-0002']


def test_voiding_in_other_income_also_reopens_the_balance(admin_client, app, seed):
    student = _with_terms(seed)
    admin_client.post('/admission-fees/student/%d/receive' % student.id, data={'amount': '5000'})
    row = _admission_income()[0]
    admin_client.post('/other-income/%d/void' % row.id, data={'reason': 'wrong child'})
    assert adm.status_for(student) == 'pending'


# --------------------------------------------------------------------------- #
# Changing terms / concessions
# --------------------------------------------------------------------------- #

def test_only_admin_can_change_terms(admin_client, accountant_client, owner_client, app, seed):
    student = _with_terms(seed)
    url = '/admission-fees/student/%d/terms' % student.id
    for denied in (accountant_client, owner_client):
        assert denied.post(url, data={'admission_fee': '1'}).status_code == 403
    admin_client.post(url, data={'admission_fee': '5000', 'admission_discount_type': 'percentage',
                                 'admission_discount_value': '50', 'admission_note': 'Hardship'})
    student = db.session.get(StudentModel, student.id)
    assert student.admission_fee_net_paisa == 250000
    assert student.admission_note == 'Hardship'


def test_terms_cannot_drop_below_what_was_received(admin_client, app, seed):
    student = _with_terms(seed)
    admin_client.post('/admission-fees/student/%d/receive' % student.id, data={'amount': '3000'})
    url = '/admission-fees/student/%d/terms' % student.id
    body = admin_client.post(url, data={'admission_fee': '5000', 'admission_discount_type': 'waived'},
                             follow_redirects=True).data
    assert b'already received' in body
    assert db.session.get(StudentModel, student.id).admission_fee_net_paisa == 500000
    admin_client.post(url, data={'admission_fee': '3000'})
    assert db.session.get(StudentModel, student.id).admission_fee_net_paisa == 300000


def test_admin_can_set_a_fee_for_a_student_admitted_before_the_feature(admin_client, app, seed):
    ali = StudentModel.query.filter_by(roll_number=1001).one()
    assert adm.status_for(ali) == 'not_applicable'
    admin_client.post('/admission-fees/student/%d/terms' % ali.id, data={'admission_fee': '2500'})
    assert adm.status_for(db.session.get(StudentModel, ali.id)) == 'pending'
    admin_client.post('/admission-fees/student/%d/terms' % ali.id, data={'admission_fee': '0'})
    assert adm.status_for(db.session.get(StudentModel, ali.id)) == 'not_applicable'


def test_changes_are_audited(admin_client, app, seed):
    from app.models.audit import AuditLog
    student = _with_terms(seed)
    admin_client.post('/admission-fees/student/%d/receive' % student.id, data={'amount': '1000'})
    admin_client.post('/admission-fees/student/%d/terms' % student.id,
                      data={'admission_fee': '5000', 'admission_discount_type': 'fixed',
                            'admission_discount_value': '500'})
    logs = AuditLog.query.filter_by(entity_type='AdmissionFee').all()
    assert {row.action for row in logs} >= {'payment', 'update'}


# --------------------------------------------------------------------------- #
# Register and roles
# --------------------------------------------------------------------------- #

def _register_fixture(seed):
    ali = _with_terms(seed, 1001, 5000)                                  # paid
    adm.receive_payment(ali, 5000)
    sara = _with_terms(seed, 1002, 5000, discount_type='percentage', discount_value=20)
    adm.receive_payment(sara, 1000)                                      # partial
    other_class = ClassModel(name='Class 2')
    db.session.add(other_class)
    db.session.flush()
    for roll, name, kind in ((3001, 'Waived Kid', 'waived'), (3002, 'Pending Kid', None)):
        student = StudentModel(roll_number=roll, student_name=name, father_name='F',
                               guardian_phone='0300', address='A', class_id=other_class.id,
                               monthly_fee=1000)
        db.session.add(student)
        db.session.flush()
        adm.apply_terms(student, 5000, discount_type=kind)
    db.session.commit()
    return other_class


def test_register_totals_filters_and_exclusions(admin_client, app, seed):
    other_class = _register_fixture(seed)
    rows, totals = adm.register()
    assert totals['count'] == 4
    assert totals['net'] == 1400000 and totals['received'] == 600000
    assert totals['balance'] == 800000 and totals['concession'] == 600000
    assert totals['by_status'] == {'pending': 1, 'partial': 1, 'paid': 1, 'waived': 1}
    assert [r['student'].student_name for r in adm.register(status='partial')[0]] == ['Sara Ali']
    assert len(adm.register(class_id=other_class.id)[0]) == 2
    assert [r['student'].student_name for r in adm.register(search='waived')[0]] == ['Waived Kid']
    body = admin_client.get('/admission-fees?status=pending').data
    assert b'Pending Kid' in body and b'Waived Kid' not in body


def test_register_leaves_out_students_without_terms_and_voided_money(admin_client, app, seed):
    student = _with_terms(seed, 1001, 5000)
    adm.receive_payment(student, 5000)
    db.session.commit()
    _, totals = adm.register()
    assert totals['count'] == 1                 # Sara has no terms, so she is not listed
    adm.void_payment(adm.active_payments(student.id)[0], 'mistake')
    db.session.commit()
    assert adm.register()[1]['received'] == 0


def test_roles(admin_client, teacher_client, accountant_client, owner_client, app, seed):
    student = _with_terms(seed)
    adm.receive_payment(student, 1000)
    db.session.commit()
    row_id = _admission_income()[0].id
    read_only = ['/admission-fees', '/admission-fees/student/%d' % student.id,
                 '/admission-fees/receipt/%d' % row_id]
    for client in (admin_client, accountant_client, owner_client):
        for url in read_only:
            assert client.get(url).status_code == 200, url
    for url in read_only:
        assert teacher_client.get(url).status_code == 403
    receive = '/admission-fees/student/%d/receive' % student.id
    assert owner_client.post(receive, data={'amount': '10'}).status_code == 403
    assert teacher_client.post(receive, data={'amount': '10'}).status_code == 403
    assert accountant_client.post(receive, data={'amount': '10'}).status_code == 302
    owner_page = owner_client.get('/admission-fees/student/%d' % student.id).data
    assert b'Receive payment' not in owner_page and b'Save terms' not in owner_page
    accountant_page = accountant_client.get('/admission-fees/student/%d' % student.id).data
    assert b'Receive payment' in accountant_page and b'Save terms' not in accountant_page


def test_student_page_for_a_student_without_terms(admin_client, app, seed):
    ali = StudentModel.query.filter_by(roll_number=1001).one()
    body = admin_client.get('/admission-fees/student/%d' % ali.id).data
    assert b'No admission fee is on record' in body and b'Set admission fee' in body


# --------------------------------------------------------------------------- #
# Money shows up where earnings show up
# --------------------------------------------------------------------------- #

def test_admission_money_counts_in_cash_in_and_leaves_with_a_void(admin_client, app, seed):
    month = current_month_key()
    before = month_snapshot(month)
    student = _with_terms(seed)
    adm.receive_payment(student, 5000)
    db.session.commit()
    after = month_snapshot(month)
    assert after['other_income'] == before['other_income'] + 5000
    assert after['cash_in'] == before['cash_in'] + 5000
    assert after['fee_income'] == before['fee_income']          # monthly fees unchanged
    assert after['fees_remaining'] == before['fees_remaining']  # not a monthly-fee dues
    adm.void_payment(adm.active_payments(student.id)[0], 'mistake')
    db.session.commit()
    assert month_snapshot(month)['cash_in'] == before['cash_in']


def test_admission_receipts_are_listed_in_other_income(admin_client, app, seed):
    student = _with_terms(seed)
    adm.receive_payment(student, 1200)
    db.session.commit()
    body = admin_client.get('/other-income').data
    assert b'Admission Fee' in body and b'Ali Khan' in body


# --------------------------------------------------------------------------- #
# Upgrading a database that is already in use
# --------------------------------------------------------------------------- #

NEW_COLUMNS = {
    'students': ['admission_fee_standard_paisa', 'admission_fee_net_paisa',
                 'admission_discount_type', 'admission_discount_value',
                 'admission_note', 'admission_fee_date', 'admission_fee_prior_paid_paisa'],
    'classes': ['admission_fee'],
    'school_settings': ['default_admission_fee'],
}
OTHER_INCOME_OLD = ('id, category_id, income_date, amount_paisa, description, is_void, '
                    'void_reason, voided_at, voided_by_name, created_by_id, created_by_name, '
                    'created_at, updated_by_id, updated_by_name, updated_at')


def _make_old_database(factory, tmp_path):
    """A school database as it was before this feature, holding real data."""
    first = factory(tmp_path, 'school.db')
    with first.app_context():
        school_class = ClassModel(name='Class 5')
        db.session.add(school_class)
        db.session.flush()
        for roll in (1, 2, 3):
            db.session.add(StudentModel(roll_number=roll, student_name='Old %d' % roll,
                                        father_name='F', guardian_phone='0300', address='A',
                                        class_id=school_class.id, monthly_fee=2000))
        other_income_service.seed_default_categories()
        other_income_service.record_income(OtherIncomeCategory.query.first(), 750, date.today())
        db.session.commit()
        snapshot = month_snapshot(current_month_key())
        db.session.remove()
        db.engine.dispose()
    connection = sqlite3.connect(tmp_path / 'school.db')
    for table, columns in NEW_COLUMNS.items():
        for column in columns:
            connection.execute('ALTER TABLE %s DROP COLUMN %s' % (table, column))
    connection.execute('CREATE TABLE oi_old AS SELECT %s FROM other_income' % OTHER_INCOME_OLD)
    connection.execute('DROP TABLE other_income')
    connection.execute('ALTER TABLE oi_old RENAME TO other_income')
    connection.commit()
    connection.close()
    return snapshot


def _columns(path, table):
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute('PRAGMA table_info(%s)' % table)}
    finally:
        connection.close()


def test_upgrade_keeps_data_and_numbers_and_takes_a_safety_backup(fresh_app_factory, tmp_path):
    before = _make_old_database(fresh_app_factory, tmp_path)
    path = tmp_path / 'school.db'
    assert 'student_id' not in _columns(path, 'other_income')
    assert 'admission_fee_net_paisa' not in _columns(path, 'students')

    upgraded = fresh_app_factory(tmp_path, 'school.db', override={'PRE_MIGRATION_BACKUP': True})
    with upgraded.app_context():
        for table, columns in NEW_COLUMNS.items():
            assert set(columns) <= _columns(path, table), table
        assert {'student_id', 'receipt_no', 'payment_method'} <= _columns(path, 'other_income')

        students = StudentModel.query.all()
        assert len(students) == 3
        assert all(adm.status_for(s) == 'not_applicable' for s in students)
        assert adm.register()[1]['count'] == 0                     # nobody is "pending"
        assert adm.is_enabled() is False                           # feature stays off

        after = month_snapshot(current_month_key())
        for key in ('cash_in', 'fee_income', 'other_income', 'expenses', 'net',
                    'fees_remaining'):
            assert after[key] == before[key], key
        (old_row,) = OtherIncome.query.all()
        assert old_row.amount_paisa == 75000 and old_row.student_id is None

    backups = list((tmp_path / 'backups').glob('*-before-admission-fee.db'))
    assert len(backups) == 1
    copy = sqlite3.connect(backups[0])
    try:                                                           # the copy is the OLD schema
        assert copy.execute('SELECT COUNT(*) FROM students').fetchone()[0] == 3
        assert 'admission_fee_net_paisa' not in {r[1] for r in copy.execute('PRAGMA table_info(students)')}
    finally:
        copy.close()


def test_second_start_is_a_no_op(fresh_app_factory, tmp_path):
    _make_old_database(fresh_app_factory, tmp_path)
    flag = {'PRE_MIGRATION_BACKUP': True}
    fresh_app_factory(tmp_path, 'school.db', override=flag)
    fresh_app_factory(tmp_path, 'school.db', override=flag)
    assert len(list((tmp_path / 'backups').glob('*-before-admission-fee.db'))) == 1


def test_brand_new_database_needs_no_backup(fresh_app_factory, tmp_path):
    fresh_app_factory(tmp_path, 'brand-new.db', override={'PRE_MIGRATION_BACKUP': True})
    assert not (tmp_path / 'backups').exists()


# =========================================================================== #
# Phase 2: import / export, opening amounts, register export, finance lines
# =========================================================================== #

IMPORT_HEADERS = ['Student Name', 'Father Name', 'Class', 'Guardian Phone', 'Address',
                  'Admission Fee', 'Admission Concession Type', 'Admission Concession Value',
                  'Admission Fee Paid']


def _csv_upload(rows, headers=IMPORT_HEADERS):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return (io.BytesIO(buffer.getvalue().encode('utf-8')), 'students.csv')


def _import(client, rows, headers=IMPORT_HEADERS, **form):
    data = dict(form, import_file=_csv_upload(rows, headers))
    return client.post('/students/import', data=data, content_type='multipart/form-data')


def _row(name, fee='', kind='', value='', paid=''):
    return [name, 'Father of ' + name, 'Class 1', '03001112222', 'Street', fee, kind, value, paid]


def _by_name(name):
    return StudentModel.query.filter_by(student_name=name).one()


# ---- opening amounts (imported "already paid", never income) --------------- #

def test_opening_amount_counts_toward_the_balance_but_not_income(app, seed):
    month = current_month_key()
    before = month_snapshot(month)
    student = StudentModel.query.filter_by(roll_number=1001).one()
    adm.apply_on_import(student, 5000, None, None, 3000, False, date.today(), None)
    db.session.commit()
    info = adm.summary(student)
    assert info['received'] == 300000 and info['prior_paid'] == 300000
    assert info['balance'] == 200000 and info['status'] == 'partial'
    assert OtherIncome.query.count() == 0                       # no income row at all
    after = month_snapshot(month)
    assert after['cash_in'] == before['cash_in'] and after['admission_fees'] == 0
    adm.receive_payment(student, 2000)                          # settle the rest
    assert adm.status_for(student) == 'paid'
    _, totals = adm.register()
    assert totals['received'] == 500000 and totals['prior'] == 300000


def test_opening_amount_cannot_be_undercut(admin_client, app, seed):
    student = StudentModel.query.filter_by(roll_number=1001).one()
    adm.apply_on_import(student, 5000, None, None, 4000, False, date.today(), None)
    db.session.commit()
    body = admin_client.post('/admission-fees/student/%d/terms' % student.id,
                             data={'admission_fee': '3000'}, follow_redirects=True).data
    assert b'already received' in body
    with pytest.raises(ValueError):
        adm.receive_payment(student, 1500)                      # more than the 1,000 left


def test_receipt_includes_the_opening_amount(admin_client, app, seed):
    student = StudentModel.query.filter_by(roll_number=1001).one()
    adm.apply_on_import(student, 5000, None, None, 3000, False, date.today(), None)
    db.session.commit()
    admin_client.post('/admission-fees/student/%d/receive' % student.id, data={'amount': '1000'})
    row = _admission_income()[0]
    body = admin_client.get('/admission-fees/receipt/%d' % row.id).data
    assert b'Rs. 4,000' in body and b'PART PAID' in body        # 3,000 opening + 1,000 now
    page = admin_client.get('/admission-fees/student/%d' % student.id).data
    assert b'opening amount' in page


def test_paid_as_income_creates_a_dated_receipt(app, seed):
    student = StudentModel.query.filter_by(roll_number=1001).one()
    when = date.today() - timedelta(days=3)
    adm.apply_on_import(student, 5000, None, None, 5000, True, when, None)
    db.session.commit()
    (income,) = _admission_income()
    assert income.income_date == when and income.receipt_no == 'ADM-0001'
    assert student.admission_fee_prior_paid_paisa is None
    assert adm.status_for(student) == 'paid'


def test_paid_more_than_the_agreed_fee_is_refused(app, seed):
    student = StudentModel.query.filter_by(roll_number=1001).one()
    with pytest.raises(ValueError):
        adm.apply_on_import(student, 5000, 'percentage', 50, 3000, False, date.today(), None)


# ---- import ------------------------------------------------------------------ #

def test_import_template_offers_admission_columns_only_when_useful(admin_client, teacher_client, app):
    from openpyxl import load_workbook

    def headers(client):
        response = client.get('/students/template/excel')
        assert response.status_code == 200
        sheet = load_workbook(io.BytesIO(response.data)).worksheets[0]
        return [str(cell.value) for cell in sheet[1] if cell.value]

    assert not any('Admission Fee' in h for h in headers(admin_client))     # feature off
    _enable(5000)
    wanted = ('Admission Fee', 'Admission Concession Type', 'Admission Concession Value',
              'Admission Fee Paid')
    shown = headers(admin_client)
    assert all(any(h.startswith(w) for h in shown) for w in wanted)
    assert not any('Admission Fee Paid' in h for h in headers(teacher_client))  # admin only


def test_import_records_terms_and_keeps_paid_as_an_opening_amount(admin_client, app, seed):
    _enable(5000)
    response = _import(admin_client, [
        _row('Import A', fee='5000', paid='5000'),
        _row('Import B', fee='6000', kind='percentage', value='50', paid='1000'),
        _row('Import C', fee='4000', kind='waived'),
        _row('Import D'),
    ])
    assert response.status_code == 200
    a, b, c, d = (_by_name(n) for n in ('Import A', 'Import B', 'Import C', 'Import D'))
    assert (adm.status_for(a), adm.summary(a)['prior_paid']) == ('paid', 500000)
    assert (adm.status_for(b), b.admission_fee_net_paisa) == ('partial', 300000)
    assert adm.status_for(c) == 'waived'
    assert adm.status_for(d) == 'not_applicable'              # no default fee on import
    assert OtherIncome.query.count() == 0                      # nothing became income


def test_import_can_also_record_the_paid_amount_as_income(admin_client, app, seed):
    _enable(5000)
    when = (date.today() - timedelta(days=2)).isoformat()
    _import(admin_client, [_row('Income A', fee='5000', paid='2500')],
            admission_paid_as_income='1', admission_income_date=when)
    student = _by_name('Income A')
    (income,) = _admission_income()
    assert income.amount_paisa == 250000 and income.income_date.isoformat() == when
    assert income.student_id == student.id and income.receipt_no == 'ADM-0001'
    assert student.admission_fee_prior_paid_paisa is None


def test_import_rejects_a_future_income_date(admin_client, app, seed):
    _enable(5000)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    _import(admin_client, [_row('Future', fee='5000', paid='100')],
            admission_paid_as_income='1', admission_income_date=tomorrow)
    assert StudentModel.query.filter_by(student_name='Future').first() is None


def test_import_skips_bad_admission_rows_with_a_reason(admin_client, app, seed):
    _enable(5000)
    response = _import(admin_client, [
        _row('Bad A', kind='fixed', value='100'),                       # concession, no fee
        _row('Bad B', fee='5000', kind='percentage', value='150'),      # > 100 %
        _row('Bad C', fee='5000', kind='percentage', value='50', paid='4000'),   # paid > net
        _row('Bad D', fee='5000', kind='mystery'),                      # unknown type
        _row('Good', fee='5000'),
    ])
    body = response.data.decode()
    assert StudentModel.query.filter_by(student_name='Good').count() == 1
    for name in ('Bad A', 'Bad B', 'Bad C', 'Bad D'):
        assert StudentModel.query.filter_by(student_name=name).first() is None, name
    assert 'Admission Fee is required' in body
    assert 'more than the agreed admission fee' in body


def test_import_ignores_admission_columns_when_the_feature_is_off(admin_client, app, seed):
    response = _import(admin_client, [_row('Plain', fee='5000', paid='5000')])
    assert response.status_code == 200
    assert adm.status_for(_by_name('Plain')) == 'not_applicable'
    assert b'Admission Fee' in response.data                    # listed as an ignored column


def test_teacher_import_never_records_admission_money(teacher_client, app, seed):
    _enable(5000)
    _import(teacher_client, [_row('By Teacher', fee='5000', paid='5000')])
    student = _by_name('By Teacher')
    assert adm.status_for(student) == 'not_applicable'
    assert OtherIncome.query.count() == 0


# ---- student list / export columns ------------------------------------------ #

def test_student_export_has_admission_columns(admin_client, app, seed):
    ali = _with_terms(seed, 1001, 5000)
    adm.receive_payment(ali, 2000)
    db.session.commit()
    body = admin_client.get('/students/export/csv?cols=student_name,admission_fee,'
                            'admission_received,admission_balance,admission_status').data.decode()
    rows = list(csv.reader(io.StringIO(body.lstrip('\ufeff'))))
    assert rows[0][-4:] == ['Admission Fee (net)', 'Admission Fee Received',
                            'Admission Fee Pending', 'Admission Fee Status']
    by_name = {r[0]: r for r in rows[1:]}
    assert by_name['Ali Khan'][-4:] == ['5,000', '2,000', '3,000', 'Partial']
    assert by_name['Sara Ali'][-4:] == ['', '', '', '']              # no admission fee on record


def test_students_page_links_to_the_admission_page_for_admin_only(admin_client, teacher_client, app, seed):
    ali = StudentModel.query.filter_by(roll_number=1001).one()
    link = ('/admission-fees/student/%d' % ali.id).encode()
    assert link not in admin_client.get('/students').data               # feature off
    _enable(5000)
    assert link in admin_client.get('/students').data
    assert link not in teacher_client.get('/students').data


# ---- register export ---------------------------------------------------------- #

def test_register_exports_follow_the_filters(admin_client, accountant_client, owner_client,
                                             teacher_client, app, seed):
    _register_fixture(seed)
    csv_body = admin_client.get('/admission-fees/export/csv?status=pending').data.decode()
    rows = list(csv.reader(io.StringIO(csv_body)))
    assert rows[0][:2] == ['Date', 'Student']
    assert [r[1] for r in rows[1:]] == ['Pending Kid']
    everyone = list(csv.reader(io.StringIO(admin_client.get('/admission-fees/export/csv').data.decode())))
    assert {r[1] for r in everyone[1:]} == {'Ali Khan', 'Sara Ali', 'Waived Kid', 'Pending Kid'}
    sara = next(r for r in everyone[1:] if r[1] == 'Sara Ali')
    assert sara[5:11] == ['5000.0', '1000.0', '4000.0', '1000.0', '3000.0', 'Partial']

    excel = admin_client.get('/admission-fees/export/xlsx')
    assert excel.status_code == 200 and excel.data[:2] == b'PK'
    pdf = admin_client.get('/admission-fees/export/pdf')
    assert pdf.status_code == 200 and pdf.data[:4] == b'%PDF'
    for client in (accountant_client, owner_client):
        assert client.get('/admission-fees/export/csv').status_code == 200
    assert teacher_client.get('/admission-fees/export/csv').status_code == 403
    assert admin_client.get('/admission-fees/export/doc').status_code == 404


def test_register_page_has_export_buttons_and_hub_card(admin_client, app, seed):
    _register_fixture(seed)
    page = admin_client.get('/admission-fees?status=partial').data
    assert b'/admission-fees/export/pdf?status=partial' in page
    assert b'Admission Fees Register' in admin_client.get('/reports/hub?tab=finance').data


# ---- finance lines ------------------------------------------------------------ #

def test_admission_line_on_the_financial_overview_is_part_of_other_income(admin_client, app, seed):
    month = current_month_key()
    assert b'admission fees:' not in admin_client.get('/financials/summary').data   # opt-in
    student = _with_terms(seed)
    adm.receive_payment(student, 5000)
    other_income_service.seed_default_categories()
    plain = OtherIncomeCategory.query.filter(OtherIncomeCategory.name != 'Admission Fee').first()
    other_income_service.record_income(plain, 700, date.today())
    db.session.commit()
    snap = month_snapshot(month)
    assert snap['admission_fees'] == 5000 and snap['other_income'] == 5700
    assert snap['cash_in'] == snap['fee_income'] + 5700                  # counted once
    page = admin_client.get('/financials/summary').data
    assert b'of which admission fees' in page and b'5,000.00' in page


def test_executive_dashboard_and_pdf_show_admission_fees(admin_client, owner_client, app, seed):
    assert b'admission fees' not in admin_client.get('/executive').data
    student = _with_terms(seed)
    adm.receive_payment(student, 1200)
    db.session.commit()
    assert b'1,200 admission fees' in admin_client.get('/executive').data
    assert b'1,200 admission fees' in owner_client.get('/executive').data
    assert admin_client.get('/executive/summary.pdf').data[:4] == b'%PDF'


def test_income_total_counts_only_active_admission_receipts_in_range(app, seed):
    student = _with_terms(seed)
    old = date.today() - timedelta(days=70)
    adm.receive_payment(student, 1000, old)
    adm.receive_payment(student, 2000)
    other_income_service.seed_default_categories()
    plain = OtherIncomeCategory.query.filter(OtherIncomeCategory.name != 'Admission Fee').first()
    other_income_service.record_income(plain, 900, date.today())
    db.session.commit()
    this_month = date.today().replace(day=1)
    assert adm.income_total(this_month, date.today()) == 2000.0
    assert adm.income_total(old, date.today()) == 3000.0
    adm.void_payment(adm.active_payments(student.id)[-1], 'mistake')
    db.session.commit()
    assert adm.income_total(old, date.today()) == 1000.0

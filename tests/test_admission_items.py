"""New-admission package: admission fee + books + uniform on one receipt.

Books and uniform (price per set x sets) are set once per class in the Admission
Fee settings, fill the Add Student form, are paid together with the admission fee
and a partial payment leaves the rest pending.
"""
import pytest

from app.database import db
from app.models import ClassModel, OtherIncome
from app.services import admission_fee as adm
from tests.test_admission_fee import (  # noqa: F401  (fixtures are used by name)
    accountant_client, admin_client, teacher_client, _add_student, _admission_income,
    _enable, _student)


def _class_items(seed, admission=2000, books=3000, uniform=1500, sets=2):
    """Admission 2,000 + books 3,000 + uniform 2 x 1,500 = 8,000 for the class."""
    class_obj = db.session.get(ClassModel, seed['class_id'])
    class_obj.admission_fee = admission
    class_obj.books_fee = books
    class_obj.uniform_fee = uniform
    class_obj.uniform_sets = sets
    db.session.commit()


def _paid_lines(student):
    return {line['key']: (line['paid'], line['balance'])
            for line in adm.summary(student)['lines']}


def test_settings_page_saves_books_and_uniform_per_class(admin_client, seed):
    cid = seed['class_id']
    resp = admin_client.post('/fees/admission-settings', data={
        'default_admission_fee': '1000', 'class_%d' % cid: '2000',
        'books_%d' % cid: '3500', 'uniform_%d' % cid: '1800', 'sets_%d' % cid: '2'})
    assert resp.status_code == 302
    class_obj = db.session.get(ClassModel, cid)
    assert (class_obj.books_fee, class_obj.uniform_fee, class_obj.uniform_sets) == (3500, 1800, 2)
    assert adm.items_by_class()[str(cid)] == {
        'books': 3500.0, 'uniform': 1800.0, 'sets': 2, 'admission': 2000.0}


def test_books_alone_switch_the_feature_on(app, seed):
    assert adm.is_enabled() is False
    class_obj = db.session.get(ClassModel, seed['class_id'])
    class_obj.books_fee = 1200
    db.session.commit()
    assert adm.is_enabled() is True


def test_bad_uniform_sets_are_rejected(app, seed):
    with pytest.raises(ValueError):
        adm.save_settings('', {}, {seed['class_id']: {'books': '', 'uniform': '1000', 'sets': '0'}})


def test_form_is_filled_from_the_class_and_one_receipt_covers_everything(admin_client, seed):
    _class_items(seed)
    resp = _add_student(admin_client, seed, 2001, 'Package Kid',
                        admission_received_now='1', admission_received_amount='6000')
    assert resp.status_code == 302
    student = _student(2001)
    assert (student.books_fee_paisa, student.uniform_qty, student.uniform_unit_paisa) == (
        300000, 2, 150000)
    info = adm.summary(student)
    assert info['total'] == 800000 and info['received'] == 600000 and info['balance'] == 200000
    assert info['status'] == 'partial'
    # 6,000 settles admission (2,000), books (3,000) then 1,000 of the 3,000 uniform.
    assert _paid_lines(student) == {'admission': (200000, 0), 'books': (300000, 0),
                                    'uniform': (100000, 200000)}
    income = _admission_income()
    assert len(income) == 1 and income[0].amount_paisa == 600000   # ONE receipt


def test_prices_are_fixed_by_the_class_and_the_form_chooses_what_is_taken(admin_client, seed):
    _class_items(seed)          # admission 2,000 + books 3,000 + uniform 1,500 per set (2 sets by default)
    # one uniform set, books taken; prices typed on the form are ignored (the class sets them)
    _add_student(admin_client, seed, 2002, 'Custom Kid', books_taken='1', uniform_qty='1',
                 books_fee='1', uniform_price='1', admission_fee='2000',
                 admission_received_now='1', admission_received_amount='6500')
    student = _student(2002)
    assert (student.books_fee_paisa, student.uniform_qty, student.uniform_unit_paisa) == (300000, 1, 150000)
    info = adm.summary(student)
    assert info['total'] == 650000 and info['balance'] == 0 and info['status'] == 'paid'


def test_two_uniform_sets_and_one_books_per_student(admin_client, seed):
    _class_items(seed, sets=1)
    _add_student(admin_client, seed, 2012, 'Two Sets', uniform_qty='2')
    _add_student(admin_client, seed, 2013, 'One Set')                  # default: 1 set + books
    _add_student(admin_client, seed, 2014, 'Uniform Only', books_taken='0', uniform_qty='3')
    assert adm.summary(_student(2012))['total'] == 200000 + 300000 + 2 * 150000
    assert adm.summary(_student(2013))['total'] == 200000 + 300000 + 150000
    only = _student(2014)
    assert only.books_fee_paisa is None and adm.summary(only)['total'] == 200000 + 3 * 150000


def test_not_taking_books_or_uniform(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 2003, 'No Books', books_taken='0')
    info = adm.summary(_student(2003))
    assert info['books'] == 0 and info['total'] == 500000      # 2,000 + 2 x 1,500
    _add_student(admin_client, seed, 2015, 'No Uniform', uniform_qty='0')
    assert adm.summary(_student(2015))['total'] == 500000      # 2,000 + 3,000 books


def test_teacher_gets_the_whole_package_as_pending(teacher_client, seed):
    _class_items(seed)
    _add_student(teacher_client, seed, 2004, 'Teacher Added', books_fee='1')   # ignored
    info = adm.summary(_student(2004))
    assert info['total'] == 800000 and info['received'] == 0 and info['status'] == 'pending'
    assert _admission_income() == []


def test_remaining_money_is_received_later_on_a_new_receipt(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 2005, 'Pays Twice',
                 admission_received_now='1', admission_received_amount='6000')
    student = _student(2005)
    resp = admin_client.post('/admission-fees/student/%d/receive' % student.id,
                             data={'amount': '2000', 'method': 'cash',
                                   'payment_date': adm.date.today().isoformat()})
    assert resp.status_code == 302
    db.session.expire_all()
    info = adm.summary(_student(2005))
    assert info['balance'] == 0 and info['status'] == 'paid'
    assert _paid_lines(_student(2005))['uniform'] == (300000, 0)
    rows = sorted(_admission_income(), key=lambda r: r.id)
    assert [r.amount_paisa for r in rows] == [600000, 200000]
    assert len({r.receipt_no for r in rows}) == 2
    # the second receipt shows only the uniform part as paid on that receipt
    page = admin_client.get('/admission-fees/receipt/%d' % rows[1].id).get_data(as_text=True)
    assert 'Books' in page and 'Uniform' in page and 'ADMISSION RECEIPT' in page


def test_paying_more_than_the_total_is_refused(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 2006, 'Too Much')
    student = _student(2006)
    with pytest.raises(ValueError):
        adm.receive_payment(student, 8001)


def test_receipt_lists_items_and_voiding_reopens_the_balance(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 2007, 'Void Kid',
                 admission_received_now='1', admission_received_amount='8000')
    student = _student(2007)
    row = _admission_income()[0]
    page = admin_client.get('/admission-fees/receipt/%d' % row.id).get_data(as_text=True)
    for text in ('Admission fee', 'Books', 'Uniform', 'Total agreed', 'PAID'):
        assert text in page
    admin_client.post('/admission-fees/receipt/%d/void' % row.id, data={'reason': 'test'})
    db.session.expire_all()
    info = adm.summary(_student(2007))
    assert info['received'] == 0 and info['balance'] == 800000 and info['status'] == 'pending'


def test_class_without_books_or_uniform_keeps_the_old_receipt(admin_client, seed):
    _enable(default=5000)
    _add_student(admin_client, seed, 2008, 'Plain Kid',
                 admission_received_now='1', admission_received_amount='5000')
    student = _student(2008)
    assert student.books_fee_paisa is None and student.uniform_qty is None
    row = _admission_income()[0]
    page = admin_client.get('/admission-fees/receipt/%d' % row.id).get_data(as_text=True)
    assert 'ADMISSION FEE RECEIPT' in page and 'Uniform' not in page


def test_books_and_uniform_without_an_admission_fee(admin_client, seed):
    cid = seed['class_id']
    class_obj = db.session.get(ClassModel, cid)
    class_obj.admission_fee = 0
    class_obj.books_fee = 1000
    class_obj.uniform_fee = 500
    class_obj.uniform_sets = 2
    db.session.commit()
    _add_student(admin_client, seed, 2009, 'Items Only',
                 admission_received_now='1', admission_received_amount='2000')
    student = _student(2009)
    info = adm.summary(student)
    assert info['total'] == 200000 and info['status'] == 'paid'
    rows, totals = adm.register()
    assert student.id in [r['student'].id for r in rows] and totals['extras'] >= 200000


def test_admin_can_change_books_and_uniform_but_not_below_what_was_paid(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 2010, 'Adjust Kid',
                 admission_received_now='1', admission_received_amount='6000')
    student = _student(2010)
    resp = admin_client.post('/admission-fees/student/%d/terms' % student.id, data={
        'admission_fee': '2000', 'books_fee': '1000', 'uniform_qty': '1',
        'uniform_price': '1000'})                         # total 4,000 < 6,000 received
    assert resp.status_code == 302
    db.session.expire_all()
    assert adm.summary(_student(2010))['total'] == 800000     # refused, unchanged
    admin_client.post('/admission-fees/student/%d/terms' % student.id, data={
        'admission_fee': '2000', 'books_fee': '3000', 'uniform_qty': '3',
        'uniform_price': '1500'})                         # total 9,500
    db.session.expire_all()
    assert adm.summary(_student(2010))['total'] == 950000


def test_register_export_has_the_books_and_uniform_column(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 2011, 'Export Kid')
    csv_text = admin_client.get('/admission-fees/export/csv').get_data(as_text=True)
    assert 'Books + Uniform (Rs)' in csv_text
    assert ',8000.0,0.0,8000.0,Pending,,6000.0' in csv_text   # net(total), received, pending, status, reason, books+uniform

"""Inventory Phase 3: books / uniform given at admission come out of stock.

The price of those items is already in the admission fee, so the issue is
booked with price 0 (income is never counted twice) while its cost is COGS.
"""
from datetime import date

import pytest

from app.database import db
from app.models import (ClassModel, Product, ProductSet, Sale, StudentIssue,
                        StudentModel)
from app.services import admission_fee as adm
from app.services import inventory_service as inv
from app.services import student_stock as stock
from tests.test_admission_fee import (  # noqa: F401  (fixtures are used by name)
    admin_client, _add_student, _student)

FAR_PAST, FAR_FUTURE = date(2000, 1, 1), date(2100, 1, 1)


@pytest.fixture()
def shop(app, seed):
    """Class 1: books 3,000 (1 set), uniform 1,500 x 2 sets, admission 2,000;
    sets "Class 1 Books" (English + Maths) and "Class 1 Uniform" (Shirt + Tie),
    each bought 10 times."""
    class_obj = db.session.get(ClassModel, seed['class_id'])
    class_obj.admission_fee, class_obj.books_fee = 2000, 3000
    class_obj.uniform_fee, class_obj.uniform_sets = 1500, 2
    english = Product(name='English 1', category='Books', sale_price_paisa=200000)
    maths = Product(name='Maths 1', category='Books', sale_price_paisa=100000)
    shirt = Product(name='Shirt', category='Uniform', sale_price_paisa=100000)
    tie = Product(name='Tie', category='Uniform', sale_price_paisa=50000)
    db.session.add_all([english, maths, shirt, tie])
    db.session.commit()
    books = inv.create_set('Class 1 Books', [(english.id, 1), (maths.id, 1)],
                           kind='books', class_id=class_obj.id)
    uniform = inv.create_set('Class 1 Uniform', [(shirt.id, 1), (tie.id, 1)],
                             kind='uniform', class_id=class_obj.id)
    db.session.commit()
    inv.purchase_set(books, 10, 18000)
    inv.purchase_set(uniform, 10, 9000)
    db.session.commit()
    return {'english': english.id, 'maths': maths.id, 'shirt': shirt.id,
            'tie': tie.id, 'books': books.id, 'uniform': uniform.id}


def _stock(shop, key):
    db.session.expire_all()
    return db.session.get(Product, shop[key]).stock_qty


def test_admission_takes_the_set_out_of_stock_without_new_income(admin_client, seed, shop):
    resp = _add_student(admin_client, seed, 3001, 'Stock Kid')
    assert resp.status_code == 302
    student = _student(3001)
    assert student.stock_tracked is True
    # 1 books set + 2 uniform sets, one of each item per set.
    assert (_stock(shop, 'english'), _stock(shop, 'maths')) == (9, 9)
    assert (_stock(shop, 'shirt'), _stock(shop, 'tie')) == (8, 8)
    sales = Sale.query.filter_by(student_id=student.id).all()
    assert len(sales) == 4 and {s.source for s in sales} == {'admission'}
    # Price 0: sales income is not counted again; the cost is COGS.
    revenue, cogs = inv.month_sales_totals(FAR_PAST, FAR_FUTURE)
    assert revenue == 0 and cogs > 0
    assert stock.issued_sets(student.id, 'books') == 1
    assert stock.issued_sets(student.id, 'uniform') == 2
    assert stock.pending_rows() == []


def test_short_stock_still_admits_the_student_and_can_be_issued_later(admin_client, seed, shop):
    english = db.session.get(Product, shop['english'])
    english.stock_qty = 0
    db.session.commit()
    resp = _add_student(admin_client, seed, 3002, 'Short Kid')
    assert resp.status_code == 302
    student = _student(3002)                      # admitted anyway
    assert stock.issued_sets(student.id, 'books') == 0
    assert stock.issued_sets(student.id, 'uniform') == 2          # uniform was fine
    pending = stock.pending_rows()
    assert [(r['student'].id, r['kind'], r['missing']) for r in pending] == [
        (student.id, 'books', 1)]
    # Nothing half-done: the Maths book was not taken either.
    assert _stock(shop, 'maths') == 10
    # Stock arrives -> "Issue now".
    inv.record_purchase(db.session.get(Product, shop['english']), 5, 1500)
    db.session.commit()
    resp = admin_client.post('/inventory/student-stock/%d/issue' % student.id)
    assert resp.status_code == 302
    assert stock.issued_sets(student.id, 'books') == 1
    assert (_stock(shop, 'english'), _stock(shop, 'maths')) == (4, 9)
    assert stock.pending_rows() == []


def test_voiding_an_issue_puts_the_stock_back_and_removes_its_cost(admin_client, seed, shop):
    _add_student(admin_client, seed, 3003, 'Void Kid')
    student = _student(3003)
    issue = StudentIssue.query.filter_by(student_id=student.id, kind='books').one()
    _, cogs_before = inv.month_sales_totals(FAR_PAST, FAR_FUTURE)
    resp = admin_client.post('/inventory/issues/%d/void' % issue.id,
                             data={'reason': 'Student did not take the books'})
    assert resp.status_code == 302
    assert (_stock(shop, 'english'), _stock(shop, 'maths')) == (10, 10)
    _, cogs_after = inv.month_sales_totals(FAR_PAST, FAR_FUTURE)
    assert cogs_after < cogs_before
    assert all(s.is_void for s in issue.sales)
    with pytest.raises(ValueError):
        stock.void_issue(db.session.get(StudentIssue, issue.id), 'again')
    with pytest.raises(ValueError):
        stock.void_issue(StudentIssue.query.filter_by(
            student_id=student.id, kind='uniform').one(), '   ')


def test_lowering_the_terms_returns_stock(admin_client, seed, shop):
    _add_student(admin_client, seed, 3004, 'Fewer Sets Kid')
    student = _student(3004)
    assert _stock(shop, 'shirt') == 8
    adm.adjust_terms(student, 2000, books_rupees=3000, uniform_qty=1,
                     uniform_unit_rupees=1500, books_sets=1)
    messages = stock.sync_student_stock(student)
    db.session.commit()
    assert stock.issued_sets(student.id, 'uniform') == 1
    assert (_stock(shop, 'shirt'), _stock(shop, 'tie')) == (9, 9)
    assert any('returned' in text.lower() for _, text in messages)


def test_old_students_are_never_touched(app, seed, shop):
    old = StudentModel.query.first()
    old.books_fee_paisa, old.books_qty = 300000, 1
    db.session.commit()
    assert not old.stock_tracked
    assert stock.sync_student_stock(old) == []
    assert _stock(shop, 'english') == 10
    assert stock.pending_rows() == []


def test_class_without_a_set_deducts_nothing_and_says_so(admin_client, seed, shop):
    books = db.session.get(ProductSet, shop['books'])
    books.is_active = False
    db.session.commit()
    _add_student(admin_client, seed, 3005, 'No Set Kid')
    student = _student(3005)
    assert stock.issued_sets(student.id, 'books') == 0
    assert _stock(shop, 'english') == 10
    rows = stock.pending_rows()
    assert rows and rows[0]['set'] is None


def test_one_item_later_paid_in_admission_or_sold_separately(admin_client, seed, shop):
    _add_student(admin_client, seed, 3006, 'Item Kid')
    student = _student(3006)
    ref = '%s (Class 1, Roll 3006) #%d' % (student.student_name, student.id)
    assert stock.find_student(ref).id == student.id
    assert stock.find_student('Nobody') is None

    # (a) already inside the admission fee: stock down, no income.
    resp = admin_client.post('/inventory/sell', data={
        'product_id': str(shop['english']), 'quantity': '1', 'student': ref,
        'in_admission': '1', 'sale_date': date.today().isoformat()})
    assert resp.status_code == 302
    assert _stock(shop, 'english') == 8                     # 9 after admission, 8 now
    revenue, _ = inv.month_sales_totals(FAR_PAST, FAR_FUTURE)
    assert revenue == 0

    # (b) a normal sale linked to the student: money is counted.
    resp = admin_client.post('/inventory/sell', data={
        'product_id': str(shop['english']), 'quantity': '1', 'student': ref,
        'sale_date': date.today().isoformat()})
    assert resp.status_code == 302
    revenue, _ = inv.month_sales_totals(FAR_PAST, FAR_FUTURE)
    assert revenue == 2000.0
    linked = Sale.query.filter_by(student_id=student.id, source='sale').one()
    assert linked.total_price_paisa == 200000

    # "Already paid in admission" without a student is refused.
    resp = admin_client.post('/inventory/sell', data={
        'product_id': str(shop['english']), 'quantity': '1', 'in_admission': '1',
        'sale_date': date.today().isoformat()})
    assert resp.status_code == 302
    assert _stock(shop, 'english') == 7


def test_inventory_page_shows_the_student_stock_box(admin_client, seed, shop):
    _add_student(admin_client, seed, 3007, 'Page Kid')
    html = admin_client.get('/inventory').get_data(as_text=True)
    assert 'Student stock' in html and 'Page Kid' in html

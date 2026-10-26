"""Void sale/purchase, gross-profit split, managed other-income categories,
student item record, expenses stock strip."""
from datetime import date

import pytest

from app.database import db
from app.models import (ClassModel, OtherIncomeCategory, Product, Purchase,
                        Sale, StudentModel)
from app.services import (admission_fee as af, financial_summary as fs,
                          inventory_service as inv, other_income_service as ois,
                          student_stock as ss)


@pytest.fixture()
def shop(app, seed):
    with app.app_context():
        cls = db.session.get(ClassModel, seed['class_id'])
        shirt = Product(name='Shirt', category='Uniform', sale_price_paisa=120000)
        trouser = Product(name='Trouser', category='Uniform', sale_price_paisa=150000)
        book = Product(name='English', category='Books', sale_price_paisa=40000)
        db.session.add_all([shirt, trouser, book])
        db.session.commit()
        uni = inv.create_set('C1 Uniform', [(shirt.id, 1), (trouser.id, 1)], 'uniform', cls.id)
        db.session.commit()
        return {'shirt': shirt.id, 'trouser': trouser.id, 'book': book.id, 'uni': uni.id}


def test_void_sale_restores_stock_and_totals(app, shop):
    with app.app_context():
        book = db.session.get(Product, shop['book'])
        inv.record_purchase(book, 10, 300.0, purchase_date=date.today())
        sale = inv.record_sale(book, 4)
        db.session.commit()
        assert book.stock_qty == 6
        with pytest.raises(ValueError):
            inv.void_sale(sale, '')
        inv.void_sale(sale, 'typed 4 instead of 1')
        db.session.commit()
        assert book.stock_qty == 10 and book.cost_paisa == 30000
        start = end = date.today()
        assert inv.month_sales_totals(start, end) == (0.0, 0.0)
        with pytest.raises(ValueError):
            inv.void_sale(sale, 'again')


def test_void_set_sale_voids_every_line_and_keeps_student(app, shop, seed):
    with app.app_context():
        uni = db.session.get(inv.ProductSet, shop['uni'])
        inv.purchase_set(uni, 5, 10000, purchase_date=date.today())
        rows = inv.sell_set(uni, 2, student_id=seed['student_id'])
        db.session.commit()
        assert all(r.student_id == seed['student_id'] for r in rows)
        inv.void_sale(rows[0], 'wrong student')
        db.session.commit()
        assert all(r.is_void for r in rows)
        assert db.session.get(Product, shop['shirt']).stock_qty == 5


def test_admission_sale_cannot_be_voided_here(app, shop, seed):
    with app.app_context():
        uni = db.session.get(inv.ProductSet, shop['uni'])
        inv.purchase_set(uni, 3, 6000, purchase_date=date.today())
        student = db.session.get(StudentModel, seed['student_id'])
        issue = ss.issue_set(student, uni, 'uniform', 1)
        db.session.commit()
        with pytest.raises(ValueError):
            inv.void_sale(issue.sales[0], 'x')


def test_void_purchase_reverses_stock_cash_and_dues(app, shop):
    with app.app_context():
        shirt = db.session.get(Product, shop['shirt'])
        purchase = inv.record_purchase(shirt, 10, 1000.0, supplier='Ali',
                                       purchase_date=date.today(), paid_rupees=4000)
        db.session.commit()
        assert inv.total_supplier_dues_paisa() == 600000
        inv.void_purchase(purchase, 'typed 10 not 1')
        db.session.commit()
        assert shirt.stock_qty == 0
        assert inv.total_supplier_dues_paisa() == 0
        assert inv.month_purchase_totals(date.today(), date.today()) == 0.0


def test_void_purchase_blocked_when_paid_later_or_sold(app, shop):
    with app.app_context():
        shirt = db.session.get(Product, shop['shirt'])
        purchase = inv.record_purchase(shirt, 10, 1000.0, supplier='Ali',
                                       purchase_date=date.today(), paid_rupees=4000)
        db.session.commit()
        inv.pay_purchase(purchase, 1000, date.today(), 'cash')
        db.session.commit()
        with pytest.raises(ValueError, match='Void those payments'):
            inv.void_purchase(purchase, 'oops')
        db.session.rollback()
        p2 = inv.record_purchase(db.session.get(Product, shop['trouser']), 5, 500.0,
                                 purchase_date=date.today())
        inv.record_sale(db.session.get(Product, shop['trouser']), 4)
        db.session.commit()
        with pytest.raises(ValueError, match='already sold'):
            inv.void_purchase(p2, 'oops')


def test_gross_profit_excludes_admission_package_cost(app, shop, seed):
    with app.app_context():
        uni = db.session.get(inv.ProductSet, shop['uni'])
        inv.purchase_set(uni, 4, 8000, purchase_date=date.today())
        student = db.session.get(StudentModel, seed['student_id'])
        ss.issue_set(student, uni, 'uniform', 1)          # price is inside admission fee
        book = db.session.get(Product, shop['book'])
        inv.record_purchase(book, 5, 300.0, purchase_date=date.today())
        inv.record_sale(book, 1)
        db.session.commit()
        snap = fs.month_snapshot(date.today().strftime('%Y-%m'))
        assert snap['package_cogs'] > 0
        assert snap['sales_cogs'] == round(snap['direct_cogs'] + snap['package_cogs'], 2)
        assert snap['gross_profit'] == round(400.0 - 300.0, 2)
        # operating position still subtracts ALL cost of goods
        assert snap['operating_position'] == round(snap['cash_in'] - snap['expenses'] - snap['sales_cogs'], 2)


def test_managed_categories_cannot_be_typed_in_other_income(app, admin_client):
    with app.app_context():
        ois.seed_default_categories()
        af.get_category()
        db.session.commit()
        names = [c.name for c in ois.manual_categories()]
        assert 'Admission Fee' not in names
        assert 'Events' in names
        cat = OtherIncomeCategory.query.filter_by(name='Admission Fee').first()
        cid = cat.id
    response = admin_client.post('/other-income/add', data={
        'category_id': cid, 'amount': '500', 'income_date': date.today().isoformat()})
    assert response.status_code == 302 and '/admission-fees' in response.headers['Location']
    ok = admin_client.post('/other-income/add', data={
        'category_id': [c for c in range(1, 20)][0], 'amount': '1', 'income_date': date.today().isoformat()})
    assert ok.status_code == 302


def test_pages_render_with_new_pieces(app, admin_client, shop, seed):
    with app.app_context():
        uni = db.session.get(inv.ProductSet, shop['uni'])
        inv.purchase_set(uni, 2, 4000, supplier='Ali', purchase_date=date.today(), paid_rupees=1000)
        inv.sell_set(uni, 1)
        db.session.commit()
    for url in ('/inventory', '/expenses', '/other-income', '/admission-fees',
                '/admission-fees/student/%d' % seed['student_id'], '/financials/summary'):
        response = admin_client.get(url)
        assert response.status_code == 200, url
    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'Still owed to suppliers' in body and 'Which page do I use' in body
    inv_body = admin_client.get('/inventory').get_data(as_text=True)
    assert 'undoModal' in inv_body


def test_void_routes_via_http(app, admin_client, shop):
    with app.app_context():
        book = db.session.get(Product, shop['book'])
        purchase = inv.record_purchase(book, 10, 300.0, purchase_date=date.today())
        sale = inv.record_sale(book, 2)
        db.session.commit()
        pid, sid = purchase.id, sale.id
    admin_client.post('/inventory/sales/%d/void' % sid, data={'reason': 'mistake'})
    admin_client.post('/inventory/purchases/%d/void' % pid, data={'reason': 'mistake'})
    with app.app_context():
        assert db.session.get(Sale, sid).is_void
        assert db.session.get(Purchase, pid).is_void
        assert db.session.get(Product, shop['book']).stock_qty == 0

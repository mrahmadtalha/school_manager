"""Supplier dues: a purchase can be part-paid, the rest is owed and paid later.

Spec example: stock worth Rs 20,000, Rs 12,000 paid to the supplier -> Rs 8,000
is shown as owed.  Only money really paid counts as cash out.
"""
from datetime import date

import pytest

from app.database import db
from app.models import Product, Purchase, SupplierPayment
from app.services import financial_summary as fs, inventory_service as inv


@pytest.fixture()
def world(app):
    with app.app_context():
        shirt = Product(name='School Shirt', category='Uniform',
                        sale_price_paisa=120000, min_stock_qty=5)
        db.session.add(shirt)
        db.session.commit()
        return {'shirt_id': shirt.id}


def _shirt(world):
    return db.session.get(Product, world['shirt_id'])


def test_part_payment_leaves_the_rest_owed(app, world):
    with app.app_context():
        purchase = inv.record_purchase(
            _shirt(world), 20, 1000.0, supplier='Ali Traders',
            purchase_date=date(2026, 10, 1), paid_rupees=12000)
        db.session.commit()
        assert purchase.total_cost_paisa == 2000000       # Rs 20,000
        assert purchase.paid_total_paisa == 1200000       # Rs 12,000
        assert purchase.balance_paisa == 800000           # Rs 8,000 owed
        dues = inv.supplier_dues()
        assert len(dues) == 1
        assert dues[0]['supplier'] == 'Ali Traders'
        assert dues[0]['balance'] == 800000
        assert inv.total_supplier_dues_paisa() == 800000
        assert _shirt(world).stock_qty == 20              # full stock arrives day one


def test_blank_paid_means_paid_in_full(app, world):
    with app.app_context():
        purchase = inv.record_purchase(_shirt(world), 10, 500.0,
                                       purchase_date=date(2026, 10, 1))
        db.session.commit()
        assert purchase.balance_paisa == 0
        assert inv.supplier_dues() == []


def test_cannot_pay_more_than_the_bill_or_less_than_nothing(app, world):
    with app.app_context():
        with pytest.raises(ValueError):
            inv.record_purchase(_shirt(world), 10, 500.0, paid_rupees=5001)
        db.session.rollback()
        with pytest.raises(ValueError):
            inv.record_purchase(_shirt(world), 10, 500.0, paid_rupees=-1)
        db.session.rollback()


def test_later_payment_settles_oldest_bill_first(app, world):
    with app.app_context():
        shirt = _shirt(world)
        first = inv.record_purchase(shirt, 10, 1000.0, supplier='Ali Traders',
                                    purchase_date=date(2026, 10, 1), paid_rupees=0)
        second = inv.record_purchase(shirt, 5, 1000.0, supplier='ali traders',
                                     purchase_date=date(2026, 10, 5), paid_rupees=0)
        db.session.commit()
        assert inv.total_supplier_dues_paisa() == 1500000

        made = inv.pay_supplier('Ali Traders', 12000, date(2026, 10, 10), 'bank')
        db.session.commit()
        assert [p.amount_paisa for p in made] == [1000000, 200000]
        assert first.balance_paisa == 0
        assert second.balance_paisa == 300000
        assert inv.total_supplier_dues_paisa() == 300000
        # 'Ali Traders' and 'ali traders' are the same supplier.
        assert len(inv.supplier_dues()) == 1


def test_overpaying_a_supplier_is_refused(app, world):
    with app.app_context():
        inv.record_purchase(_shirt(world), 10, 1000.0, supplier='Ali Traders',
                            paid_rupees=0)
        db.session.commit()
        with pytest.raises(ValueError):
            inv.pay_supplier('Ali Traders', 10001)
        db.session.rollback()
        with pytest.raises(ValueError):
            inv.pay_supplier('Nobody', 10)
        db.session.rollback()


def test_void_payment_reopens_the_balance(app, world):
    with app.app_context():
        purchase = inv.record_purchase(_shirt(world), 10, 1000.0,
                                       supplier='Ali Traders', paid_rupees=0)
        db.session.commit()
        payment = inv.pay_purchase(purchase, 4000, date.today(), 'cash')
        db.session.commit()
        assert purchase.balance_paisa == 600000
        with pytest.raises(ValueError):
            inv.void_supplier_payment(payment, '   ')
        inv.void_supplier_payment(payment, 'entered twice')
        db.session.commit()
        assert purchase.balance_paisa == 1000000
        assert inv.total_supplier_dues_paisa() == 1000000


def test_cash_out_counts_only_money_really_paid(app, world):
    """20,000 of stock, 12,000 paid on the day, 3,000 paid later in November."""
    with app.app_context():
        purchase = inv.record_purchase(
            _shirt(world), 20, 1000.0, supplier='Ali Traders',
            purchase_date=date(2025, 10, 1), paid_rupees=12000)
        db.session.commit()
        inv.pay_purchase(purchase, 3000, date(2025, 11, 3), 'cash')
        db.session.commit()

        october = fs.month_snapshot('2025-10')
        assert october['purchases'] == 12000.0
        assert october['cash_out'] == 12000.0
        assert october['expenses'] == 0.0             # stock is still not an expense
        assert october['supplier_dues'] == 5000.0     # 8,000 - 3,000 at today's date

        november = fs.month_snapshot('2025-11')
        assert november['purchases'] == 3000.0
        assert november['cash_out'] == 3000.0

        # The comparison engine agrees with the month snapshot.
        buckets = fs._window_totals(date(2025, 10, 1), date(2025, 11, 30))
        assert buckets['purchases'] == {'2025-10': 12000.0, '2025-11': 3000.0}


def test_old_purchases_without_paid_column_count_as_fully_paid(app, world):
    with app.app_context():
        purchase = inv.record_purchase(_shirt(world), 10, 500.0,
                                       purchase_date=date(2026, 10, 1))
        purchase.paid_paisa = None                      # a pre-upgrade row
        db.session.commit()
        assert purchase.balance_paisa == 0
        assert inv.month_purchase_totals(date(2026, 10, 1), date(2026, 10, 31)) == 5000.0


def test_pages_and_posts_end_to_end(admin_client, app, world):
    shirt_id = world['shirt_id']
    response = admin_client.post('/inventory/purchase', data={
        'product_id': str(shirt_id), 'quantity': '20', 'unit_cost': '1000',
        'purchase_date': '2026-10-01', 'supplier': 'Ali Traders',
        'paid_now': '12000',
    }, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert 'Stock added: 20 x School Shirt' in body
    assert 'still owed to Ali Traders: Rs 8,000.00' in body
    assert 'Supplier dues' in body and 'Pay supplier' in body

    with app.app_context():
        purchase_id = Purchase.query.first().id

    response = admin_client.post('/inventory/suppliers/pay', data={
        'supplier': 'Ali Traders', 'amount': '5000',
        'payment_date': date.today().strftime('%Y-%m-%d'), 'method': 'bank',
    }, follow_redirects=True)
    assert 'Still owed to this supplier: Rs 3,000.00' in response.get_data(as_text=True)

    response = admin_client.post('/inventory/purchases/%d/pay' % purchase_id, data={
        'amount': '3000', 'payment_date': date.today().strftime('%Y-%m-%d'),
    }, follow_redirects=True)
    assert 'Still owed on this bill: Rs 0.00' in response.get_data(as_text=True)

    with app.app_context():
        assert inv.total_supplier_dues_paisa() == 0
        payment = SupplierPayment.query.first()
        payment_id = payment.id
    response = admin_client.post(
        '/inventory/supplier-payments/%d/void' % payment_id,
        data={'reason': 'wrong supplier'}, follow_redirects=True)
    assert 'voided' in response.get_data(as_text=True)
    with app.app_context():
        assert inv.total_supplier_dues_paisa() == 500000


def test_teacher_cannot_pay_suppliers(teacher_client, app, world):
    response = teacher_client.post('/inventory/suppliers/pay', data={
        'supplier': 'X', 'amount': '1'})
    assert response.status_code in (302, 403)
    with app.app_context():
        assert SupplierPayment.query.count() == 0

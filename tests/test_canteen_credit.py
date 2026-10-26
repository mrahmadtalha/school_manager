"""Canteen "totals only" purchases bought on credit (supplier udhaar)."""
from datetime import date

import pytest

from app.database import db
from app.models import CanteenEntry, Expense
from app.services import (canteen_service as canteen, financial_summary as fs,
                          inventory_service as inv)

TODAY = date.today()
MONTH = TODAY.strftime('%Y-%m')


def _bounds():
    return fs.month_bounds(MONTH)


def _expense_total():
    return sum(e.amount_paisa for e in Expense.query.filter_by(is_void=False).all()
               if e.description and e.description.startswith('Canteen'))


def test_paid_in_full_purchase_is_unchanged(app):
    with app.app_context():
        entry = canteen.record_total('purchase', 1000, TODAY, supplier='Ali Traders')
        db.session.commit()
        assert not entry.is_credit
        assert entry.amount_paisa == 100000 and entry.balance_paisa == 0
        assert _expense_total() == 100000
        assert canteen.supplier_dues() == []


def test_credit_purchase_only_paid_part_is_an_expense(app):
    with app.app_context():
        entry = canteen.record_total('purchase', 2000, TODAY, supplier='Ali Traders',
                                     paid_rupees=500)
        db.session.commit()
        assert entry.is_credit
        assert entry.amount_paisa == 200000
        assert entry.paid_total_paisa == 50000
        assert entry.balance_paisa == 150000
        assert _expense_total() == 50000                 # the unpaid part is no expense
        summary = canteen.month_summary(*_bounds())
        assert summary['totals']['purchases'] == 200000  # bought = the whole bill
        assert summary['paid'] == 50000
        assert summary['owed'] == 150000
        assert inv.total_supplier_dues_paisa() == 150000


def test_nothing_paid_today_creates_no_expense_and_can_still_be_voided(app):
    with app.app_context():
        entry = canteen.record_total('purchase', 800, TODAY, supplier='Khan', paid_rupees=0)
        db.session.commit()
        assert entry.expense_id is None and entry.balance_paisa == 80000
        assert not entry.is_void
        canteen.void_entry(entry, 'typed twice')
        db.session.commit()
        assert entry.is_void and entry.balance_paisa == 0
        assert canteen.supplier_dues() == []


def test_paying_the_supplier_later_makes_cash_out_then(app):
    with app.app_context():
        first = canteen.record_total('purchase', 1000, TODAY, supplier='Ali', paid_rupees=0)
        second = canteen.record_total('purchase', 600, TODAY, supplier='Ali', paid_rupees=100)
        db.session.commit()
        assert canteen.supplier_dues()[0]['balance'] == 100000 + 50000
        made = canteen.pay_supplier('Ali', 1100, TODAY, 'bank')
        db.session.commit()
        assert len(made) == 2                          # oldest bill first, then the next
        assert first.balance_paisa == 0
        assert second.balance_paisa == 40000
        assert _expense_total() == 10000 + 110000
        assert canteen.month_summary(*_bounds())['paid'] == 120000
        with pytest.raises(ValueError):
            canteen.pay_supplier('Ali', 9999, TODAY)
        db.session.rollback()


def test_voiding_a_payment_reopens_the_balance_and_removes_the_expense(app):
    with app.app_context():
        entry = canteen.record_total('purchase', 1000, TODAY, supplier='Ali', paid_rupees=0)
        payment = canteen.pay_entry(entry, 400, TODAY)
        db.session.commit()
        assert entry.balance_paisa == 60000
        with pytest.raises(ValueError):
            canteen.void_payment(payment, '')
        canteen.void_payment(payment, 'wrong amount')
        db.session.commit()
        assert entry.balance_paisa == 100000
        assert _expense_total() == 0


def test_a_bill_with_payments_cannot_be_voided_first(app):
    with app.app_context():
        entry = canteen.record_total('purchase', 1000, TODAY, supplier='Ali', paid_rupees=0)
        canteen.pay_entry(entry, 400, TODAY)
        db.session.commit()
        with pytest.raises(ValueError):
            canteen.void_entry(entry, 'mistake')
        db.session.rollback()


def test_paid_now_is_validated(app):
    with app.app_context():
        with pytest.raises(ValueError):
            canteen.record_total('purchase', 100, TODAY, paid_rupees=150)
        with pytest.raises(ValueError):
            canteen.record_total('purchase', 100, TODAY, paid_rupees=-1)
        db.session.rollback()


def test_canteen_credit_routes_end_to_end(admin_client, app):
    admin_client.post('/inventory/canteen/mode', data={'mode': 'totals'})
    day = TODAY.strftime('%Y-%m-%d')
    admin_client.post('/inventory/canteen/total', data={
        'kind': 'purchase', 'amount': '1000', 'entry_date': day,
        'supplier': 'Ali Traders', 'paid_now': '250'})
    page = admin_client.get('/inventory')
    assert b'id="supplierDues"' in page.data and b'Ali Traders' in page.data
    with app.app_context():
        entry = CanteenEntry.query.one()
        assert entry.balance_paisa == 75000
        entry_id = entry.id

    admin_client.post('/inventory/suppliers/pay', data={
        'supplier': 'Ali Traders', 'source': 'canteen', 'amount': '300',
        'payment_date': day, 'method': 'cash'})
    with app.app_context():
        assert db.session.get(CanteenEntry, entry_id).balance_paisa == 45000

    admin_client.post('/inventory/canteen/entries/%d/pay' % entry_id, data={
        'amount': '450', 'payment_date': day, 'method': 'cash'})
    with app.app_context():
        entry = db.session.get(CanteenEntry, entry_id)
        assert entry.balance_paisa == 0
        assert canteen.supplier_dues() == []


def test_inventory_page_has_section_tabs(admin_client):
    page = admin_client.get('/inventory')
    assert page.status_code == 200
    for key in (b'data-sec-tab="items"', b'data-sec-tab="setup"', b'data-sec-tab="canteen"',
                b'data-sec-tab="sets"', b'data-sec-tab="stock"'):
        assert key in page.data
    assert b'data-sec-tab="dues"' not in page.data      # nobody is owed yet
    for section in (b'id="setup" data-sec="setup"', b'id="canteen" data-sec="canteen"',
                    b'id="sets" data-sec="sets"', b'id="studentStock" data-sec="stock"',
                    b'id="products" data-sec="items"'):
        assert section in page.data

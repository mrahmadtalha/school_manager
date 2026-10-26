"""Phase 4: canteen inside Inventory, opening stock and the setup checklist."""
from datetime import date

import pytest

from app.database import db
from app.models import (CanteenEntry, Expense, ExpenseCategory, OtherIncome,
                        OtherIncomeCategory, Product, Purchase)
from app.services import (canteen_service as canteen, financial_summary as fs,
                          inventory_service as inv, other_income_service as oi,
                          student_stock)

TODAY = date.today()
MONTH = TODAY.strftime('%Y-%m')


def _bounds():
    return fs.month_bounds(MONTH)


def _product(name='Shirt', category='Uniform', price=100000):
    product = Product(name=name, category=category, sale_price_paisa=price)
    db.session.add(product)
    db.session.commit()
    return product


# --------------------------------------------------------------------------- #
# Opening stock
# --------------------------------------------------------------------------- #

def test_opening_stock_fills_the_shelf_but_is_never_cash_out(app):
    with app.app_context():
        shirt = _product()
        row = inv.record_opening_stock(shirt, 40, 600.0, as_of=TODAY)
        db.session.commit()
        assert shirt.stock_qty == 40
        assert shirt.cost_paisa == 60000
        assert row.is_opening is True and row.bill_label == 'Opening stock'
        assert row.balance_paisa == 0                 # nobody is owed
        assert inv.supplier_dues() == []
        start, end = _bounds()
        assert inv.month_purchase_totals(start, end) == 0.0     # not cash out
        assert fs.month_snapshot(MONTH)['purchases'] == 0.0


def test_a_real_purchase_after_opening_stock_still_counts_and_averages(app):
    with app.app_context():
        shirt = _product()
        inv.record_opening_stock(shirt, 10, 500.0, as_of=TODAY)
        inv.record_purchase(shirt, 10, 700.0, purchase_date=TODAY)
        db.session.commit()
        assert shirt.stock_qty == 20
        assert shirt.cost_paisa == 60000                       # (500 + 700) / 2
        start, end = _bounds()
        assert inv.month_purchase_totals(start, end) == 7000.0  # only the real one


def test_opening_stock_is_validated(app):
    with app.app_context():
        shirt = _product()
        with pytest.raises(ValueError):
            inv.record_opening_stock(shirt, 0, 100)
        with pytest.raises(ValueError):
            inv.record_opening_stock(shirt, 5, 0)
        with pytest.raises(ValueError):
            inv.record_opening_stock(shirt, 'x', 100)
        with pytest.raises(ValueError):
            inv.record_opening_stock(shirt, 5, 100, as_of=date(2999, 1, 1))
        db.session.rollback()
        assert Purchase.query.count() == 0


# --------------------------------------------------------------------------- #
# Canteen mode
# --------------------------------------------------------------------------- #

def test_canteen_is_off_until_chosen(app):
    with app.app_context():
        assert canteen.get_mode() == 'off'
        assert canteen.is_open_for_other_income()
        canteen.set_mode('totals')
        db.session.commit()
        assert canteen.get_mode() == 'totals'
        assert not canteen.is_open_for_other_income()
        with pytest.raises(ValueError):
            canteen.set_mode('everything')
        assert canteen.get_mode() == 'totals'


# --------------------------------------------------------------------------- #
# Totals only
# --------------------------------------------------------------------------- #

def test_total_sales_become_other_income_and_purchases_an_expense(app):
    with app.app_context():
        sale = canteen.record_total('sale', 2500, TODAY, note='Monday')
        buy = canteen.record_total('purchase', 1000, TODAY)
        db.session.commit()
        assert sale.amount_paisa == 250000 and buy.amount_paisa == 100000
        income = db.session.get(OtherIncome, sale.income_id)
        assert income.category.name == 'Canteen'
        expense = db.session.get(Expense, buy.expense_id)
        assert expense.category.name == 'Canteen Purchases'

        snap = fs.month_snapshot(MONTH)
        assert snap['other_income'] == 2500.0              # counted once
        assert snap['expenses'] == 1000.0
        assert snap['net'] == 1500.0

        start, end = _bounds()
        totals = canteen.month_summary(start, end)['totals']
        assert totals == {'sales': 250000, 'purchases': 100000, 'profit': 150000}


def test_expense_defaults_are_not_suppressed_by_the_canteen_category(app):
    with app.app_context():
        ExpenseCategory.query.delete()
        db.session.commit()
        canteen.record_total('purchase', 100, TODAY)
        db.session.commit()
        names = {c.name for c in ExpenseCategory.query.all()}
        assert 'Canteen Purchases' in names and 'Utilities' in names


def test_voiding_a_total_removes_it_from_every_figure(app):
    with app.app_context():
        sale = canteen.record_total('sale', 900, TODAY)
        buy = canteen.record_total('purchase', 300, TODAY)
        db.session.commit()
        with pytest.raises(ValueError):
            canteen.void_entry(sale, '  ')
        canteen.void_entry(sale, 'typed twice')
        canteen.void_entry(buy, 'wrong day')
        db.session.commit()
        assert sale.is_void and sale.void_reason == 'typed twice'
        assert buy.is_void
        snap = fs.month_snapshot(MONTH)
        assert snap['other_income'] == 0.0 and snap['expenses'] == 0.0
        start, end = _bounds()
        assert canteen.month_summary(start, end)['totals']['profit'] == 0
        with pytest.raises(ValueError):
            canteen.void_entry(sale, 'again')


def test_total_validation(app):
    with app.app_context():
        for bad in (0, -5, ''):
            with pytest.raises(ValueError):
                canteen.record_total('sale', bad, TODAY)
        with pytest.raises(ValueError):
            canteen.record_total('sale', 100, date(2999, 1, 1))
        with pytest.raises(ValueError):
            canteen.record_total('gift', 100, TODAY)
        db.session.rollback()
        assert CanteenEntry.query.count() == 0


def test_voiding_the_other_income_row_voids_the_canteen_entry_too(app):
    with app.app_context():
        sale = canteen.record_total('sale', 400, TODAY)
        db.session.commit()
        oi.void_income(sale.income, 'wrong')
        db.session.commit()
        assert sale.is_void


# --------------------------------------------------------------------------- #
# Item by item
# --------------------------------------------------------------------------- #

def test_item_by_item_summary_uses_only_canteen_products(app):
    with app.app_context():
        samosa = _product('Samosa', 'Canteen', 5000)
        shirt = _product('Shirt', 'Uniform', 100000)
        inv.record_opening_stock(samosa, 50, 30.0, as_of=TODAY)
        inv.record_purchase(samosa, 100, 30.0, purchase_date=TODAY)     # Rs 3,000 bought
        inv.record_purchase(shirt, 10, 500.0, purchase_date=TODAY)      # not canteen
        inv.record_sale(samosa, 20, sale_date=TODAY)                    # Rs 1,000 sold
        inv.record_sale(shirt, 1, sale_date=TODAY)
        db.session.commit()
        start, end = _bounds()
        detailed = canteen.month_summary(start, end)['detailed']
        assert detailed['sales'] == 100000
        assert detailed['cost_of_goods'] == 60000          # 20 x Rs 30
        assert detailed['profit'] == 40000
        assert detailed['bought'] == 300000                # opening stock excluded
        assert detailed['stock_value'] == 130 * 3000       # 130 left x Rs 30
        assert [p.name for p in canteen.canteen_products()] == ['Samosa']


def test_both_sources_are_added_so_switching_mode_loses_nothing(app):
    with app.app_context():
        samosa = _product('Samosa', 'Canteen', 5000)
        inv.record_purchase(samosa, 10, 30.0, purchase_date=TODAY)
        inv.record_sale(samosa, 4, sale_date=TODAY)
        canteen.record_total('sale', 100, TODAY)
        db.session.commit()
        start, end = _bounds()
        result = canteen.month_summary(start, end)
        assert result['sales'] == 20000 + 10000
        assert result['profit'] == (20000 - 12000) + 10000


# --------------------------------------------------------------------------- #
# Other Income page no longer takes canteen money once Inventory keeps it
# --------------------------------------------------------------------------- #

def _canteen_category_id():
    oi.seed_default_categories()
    return OtherIncomeCategory.query.filter_by(name='Canteen').one().id


def test_other_income_canteen_is_closed_when_the_canteen_is_in_inventory(admin_client, app):
    with app.app_context():
        category_id = _canteen_category_id()
        before = OtherIncome.query.count()
    admin_client.post('/other-income/add', data={
        'category_id': category_id, 'amount': '500',
        'income_date': TODAY.strftime('%Y-%m-%d')})
    with app.app_context():
        assert OtherIncome.query.count() == before + 1      # still open (mode off)
        canteen.set_mode('detailed')
        db.session.commit()
    response = admin_client.post('/other-income/add', data={
        'category_id': category_id, 'amount': '700',
        'income_date': TODAY.strftime('%Y-%m-%d')})
    assert response.status_code == 302 and '/inventory' in response.headers['Location']
    with app.app_context():
        assert OtherIncome.query.count() == before + 1      # refused, not doubled
    page = admin_client.get('/other-income')
    assert b'Inventory' in page.data and b'counted twice' in page.data


# --------------------------------------------------------------------------- #
# Uniform for all classes
# --------------------------------------------------------------------------- #

def test_a_common_uniform_set_serves_every_class_but_books_do_not(app, seed):
    with app.app_context():
        shirt = _product('Shirt')
        english = _product('English', 'Books')
        common = inv.create_set('Uniform (all)', [(shirt.id, 1)], kind='uniform')
        loose_books = inv.create_set('Books (no class)', [(english.id, 1)], kind='books')
        db.session.commit()
        assert student_stock.class_set(seed['class_id'], 'uniform').id == common.id
        assert student_stock.class_set(seed['class_id'], 'books') is None
        # A set made for the class itself always wins.
        own = inv.create_set('Class 1 Uniform', [(shirt.id, 2)], kind='uniform',
                             class_id=seed['class_id'])
        db.session.commit()
        assert student_stock.class_set(seed['class_id'], 'uniform').id == own.id
        assert loose_books.class_id is None


# --------------------------------------------------------------------------- #
# Setup checklist
# --------------------------------------------------------------------------- #

def test_checklist_moves_step_by_step_to_ready(app, seed):
    with app.app_context():
        status = canteen.setup_status()
        assert status['done_count'] == 0 and not status['all_done']
        assert status['class_count'] == 1 and status['percent'] == 0

        shirt = _product('Shirt')
        english = _product('English', 'Books')
        status = canteen.setup_status()
        assert status['items_done'] and not status['stock_done']
        assert [p.name for p in status['without_stock']] == ['English', 'Shirt']

        inv.record_opening_stock(shirt, 10, 500.0)
        inv.record_opening_stock(english, 10, 200.0)
        db.session.commit()
        status = canteen.setup_status()
        assert status['stock_done'] and not status['sets_done']
        assert status['done_count'] == 2

        inv.create_set('Class 1 Books', [(english.id, 1)], kind='books',
                       class_id=seed['class_id'])
        inv.create_set('Uniform (all)', [(shirt.id, 1)], kind='uniform')
        db.session.commit()
        status = canteen.setup_status()
        row = status['class_rows'][0]
        assert row['complete'] and row['uniform_common']
        assert status['sets_done'] and status['all_done'] and status['percent'] == 100


# --------------------------------------------------------------------------- #
# Pages and permissions
# --------------------------------------------------------------------------- #

def test_inventory_page_shows_checklist_canteen_and_student_stock_without_dues(admin_client):
    page = admin_client.get('/inventory')
    assert page.status_code == 200
    assert b'Setup checklist' in page.data
    assert b'id="canteen"' in page.data
    # Regression: the Student stock box used to appear only while a supplier was owed.
    assert b'id="studentStock"' in page.data
    assert b'id="supplierDues"' not in page.data


def test_canteen_routes_end_to_end(admin_client, app):
    admin_client.post('/inventory/canteen/mode', data={'mode': 'totals'})
    admin_client.post('/inventory/canteen/total', data={
        'kind': 'sale', 'amount': '1200', 'entry_date': TODAY.strftime('%Y-%m-%d'),
        'note': 'Tuesday'})
    admin_client.post('/inventory/canteen/total', data={
        'kind': 'purchase', 'amount': '400', 'entry_date': TODAY.strftime('%Y-%m-%d')})
    page = admin_client.get('/inventory')
    assert b'Total sales' in page.data and b'Tuesday' in page.data
    with app.app_context():
        assert canteen.get_mode() == 'totals'
        entries = CanteenEntry.query.order_by(CanteenEntry.id).all()
        assert [e.kind for e in entries] == ['sale', 'purchase']
        entry_id = entries[0].id
    # a void needs a reason
    admin_client.post('/inventory/canteen/entries/%d/void' % entry_id, data={'reason': ''})
    with app.app_context():
        assert not db.session.get(CanteenEntry, entry_id).is_void
    admin_client.post('/inventory/canteen/entries/%d/void' % entry_id,
                      data={'reason': 'duplicate'})
    with app.app_context():
        assert db.session.get(CanteenEntry, entry_id).is_void


def test_opening_stock_route(admin_client, app):
    with app.app_context():
        product_id = _product('Tie').id
    admin_client.post('/inventory/opening-stock', data={
        'product_id': product_id, 'quantity': '12', 'unit_cost': '150',
        'as_of': TODAY.strftime('%Y-%m-%d')})
    with app.app_context():
        assert db.session.get(Product, product_id).stock_qty == 12
        assert Purchase.query.filter_by(is_opening=True).count() == 1
    admin_client.post('/inventory/opening-stock', data={
        'product_id': product_id, 'quantity': '5', 'unit_cost': '0',
        'as_of': TODAY.strftime('%Y-%m-%d')})
    with app.app_context():
        assert db.session.get(Product, product_id).stock_qty == 12      # refused


def test_teachers_cannot_use_the_new_routes(teacher_client):
    for path, data in (('/inventory/canteen/mode', {'mode': 'totals'}),
                       ('/inventory/canteen/total', {'kind': 'sale', 'amount': '5'}),
                       ('/inventory/opening-stock', {'product_id': '1', 'quantity': '1',
                                                     'unit_cost': '1'})):
        assert teacher_client.post(path, data=data).status_code == 403

"""Phase 3b: Inventory & Sales — weighted-average cost, COGS on sale, no
negative stock, snapshot immutability, dashboard flow and reconciliation.

Spec examples that must pass:
  2 shirts sold  -> Sales 2,400, Cost 1,800, Profit 600, Stock 48
  10 x Rs 2,000  -> Sales 20,000, Cost 14,000, Profit 6,000
"""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.models import Product
from app.services import financial_summary as fs, inventory_service as inv


@pytest.fixture()
def world(app):
    with app.app_context():
        shirt = Product(name='School Shirt', category='Uniform',
                        sale_price_paisa=120000, min_stock_qty=5)
        db.session.add(shirt)
        db.session.commit()
        return {'shirt_id': shirt.id}


def _get_shirt(app):
    return db.session.get(Product, app['shirt_id'])


def test_spec_example_two_shirts_and_weighted_average(app, world):
    with app.app_context():
        shirt = _get_shirt(world)
        inv.record_purchase(shirt, 50, 900.0, purchase_date=date(2026, 10, 1))
        db.session.commit()

        sale = inv.record_sale(shirt, 2, sale_date=date(2026, 10, 5))
        db.session.commit()
        assert sale.total_price_paisa == 240000      # Rs 2,400
        assert sale.total_cost_paisa == 180000       # Rs 1,800
        assert sale.gross_profit_paisa == 60000      # Rs 600
        assert shirt.stock_qty == 48

        # Weighted average recalculates on every purchase: 48 @ 900 + 10 @ 1100.
        inv.record_purchase(shirt, 10, 1100.0, purchase_date=date(2026, 10, 6))
        db.session.commit()
        assert shirt.stock_qty == 58
        assert shirt.cost_paisa == int(round((48 * 90000 + 10 * 110000) / 58))

        sales, cogs = inv.month_sales_totals(date(2026, 10, 1), date(2026, 10, 31))
        assert (sales, cogs) == (2400.0, 1800.0)


def test_spec_example_ten_uniforms(app, world):
    with app.app_context():
        uniform = _get_shirt(world)
        uniform.sale_price_paisa = 200000
        inv.record_purchase(uniform, 5, 1300.0, purchase_date=date(2026, 10, 1))
        inv.record_purchase(uniform, 5, 1500.0, purchase_date=date(2026, 10, 2))
        db.session.commit()
        assert uniform.cost_paisa == 140000          # (5*1300 + 5*1500) / 10

        sale = inv.record_sale(uniform, 10, sale_date=date(2026, 10, 9))
        db.session.commit()
        assert sale.total_price_paisa == 2000000     # Rs 20,000
        assert sale.total_cost_paisa == 1400000      # Rs 14,000
        assert sale.gross_profit_paisa == 600000     # Rs 6,000
        assert uniform.stock_qty == 0


def test_no_negative_stock_service_and_database(app, world):
    with app.app_context():
        shirt = _get_shirt(world)
        inv.record_purchase(shirt, 3, 900.0)
        db.session.commit()
        with pytest.raises(ValueError):
            inv.record_sale(shirt, 5)                # service check
        db.session.rollback()

        # Even when overselling is explicitly allowed, the DB constraint
        # refuses a negative stock.
        app.config['ALLOW_SALES_BEYOND_STOCK'] = True
        try:
            inv.record_sale(shirt, 10)
            db.session.commit()
            raise AssertionError('negative stock should be impossible')
        except IntegrityError:
            db.session.rollback()
        finally:
            app.config['ALLOW_SALES_BEYOND_STOCK'] = False
        assert db.session.get(Product, shirt.id).stock_qty == 3


def test_price_and_cost_changes_never_alter_history(app, world):
    with app.app_context():
        shirt = _get_shirt(world)
        inv.record_purchase(shirt, 20, 900.0, purchase_date=date(2026, 10, 1))
        db.session.commit()
        sale = inv.record_sale(shirt, 2, sale_date=date(2026, 10, 5))
        db.session.commit()

        # Later: prices and costs change, more stock is bought.
        shirt.sale_price_paisa = 150000
        inv.record_purchase(shirt, 10, 1200.0, purchase_date=date(2026, 10, 20))
        db.session.commit()

        db.session.expire(sale)
        assert sale.unit_price_paisa == 120000
        assert sale.unit_cost_paisa == 90000
        assert sale.gross_profit_paisa == 60000
        sales, cogs = inv.month_sales_totals(date(2026, 10, 1), date(2026, 10, 31))
        assert (sales, cogs) == (2400.0, 1800.0)


def test_summary_flow_purchases_cash_out_cogs_operating(app, world):
    """Cash In − Cash Out = Net Position and the operating split, with stock."""
    with app.app_context():
        shirt = _get_shirt(world)
        inv.record_purchase(shirt, 50, 900.0, purchase_date=date(2026, 10, 1))
        db.session.commit()
        inv.record_sale(shirt, 2, sale_date=date(2026, 10, 5))
        db.session.commit()

        snap = fs.month_snapshot('2026-10')
        assert snap['sales'] == 2400.0
        assert snap['sales_cogs'] == 1800.0
        assert snap['gross_profit'] == 600.0
        assert snap['cash_in'] == 2400.0
        assert snap['purchases'] == 45000.0
        assert snap['cash_out'] == 45000.0            # expenses + purchases
        assert snap['expenses'] == 0.0                # stock is NOT an expense
        assert snap['other_expenses'] == 0.0
        assert snap['net'] == snap['cash_in'] - snap['cash_out']
        # Operating: Revenue − Salaries − Operating Expenses − COGS.
        assert snap['operating_position'] == 600.0

        # Period engine (comparison grid path) agrees with the month snapshot.
        period = fs.period_descriptor('2026-10')
        buckets = fs._window_totals(snap['start'], snap['end'])
        psnap = fs.period_snapshot(
            period, buckets['revenue'], buckets['expenses'], buckets['payroll'],
            other_income=buckets['other_income'], sales=buckets['sales_revenue'],
            sales_cogs=buckets['sales_cogs'], purchases=buckets['purchases'])
        assert psnap['sales'] == 2400.0
        assert psnap['net'] == snap['net']
        assert psnap['operating_position'] == 600.0


def test_pages_and_posts_end_to_end(admin_client, app, world):
    with app.app_context():
        shirt = _get_shirt(world)
        shirt_id = shirt.id

    body = admin_client.get('/inventory').get_data(as_text=True)
    assert 'School Shirt' in body and 'Add product' in body

    # Purchase through the real form.
    response = admin_client.post('/inventory/purchase', data={
        'product_id': str(shirt_id), 'quantity': '50', 'unit_cost': '900',
        'purchase_date': '2026-10-01',
    }, follow_redirects=True)
    assert 'Stock added: 50 x School Shirt' in response.get_data(as_text=True)

    # Sale through the real form.
    response = admin_client.post('/inventory/sell', data={
        'product_id': str(shirt_id), 'quantity': '2',
        'sale_date': '2026-10-05', 'note': 'first two shirts',
    }, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert 'Sold 2 x School Shirt' in body and 'gross profit Rs 600.00' in body

    with app.app_context():
        assert db.session.get(Product, shirt_id).stock_qty == 48


def test_summary_page_shows_operating_cards_and_nav(admin_client, app, world):
    with app.app_context():
        shirt = _get_shirt(world)
        inv.record_purchase(shirt, 50, 900.0, purchase_date=date(2026, 10, 1))
        inv.record_sale(shirt, 2, sale_date=date(2026, 10, 5))
        db.session.commit()

    body = admin_client.get('/financials/summary?month=2026-10') \
        .get_data(as_text=True)
    assert 'Sales Revenue' in body
    assert 'Cost of Goods Sold' in body
    assert 'Estimated Net Operating Position' in body
    assert 'Rs. 2,400.00' in body                       # sales card
    assert 'Net Position' in body                       # cash card still there
    assert 'Inventory &amp; Sales' in body              # nav link

    # The comparison grid separates sales receipts from fee collections.
    assert 'of which Sales (inventory)' in body


def test_low_stock_alert_reaches_summary(admin_client, app, world):
    with app.app_context():
        shirt = _get_shirt(world)
        inv.record_purchase(shirt, 6, 900.0)
        db.session.commit()
        inv.record_sale(shirt, 2)                       # 4 left, min 5
        db.session.commit()

    alerts = admin_client.get('/financials/summary?month=2026-10') \
        .get_data(as_text=True)
    assert 'Low stock:' in alerts and 'School Shirt (4 left)' in alerts


def test_flag_off_hides_module(app, admin_client, world):
    with app.app_context():
        app.config['FEATURE_INVENTORY_SALES'] = False
    try:
        assert admin_client.get('/inventory').status_code == 404
        body = admin_client.get('/financials/summary?month=2026-10') \
            .get_data(as_text=True)
        assert 'Estimated Net Operating Position' not in body
        assert 'of which Sales (inventory)' not in body
        assert 'Inventory &amp; Sales' not in body
    finally:
        with app.app_context():
            app.config['FEATURE_INVENTORY_SALES'] = True

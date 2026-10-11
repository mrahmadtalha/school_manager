"""Inventory / sales service (Phase 3a+3b).

Purchases replenish stock and are NOT expenses — the item cost moves into
Cost of Goods Sold when the item is sold, using weighted-average cost
recalculated on every purchase.  All money is integer paisa internally.
"""
from datetime import date

from flask import current_app

from app.database import db
from app.models import Product, Purchase, Sale, to_paisa


def inventory_enabled():
    return current_app.config.get('FEATURE_INVENTORY_SALES', False)


def sales_beyond_stock_allowed():
    return current_app.config.get('ALLOW_SALES_BEYOND_STOCK', False)


def _actor_name(actor):
    return getattr(actor, 'username', None) or actor or 'system'


def record_purchase(product, quantity, unit_cost_rupees, supplier=None,
                    purchase_date=None, actor=None):
    """Add stock to a product (weighted-average cost recalculated)."""
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a whole number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    unit_cost = to_paisa(unit_cost_rupees)
    if unit_cost <= 0:
        raise ValueError('Purchase price must be greater than zero.')

    old_stock = product.stock_qty or 0
    old_cost = product.cost_paisa or 0
    product.stock_qty = old_stock + quantity
    product.cost_paisa = int(round(
        (old_stock * old_cost + quantity * unit_cost) / product.stock_qty))

    purchase = Purchase(
        product_id=product.id, quantity=quantity,
        unit_cost_paisa=unit_cost, total_cost_paisa=unit_cost * quantity,
        supplier=(supplier or None) and str(supplier)[:120],
        purchase_date=purchase_date or date.today(),
        created_by_name=_actor_name(actor))
    db.session.add(purchase)
    return purchase


def record_sale(product, quantity, note=None, sale_date=None, actor=None):
    """Sell quantity units: stock down, price/cost snapshotted, COGS booked."""
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a whole number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    stock = product.stock_qty or 0
    if quantity > stock and not sales_beyond_stock_allowed():
        raise ValueError('Only %d left in stock for %s.' % (stock, product.name))

    unit_price = product.sale_price_paisa or 0
    unit_cost = product.cost_paisa or 0
    sale = Sale(
        product_id=product.id, quantity=quantity,
        unit_price_paisa=unit_price, unit_cost_paisa=unit_cost,
        total_price_paisa=unit_price * quantity,
        total_cost_paisa=unit_cost * quantity,
        gross_profit_paisa=(unit_price - unit_cost) * quantity,
        sale_date=sale_date or date.today(),
        note=(note or None) and str(note)[:200],
        created_by_name=_actor_name(actor))
    db.session.add(sale)
    product.stock_qty = stock - quantity
    return sale


def low_stock_list():
    """Active products at or below their minimum stock level."""
    return [p for p in Product.query.filter_by(is_active=True).order_by(
        Product.name).all()
        if (p.min_stock_qty or 0) > 0 and p.stock_qty <= p.min_stock_qty]


def recent_sales(limit=15):
    return (Sale.query.order_by(Sale.created_at.desc(),
                                Sale.id.desc()).limit(limit).all())


def recent_purchases(limit=15):
    return (Purchase.query.order_by(Purchase.created_at.desc(),
                                    Purchase.id.desc()).limit(limit).all())


def month_sales_totals(start, end):
    """(sales income, COGS) in rupees for the inclusive date range."""
    rows = (db.session.query(
                db.func.coalesce(db.func.sum(Sale.total_price_paisa), 0),
                db.func.coalesce(db.func.sum(Sale.total_cost_paisa), 0))
            .filter(Sale.sale_date >= start, Sale.sale_date <= end)
            .first())
    return round(rows[0] / 100.0, 2), round(rows[1] / 100.0, 2)


def month_purchase_totals(start, end):
    """Inventory purchase payments in rupees for the inclusive date range."""
    total = (db.session.query(
                 db.func.coalesce(db.func.sum(Purchase.total_cost_paisa), 0))
             .filter(Purchase.purchase_date >= start,
                     Purchase.purchase_date <= end).scalar()) or 0
    return round(total / 100.0, 2)

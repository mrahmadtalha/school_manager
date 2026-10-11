"""Inventory / sales routes (Phase 3b): uniforms, books, stationery resale.

Everything here exists only while FEATURE_INVENTORY_SALES is on.  Purchases
replenish stock (they are not expenses); selling snapshots price and cost and
books the COGS.  Ordinary supplies bought for the school's own use belong in
/expenses, not here.
"""
from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.models import (Product, ROLE_ACCOUNTANT, ROLE_ADMIN,
                        ROLE_OWNER)
from app.routes import main
from app.security import role_required
from app.services import inventory_service
from app.services.audit import log_action

INVENTORY_ROLES = (ROLE_ADMIN, ROLE_OWNER, ROLE_ACCOUNTANT)


def _feature_on():
    if not inventory_service.inventory_enabled():
        abort(404)


def _parse_date(value):
    value = (value or '').strip()
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


@main.route('/inventory')
@role_required(*INVENTORY_ROLES)
def inventory_page():
    _feature_on()
    products = (Product.query.order_by(Product.is_active.desc(), Product.name)
                .all())
    low_stock = inventory_service.low_stock_list()
    return render_template(
        'inventory.html',
        products=products,
        low_stock=low_stock,
        sales=inventory_service.recent_sales(),
        purchases=inventory_service.recent_purchases(),
        today=date.today())


@main.route('/inventory/products/add', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_product_add():
    _feature_on()
    name = (request.form.get('name') or '').strip()
    category = (request.form.get('category') or 'Other').strip() or 'Other'
    supplier = (request.form.get('supplier') or '').strip()
    try:
        sale_price = float((request.form.get('sale_price') or '').strip())
        min_stock = int(request.form.get('min_stock') or 0)
    except ValueError:
        sale_price, min_stock = -1, 0

    if not name:
        flash('Product name is required.', 'danger')
    elif sale_price < 0:
        flash('Selling price must be a valid amount.', 'danger')
    elif Product.query.filter(db.func.lower(Product.name) == name.lower(),
                              Product.is_active.is_(True)).first():
        flash('An active product with that name already exists.', 'warning')
    else:
        product = Product(
            name=name[:120], category=category[:80],
            sale_price_paisa=inventory_service.to_paisa(sale_price),
            min_stock_qty=max(0, min_stock), supplier=supplier[:120] or None)
        db.session.add(product)
        db.session.commit()
        log_action('create', entity_type='Product', entity_id=product.id,
                   summary='Product added: %s' % product.name)
        flash('Product "%s" added. Record a purchase to stock it.'
              % product.name, 'success')
    return redirect(url_for('main.inventory_page'))


@main.route('/inventory/purchase', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_purchase():
    _feature_on()
    product = db.session.get(Product,
                             request.form.get('product_id', type=int) or 0)
    purchase_date = _parse_date(request.form.get('purchase_date'))
    try:
        unit_cost = float((request.form.get('unit_cost') or '').strip())
    except ValueError:
        unit_cost = -1
    if product is None:
        flash('Please choose a product.', 'danger')
    elif purchase_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif unit_cost < 0:
        flash('Purchase price must be a valid amount.', 'danger')
    else:
        try:
            purchase = inventory_service.record_purchase(
                product, request.form.get('quantity'), unit_cost,
                supplier=request.form.get('supplier'),
                purchase_date=purchase_date, actor=current_user)
            log_action('create', entity_type='Purchase', entity_id=purchase.id,
                       summary='Stock purchased: %d x %s' % (
                           purchase.quantity, product.name))
            db.session.commit()
            flash('Stock added: %d x %s. Stock is not an expense — its cost '
                  'becomes Cost of Goods Sold when items are sold.'
                  % (purchase.quantity, product.name), 'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page'))


@main.route('/inventory/sell', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_sell():
    _feature_on()
    product = db.session.get(Product,
                             request.form.get('product_id', type=int) or 0)
    sale_date = _parse_date(request.form.get('sale_date'))
    note = (request.form.get('note') or '').strip()
    if product is None:
        flash('Please choose a product.', 'danger')
    elif sale_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    else:
        try:
            sale = inventory_service.record_sale(
                product, request.form.get('quantity'), note=note,
                sale_date=sale_date, actor=current_user)
            log_action('create', entity_type='Sale', entity_id=sale.id,
                       summary='Sale: %d x %s for Rs %s' % (
                           sale.quantity, product.name,
                           '{:,.2f}'.format(sale.total_price_paisa / 100.0)))
            db.session.commit()
            flash('Sold %d x %s — Rs %s received, cost Rs %s, gross profit '
                  'Rs %s.' % (
                      sale.quantity, product.name,
                      '{:,.2f}'.format(sale.total_price_paisa / 100.0),
                      '{:,.2f}'.format(sale.total_cost_paisa / 100.0),
                      '{:,.2f}'.format(sale.gross_profit_paisa / 100.0)),
                  'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page'))


@main.route('/inventory/products/<int:product_id>/toggle', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_product_toggle(product_id):
    _feature_on()
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    log_action('update', entity_type='Product', entity_id=product.id,
               summary='%s: %s' % (
                   product.name, 'active' if product.is_active else 'retired'))
    flash('Product %s.' % ('active' if product.is_active else 'retired'),
          'success')
    return redirect(url_for('main.inventory_page'))

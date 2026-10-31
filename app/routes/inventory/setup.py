"""Inventory pricing, opening stock and canteen mode."""

from flask import flash, redirect, request, url_for
from flask_login import current_user
from app.database import db
from app.models import (
    CanteenEntry,
    CanteenPayment,
    Product,
    ProductSet,
    Purchase,
    Sale,
    ROLE_ADMIN,
    ROLE_OWNER,
)
from app.routes import main
from app.security import role_required
from app.services import canteen_service, inventory_service, student_stock
from app.services.audit import log_action

from app.routes.inventory.stock import INVENTORY_ROLES, _feature_on, _parse_date, _payment_args


@main.route('/inventory/sets/<int:set_id>/buy', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_set_buy(set_id):
    _feature_on()
    target = ProductSet.query.get_or_404(set_id)
    purchase_date = _parse_date(request.form.get('purchase_date'))
    try:
        total = float((request.form.get('total_bill') or '').strip().replace(',', ''))
    except ValueError:
        total = -1
    paid_raw = (request.form.get('paid_now') or '').strip().replace(',', '')
    try:
        paid_now = float(paid_raw) if paid_raw else None
    except ValueError:
        paid_now = -1
    if purchase_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif total <= 0:
        flash('Please enter the total bill of the set purchase.', 'danger')
    elif paid_now is not None and paid_now < 0:
        flash('The amount paid must be a valid amount.', 'danger')
    else:
        try:
            rows = inventory_service.purchase_set(
                target, request.form.get('number_of_sets'), total,
                supplier=request.form.get('supplier'),
                purchase_date=purchase_date, actor=current_user,
                paid_rupees=paid_now)
            for row in rows:
                db.session.flush()
                log_action('create', entity_type='Purchase', entity_id=row.id,
                           summary='Stock purchased: %d x %s (%s)' % (
                               row.quantity, row.product.name, row.bill_label))
            db.session.commit()
            owed = sum(r.balance_paisa for r in rows)
            message = 'Set stock added: %s — %d items filled.' % (
                rows[0].bill_label, len(rows))
            if owed:
                message += ' Bill %s, still owed to %s: %s.' % (
                    inventory_service.money(sum(r.total_cost_paisa for r in rows)),
                    rows[0].supplier or 'the supplier',
                    inventory_service.money(owed))
            flash(message, 'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#sets')


@main.route('/inventory/sets/<int:set_id>/sell', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_set_sell(set_id):
    _feature_on()
    target = ProductSet.query.get_or_404(set_id)
    sale_date = _parse_date(request.form.get('sale_date'))
    student_ref = (request.form.get('student') or '').strip()
    student = student_stock.find_student(student_ref) if student_ref else None
    if sale_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif student_ref and student is None:
        flash('Please pick the student from the suggestions (or leave the box empty).',
              'danger')
    else:
        try:
            sales = inventory_service.sell_set(
                target, request.form.get('number_of_sets'),
                note=request.form.get('note'), sale_date=sale_date,
                actor=current_user, student_id=student.id if student else None)
            for sale in sales:
                db.session.flush()
                log_action('create', entity_type='Sale', entity_id=sale.id,
                           summary='Sale: %d x %s for Rs %s' % (
                               sale.quantity, sale.product.name,
                               '{:,.2f}'.format(sale.total_price_paisa / 100.0)))
            db.session.commit()
            flash('Sold %s — Rs %s received, gross profit Rs %s.' % (
                'Set: %s x %s' % (target.name, request.form.get('number_of_sets')),
                '{:,.2f}'.format(sum(s.total_price_paisa for s in sales) / 100.0),
                '{:,.2f}'.format(sum(s.gross_profit_paisa for s in sales) / 100.0)),
                'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#sets')


@main.route('/inventory/opening-stock', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_opening_stock():
    """Put stock that is already on the shelf into Inventory (no money paid)."""
    _feature_on()
    product = db.session.get(Product, request.form.get('product_id', type=int) or 0)
    as_of = _parse_date(request.form.get('as_of'))
    try:
        unit_cost = float((request.form.get('unit_cost') or '').strip().replace(',', ''))
    except ValueError:
        unit_cost = -1
    if product is None:
        flash('Please choose a product.', 'danger')
    elif as_of is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif unit_cost <= 0:
        flash('Enter what one piece cost you (your best estimate is fine).', 'danger')
    else:
        try:
            row = inventory_service.record_opening_stock(
                product, request.form.get('quantity'), unit_cost, as_of=as_of,
                actor=current_user)
            db.session.flush()
            log_action('create', entity_type='Purchase', entity_id=row.id,
                       summary='Opening stock: %d x %s' % (row.quantity, product.name))
            db.session.commit()
            flash('Opening stock added: %d x %s. Nothing was paid, so it is not '
                  'cash out and not a supplier due.' % (row.quantity, product.name),
                  'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#setup')


@main.route('/inventory/canteen/mode', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_canteen_mode():
    _feature_on()
    mode = (request.form.get('mode') or '').strip()
    try:
        canteen_service.set_mode(mode)
        log_action('settings_change', entity_type='Canteen',
                   summary='Canteen is kept: %s' % canteen_service.MODE_LABELS[mode])
        db.session.commit()
        flash('Canteen: %s.' % canteen_service.MODE_LABELS[mode], 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#canteen')


@main.route('/inventory/canteen/total', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_canteen_total():
    """Add one canteen total (sales or purchases) - the "totals only" way."""
    _feature_on()
    kind = (request.form.get('kind') or '').strip()
    entry_date = _parse_date(request.form.get('entry_date'))
    try:
        amount = float((request.form.get('amount') or '').strip().replace(',', ''))
    except ValueError:
        amount = -1
    if entry_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif amount <= 0:
        flash('Please enter an amount greater than zero.', 'danger')
    else:
        try:
            paid_text = (request.form.get('paid_now') or '').strip().replace(',', '')
            try:
                paid_now = float(paid_text) if paid_text else None
            except ValueError:
                raise ValueError('Please enter a valid amount for "Paid now".')
            entry = canteen_service.record_total(
                kind, amount, entry_date, note=request.form.get('note'),
                actor=current_user, supplier=request.form.get('supplier'),
                paid_rupees=paid_now)
            log_action('create', entity_type='CanteenEntry', entity_id=entry.id,
                       summary='Canteen %s total: Rs %s (%s)' % (
                           'sales' if kind == 'sale' else 'purchases',
                           '{:,.2f}'.format(amount), entry_date.strftime('%d %b %Y')))
            db.session.commit()
            message = 'Canteen %s total of Rs. %s saved.' % (
                'sales' if kind == 'sale' else 'purchases', '{:,.2f}'.format(amount))
            if entry.is_credit:
                message += ' Still owed to %s: %s.' % (
                    entry.supplier or 'the supplier',
                    inventory_service.money(entry.balance_paisa))
            flash(message, 'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page',
                            month=entry_date.strftime('%Y-%m') if entry_date else None)
                    + '#canteen')


@main.route('/inventory/canteen/entries/<int:entry_id>/pay', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_canteen_entry_pay(entry_id):
    """Pay (part of) what is still owed on one canteen purchase total."""
    _feature_on()
    entry = CanteenEntry.query.get_or_404(entry_id)
    pay_date, amount, method, note = _payment_args()
    if pay_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    else:
        try:
            payment = canteen_service.pay_entry(
                entry, amount, pay_date, method, note, actor=current_user)
            log_action('payment', entity_type='CanteenPayment', entity_id=payment.id,
                       summary='Paid %s to %s (canteen bill #%d)' % (
                           inventory_service.money(payment.amount_paisa),
                           entry.supplier or 'supplier', entry.id))
            db.session.commit()
            flash('Paid %s. Still owed on this bill: %s.' % (
                inventory_service.money(payment.amount_paisa),
                inventory_service.money(entry.balance_paisa)), 'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#canteen')


@main.route('/inventory/canteen/payments/<int:payment_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_canteen_payment_void(payment_id):
    _feature_on()
    payment = CanteenPayment.query.get_or_404(payment_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        canteen_service.void_payment(payment, reason, actor=current_user)
        log_action('void', entity_type='CanteenPayment', entity_id=payment.id,
                   summary='Canteen supplier payment voided: %s' % reason[:120])
        db.session.commit()
        flash('Payment voided - the amount is owed to the supplier again.', 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#canteen')


@main.route('/inventory/canteen/entries/<int:entry_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_canteen_entry_void(entry_id):
    _feature_on()
    entry = CanteenEntry.query.get_or_404(entry_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        canteen_service.void_entry(entry, reason, actor=current_user)
        log_action('void', entity_type='CanteenEntry', entity_id=entry.id,
                   summary='Canteen entry voided: %s' % reason[:120])
        db.session.commit()
        flash('Canteen entry voided - it no longer counts in any total.', 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#canteen')


@main.route('/inventory/sales/<int:sale_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_sale_void(sale_id):
    _feature_on()
    sale = Sale.query.get_or_404(sale_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        rows = inventory_service.void_sale(sale, reason, actor=current_user)
        for row in rows:
            log_action('void', entity_type='Sale', entity_id=row.id,
                       summary='Sale voided: %d x %s (%s)' % (
                           row.quantity, row.product.name, reason[:120]))
        db.session.commit()
        flash('Sale undone - %d item line(s) are back in stock and the sale no '
              'longer counts in any total.' % len(rows), 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#products')


@main.route('/inventory/purchases/<int:purchase_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_purchase_void(purchase_id):
    _feature_on()
    purchase = Purchase.query.get_or_404(purchase_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        rows = inventory_service.void_purchase(purchase, reason, actor=current_user)
        for row in rows:
            log_action('void', entity_type='Purchase', entity_id=row.id,
                       summary='Purchase voided: %d x %s (%s)' % (
                           row.quantity, row.product.name, reason[:120]))
        db.session.commit()
        flash('Purchase undone - the stock was taken off the shelf and the bill '
              'no longer counts as cash out or as a supplier due.', 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#products')

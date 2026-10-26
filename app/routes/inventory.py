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
from app.models import (CanteenEntry, CanteenPayment, ClassModel, Product, ProductSet, Purchase, Sale,
                        ROLE_ACCOUNTANT,
                        ROLE_ADMIN, ROLE_OWNER, SET_KINDS, StudentIssue,
                        SupplierPayment)
from app.routes import main
from app.security import role_required
from app.services import (canteen_service, inventory_service, payroll_service,
                          student_stock)
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
    month = _canteen_month()
    month_start, month_end = payroll_service.month_bounds(month)
    return render_template(
        'inventory.html',
        products=products,
        low_stock=low_stock,
        sales=inventory_service.recent_sales(),
        purchases=inventory_service.recent_purchases(),
        dues=([dict(d, source='inventory') for d in inventory_service.supplier_dues()]
              + canteen_service.supplier_dues()),
        canteen_payments=canteen_service.recent_payments(),
        canteen_suppliers=sorted({(e.supplier or '').strip() for e in
                                  CanteenEntry.query.filter(CanteenEntry.supplier.isnot(None)).all()
                                  if (e.supplier or '').strip()}),
        dues_total=inventory_service.total_supplier_dues_paisa(),
        open_bills=inventory_service.open_bills(),
        supplier_payments=inventory_service.recent_supplier_payments(),
        suppliers=inventory_service.known_suppliers(),
        sets_view=_sets_view(),
        pending_issues=student_stock.pending_rows(),
        recent_issues=student_stock.recent_issues(),
        student_choices=student_stock.student_choices(),
        set_kinds=SET_KINDS,
        classes=ClassModel.query.order_by(ClassModel.name).all(),
        setup=canteen_service.setup_status(),
        canteen_mode=canteen_service.get_mode(),
        canteen_modes=canteen_service.MODE_LABELS,
        canteen=canteen_service.month_summary(month_start, month_end),
        canteen_entries=canteen_service.recent_entries(),
        canteen_products=canteen_service.canteen_products(active_only=False),
        canteen_month=month,
        canteen_month_label=payroll_service.month_label(month),
        canteen_prev=payroll_service.shift_month(month, -1),
        canteen_next=payroll_service.shift_month(month, 1),
        today=date.today())


def _canteen_month():
    value = (request.args.get('month') or '').strip()
    return value if payroll_service.parse_month(value) \
        else payroll_service.current_month_key()


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
    paid_raw = (request.form.get('paid_now') or '').strip().replace(',', '')
    try:
        paid_now = float(paid_raw) if paid_raw else None
    except ValueError:
        paid_now = -1
    if product is None:
        flash('Please choose a product.', 'danger')
    elif purchase_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif unit_cost < 0:
        flash('Purchase price must be a valid amount.', 'danger')
    elif paid_now is not None and paid_now < 0:
        flash('The amount paid must be a valid amount.', 'danger')
    else:
        try:
            purchase = inventory_service.record_purchase(
                product, request.form.get('quantity'), unit_cost,
                supplier=request.form.get('supplier'),
                purchase_date=purchase_date, actor=current_user,
                paid_rupees=paid_now)
            log_action('create', entity_type='Purchase', entity_id=purchase.id,
                       summary='Stock purchased: %d x %s' % (
                           purchase.quantity, product.name))
            db.session.commit()
            message = ('Stock added: %d x %s. Stock is not an expense — its cost '
                       'becomes Cost of Goods Sold when items are sold.'
                       % (purchase.quantity, product.name))
            if purchase.balance_paisa:
                message += (' Bill %s, paid %s, still owed to %s: %s.' % (
                    inventory_service.money(purchase.total_cost_paisa),
                    inventory_service.money(purchase.paid_total_paisa),
                    purchase.supplier or 'the supplier',
                    inventory_service.money(purchase.balance_paisa)))
            flash(message, 'success')
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
    student_ref = (request.form.get('student') or '').strip()
    student = student_stock.find_student(student_ref) if student_ref else None
    # "Already paid in the admission fee": stock only, no new income.
    in_admission = request.form.get('in_admission') == '1'
    if product is None:
        flash('Please choose a product.', 'danger')
    elif sale_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif student_ref and student is None:
        flash('Please pick the student from the suggestions (or leave the box empty).',
              'danger')
    elif in_admission and student is None:
        flash('Choose the student whose admission fee already covers this item.',
              'danger')
    elif in_admission:
        try:
            issue = student_stock.issue_item(student, product,
                                             request.form.get('quantity'),
                                             actor=current_user,
                                             issue_date=sale_date, note=note)
            log_action('create', entity_type='StudentIssue', entity_id=issue.id,
                       summary='Item given with admission: %s to %s' % (
                           issue.label, student.student_name))
            db.session.commit()
            flash('Stock reduced: %s given to %s. No new income - it is already '
                  'in the admission fee.' % (issue.label, student.student_name),
                  'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    else:
        try:
            sale = inventory_service.record_sale(
                product, request.form.get('quantity'), note=note,
                sale_date=sale_date, actor=current_user,
                student_id=student.id if student else None)
            log_action('create', entity_type='Sale', entity_id=sale.id,
                       summary='Sale: %d x %s for Rs %s' % (
                           sale.quantity, product.name,
                           '{:,.2f}'.format(sale.total_price_paisa / 100.0)))
            db.session.commit()
            flash('Sold %d x %s%s — Rs %s received, cost Rs %s, gross profit '
                  'Rs %s.' % (
                      sale.quantity, product.name,
                      (' to %s' % student.student_name) if student else '',
                      '{:,.2f}'.format(sale.total_price_paisa / 100.0),
                      '{:,.2f}'.format(sale.total_cost_paisa / 100.0),
                      '{:,.2f}'.format(sale.gross_profit_paisa / 100.0)),
                  'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page'))


# --------------------------------------------------------------------------- #
# Student stock (Phase 3): books / uniform given at admission
# --------------------------------------------------------------------------- #

@main.route('/inventory/student-stock/<int:student_id>/issue', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_student_issue(student_id):
    """"Issue now": hand over the books / uniform still pending for a student."""
    _feature_on()
    from app.models import StudentModel
    student = StudentModel.query.get_or_404(student_id)
    try:
        messages = student_stock.sync_student_stock(student, actor=current_user)
        db.session.commit()
        if not messages:
            flash('Nothing is pending for %s.' % student.student_name, 'info')
        for category, text in messages:
            flash(text, category)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#studentStock')


@main.route('/inventory/issues/<int:issue_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_issue_void(issue_id):
    _feature_on()
    issue = StudentIssue.query.get_or_404(issue_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        student_stock.void_issue(issue, reason, actor=current_user)
        log_action('void', entity_type='StudentIssue', entity_id=issue.id,
                   summary='Student stock issue voided: %s (%s)' % (
                       issue.label, reason[:120]))
        db.session.commit()
        flash('Issue voided - the stock is back in Inventory.', 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#studentStock')


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


def _payment_args():
    pay_date = _parse_date(request.form.get('payment_date'))
    try:
        amount = float((request.form.get('amount') or '').strip().replace(',', ''))
    except ValueError:
        amount = 0
    return (pay_date, amount, request.form.get('method'),
            (request.form.get('note') or '').strip())


@main.route('/inventory/purchases/<int:purchase_id>/pay', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_purchase_pay(purchase_id):
    _feature_on()
    purchase = Purchase.query.get_or_404(purchase_id)
    pay_date, amount, method, note = _payment_args()
    if pay_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    else:
        try:
            payment = inventory_service.pay_purchase(
                purchase, amount, pay_date, method, note, actor=current_user)
            log_action('payment', entity_type='SupplierPayment',
                       entity_id=payment.id,
                       summary='Paid %s to %s (bill #%d)' % (
                           inventory_service.money(payment.amount_paisa),
                           purchase.supplier or 'supplier', purchase.id))
            db.session.commit()
            flash('Paid %s. Still owed on this bill: %s.' % (
                inventory_service.money(payment.amount_paisa),
                inventory_service.money(purchase.balance_paisa)), 'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page'))


@main.route('/inventory/suppliers/pay', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_supplier_pay():
    _feature_on()
    supplier = request.form.get('supplier') or inventory_service.NO_SUPPLIER
    pay_date, amount, method, note = _payment_args()
    if pay_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    elif request.form.get('source') == 'canteen':
        try:
            made = canteen_service.pay_supplier(
                supplier, amount, pay_date, method, note, actor=current_user)
            total = sum(p.amount_paisa for p in made)
            for payment in made:
                log_action('payment', entity_type='CanteenPayment',
                           entity_id=payment.id,
                           summary='Paid %s to %s (canteen bill #%d)' % (
                               inventory_service.money(payment.amount_paisa),
                               supplier or 'supplier', payment.entry_id))
            db.session.commit()
            flash('Paid %s to %s (canteen). Still owed to this supplier: %s.' % (
                inventory_service.money(total), supplier or 'the supplier',
                inventory_service.money(sum(
                    b.balance_paisa for b in canteen_service.open_bills(supplier)))),
                'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    else:
        try:
            made = inventory_service.pay_supplier(
                supplier, amount, pay_date, method, note, actor=current_user)
            total = sum(p.amount_paisa for p in made)
            for payment in made:
                log_action('payment', entity_type='SupplierPayment',
                           entity_id=payment.id,
                           summary='Paid %s to %s (bill #%d)' % (
                               inventory_service.money(payment.amount_paisa),
                               supplier or 'supplier', payment.purchase_id))
            db.session.commit()
            flash('Paid %s to %s. Still owed to this supplier: %s.' % (
                inventory_service.money(total), supplier or 'the supplier',
                inventory_service.money(sum(
                    b.balance_paisa for b in inventory_service.open_bills(supplier)))),
                'success')
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page'))


@main.route('/inventory/supplier-payments/<int:payment_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_supplier_payment_void(payment_id):
    _feature_on()
    payment = SupplierPayment.query.get_or_404(payment_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        inventory_service.void_supplier_payment(payment, reason, actor=current_user)
        log_action('void', entity_type='SupplierPayment', entity_id=payment.id,
                   summary='Supplier payment voided: %s' % reason[:120])
        db.session.commit()
        flash('Payment voided — the amount is owed to the supplier again.', 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page'))


# --------------------------------------------------------------------------- #
# Sets (bundles of items)
# --------------------------------------------------------------------------- #

def _sets_view():
    """Everything the Sets box needs, one dict per set (active first)."""
    rows = []
    sets = (ProductSet.query.order_by(ProductSet.is_active.desc(), ProductSet.name)
            .all())
    for target in sets:
        rows.append({
            'id': target.id, 'name': target.name, 'kind': target.kind,
            'class_id': target.class_id,
            'class_name': target.class_.name if target.class_ else '',
            'is_active': target.is_active,
            'items': [{'product_id': i.product_id, 'name': i.product.name,
                       'qty': i.quantity} for i in target.items],
            'price': inventory_service.set_price_paisa(target),
            'cost': inventory_service.set_cost_paisa(target),
            'available': inventory_service.sets_available(target),
        })
    return rows


def _set_form():
    """``(name, items, kind, class_id)`` from the add / edit set form."""
    items = list(zip(request.form.getlist('item_product'),
                     request.form.getlist('item_qty')))
    items = [(p, q) for p, q in items if (p or '').strip()]
    return ((request.form.get('name') or '').strip(), items,
            request.form.get('kind'), request.form.get('class_id', type=int))


@main.route('/inventory/sets/add', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_set_add():
    _feature_on()
    name, items, kind, class_id = _set_form()
    try:
        new = inventory_service.create_set(name, items, kind, class_id)
        log_action('create', entity_type='ProductSet', entity_id=new.id,
                   summary='Set added: %s (%d items)' % (new.name, len(new.items)))
        db.session.commit()
        flash('Set "%s" added. Use Buy to put its stock in.' % new.name, 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#sets')


@main.route('/inventory/sets/<int:set_id>/edit', methods=['POST'])
@role_required(*INVENTORY_ROLES)
def inventory_set_edit(set_id):
    _feature_on()
    target = ProductSet.query.get_or_404(set_id)
    name, items, kind, class_id = _set_form()
    try:
        inventory_service.update_set(target, name, items, kind, class_id)
        log_action('update', entity_type='ProductSet', entity_id=target.id,
                   summary='Set changed: %s' % target.name)
        db.session.commit()
        flash('Set "%s" saved. Earlier purchases and sales are unchanged.'
              % target.name, 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.inventory_page') + '#sets')


@main.route('/inventory/sets/<int:set_id>/toggle', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def inventory_set_toggle(set_id):
    _feature_on()
    target = ProductSet.query.get_or_404(set_id)
    if not target.is_active and ProductSet.query.filter(
            db.func.lower(ProductSet.name) == target.name.lower(),
            ProductSet.is_active.is_(True)).first():
        flash('An active set with that name already exists.', 'warning')
    else:
        target.is_active = not target.is_active
        db.session.commit()
        log_action('update', entity_type='ProductSet', entity_id=target.id,
                   summary='%s: %s' % (target.name,
                                       'active' if target.is_active else 'retired'))
        flash('Set %s.' % ('active' if target.is_active else 'retired'), 'success')
    return redirect(url_for('main.inventory_page') + '#sets')


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


# --------------------------------------------------------------------------- #
# Phase 4: opening stock, canteen and the setup checklist
# --------------------------------------------------------------------------- #

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



# --------------------------------------------------------------------------- #
# Fixing mistakes: void a sale / a purchase
# --------------------------------------------------------------------------- #

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

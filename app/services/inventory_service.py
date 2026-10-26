"""Inventory / sales service (Phase 3a+3b).

Purchases replenish stock and are NOT expenses — the item cost moves into
Cost of Goods Sold when the item is sold, using weighted-average cost
recalculated on every purchase.  All money is integer paisa internally.
"""
from datetime import date

from flask import current_app

from app.database import db
from app.models import (Product, ProductSet, ProductSetItem, Purchase, Sale,
                        SupplierPayment, to_paisa)


def inventory_enabled():
    return current_app.config.get('FEATURE_INVENTORY_SALES', False)


def sales_beyond_stock_allowed():
    return current_app.config.get('ALLOW_SALES_BEYOND_STOCK', False)


def money(paisa):
    return 'Rs %s' % '{:,.2f}'.format((paisa or 0) / 100.0)


def _actor_name(actor):
    return getattr(actor, 'username', None) or actor or 'system'


def record_purchase(product, quantity, unit_cost_rupees, supplier=None,
                    purchase_date=None, actor=None, paid_rupees=None):
    """Add stock to a product (weighted-average cost recalculated).

    ``paid_rupees`` is what was handed to the supplier today.  ``None`` (the
    default) means paid in full; anything less leaves the rest as a supplier
    due that can be paid later with ``pay_purchase`` / ``pay_supplier``.
    """
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a whole number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    unit_cost = to_paisa(unit_cost_rupees)
    if unit_cost <= 0:
        raise ValueError('Purchase price must be greater than zero.')

    total = unit_cost * quantity
    paid = _paid_paisa(paid_rupees, total)
    return _add_stock(product, quantity, total, unit_cost, paid, supplier,
                      purchase_date, actor)


def _paid_paisa(paid_rupees, total):
    """Paid-now in paisa: blank / None = the whole bill; never above the bill."""
    if paid_rupees is None or (isinstance(paid_rupees, str) and not paid_rupees.strip()):
        return total
    paid = to_paisa(paid_rupees)
    if paid < 0:
        raise ValueError('The amount paid cannot be negative.')
    if paid > total:
        raise ValueError('The amount paid (%s) is more than the total bill (%s).'
                         % (money(paid), money(total)))
    return paid


def _add_stock(product, quantity, total, unit_cost, paid, supplier, purchase_date,
               actor, bill_label=None, is_opening=False):
    """Book one purchase line: stock up, weighted-average cost, the bill row."""
    old_stock = product.stock_qty or 0
    old_cost = product.cost_paisa or 0
    product.stock_qty = old_stock + quantity
    product.cost_paisa = int(round(
        (old_stock * old_cost + total) / product.stock_qty))

    purchase = Purchase(
        product_id=product.id, quantity=quantity,
        unit_cost_paisa=unit_cost, total_cost_paisa=total, paid_paisa=paid,
        supplier=((supplier or '').strip() or None) and str(supplier).strip()[:120],
        purchase_date=purchase_date or date.today(),
        bill_label=bill_label, is_opening=bool(is_opening),
        created_by_name=_actor_name(actor))
    db.session.add(purchase)
    return purchase


def record_opening_stock(product, quantity, unit_cost_rupees, as_of=None, actor=None):
    """Put stock that is ALREADY on the shelf into Inventory (setup step).

    The quantity and its cost are booked exactly like a purchase (so the
    weighted-average cost and later Cost of Goods Sold are right), but nobody
    is paid: it is never cash out and never a supplier due.  Does not commit.
    """
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a whole number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    unit_cost = to_paisa(unit_cost_rupees)
    if unit_cost <= 0:
        raise ValueError('Enter what one piece cost you (your best estimate is fine).')
    as_of = as_of or date.today()
    if as_of > date.today():
        raise ValueError('The opening stock date cannot be in the future.')
    total = unit_cost * quantity
    return _add_stock(product, quantity, total, unit_cost, total, None, as_of,
                      actor, bill_label='Opening stock', is_opening=True)


def record_sale(product, quantity, note=None, sale_date=None, actor=None,
                student_id=None, admission_issue=None):
    """Sell quantity units: stock down, price/cost snapshotted, COGS booked.

    ``student_id`` links the sale to a student.  ``admission_issue`` (a
    ``StudentIssue``) marks stock handed over as part of the admission package:
    the price is booked as 0 because the money is already income through the
    admission fee, so revenue is never counted twice (the cost still is COGS).
    """
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a whole number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    stock = product.stock_qty or 0
    if quantity > stock and not sales_beyond_stock_allowed():
        raise ValueError('Only %d left in stock for %s.' % (stock, product.name))

    unit_price = 0 if admission_issue is not None else (product.sale_price_paisa or 0)
    unit_cost = product.cost_paisa or 0
    sale = Sale(
        product_id=product.id, quantity=quantity,
        unit_price_paisa=unit_price, unit_cost_paisa=unit_cost,
        total_price_paisa=unit_price * quantity,
        total_cost_paisa=unit_cost * quantity,
        gross_profit_paisa=(unit_price - unit_cost) * quantity,
        sale_date=sale_date or date.today(),
        note=(note or None) and str(note)[:200],
        student_id=student_id,
        source='admission' if admission_issue is not None else 'sale',
        created_by_name=_actor_name(actor))
    if admission_issue is not None:
        sale.issue = admission_issue
    db.session.add(sale)
    product.stock_qty = stock - quantity
    return sale


def low_stock_list():
    """Active products at or below their minimum stock level."""
    return [p for p in Product.query.filter_by(is_active=True).order_by(
        Product.name).all()
        if (p.min_stock_qty or 0) > 0 and p.stock_qty <= p.min_stock_qty]


def recent_sales(limit=15):
    return (Sale.query.filter(Sale.is_void.is_(False))
            .order_by(Sale.created_at.desc(), Sale.id.desc()).limit(limit).all())


def recent_purchases(limit=15):
    return (Purchase.query.order_by(Purchase.created_at.desc(),
                                    Purchase.id.desc()).limit(limit).all())


def month_sales_breakdown(start, end):
    """Sales figures (rupees) for the inclusive date range, one query.

    ``sales``          money received for items sold across the counter
    ``cogs``           cost of every item that left the shelf
    ``package_cogs``   part of ``cogs`` that went out INSIDE an admission package
                       (its price is already part of the admission fee)
    ``direct_cogs``    the rest: cost of the items that were sold separately
    """
    row = (db.session.query(
               db.func.coalesce(db.func.sum(Sale.total_price_paisa), 0),
               db.func.coalesce(db.func.sum(Sale.total_cost_paisa), 0),
               db.func.coalesce(db.func.sum(db.case(
                   (Sale.source == 'admission', Sale.total_cost_paisa), else_=0)), 0))
           .filter(Sale.sale_date >= start, Sale.sale_date <= end,
                   Sale.is_void.is_(False)).first())
    sales, cogs, package = (row[0] or 0), (row[1] or 0), (row[2] or 0)
    return {'sales': round(sales / 100.0, 2), 'cogs': round(cogs / 100.0, 2),
            'package_cogs': round(package / 100.0, 2),
            'direct_cogs': round((cogs - package) / 100.0, 2)}


def month_sales_totals(start, end):
    """(sales income, COGS) in rupees for the inclusive date range."""
    data = month_sales_breakdown(start, end)
    return data['sales'], data['cogs']


def month_purchase_totals(start, end):
    """Money actually PAID to suppliers in the inclusive date range (rupees).

    That is the part paid on the purchase day plus later instalments by their
    payment date.  The unpaid part is a supplier due, not cash out.  Opening
    stock (already owned when Inventory was set up) is never cash out.
    """
    return round(sum(purchase_payment_buckets(start, end).values()), 2)


def purchase_payment_buckets(start, end):
    """``{'YYYY-MM': rupees}`` paid to suppliers, grouped by month."""
    buckets = {}
    at_purchase = (db.session.query(
            db.func.strftime('%Y-%m', Purchase.purchase_date),
            db.func.coalesce(db.func.sum(
                db.func.coalesce(Purchase.paid_paisa, Purchase.total_cost_paisa)), 0))
        .filter(Purchase.purchase_date >= start, Purchase.purchase_date <= end,
                Purchase.is_opening.is_(False), Purchase.is_void.is_(False))
        .group_by(db.func.strftime('%Y-%m', Purchase.purchase_date)).all())
    later = (db.session.query(
            db.func.strftime('%Y-%m', SupplierPayment.payment_date),
            db.func.coalesce(db.func.sum(SupplierPayment.amount_paisa), 0))
        .filter(SupplierPayment.is_void.is_(False),
                SupplierPayment.payment_date >= start,
                SupplierPayment.payment_date <= end)
        .group_by(db.func.strftime('%Y-%m', SupplierPayment.payment_date)).all())
    for key, value in list(at_purchase) + list(later):
        buckets[key] = buckets.get(key, 0) + value
    return {key: round(value / 100.0, 2) for key, value in buckets.items()}


# --------------------------------------------------------------------------- #
# Supplier dues
# --------------------------------------------------------------------------- #

NO_SUPPLIER = 'No supplier name'
PAYMENT_METHODS = ('cash', 'bank', 'cheque', 'online')


def open_bills(supplier=None):
    """Purchases that still owe money, oldest first.

    ``supplier`` filters by name (``NO_SUPPLIER`` / '' = purchases without a
    name); ``None`` means every supplier.
    """
    rows = (Purchase.query.filter(Purchase.is_void.is_(False))
            .order_by(Purchase.purchase_date, Purchase.id).all())
    bills = [p for p in rows if p.balance_paisa > 0]
    if supplier is not None:
        wanted = '' if supplier == NO_SUPPLIER else (supplier or '').strip().lower()
        bills = [p for p in bills if (p.supplier or '').strip().lower() == wanted]
    return bills


def supplier_dues():
    """One row per supplier that is still owed money, biggest balance first.

    ``[{'supplier', 'bills', 'total', 'paid', 'balance'}]`` (paisa).
    """
    groups = {}
    for bill in open_bills():
        name = (bill.supplier or '').strip() or NO_SUPPLIER
        key = name.lower()
        row = groups.setdefault(key, {'supplier': name, 'bills': 0, 'total': 0,
                                      'paid': 0, 'balance': 0})
        row['bills'] += 1
        row['total'] += bill.total_cost_paisa
        row['paid'] += bill.paid_total_paisa
        row['balance'] += bill.balance_paisa
    return sorted(groups.values(), key=lambda r: (-r['balance'], r['supplier'].lower()))


def total_supplier_dues_paisa():
    """Everything still owed to suppliers: stock purchases plus canteen totals."""
    from app.services import canteen_service
    return (sum(bill.balance_paisa for bill in open_bills())
            + canteen_service.total_owed_paisa())


def _clean_method(method):
    method = (method or 'cash').strip().lower()
    return method if method in PAYMENT_METHODS else 'cash'


def _check_payment(amount_rupees, pay_date):
    amount = to_paisa(amount_rupees)
    if amount <= 0:
        raise ValueError('The amount must be greater than zero.')
    pay_date = pay_date or date.today()
    if pay_date > date.today():
        raise ValueError('The payment date cannot be in the future.')
    return amount, pay_date


def pay_purchase(purchase, amount_rupees, pay_date=None, method='cash',
                 note=None, actor=None):
    """Pay (part of) what is owed on ONE purchase.  Does not commit."""
    amount, pay_date = _check_payment(amount_rupees, pay_date)
    balance = purchase.balance_paisa
    if balance <= 0:
        raise ValueError('This purchase is already paid in full.')
    if amount > balance:
        raise ValueError('The amount is more than what is still owed (%s).'
                         % money(balance))
    payment = SupplierPayment(
        purchase_id=purchase.id, amount_paisa=amount, payment_date=pay_date,
        method=_clean_method(method),
        note=((note or '').strip() or None) and note.strip()[:200],
        created_by_name=_actor_name(actor))
    db.session.add(payment)
    db.session.flush()
    db.session.expire(purchase, ['payments'])
    return payment


def pay_supplier(supplier, amount_rupees, pay_date=None, method='cash',
                 note=None, actor=None):
    """Pay a supplier a lump sum: the oldest unpaid purchases are settled first.

    Returns the list of ``SupplierPayment`` rows made (one per purchase touched).
    Does not commit.
    """
    amount, pay_date = _check_payment(amount_rupees, pay_date)
    bills = open_bills(supplier)
    owed = sum(b.balance_paisa for b in bills)
    if owed <= 0:
        raise ValueError('Nothing is owed to this supplier.')
    if amount > owed:
        raise ValueError('The amount is more than what is still owed (%s).' % money(owed))
    made, left = [], amount
    for bill in bills:
        if left <= 0:
            break
        part = min(left, bill.balance_paisa)
        made.append(pay_purchase(bill, part / 100.0, pay_date, method, note, actor))
        left -= part
    return made


def void_supplier_payment(payment, reason, actor=None):
    """Void a later payment (reason mandatory); the balance re-opens."""
    from datetime import datetime
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void a payment.')
    if payment.is_void:
        raise ValueError('This payment is already voided.')
    payment.is_void = True
    payment.void_reason = reason[:255]
    payment.voided_at = datetime.utcnow()
    payment.voided_by_name = _actor_name(actor)
    return payment


def recent_supplier_payments(limit=10):
    return (SupplierPayment.query.order_by(SupplierPayment.payment_date.desc(),
                                           SupplierPayment.id.desc())
            .limit(limit).all())


def known_suppliers():
    """Supplier names used before (for the purchase form's suggestions)."""
    names = {}
    for (name,) in db.session.query(Purchase.supplier).filter(
            Purchase.supplier.isnot(None)).distinct().all():
        clean = (name or '').strip()
        if clean:
            names.setdefault(clean.lower(), clean)
    return sorted(names.values(), key=str.lower)


# --------------------------------------------------------------------------- #
# Sets (bundles of items)
# --------------------------------------------------------------------------- #
# Stock is always kept per item.  A set is only a recipe: buying 10 sets of
# "Class 1 Books" adds 10 of every book in it; selling one set takes one of each.

def _clean_items(items):
    """``[(product, qty)]`` from ``[(product_id, qty)]``; merges repeats, validates."""
    merged = {}
    for product_id, qty in items or []:
        try:
            product_id, qty = int(product_id), int(qty)
        except (TypeError, ValueError):
            raise ValueError('Every item needs a product and a whole-number quantity.')
        if qty <= 0:
            raise ValueError('Item quantities must be greater than zero.')
        merged[product_id] = merged.get(product_id, 0) + qty
    if not merged:
        raise ValueError('A set needs at least one item.')
    result = []
    for product_id, qty in merged.items():
        product = db.session.get(Product, product_id)
        if product is None:
            raise ValueError('One of the chosen items no longer exists.')
        if not product.is_active:
            raise ValueError('"%s" is retired — restore it or choose another item.'
                             % product.name)
        result.append((product, qty))
    return result


def _check_set_name(name, exclude_id=None):
    name = (name or '').strip()
    if not name:
        raise ValueError('The set needs a name.')
    clash = ProductSet.query.filter(db.func.lower(ProductSet.name) == name.lower(),
                                    ProductSet.is_active.is_(True))
    if exclude_id:
        clash = clash.filter(ProductSet.id != exclude_id)
    if clash.first():
        raise ValueError('An active set with that name already exists.')
    return name[:120]


def _clean_kind(kind):
    from app.models import SET_KINDS
    kind = (kind or 'other').strip().lower()
    return kind if kind in SET_KINDS else 'other'


def create_set(name, items, kind='other', class_id=None):
    """Create a set.  ``items`` is ``[(product_id, qty)]``.  Does not commit."""
    name = _check_set_name(name)
    pairs = _clean_items(items)
    new = ProductSet(name=name, kind=_clean_kind(kind), class_id=class_id or None)
    db.session.add(new)
    for product, qty in pairs:
        new.items.append(ProductSetItem(product_id=product.id, quantity=qty))
    db.session.flush()
    return new


def update_set(target, name, items, kind='other', class_id=None):
    """Rename / re-compose a set.  Past purchases and sales are never touched."""
    name = _check_set_name(name, exclude_id=target.id)
    pairs = _clean_items(items)
    target.name, target.kind = name, _clean_kind(kind)
    target.class_id = class_id or None
    # Edit in place (not delete + re-insert) so the one-row-per-item rule holds.
    wanted = {p.id: q for p, q in pairs}
    for item in list(target.items):
        if item.product_id in wanted:
            item.quantity = wanted.pop(item.product_id)
        else:
            target.items.remove(item)
    for product_id, qty in wanted.items():
        target.items.append(ProductSetItem(product_id=product_id, quantity=qty))
    db.session.flush()
    return target


def set_price_paisa(target):
    """What one set sells for: the sum of its items' selling prices."""
    return sum((i.product.sale_price_paisa or 0) * i.quantity for i in target.items)


def set_cost_paisa(target):
    """What one set currently costs: the sum of its items' average costs."""
    return sum((i.product.cost_paisa or 0) * i.quantity for i in target.items)


def sets_available(target):
    """How many whole sets the stock can make right now."""
    if not target.items:
        return 0
    return min((i.product.stock_qty or 0) // i.quantity for i in target.items)


def _whole_number(value, label):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError('%s must be a whole number.' % label)
    if number <= 0:
        raise ValueError('%s must be greater than zero.' % label)
    return number


def _split(total, weights):
    """Split ``total`` (int paisa) by ``weights``; the parts add up exactly."""
    weight_sum = sum(weights)
    parts = [total * w // weight_sum for w in weights]
    leftover = total - sum(parts)
    order = sorted(range(len(weights)), key=lambda i: (-weights[i], i))
    for index in order[:leftover]:
        parts[index] += 1
    return parts


def purchase_set(target, number_of_sets, total_bill_rupees, supplier=None,
                 purchase_date=None, actor=None, paid_rupees=None):
    """Buy ``number_of_sets`` of a set on ONE bill.  Does not commit.

    The bill is shared across the items by their selling value (or by quantity
    when an item has no selling price), so each item gets a fair unit cost.
    ``paid_rupees`` is shared the same way; blank means paid in full.
    Returns the list of ``Purchase`` rows (one per item).
    """
    count = _whole_number(number_of_sets, 'The number of sets')
    total = to_paisa(total_bill_rupees)
    if total <= 0:
        raise ValueError('The total bill must be greater than zero.')
    if not target.is_active:
        raise ValueError('This set is retired.')
    if not target.items:
        raise ValueError('This set has no items.')
    paid_total = _paid_paisa(paid_rupees, total)

    lines = [(i.product, i.quantity * count) for i in target.items]
    if all((p.sale_price_paisa or 0) > 0 for p, _ in lines):
        weights = [(p.sale_price_paisa or 0) * q for p, q in lines]
    else:
        weights = [q for _, q in lines]
    totals = _split(total, weights)
    if min(totals) <= 0:
        raise ValueError('The bill is too small to share across the items.')
    paids = _split(paid_total, totals) if paid_total else [0] * len(totals)
    # Rounding must never push one line's payment above its own bill.
    over = 0
    for index, (paid, line_total) in enumerate(zip(paids, totals)):
        if paid > line_total:
            over += paid - line_total
            paids[index] = line_total
    for index, line_total in enumerate(totals):
        if not over:
            break
        room = line_total - paids[index]
        take = min(room, over)
        paids[index] += take
        over -= take

    label = ('Set: %s x %d' % (target.name, count))[:120]
    rows = []
    for (product, quantity), line_total, paid in zip(lines, totals, paids):
        unit = max(1, int(round(line_total / quantity)))
        rows.append(_add_stock(product, quantity, line_total, unit, paid,
                               supplier, purchase_date, actor, bill_label=label))
    return rows


def sell_set(target, number_of_sets, note=None, sale_date=None, actor=None,
             student_id=None):
    """Sell ``number_of_sets``: every item in the set is sold.  Does not commit.

    Checks all stock first, so a set is never sold half.  Returns the ``Sale``
    rows (one per item).  ``student_id`` (optional) records who bought it, so the
    sale shows on that student's page.
    """
    count = _whole_number(number_of_sets, 'The number of sets')
    if not target.is_active:
        raise ValueError('This set is retired.')
    if not target.items:
        raise ValueError('This set has no items.')
    if not sales_beyond_stock_allowed():
        short = [('%s (need %d, have %d)' % (i.product.name, i.quantity * count,
                                              i.product.stock_qty or 0))
                 for i in target.items
                 if i.quantity * count > (i.product.stock_qty or 0)]
        if short:
            raise ValueError('Not enough stock for: %s.' % '; '.join(short))
    label = ('Set: %s x %d' % (target.name, count))
    text = ('%s - %s' % (label, note.strip())) if (note or '').strip() else label
    return [record_sale(i.product, i.quantity * count, note=text[:200],
                        sale_date=sale_date, actor=actor, student_id=student_id)
            for i in target.items]


# --------------------------------------------------------------------------- #
# Fixing mistakes: void a sale / a purchase (never deleted)
# --------------------------------------------------------------------------- #
# A wrong quantity or a wrong item must be correctable, otherwise stock, cost of
# goods and the supplier dues stay wrong forever.  A voided row is ignored by
# every total; the stock (and the average cost) go back to what they were.

_SAME_ENTRY_SECONDS = 10


def _same_moment(first, second):
    if first.created_at is None or second.created_at is None:
        return True
    return abs((first.created_at - second.created_at).total_seconds()) <= _SAME_ENTRY_SECONDS


def sale_group(sale):
    """The sale rows that were typed as ONE entry (a set sale books one row per item)."""
    note = sale.note or ''
    if sale.source != 'sale' or not note.startswith('Set: '):
        return [sale]
    rows = Sale.query.filter(Sale.sale_date == sale.sale_date,
                             Sale.source == 'sale', Sale.note == sale.note,
                             Sale.is_void.is_(False)).all()
    group = [r for r in rows if r.created_by_name == sale.created_by_name
             and r.student_id == sale.student_id and _same_moment(r, sale)]
    return sorted(group or [sale], key=lambda r: r.id)


def purchase_group(purchase):
    """The purchase rows that were typed as ONE bill (a set purchase = one row per item)."""
    if not purchase.bill_label or purchase.is_opening:
        return [purchase]
    rows = Purchase.query.filter(Purchase.bill_label == purchase.bill_label,
                                 Purchase.purchase_date == purchase.purchase_date,
                                 Purchase.is_void.is_(False),
                                 Purchase.is_opening.is_(False)).all()
    group = [r for r in rows if (r.supplier or '') == (purchase.supplier or '')
             and r.created_by_name == purchase.created_by_name
             and _same_moment(r, purchase)]
    return sorted(group or [purchase], key=lambda r: r.id)


def _clean_reason(reason, what):
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void %s.' % what)
    return reason[:255]


def void_sale(sale, reason, actor=None):
    """Undo a sale (and the other lines of the same set sale).  Does not commit.

    The items go back on the shelf at the cost they were sold at.  Stock handed
    over with an admission is undone from \"Student stock\", not here.
    Returns the list of voided rows.
    """
    from datetime import datetime
    reason = _clean_reason(reason, 'a sale')
    if sale.is_void:
        raise ValueError('This sale is already voided.')
    if sale.source == 'admission' or sale.issue_id:
        raise ValueError('This stock was given with an admission. Undo it from '
                         '"Student stock" instead.')
    rows = [r for r in sale_group(sale) if not r.is_void]
    for row in rows:
        product = row.product
        old_stock = product.stock_qty or 0
        new_stock = old_stock + row.quantity
        product.cost_paisa = int(round(
            (old_stock * (product.cost_paisa or 0)
             + row.quantity * (row.unit_cost_paisa or 0)) / new_stock))
        product.stock_qty = new_stock
        row.is_void = True
        row.void_reason = reason
        row.voided_at = datetime.utcnow()
        row.voided_by_name = _actor_name(actor)
    return rows


def void_purchase(purchase, reason, actor=None):
    """Undo a purchase typed by mistake (the whole bill of a set purchase).

    Allowed only while the stock is still on the shelf and no money was paid to
    the supplier afterwards - those must be undone first, so no number is left
    pointing at something that no longer exists.  Does not commit.
    Returns the list of voided rows.
    """
    from datetime import datetime
    reason = _clean_reason(reason, 'a purchase')
    if purchase.is_void:
        raise ValueError('This purchase is already voided.')
    rows = [r for r in purchase_group(purchase) if not r.is_void]

    later = sum(p.amount_paisa for r in rows for p in r.payments if not p.is_void)
    if later:
        raise ValueError(
            'Rs %s was paid to the supplier on this bill after the purchase day. '
            'Void those payments first (see "Payments to suppliers"), then void '
            'the purchase.' % '{:,.2f}'.format(later / 100.0))

    need = {}
    for row in rows:
        need[row.product_id] = need.get(row.product_id, 0) + row.quantity
    short = []
    for row in rows:
        have = row.product.stock_qty or 0
        if need.get(row.product_id, 0) > have and row.product.name not in short:
            short.append('%s (bought %d, only %d left)' % (
                row.product.name, need[row.product_id], have))
    if short:
        raise ValueError('Cannot remove this stock - some of it is already sold or '
                         'given: %s. Undo those sales first.' % '; '.join(short))

    for row in rows:
        product = row.product
        old_stock = product.stock_qty or 0
        new_stock = old_stock - row.quantity
        if new_stock > 0:
            product.cost_paisa = max(0, int(round(
                (old_stock * (product.cost_paisa or 0)
                 - (row.total_cost_paisa or 0)) / new_stock)))
        product.stock_qty = new_stock
        row.is_void = True
        row.void_reason = reason
        row.voided_at = datetime.utcnow()
        row.voided_by_name = _actor_name(actor)
    return rows


def month_cogs_split(start, end):
    """``(sold_separately, given_with_admission)`` cost of goods in rupees.

    Stock handed over inside an admission package was PAID for through the
    admission fee, so its cost is not a loss on the items sold across the
    counter.  Both parts are real cost of goods; they are shown apart.
    """
    data = month_sales_breakdown(start, end)
    return data['direct_cogs'], data['package_cogs']

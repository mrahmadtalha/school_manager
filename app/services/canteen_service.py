"""Canteen inside Inventory + the Inventory setup checklist (Phase 4).

A school can run its canteen in one of two ways (or not at all):

* ``detailed`` - every canteen item is an ordinary Inventory product in the
  category **Canteen**.  Stock, purchases, sales, cost of goods and profit work
  item by item, exactly like uniform and books.
* ``totals``   - no items.  The school only types the **total sales** and the
  **total purchases** of a day (or week).  A sales total is an Other Income row
  in the "Canteen" category; a purchases total is an Expense row in the
  "Canteen Purchases" category - so every financial screen already counts them
  and nothing is counted twice.

Switching the mode never deletes anything: the summary always adds both
sources, the mode only decides which entry forms are shown.  The old "Canteen"
box on the Other Income page is closed once a mode is chosen, so the same money
cannot be typed in two places.
"""
from datetime import date, datetime

from app.database import db
from app.models import (CanteenEntry, CanteenPayment, ClassModel, Expense, ExpenseCategory,
                        OtherIncome, OtherIncomeCategory, Product, ProductSet,
                        Purchase, Sale, SystemSettingModel, to_paisa)
from app.services import other_income_service

MODE_KEY = 'canteen_mode'
MODE_OFF, MODE_DETAILED, MODE_TOTALS = 'off', 'detailed', 'totals'
MODES = (MODE_OFF, MODE_DETAILED, MODE_TOTALS)
MODE_LABELS = {
    MODE_OFF: 'No canteen',
    MODE_DETAILED: 'Item by item',
    MODE_TOTALS: 'Totals only',
}

CANTEEN_PRODUCT_CATEGORY = 'Canteen'
INCOME_CATEGORY = 'Canteen'
PURCHASE_EXPENSE_CATEGORY = 'Canteen Purchases'

KIND_SALE, KIND_PURCHASE = 'sale', 'purchase'

NO_SUPPLIER = 'No supplier name'
PAYMENT_METHODS = ('cash', 'bank', 'cheque', 'online')


def _actor_name(actor):
    return getattr(actor, 'username', None) or actor or 'system'


# --------------------------------------------------------------------------- #
# Mode
# --------------------------------------------------------------------------- #

def get_mode():
    row = SystemSettingModel.query.filter_by(key=MODE_KEY).first()
    value = row.value if row is not None else MODE_OFF
    return value if value in MODES else MODE_OFF


def set_mode(mode):
    """Choose how the canteen is kept.  Does not commit."""
    if mode not in MODES:
        raise ValueError('Please choose how the canteen is kept.')
    row = SystemSettingModel.query.filter_by(key=MODE_KEY).first()
    if row is None:
        row = SystemSettingModel(key=MODE_KEY, value=mode)
        db.session.add(row)
    row.value = mode
    return mode


def is_open_for_other_income():
    """True while the plain "Canteen" other-income entry is still allowed."""
    return get_mode() == MODE_OFF


def is_canteen_income_category(category):
    return bool(category) and (category.name or '').strip().lower() == INCOME_CATEGORY.lower()


# --------------------------------------------------------------------------- #
# Totals-only entries
# --------------------------------------------------------------------------- #

def _income_category():
    other_income_service.seed_default_categories()
    category = (OtherIncomeCategory.query
                .filter(db.func.lower(OtherIncomeCategory.name) == INCOME_CATEGORY.lower())
                .first())
    if category is None:
        category = OtherIncomeCategory(name=INCOME_CATEGORY)
        db.session.add(category)
        db.session.flush()
    elif not category.is_active:
        category.is_active = True
    return category


def _purchase_category():
    # A brand-new school has no expense categories yet; seed the defaults first
    # (they are only seeded into an EMPTY table) so ours does not suppress them.
    from app.services.expense_service import seed_default_categories
    seed_default_categories()
    category = (ExpenseCategory.query
                .filter(db.func.lower(ExpenseCategory.name)
                        == PURCHASE_EXPENSE_CATEGORY.lower()).first())
    if category is None:
        category = ExpenseCategory(
            name=PURCHASE_EXPENSE_CATEGORY,
            description='Stock bought for the school canteen (totals only)')
        db.session.add(category)
        db.session.flush()
    elif not category.is_active:
        category.is_active = True
    return category


def record_total(kind, amount_rupees, entry_date=None, note=None, actor=None,
                 supplier=None, paid_rupees=None):
    """Add one canteen total.  ``kind`` is ``'sale'`` or ``'purchase'``.

    For a purchase, ``supplier`` and ``paid_rupees`` (paid today) record supplier
    credit: ``paid_rupees=None`` (or the full bill) means paid in full, exactly
    as before; less than the bill leaves the rest as a supplier due.  Only the
    money really paid becomes an expense.

    Returns the ``CanteenEntry``.  Does not commit.
    """
    if kind not in (KIND_SALE, KIND_PURCHASE):
        raise ValueError('Choose sales or purchases.')
    amount = to_paisa(amount_rupees)
    if amount <= 0:
        raise ValueError('The amount must be greater than zero.')
    entry_date = entry_date or date.today()
    if entry_date > date.today():
        raise ValueError('The date cannot be in the future.')
    note = (note or '').strip()[:150] or None
    name = _actor_name(actor)

    entry = CanteenEntry(kind=kind, entry_date=entry_date, note=note,
                         created_by_name=name)
    if kind == KIND_SALE:
        text = 'Canteen sales (total)' + (' - %s' % note if note else '')
        income = other_income_service.record_income(
            _income_category(), amount / 100.0, entry_date,
            description=text, actor=actor)
        db.session.flush()
        entry.income_id = income.id
    else:
        supplier = (supplier or '').strip()[:120] or None
        paid = amount
        if paid_rupees is not None and str(paid_rupees).strip() != '':
            paid = to_paisa(paid_rupees)
            if paid < 0:
                raise ValueError('The amount paid now cannot be negative.')
            if paid > amount:
                raise ValueError('The amount paid now cannot be more than the bill.')
        entry.supplier = supplier
        if paid < amount:
            entry.bill_paisa = amount
            entry.paid_paisa = paid
        text = 'Canteen purchases (total)' + (' - %s' % note if note else '')
        if paid < amount:
            text += ' [bill %s, paid now %s]' % (_money(amount), _money(paid))
        if paid > 0:
            expense = _make_expense(paid, entry_date, text, 'Cash', actor)
            entry.expense_id = expense.id
    db.session.add(entry)
    db.session.flush()
    return entry


def _money(paisa):
    return 'Rs. {:,.2f}'.format((paisa or 0) / 100.0)


def _make_expense(amount_paisa, when, text, method, actor):
    expense = Expense(category_id=_purchase_category().id, amount_paisa=amount_paisa,
                      payment_method=method, date=when, description=text[:255],
                      logged_by_id=getattr(actor, 'id', None),
                      logged_by_name=_actor_name(actor))
    db.session.add(expense)
    db.session.flush()
    return expense


def void_entry(entry, reason, actor=None):
    """Void a total (reason mandatory).  The linked income / expense row is
    voided with it, so it leaves every figure.  Does not commit."""
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void a canteen entry.')
    if entry.is_void:
        raise ValueError('This entry is already voided.')
    if entry.kind == KIND_SALE:
        other_income_service.void_income(entry.income, reason, actor=actor)
    else:
        from app.services.expense_service import void_expense
        if entry.is_credit and any(not p.is_void for p in entry.payments):
            raise ValueError('Money was already paid to the supplier on this bill '
                             'after the purchase day. Void those payments first, '
                             'then void the bill.')
        if entry.expense is not None:
            void_expense(entry.expense, reason, _actor_name(actor))
        if entry.is_credit:
            entry.void_flag = True
            entry.void_note = reason[:255]
    return entry


# --------------------------------------------------------------------------- #
# Supplier dues of canteen purchases (udhaar)
# --------------------------------------------------------------------------- #

def open_bills(supplier=None):
    """Canteen purchase totals that still owe money, oldest first."""
    rows = (CanteenEntry.query
            .filter(CanteenEntry.kind == KIND_PURCHASE,
                    CanteenEntry.bill_paisa.isnot(None),
                    CanteenEntry.void_flag.is_(False))
            .order_by(CanteenEntry.entry_date, CanteenEntry.id).all())
    bills = [e for e in rows if e.balance_paisa > 0]
    if supplier is not None:
        wanted = '' if supplier == NO_SUPPLIER else (supplier or '').strip().lower()
        bills = [e for e in bills if (e.supplier or '').strip().lower() == wanted]
    return bills


def supplier_dues():
    """One row per canteen supplier still owed money (amounts in paisa)."""
    groups = {}
    for bill in open_bills():
        label = (bill.supplier or '').strip() or NO_SUPPLIER
        row = groups.setdefault(label.lower(), {
            'supplier': label, 'bills': 0, 'total': 0, 'paid': 0, 'balance': 0,
            'source': 'canteen'})
        row['bills'] += 1
        row['total'] += bill.bill_paisa or 0
        row['paid'] += bill.paid_total_paisa
        row['balance'] += bill.balance_paisa
    return sorted(groups.values(), key=lambda r: (-r['balance'], r['supplier'].lower()))


def total_owed_paisa():
    return sum(bill.balance_paisa for bill in open_bills())


def _check_payment(amount_rupees, pay_date):
    amount = to_paisa(amount_rupees)
    if amount <= 0:
        raise ValueError('The amount must be greater than zero.')
    pay_date = pay_date or date.today()
    if pay_date > date.today():
        raise ValueError('The payment date cannot be in the future.')
    return amount, pay_date


def _clean_method(method):
    method = (method or 'cash').strip().lower()
    return method if method in PAYMENT_METHODS else 'cash'


def pay_entry(entry, amount_rupees, pay_date=None, method='cash', note=None, actor=None):
    """Pay (part of) what is owed on ONE canteen purchase.  Does not commit."""
    amount, pay_date = _check_payment(amount_rupees, pay_date)
    balance = entry.balance_paisa
    if balance <= 0:
        raise ValueError('This canteen purchase is already paid in full.')
    if amount > balance:
        raise ValueError('The amount is more than what is still owed (%s).' % _money(balance))
    method = _clean_method(method)
    who = (entry.supplier or '').strip() or 'supplier'
    expense = _make_expense(
        amount, pay_date,
        'Canteen supplier payment - %s (bill of %s)' % (
            who, entry.entry_date.strftime('%d %b %Y')),
        method.capitalize(), actor)
    payment = CanteenPayment(
        entry_id=entry.id, amount_paisa=amount, payment_date=pay_date,
        method=method, note=((note or '').strip() or None) and note.strip()[:200],
        expense_id=expense.id, created_by_name=_actor_name(actor))
    db.session.add(payment)
    db.session.flush()
    db.session.expire(entry, ['payments'])
    return payment


def pay_supplier(supplier, amount_rupees, pay_date=None, method='cash', note=None,
                 actor=None):
    """Pay a canteen supplier a lump sum: oldest bills are settled first."""
    amount, pay_date = _check_payment(amount_rupees, pay_date)
    bills = open_bills(supplier)
    owed = sum(b.balance_paisa for b in bills)
    if owed <= 0:
        raise ValueError('Nothing is owed to this supplier.')
    if amount > owed:
        raise ValueError('The amount is more than what is still owed (%s).' % _money(owed))
    made, left = [], amount
    for bill in bills:
        if left <= 0:
            break
        part = min(left, bill.balance_paisa)
        made.append(pay_entry(bill, part / 100.0, pay_date, method, note, actor))
        left -= part
    return made


def void_payment(payment, reason, actor=None):
    """Void a later payment (reason mandatory); its expense goes and the balance re-opens."""
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void a payment.')
    if payment.is_void:
        raise ValueError('This payment is already voided.')
    from app.services.expense_service import void_expense
    payment.is_void = True
    payment.void_reason = reason[:255]
    payment.voided_at = datetime.utcnow()
    payment.voided_by_name = _actor_name(actor)
    if payment.expense is not None:
        void_expense(payment.expense, reason, _actor_name(actor))
    return payment


def recent_payments(limit=10):
    return (CanteenPayment.query
            .order_by(CanteenPayment.payment_date.desc(), CanteenPayment.id.desc())
            .limit(limit).all())


def recent_entries(limit=15):
    return (CanteenEntry.query
            .order_by(CanteenEntry.entry_date.desc(), CanteenEntry.id.desc())
            .limit(limit).all())


# --------------------------------------------------------------------------- #
# Month summary
# --------------------------------------------------------------------------- #

def canteen_products(active_only=True):
    query = Product.query.filter(
        db.func.lower(Product.category) == CANTEEN_PRODUCT_CATEGORY.lower())
    if active_only:
        query = query.filter(Product.is_active.is_(True))
    return query.order_by(Product.name).all()


def _sum(query):
    return int(query.scalar() or 0)


def month_summary(start, end):
    """Canteen figures for the inclusive date range, all money in paisa.

    ``detailed`` comes from Inventory (products in the Canteen category) and
    ``totals`` from the totals-only entries.  ``profit`` is the item-by-item
    gross profit (sales minus the cost of what was sold) plus, for the totals
    part, sales minus purchases.
    """
    canteen = db.func.lower(Product.category) == CANTEEN_PRODUCT_CATEGORY.lower()

    sales_price = _sum(db.session.query(db.func.coalesce(db.func.sum(Sale.total_price_paisa), 0))
                       .join(Product, Sale.product_id == Product.id)
                       .filter(canteen, Sale.is_void.is_(False),
                               Sale.sale_date >= start, Sale.sale_date <= end))
    sales_cost = _sum(db.session.query(db.func.coalesce(db.func.sum(Sale.total_cost_paisa), 0))
                      .join(Product, Sale.product_id == Product.id)
                      .filter(canteen, Sale.is_void.is_(False),
                              Sale.sale_date >= start, Sale.sale_date <= end))
    bought = _sum(db.session.query(db.func.coalesce(db.func.sum(Purchase.total_cost_paisa), 0))
                  .join(Product, Purchase.product_id == Product.id)
                  .filter(canteen, Purchase.is_opening.is_(False),
                          Purchase.is_void.is_(False),
                          Purchase.purchase_date >= start, Purchase.purchase_date <= end))
    stock_value = sum((p.stock_qty or 0) * (p.cost_paisa or 0)
                      for p in canteen_products())

    totals_sales = _sum(
        db.session.query(db.func.coalesce(db.func.sum(OtherIncome.amount_paisa), 0))
        .join(CanteenEntry, CanteenEntry.income_id == OtherIncome.id)
        .filter(OtherIncome.is_void.is_(False),
                OtherIncome.income_date >= start, OtherIncome.income_date <= end))
    # What was BOUGHT: paid-in-full totals (their expense) plus the full bill of
    # purchases made on credit.  What was PAID is the cash that really left,
    # including later instalments to the supplier.
    plain_bought = _sum(
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount_paisa), 0))
        .join(CanteenEntry, CanteenEntry.expense_id == Expense.id)
        .filter(Expense.is_void.is_(False), CanteenEntry.bill_paisa.is_(None),
                Expense.date >= start, Expense.date <= end))
    credit_bought = _sum(
        db.session.query(db.func.coalesce(db.func.sum(CanteenEntry.bill_paisa), 0))
        .filter(CanteenEntry.kind == KIND_PURCHASE,
                CanteenEntry.bill_paisa.isnot(None),
                CanteenEntry.void_flag.is_(False),
                CanteenEntry.entry_date >= start, CanteenEntry.entry_date <= end))
    totals_purchases = plain_bought + credit_bought
    paid_with_entry = _sum(
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount_paisa), 0))
        .join(CanteenEntry, CanteenEntry.expense_id == Expense.id)
        .filter(Expense.is_void.is_(False),
                Expense.date >= start, Expense.date <= end))
    paid_later = _sum(
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount_paisa), 0))
        .join(CanteenPayment, CanteenPayment.expense_id == Expense.id)
        .filter(Expense.is_void.is_(False), CanteenPayment.is_void.is_(False),
                Expense.date >= start, Expense.date <= end))
    totals_paid = paid_with_entry + paid_later

    return {
        'detailed': {'sales': sales_price, 'cost_of_goods': sales_cost,
                     'profit': sales_price - sales_cost, 'bought': bought,
                     'stock_value': stock_value},
        'totals': {'sales': totals_sales, 'purchases': totals_purchases,
                   'profit': totals_sales - totals_purchases},
        # Cash that really left for canteen purchases this period, and what is
        # still owed to canteen suppliers right now (udhaar).
        'paid': totals_paid + 0,
        'owed': total_owed_paisa(),
        'sales': sales_price + totals_sales,
        'purchases': bought + totals_purchases,
        'profit': (sales_price - sales_cost) + (totals_sales - totals_purchases),
    }


# --------------------------------------------------------------------------- #
# Setup checklist
# --------------------------------------------------------------------------- #

def setup_status():
    """What is still to do before Inventory is ready for admissions.

    Three steps: (1) items added, (2) opening stock in, (3) every class has
    its books set and a uniform set.  ``percent`` is the share of steps done.
    """
    from app.services.student_stock import class_set

    products = (Product.query.filter(Product.is_active.is_(True))
                .order_by(Product.name).all())
    items_done = len(products) > 0
    stocked = [p for p in products if (p.stock_qty or 0) > 0]
    has_opening = Purchase.query.filter(Purchase.is_opening.is_(True)).first() is not None
    has_any_stock = bool(stocked) or has_opening or Purchase.query.first() is not None
    stock_done = items_done and has_any_stock

    classes = ClassModel.query.order_by(ClassModel.name).all()
    rows = []
    for klass in classes:
        books = class_set(klass.id, 'books')
        uniform = class_set(klass.id, 'uniform')
        rows.append({
            'id': klass.id, 'name': klass.name,
            'books': books, 'uniform': uniform,
            'uniform_common': bool(uniform is not None and uniform.class_id is None),
            'complete': books is not None and uniform is not None,
        })
    sets_done = bool(rows) and all(r['complete'] for r in rows)

    steps = [items_done, stock_done, sets_done]
    return {
        'items_done': items_done, 'item_count': len(products),
        'stock_done': stock_done, 'stocked_count': len(stocked),
        'without_stock': [p for p in products if (p.stock_qty or 0) <= 0],
        'sets_done': sets_done, 'class_rows': rows,
        'classes_complete': sum(1 for r in rows if r['complete']),
        'class_count': len(rows),
        'done_count': sum(1 for step in steps if step),
        'percent': int(round(100.0 * sum(1 for step in steps if step) / len(steps))),
        'all_done': all(steps),
    }

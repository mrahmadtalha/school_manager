"""Stage: inventory - products, class book / uniform sets, purchases, supplier dues and sales.

Everything goes through the real ``inventory_service`` functions, so stock,
weighted-average cost, supplier balances and cost of goods sold are exactly
what the Inventory screens would have produced from daily use.
"""

from datetime import timedelta

from app.database import db
from app.models import Product, ProductSet, StudentModel
from app.services import inventory_service as inv

from .data import (CLASS_LEVELS, RETIRED_PRODUCT, STATIONERY_PRODUCTS, SUBJECT_NAMES, SUPPLIERS,
                   UNIFORM_PRODUCTS)
from .helpers import _today

_JUNIOR_LAST_INDEX = 5          # Playgroup .. Class 4 wear the junior uniform
_SALE_NOTES = [None, None, 'Counter sale', 'Sold to parent', 'Cash sale']


def _round5(value):
    return int(round(value / 5.0)) * 5


def _stage_inventory(rng, cfg, progress, classes, months, period_start, period_end):
    """Returns ``{'products', 'product_sets', 'purchases', 'sales', 'supplier_payments'}``."""
    today = _today()
    counts = {}
    for class_id, in_class in (db.session.query(StudentModel.class_id, db.func.count(StudentModel.id))
                               .group_by(StudentModel.class_id).all()):
        counts[class_id] = in_class

    cost_rupees = {}          # product id -> typical unit cost in rupees

    def add_product(name, category, price, cost, min_stock, supplier):
        product = Product(name=name, category=category, sale_price_paisa=int(round(price * 100)),
                          min_stock_qty=min_stock, supplier=supplier, stock_qty=0, cost_paisa=0)
        db.session.add(product)
        db.session.flush()
        cost_rupees[product.id] = cost
        return product

    # ---- catalogue -------------------------------------------------------------
    uniform = {name: add_product(name, cat, price, cost, low, sup)
               for name, cat, price, cost, low, sup in UNIFORM_PRODUCTS}
    stationery = [add_product(*row) for row in STATIONERY_PRODUCTS]
    retired = add_product(*RETIRED_PRODUCT)

    class_books = {}          # class id -> [products]
    class_index = {}
    for position, class_obj in enumerate(classes):
        class_index[class_obj.id] = position
        items = []
        for sub_index, subject in enumerate(SUBJECT_NAMES):
            price = _round5(160 + position * 30 + sub_index * 12)
            items.append(add_product(f'{class_obj.name} {subject} Book', 'Books', price,
                                     _round5(price * 0.72), 5, 'Ali Book Depot'))
        class_books[class_obj.id] = items

    # ---- class sets (the admission package) ------------------------------------
    book_sets, uniform_sets = {}, {}
    for class_obj in classes:
        book_sets[class_obj.id] = inv.create_set(
            f'{class_obj.name} Books', [(p.id, 1) for p in class_books[class_obj.id]],
            kind='books', class_id=class_obj.id)
        junior = class_index[class_obj.id] <= _JUNIOR_LAST_INDEX
        shirt = uniform['Junior Shirt' if junior else 'Senior Shirt']
        trouser = uniform['Junior Trouser / Shalwar' if junior else 'Senior Trouser / Shalwar']
        uniform_sets[class_obj.id] = inv.create_set(
            f'{class_obj.name} Uniform', [(shirt.id, 1), (trouser.id, 1), (uniform['School Tie'].id, 1)],
            kind='uniform', class_id=class_obj.id)
    db.session.flush()
    progress.report('inventory', 0.15)

    # ---- opening stock (already on the shelf when the school started the software) --
    reserve_books = {c.id: int(counts.get(c.id, 0) * 0.4) + 3 for c in classes}
    reserve_uniform = {c.id: int(counts.get(c.id, 0) * 0.9) + 4 for c in classes}
    purchases = 0
    for class_obj in classes:
        qty = max(10, int(counts.get(class_obj.id, 0) * 0.5) + 8)
        for product in class_books[class_obj.id]:
            inv.record_opening_stock(product, qty, cost_rupees[product.id], as_of=period_start)
            purchases += 1
    junior_students = sum(counts.get(c.id, 0) for c in classes if class_index[c.id] <= _JUNIOR_LAST_INDEX)
    senior_students = sum(counts.get(c.id, 0) for c in classes if class_index[c.id] > _JUNIOR_LAST_INDEX)
    for name, product in uniform.items():
        if name == 'School Tie':
            need = junior_students + senior_students
        elif name.startswith('Junior'):
            need = junior_students
        elif name.startswith('Senior'):
            need = senior_students
        else:
            need = 12
        inv.record_opening_stock(product, max(12, int(need * 0.9) + 10), cost_rupees[product.id],
                                 as_of=period_start)
        purchases += 1
    for product in stationery:
        inv.record_opening_stock(product, rng.randint(40, 90), cost_rupees[product.id], as_of=period_start)
        purchases += 1
    inv.record_opening_stock(retired, 18, cost_rupees[retired.id], as_of=period_start)
    purchases += 1
    db.session.flush()
    progress.report('inventory', 0.3)

    # ---- restocking through the period (some bills left partly unpaid) ---------
    restock_pool = stationery + [uniform['School Sweater'], uniform['School Tie']]
    partial_bills = []
    all_purchases = []
    for m_index, (_label, m_start, m_end) in enumerate(months):
        for _ in range(rng.randint(1, 3)):
            product = rng.choice(restock_pool)
            qty = rng.randint(15, 60)
            unit = round(cost_rupees[product.id] * rng.uniform(0.97, 1.06), 2)
            day = min(m_start + timedelta(days=rng.randint(0, (m_end - m_start).days)), today)
            paid = None
            if rng.random() < 0.3:
                paid = round(qty * unit * rng.uniform(0.4, 0.8), 2)
            bill = inv.record_purchase(product, qty, unit, supplier=product.supplier,
                                       purchase_date=day, actor='admin', paid_rupees=paid)
            all_purchases.append(bill)
            purchases += 1
            if paid is not None:
                partial_bills.append(bill)
        if rng.random() < 0.35:           # a whole class's books on one bill
            target = book_sets[rng.choice(classes).id]
            count = rng.randint(5, 12)
            total = round(sum(cost_rupees[i.product_id] * i.quantity for i in target.items) * count, 2)
            day = min(m_start + timedelta(days=rng.randint(0, (m_end - m_start).days)), today)
            paid = round(total * rng.uniform(0.5, 0.9), 2) if rng.random() < 0.3 else None
            rows = inv.purchase_set(target, count, total, supplier='Ali Book Depot',
                                    purchase_date=day, actor='admin', paid_rupees=paid)
            purchases += len(rows)
            if paid is not None:
                partial_bills.extend(rows)
        db.session.flush()
        progress.report('inventory', 0.3 + 0.3 * (m_index + 1) / len(months))

    # ---- paying suppliers later (instalments); a few bills stay unpaid ----------
    supplier_payments = 0
    for bill in partial_bills:
        if bill.is_void or bill.balance_paisa <= 0 or rng.random() < 0.25:
            continue
        pay_day = min(bill.purchase_date + timedelta(days=rng.randint(7, 45)), today)
        if pay_day <= bill.purchase_date:
            continue
        part = bill.balance_paisa if rng.random() < 0.6 else max(100, bill.balance_paisa // 2)
        try:
            inv.pay_purchase(bill, part / 100.0, pay_day, rng.choice(['cash', 'bank', 'cheque']),
                             'Supplier instalment', 'admin')
            supplier_payments += 1
        except ValueError:
            continue
    db.session.flush()

    # ---- sales across the period ---------------------------------------------------
    students_by_class = {}
    for student in StudentModel.query.filter_by(is_active=True).all():
        students_by_class.setdefault(student.class_id, []).append(student)
    singles = stationery + [uniform['School Sweater']]
    sales = 0
    sale_rows = []
    for m_index, (_label, m_start, m_end) in enumerate(months):
        span = max(0, (min(m_end, today) - m_start).days)
        for _ in range(rng.randint(6, 14)):
            product = rng.choice(singles)
            qty = rng.randint(1, 3)
            if (product.stock_qty or 0) < qty:
                continue
            day = m_start + timedelta(days=rng.randint(0, span))
            buyer = None
            if rng.random() < 0.5:
                pool = students_by_class.get(rng.choice(classes).id) or []
                buyer = rng.choice(pool).id if pool else None
            sale_rows.append(inv.record_sale(product, qty, note=rng.choice(_SALE_NOTES), sale_date=day,
                                             actor='admin', student_id=buyer))
            sales += 1
        for _ in range(rng.randint(2, 5)):        # a book set or a uniform set to one student
            class_obj = rng.choice(classes)
            kind = rng.choice(['books', 'uniform'])
            target = (book_sets if kind == 'books' else uniform_sets)[class_obj.id]
            reserve = (reserve_books if kind == 'books' else reserve_uniform)[class_obj.id]
            if inv.sets_available(target) <= reserve + 1:
                continue
            pool = students_by_class.get(class_obj.id) or []
            day = m_start + timedelta(days=rng.randint(0, span))
            made = inv.sell_set(target, 1, note='Extra set', sale_date=day, actor='admin',
                                student_id=rng.choice(pool).id if pool else None)
            sale_rows.extend(made)
            sales += len(made)
        # the retired product sold while it was still on the shelf
        if m_index == 0 and (retired.stock_qty or 0) >= 6:
            sale_rows.append(inv.record_sale(retired, 6, note='Clearance sale', sale_date=m_start,
                                             actor='admin'))
            sales += 1
        db.session.flush()
        progress.report('inventory', 0.6 + 0.35 * (m_index + 1) / len(months))

    # ---- corrections: a wrong sale and a duplicated purchase are voided ------------
    for sale in sale_rows[:12]:
        if sale.student_id is None and not sale.is_void:
            try:
                inv.void_sale(sale, 'Wrong item entered', 'admin')
            except ValueError:
                pass
            break
    for bill in all_purchases:
        if bill not in partial_bills and not bill.is_void and bill.product.stock_qty >= bill.quantity:
            try:
                inv.void_purchase(bill, 'Bill entered twice', 'admin')
            except ValueError:
                continue
            break

    # ---- the retired product is switched off; two items are running low --------------
    retired.is_active = False
    live = [p for p in stationery if p.is_active]
    for product in rng.sample(live, k=min(2, len(live))):
        product.min_stock_qty = (product.stock_qty or 0) + 3

    db.session.commit()
    progress.report('inventory', 1.0)
    return {'products': Product.query.count(), 'product_sets': ProductSet.query.count(),
            'purchases': purchases, 'sales': sales, 'supplier_payments': supplier_payments}, \
        book_sets, uniform_sets

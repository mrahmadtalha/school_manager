"""Inventory / sales models (Phase 3a+3b).

The school sells items (uniforms, books, stationery) in volume.  Purchases
are stock replenishment — NOT expenses; the cost of a purchased item moves
into Cost of Goods Sold when the item is SOLD, using weighted-average cost
recalculated on every purchase.  Money is stored as integer paisa, like the
rest of the financial modules.
"""
from datetime import datetime

from app.database import db


class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        # Backstop for the service-level check: stock can never go negative.
        db.CheckConstraint('stock_qty >= 0', name='ck_products_stock_non_negative'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False, default='Other')
    sale_price_paisa = db.Column(db.Integer, nullable=False, default=0)
    stock_qty = db.Column(db.Integer, nullable=False, default=0)
    min_stock_qty = db.Column(db.Integer, nullable=False, default=0)
    supplier = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Weighted-average unit cost (paisa), recalculated on every purchase.
    cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    purchases = db.relationship('Purchase', backref='product', lazy=True)
    sales = db.relationship('Sale', backref='product', lazy=True)

    def __repr__(self):
        return f'<Product {self.name} stock={self.stock_qty}>'


class Purchase(db.Model):
    __tablename__ = 'inventory_purchases'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    total_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    supplier = db.Column(db.String(120), nullable=True)
    purchase_date = db.Column(db.Date, nullable=False)
    # Money handed to the supplier on the day of purchase.  NULL means "paid in
    # full" (every purchase made before supplier dues existed).  What is still
    # owed is total - paid - later SupplierPayment rows.
    paid_paisa = db.Column(db.Integer, nullable=True)
    # Set when this row is one line of a SET purchase ("Class 1 Books x 10"), so
    # the lines of one bill can be told apart from single-item purchases.
    bill_label = db.Column(db.String(120), nullable=True)
    # Phase 4: stock that was already on the shelf when the school started using
    # Inventory ("opening stock").  It fills the shelf and sets the cost, but no
    # money was paid today, so it is never cash out and never a supplier due.
    is_opening = db.Column(db.Boolean, nullable=False, default=False,
                           server_default='0')
    # A purchase typed by mistake is voided (never deleted): its stock leaves the
    # shelf again, it stops being cash out and it stops being a supplier due.
    is_void = db.Column(db.Boolean, nullable=False, default=False,
                        server_default='0')
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    payments = db.relationship('SupplierPayment', backref='purchase', lazy=True,
                               order_by='SupplierPayment.id')

    @property
    def paid_at_purchase_paisa(self):
        if self.paid_paisa is None:
            return self.total_cost_paisa or 0
        return self.paid_paisa

    @property
    def paid_total_paisa(self):
        later = sum(p.amount_paisa for p in self.payments if not p.is_void)
        return self.paid_at_purchase_paisa + later

    @property
    def balance_paisa(self):
        if self.is_void:
            return 0
        return max(0, (self.total_cost_paisa or 0) - self.paid_total_paisa)


class SupplierPayment(db.Model):
    """Money paid to a supplier AFTER the purchase day (instalments).

    Append-only like every other money table: a mistake is voided with a
    reason, and a voided payment re-opens the supplier's balance.
    """
    __tablename__ = 'supplier_payments'
    __table_args__ = (
        db.CheckConstraint('amount_paisa > 0', name='ck_supplier_payments_positive'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('inventory_purchases.id'),
                            nullable=False, index=True)
    amount_paisa = db.Column(db.Integer, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, index=True)
    method = db.Column(db.String(20), nullable=True)
    note = db.Column(db.String(200), nullable=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')


class Sale(db.Model):
    __tablename__ = 'inventory_sales'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_inventory_sales_qty_positive'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    # Price and cost are snapshotted at sale time; later price changes never
    # alter historical sales.
    unit_price_paisa = db.Column(db.Integer, nullable=False, default=0)
    unit_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    total_price_paisa = db.Column(db.Integer, nullable=False, default=0)
    total_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    gross_profit_paisa = db.Column(db.Integer, nullable=False, default=0)
    sale_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(200), nullable=True)
    # Phase 3 (admission link).  ``source`` is 'sale' for a normal sale (money
    # received, counted as sales income) or 'admission' for stock handed to a
    # student whose price is already part of the admission fee: such a row has
    # price 0, so income is never counted twice, but its cost still becomes COGS.
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True,
                           index=True)
    source = db.Column(db.String(20), nullable=False, default='sale',
                       server_default='sale')
    issue_id = db.Column(db.Integer, db.ForeignKey('student_issues.id'),
                         nullable=True, index=True)
    # A voided row is ignored everywhere (stock was put back); never deleted.
    is_void = db.Column(db.Boolean, nullable=False, default=False,
                        server_default='0')
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    student = db.relationship('StudentModel', lazy=True)


class StudentIssue(db.Model):
    """Stock handed to a student as part of the admission package (Phase 3).

    ``kind`` is 'books' or 'uniform' (``quantity`` = number of SETS taken from
    the class's set) or 'item' (``quantity`` = units of ``product_id``).  Its
    ``Sale`` rows carry price 0 - the money was already received through the
    admission fee.  Append-only: a mistake is voided (stock goes back).
    """
    __tablename__ = 'student_issues'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_student_issues_qty_positive'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False,
                           index=True)
    kind = db.Column(db.String(20), nullable=False)
    set_id = db.Column(db.Integer, db.ForeignKey('product_sets.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(200), nullable=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    student = db.relationship('StudentModel', lazy=True)
    set = db.relationship('ProductSet', lazy=True)
    product = db.relationship('Product', lazy=True)
    sales = db.relationship('Sale', backref='issue', lazy=True,
                            order_by='Sale.id')

    @property
    def label(self):
        if self.kind == 'item':
            return '%d x %s' % (self.quantity, self.product.name if self.product else 'item')
        name = self.set.name if self.set else self.kind.capitalize()
        return '%s x %d' % (name, self.quantity)


SET_KINDS = ('books', 'uniform', 'other')


class ProductSet(db.Model):
    """A bundle of items bought or sold together (a class's books, a full uniform).

    A set never holds stock of its own: stock is always kept per item, so one
    English book can still be sold alone.  Buying or selling a set simply books
    every item in it.
    """
    __tablename__ = 'product_sets'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='other')
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship('ProductSetItem', backref='set', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='ProductSetItem.id')
    class_ = db.relationship('ClassModel', lazy=True)


class ProductSetItem(db.Model):
    __tablename__ = 'product_set_items'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_product_set_items_qty_positive'),
        db.UniqueConstraint('set_id', 'product_id', name='uq_product_set_items'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey('product_sets.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    product = db.relationship('Product', lazy=True)


class CanteenEntry(db.Model):
    """One "totals only" canteen figure (Phase 4): the day's / week's total
    sales or total purchases, typed as a single amount.

    It owns no money of its own.  A *sale* total is an ``OtherIncome`` row in the
    "Canteen" category and a *purchase* total is an ``Expense`` row in the
    "Canteen Purchases" category, so every financial screen already counts them
    and nothing is counted twice.  Voiding an entry voids that linked row.
    """
    __tablename__ = 'canteen_entries'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False)          # 'sale' | 'purchase'
    entry_date = db.Column(db.Date, nullable=False, index=True)
    note = db.Column(db.String(200), nullable=True)
    income_id = db.Column(db.Integer, db.ForeignKey('other_income.id'),
                          nullable=True, index=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'),
                           nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    # Supplier credit (udhaar) on a purchase total.  ``bill_paisa`` is filled ONLY
    # when part of the bill was left unpaid; every older purchase (NULL) was
    # paid in full and behaves exactly as before.  The linked Expense then holds
    # just the money paid on the day (``paid_paisa``) - the unpaid part is a
    # supplier due, never an expense - and later payments are CanteenPayment rows.
    supplier = db.Column(db.String(120), nullable=True)
    bill_paisa = db.Column(db.Integer, nullable=True)
    paid_paisa = db.Column(db.Integer, nullable=True)
    # A bill with nothing paid today has no Expense row to carry the void state.
    void_flag = db.Column(db.Boolean, nullable=False, default=False,
                          server_default='0')
    void_note = db.Column(db.String(255), nullable=True)

    income = db.relationship('OtherIncome', lazy=True)
    expense = db.relationship('Expense', lazy=True)

    @property
    def linked(self):
        return self.income if self.kind == 'sale' else self.expense

    @property
    def is_credit(self):
        return self.kind == 'purchase' and self.bill_paisa is not None

    @property
    def amount_paisa(self):
        if self.is_credit:
            return self.bill_paisa or 0
        row = self.linked
        return (row.amount_paisa or 0) if row is not None else 0

    @property
    def is_void(self):
        if self.is_credit:
            return bool(self.void_flag)
        row = self.linked
        return bool(row.is_void) if row is not None else True

    @property
    def void_reason(self):
        if self.is_credit:
            return (self.void_note or '') if self.void_flag else ''
        row = self.linked
        return (row.void_reason or '') if row is not None and row.is_void else ''

    @property
    def paid_total_paisa(self):
        if not self.is_credit:
            return self.amount_paisa
        later = sum(p.amount_paisa for p in self.payments if not p.is_void)
        return (self.paid_paisa or 0) + later

    @property
    def balance_paisa(self):
        if not self.is_credit or self.is_void:
            return 0
        return max(0, (self.bill_paisa or 0) - self.paid_total_paisa)


class CanteenPayment(db.Model):
    """Money paid to a canteen supplier AFTER the purchase day.

    Each payment owns one ``Expense`` row (category "Canteen Purchases") dated
    the payment day, so it is cash out exactly when it is paid.  A mistake is
    voided with a reason (the expense goes with it) and the balance re-opens.
    """
    __tablename__ = 'canteen_payments'
    __table_args__ = (
        db.CheckConstraint('amount_paisa > 0', name='ck_canteen_payments_positive'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('canteen_entries.id'),
                         nullable=False, index=True)
    amount_paisa = db.Column(db.Integer, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, index=True)
    method = db.Column(db.String(20), nullable=True)
    note = db.Column(db.String(200), nullable=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'),
                           nullable=True, index=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    entry = db.relationship('CanteenEntry', lazy=True,
                            backref=db.backref('payments', lazy=True,
                                               order_by='CanteenPayment.id'))
    expense = db.relationship('Expense', lazy=True)


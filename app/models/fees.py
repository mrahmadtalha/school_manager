"""Fee ledger models (financial v2).

Money is stored as **integer paisa** (1 rupee = 100 paisa) in every ``*_paisa``
column.  The ``*_rupees``-style Python properties (``amount``, ``amount_due``,
``amount_paid``) convert on read and on write, so existing service code keeps
working unchanged while the database never stores a float.
"""

from datetime import datetime

from app.database import db

TXN_CHARGE = 'charge'
TXN_PAYMENT = 'payment'
TXN_ADJUSTMENT = 'adjustment'
TXN_REFUND = 'refund'
TXN_WRITEOFF = 'writeoff'

TXN_TYPES = (TXN_CHARGE, TXN_PAYMENT, TXN_ADJUSTMENT, TXN_REFUND, TXN_WRITEOFF)

TXN_LABELS = {
    TXN_CHARGE: 'Fee charged',
    TXN_PAYMENT: 'Payment received',
    TXN_ADJUSTMENT: 'Adjustment',
    TXN_REFUND: 'Refund',
    TXN_WRITEOFF: 'Write-off',
}

#: Transaction types that settle charges through allocations.
SETTLING_TYPES = (TXN_PAYMENT, TXN_WRITEOFF)


def to_paisa(value):
    """Rupees (float/int/str) -> integer paisa, half-up rounded."""
    try:
        return int(round(float(value or 0) * 100))
    except (TypeError, ValueError):
        return 0


def to_rupees(paisa):
    return (paisa or 0) / 100.0


class FeeRecordModel(db.Model):
    """Derived per-student, per-month fee summary.

    This table is a *cache* of the ledger + allocations. It is always
    recomputed by ``app.services.fee_ledger.recompute_fee_record`` so the
    stored totals can never drift from the underlying transactions.
    """

    __tablename__ = 'fee_records'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    month_year = db.Column(db.String(20), nullable=False)  # e.g. "September 2026"
    amount_due_paisa = db.Column(db.Integer, nullable=False, default=0)
    amount_paid_paisa = db.Column(db.Integer, nullable=False, default=0)
    amount_written_off_paisa = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='Pending')  # Paid, Pending, Partial
    payment_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(200), nullable=True)

    student_info = db.relationship('StudentModel', backref='fee_records', lazy=True)

    @property
    def amount_due(self):
        return to_rupees(self.amount_due_paisa)

    @amount_due.setter
    def amount_due(self, value):
        self.amount_due_paisa = to_paisa(value)

    @property
    def amount_paid(self):
        return to_rupees(self.amount_paid_paisa)

    @amount_paid.setter
    def amount_paid(self, value):
        self.amount_paid_paisa = to_paisa(value)

    @property
    def amount_written_off(self):
        return to_rupees(self.amount_written_off_paisa)

    @amount_written_off.setter
    def amount_written_off(self, value):
        self.amount_written_off_paisa = to_paisa(value)

    @property
    def balance(self):
        return round((self.amount_due or 0.0) - (self.amount_paid or 0.0)
                     - (self.amount_written_off or 0.0), 2)


class FeeTransaction(db.Model):
    """Append-only fee ledger entry.

    A record exists for every amount charged to a student and for every cash
    movement (payment, refund, write-off), so any month's balance can be
    reconstructed from the ledger and reconciled against the derived summary in
    ``fee_records``.

    ``payment_date`` is the explicit cash date (back-dating is normal); it
    drives every Cash In figure.  ``related_txn_id`` links a refund to the
    payment it returns.
    """

    __tablename__ = 'fee_transactions'
    __table_args__ = (
        db.Index('idx_fee_txn_student_month', 'student_id', 'month_year'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    month_year = db.Column(db.String(20), nullable=False)
    txn_type = db.Column(db.String(20), nullable=False)  # charge|payment|adjustment|refund|writeoff
    amount_paisa = db.Column(db.Integer, nullable=False, default=0)
    method = db.Column(db.String(30), nullable=True)      # cash | bank | online | other
    reference = db.Column(db.String(80), nullable=True)   # receipt no / slip no
    note = db.Column(db.String(255), nullable=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    payment_date = db.Column(db.Date, nullable=True)      # explicit cash date (payments/refunds)
    # Allocation order override (payments/write-offs only).  NULL = default
    # oldest-dues-first.  A month label here settles THAT month first, then the
    # rest oldest-first.  Legacy rows carry their original month so a refund's
    # re-allocation reproduces exactly what they settled before the rule change.
    apply_month = db.Column(db.String(20), nullable=True)
    related_txn_id = db.Column(db.Integer, db.ForeignKey('fee_transactions.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    student_info = db.relationship('StudentModel', backref='fee_transactions', lazy=True)

    @property
    def amount(self):
        return to_rupees(self.amount_paisa)

    @amount.setter
    def amount(self, value):
        self.amount_paisa = to_paisa(value)

    @property
    def type_label(self):
        return TXN_LABELS.get(self.txn_type, self.txn_type)

    @property
    def signed_amount(self):
        """Signed rupees: charges/adjustments +, payments/refunds/write-offs −."""
        if self.is_void:
            return 0.0
        value = to_rupees(self.amount_paisa)
        if self.txn_type in (TXN_PAYMENT, TXN_REFUND, TXN_WRITEOFF):
            return -round(value, 2)
        return round(value, 2)

    def __repr__(self):
        return f'<FeeTransaction {self.id} {self.txn_type} {self.amount_paisa} {self.month_year}>'


class FeePaymentAllocation(db.Model):
    """Links a settling transaction (payment or write-off) to a specific charge.

    Created oldest-charge-first by ``fee_ledger.allocate_transaction``;
    allocations are the single source of truth for how much of each charge is
    settled.  A payment whose amount exceeds all outstanding charges keeps the
    remainder unallocated — that is the student's advance credit.
    """

    __tablename__ = 'fee_payment_allocations'
    __table_args__ = (
        db.Index('idx_fee_alloc_charge', 'charge_txn_id'),
        db.Index('idx_fee_alloc_payment', 'payment_txn_id'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    payment_txn_id = db.Column(db.Integer, db.ForeignKey('fee_transactions.id'),
                               nullable=False)
    charge_txn_id = db.Column(db.Integer, db.ForeignKey('fee_transactions.id'),
                              nullable=False)
    amount_paisa = db.Column(db.Integer, nullable=False, default=0)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    payment_txn = db.relationship('FeeTransaction', foreign_keys=[payment_txn_id],
                                  backref='allocations')
    charge_txn = db.relationship('FeeTransaction', foreign_keys=[charge_txn_id],
                                 backref='charge_allocations')

    @property
    def amount(self):
        return to_rupees(self.amount_paisa)

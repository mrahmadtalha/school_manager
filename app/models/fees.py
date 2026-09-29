from datetime import datetime

from app.database import db

TXN_CHARGE = 'charge'
TXN_PAYMENT = 'payment'
TXN_ADJUSTMENT = 'adjustment'

TXN_TYPES = (TXN_CHARGE, TXN_PAYMENT, TXN_ADJUSTMENT)

TXN_LABELS = {
    TXN_CHARGE: 'Fee charged',
    TXN_PAYMENT: 'Payment received',
    TXN_ADJUSTMENT: 'Adjustment',
}


class FeeRecordModel(db.Model):
    """Derived per-student, per-month fee summary.

    This table is a *cache* of ``FeeTransaction`` rows. It is always recomputed
    from the ledger by ``app.services.fee_ledger.recompute_fee_record`` so that
    the stored totals can never drift from the underlying transactions.
    """

    __tablename__ = 'fee_records'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    month_year = db.Column(db.String(20), nullable=False)  # e.g. "September 2026"
    amount_due = db.Column(db.Float, nullable=False, default=0.0)
    amount_paid = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default='Pending')  # Paid, Pending, Partial
    payment_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(200), nullable=True)

    student_info = db.relationship('StudentModel', backref='fee_records', lazy=True)

    @property
    def balance(self):
        return round((self.amount_due or 0.0) - (self.amount_paid or 0.0), 2)


class FeeTransaction(db.Model):
    """Append-only fee ledger entry.

    A record exists for every amount charged to a student and for every payment
    received, so any month's balance can be reconstructed from the ledger and
    reconciled against the derived summary in ``fee_records``.
    """

    __tablename__ = 'fee_transactions'
    __table_args__ = (
        db.Index('idx_fee_txn_student_month', 'student_id', 'month_year'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    month_year = db.Column(db.String(20), nullable=False)
    txn_type = db.Column(db.String(20), nullable=False)  # charge | payment | adjustment
    amount = db.Column(db.Float, nullable=False, default=0.0)
    method = db.Column(db.String(30), nullable=True)      # cash | bank | online | other
    reference = db.Column(db.String(80), nullable=True)   # receipt no / slip no
    note = db.Column(db.String(255), nullable=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    student_info = db.relationship('StudentModel', backref='fee_transactions', lazy=True)

    @property
    def type_label(self):
        return TXN_LABELS.get(self.txn_type, self.txn_type)

    @property
    def signed_amount(self):
        """Positive for charges/adjustments, negative for payments."""
        if self.is_void:
            return 0.0
        if self.txn_type == TXN_PAYMENT:
            return -round(self.amount or 0.0, 2)
        return round(self.amount or 0.0, 2)

    def __repr__(self):
        return f'<FeeTransaction {self.id} {self.txn_type} {self.amount} {self.month_year}>'

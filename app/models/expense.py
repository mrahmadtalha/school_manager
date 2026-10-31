"""Operational expense tracking (categories + expense entries), financial v2.

Money is stored as integer paisa.  Expenses are voided, never deleted: a
voided row keeps its amount, reason and actor, and every total excludes it.

The **"Salaries" category is system-reserved** (``is_system``): rows in it are
created only by salary payments, and manual expense entry refuses the category
— so Salaries in the expense totals comes only from Payroll, by construction.
"""
from datetime import datetime
from app.timeutil import utcnow

from app.database import db
from app.models.fees import to_paisa, to_rupees

#: Payment methods available when logging an expense.
EXPENSE_PAYMENT_METHODS = ('Cash', 'Bank', 'Cheque')

#: Categories created automatically on a fresh installation.
DEFAULT_EXPENSE_CATEGORIES = (
    'Utilities',
    'Building/Rent',
    'Maintenance',
    'Stationery & Printing',
    'Refreshment/Events',
    'Miscellaneous',
)

#: System-reserved category fed exclusively by payroll payments.
RESERVED_SALARIES_CATEGORY = 'Salaries'


class ExpenseCategory(db.Model):
    """A school-defined category for operational expenses."""

    __tablename__ = 'expense_categories'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'


class Expense(db.Model):
    """A single logged operational expense (voidable, never deleted)."""

    __tablename__ = 'expenses'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'),
                            nullable=False)
    amount_paisa = db.Column(db.Integer, nullable=False, default=0)
    payment_method = db.Column(db.String(20), nullable=False, default='Cash')
    date = db.Column(db.Date, nullable=False, default=utcnow)
    receipt_no = db.Column(db.String(80), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    logged_by_id = db.Column(db.Integer, nullable=True)
    logged_by_name = db.Column(db.String(80), nullable=True, default='system')
    updated_by_id = db.Column(db.Integer, nullable=True)
    updated_by_name = db.Column(db.String(80), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    category = db.relationship('ExpenseCategory',
                               backref=db.backref('expenses', lazy='dynamic'))

    @property
    def amount(self):
        return to_rupees(self.amount_paisa)

    @amount.setter
    def amount(self, value):
        self.amount_paisa = to_paisa(value)

    def __repr__(self):
        return f'<Expense #{self.id} {self.amount_paisa} ({self.payment_method})>'

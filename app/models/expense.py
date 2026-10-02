"""Operational expense tracking (categories + expense entries)."""
from datetime import datetime

from app.database import db

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


class ExpenseCategory(db.Model):
    """A school-defined category for operational expenses."""

    __tablename__ = 'expense_categories'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'


class Expense(db.Model):
    """A single logged operational expense."""

    __tablename__ = 'expenses'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'),
                            nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    payment_method = db.Column(db.String(20), nullable=False, default='Cash')
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    receipt_no = db.Column(db.String(80), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    logged_by_id = db.Column(db.Integer, nullable=True)
    logged_by_name = db.Column(db.String(80), nullable=True, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    category = db.relationship('ExpenseCategory',
                               backref=db.backref('expenses', lazy='dynamic'))

    def __repr__(self):
        return f'<Expense #{self.id} {self.amount} ({self.payment_method})>'

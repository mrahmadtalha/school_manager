"""Other Income models (Phase 3a): non-fee money the school receives.

Canteen, events, trips, activities, certificates, miscellaneous — money is
integer paisa like every other financial table.  Records are append-only:
corrections void a row (mandatory reason); voided rows appear in no total.
"""
from datetime import datetime

from app.database import db
from app.models.fees import to_paisa, to_rupees

DEFAULT_OTHER_INCOME_CATEGORIES = (
    'Canteen', 'Events', 'Trips', 'Activities', 'Certificates', 'ID Cards',
    'Miscellaneous',
)


class OtherIncomeCategory(db.Model):
    __tablename__ = 'other_income_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class OtherIncome(db.Model):
    __tablename__ = 'other_income'
    __table_args__ = (
        db.CheckConstraint('amount_paisa > 0', name='ck_other_income_positive'),
    )

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer,
                            db.ForeignKey('other_income_categories.id'),
                            nullable=False)
    income_date = db.Column(db.Date, nullable=False, index=True)
    amount_paisa = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200), nullable=True)

    # Set for money that belongs to one student (admission fee receipts).
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           nullable=True, index=True)
    receipt_no = db.Column(db.String(40), nullable=True, index=True)
    payment_method = db.Column(db.String(20), nullable=True)

    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)

    created_by_id = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_by_id = db.Column(db.Integer, nullable=True)
    updated_by_name = db.Column(db.String(80), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True,
                           onupdate=datetime.utcnow)

    category = db.relationship('OtherIncomeCategory', backref='incomes')
    student = db.relationship('StudentModel', lazy=True)

    @property
    def amount(self):
        return to_rupees(self.amount_paisa)

    @amount.setter
    def amount(self, value):
        self.amount_paisa = to_paisa(value)

    def __repr__(self):
        return f'<OtherIncome {self.id} {self.amount_paisa}>'

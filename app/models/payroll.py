"""Monthly staff payroll records (financial v2).

Money is stored as integer paisa; ``base_salary``/``bonus``/``deductions``/
``net_salary`` are rupee properties that convert on read and write.

Payments live in :class:`SalaryPayment` rows (partial payments allowed); a
payroll row's paid amount and status are derived from them.  Every salary
payment automatically creates an Expense row in the system-reserved "Salaries"
category, so Cash Out and the expense breakdown never double-count and never
miss salaries.
"""
from datetime import datetime
from app.timeutil import utcnow

from app.database import db
from app.models.fees import to_paisa, to_rupees

#: Legacy payment status values (kept in sync on write for compatibility).
PAYROLL_STATUSES = ('Pending', 'Partial', 'Paid')

#: Payment methods available when settling a salary.
PAYROLL_PAYMENT_METHODS = ('Cash', 'Bank', 'Cheque')


class StaffPayroll(db.Model):
    """One month of salary for one teacher (unique per teacher + month)."""

    __tablename__ = 'staff_payroll'
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'month_year',
                            name='uq_staff_payroll_teacher_month'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    month_year = db.Column(db.String(10), nullable=False)  # '2026-09'
    base_salary_paisa = db.Column(db.Integer, nullable=False, default=0)
    bonus_paisa = db.Column(db.Integer, nullable=False, default=0)
    deductions_paisa = db.Column(db.Integer, nullable=False, default=0)
    net_salary_paisa = db.Column(db.Integer, nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default='Pending')
    payment_date = db.Column(db.Date, nullable=True)   # date of the first/last payment
    payment_method = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    generated_by = db.Column(db.String(80), nullable=True, default='system')
    updated_by_id = db.Column(db.Integer, nullable=True)
    updated_by_name = db.Column(db.String(80), nullable=True)

    # Attendance snapshot for the month (kept for audits and payslips).
    working_days = db.Column(db.Integer, nullable=True)
    present_days = db.Column(db.Integer, nullable=True)
    absent_days = db.Column(db.Integer, nullable=True)
    late_days = db.Column(db.Integer, nullable=True)
    leave_days = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow,
                           onupdate=utcnow, nullable=False)

    teacher = db.relationship('TeacherModel',
                              backref=db.backref('payroll_records', lazy='dynamic'))
    payments = db.relationship('SalaryPayment', backref='payroll', lazy=True)

    @property
    def base_salary(self):
        return to_rupees(self.base_salary_paisa)

    @base_salary.setter
    def base_salary(self, value):
        self.base_salary_paisa = to_paisa(value)

    @property
    def bonus(self):
        return to_rupees(self.bonus_paisa)

    @bonus.setter
    def bonus(self, value):
        self.bonus_paisa = to_paisa(value)

    @property
    def deductions(self):
        return to_rupees(self.deductions_paisa)

    @deductions.setter
    def deductions(self, value):
        self.deductions_paisa = to_paisa(value)

    @property
    def net_salary(self):
        return to_rupees(self.net_salary_paisa)

    @net_salary.setter
    def net_salary(self, value):
        self.net_salary_paisa = to_paisa(value)

    @property
    def paid_amount(self):
        """Rupees actually paid against this month (from active payments).

        Deliberately query-based: the ``payments`` relationship caches, and a
        payment recorded moments ago must be visible immediately.
        """
        from sqlalchemy import func
        return to_rupees((db.session.query(
            func.coalesce(func.sum(SalaryPayment.amount_paisa), 0))
            .filter(SalaryPayment.payroll_id == self.id,
                    SalaryPayment.is_void.is_(False)).scalar()) or 0)

    @property
    def remaining_amount(self):
        return round(self.net_salary - self.paid_amount, 2)

    def __repr__(self):
        return f'<StaffPayroll {self.month_year} teacher={self.teacher_id} net={self.net_salary_paisa}>'


class SalaryPayment(db.Model):
    """A cash payment against one month's salary (partial payments allowed).

    Every active payment is mirrored by an Expense row in the reserved
    "Salaries" category (created by ``payroll_service.record_salary_payment``),
    which is what makes the expense totals and Cash Out agree by construction.
    """

    __tablename__ = 'salary_payments'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    payroll_id = db.Column(db.Integer, db.ForeignKey('staff_payroll.id'), nullable=False)
    amount_paisa = db.Column(db.Integer, nullable=False, default=0)
    payment_date = db.Column(db.Date, nullable=False)
    method = db.Column(db.String(20), nullable=True)
    note = db.Column(db.String(255), nullable=True)
    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    created_by_id = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')

    teacher = db.relationship('TeacherModel', backref='salary_payments')
    expense = db.relationship('Expense', backref='salary_payment', foreign_keys=[expense_id])

    @property
    def amount(self):
        return to_rupees(self.amount_paisa)

    @amount.setter
    def amount(self, value):
        self.amount_paisa = to_paisa(value)

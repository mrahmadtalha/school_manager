"""Monthly staff payroll records."""
from datetime import datetime

from app.database import db

#: Payment status values for a payroll row.
PAYROLL_STATUSES = ('Pending', 'Paid')

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
    base_salary = db.Column(db.Float, nullable=False, default=0.0)
    bonus = db.Column(db.Float, nullable=False, default=0.0)
    deductions = db.Column(db.Float, nullable=False, default=0.0)
    net_salary = db.Column(db.Float, nullable=False, default=0.0)
    payment_status = db.Column(db.String(20), nullable=False, default='Pending')
    payment_date = db.Column(db.Date, nullable=True)
    payment_method = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    generated_by = db.Column(db.String(80), nullable=True, default='system')

    # Attendance snapshot for the month (kept for audits and payslips).
    working_days = db.Column(db.Integer, nullable=True)
    present_days = db.Column(db.Integer, nullable=True)
    absent_days = db.Column(db.Integer, nullable=True)
    late_days = db.Column(db.Integer, nullable=True)
    leave_days = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    teacher = db.relationship('TeacherModel',
                              backref=db.backref('payroll_records', lazy='dynamic'))

    def __repr__(self):
        return f'<StaffPayroll {self.month_year} teacher={self.teacher_id} net={self.net_salary}>'

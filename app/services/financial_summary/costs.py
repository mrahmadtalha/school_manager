"""Cost side of the summary: salaries paid, expenses and the payroll / expense breakdowns."""

from app.database import db
from app.models import (Expense, ExpenseCategory, SalaryPayment, StaffPayroll, TeacherModel)

from .common import _money


def salaries_paid_total(start, end):
    """Cash Out to staff: salary payments by their explicit payment date."""
    if not start or not end:
        return 0.0
    total = (SalaryPayment.query
             .filter(SalaryPayment.is_void.is_(False),
                     SalaryPayment.payment_date >= start,
                     SalaryPayment.payment_date <= end)
             .with_entities(db.func.coalesce(db.func.sum(SalaryPayment.amount_paisa), 0))
             .scalar())
    return _money((total or 0) / 100.0)


def expenses_total(start, end):
    """Cash Out: every active expense in the window, Salaries category included."""
    if not start or not end:
        return 0.0
    total = (Expense.query
             .filter(Expense.is_void.is_(False),
                     Expense.date >= start, Expense.date <= end)
             .with_entities(db.func.coalesce(db.func.sum(Expense.amount_paisa), 0))
             .scalar())
    return _money((total or 0) / 100.0)


def payroll_snapshot(month_year):
    """Accrual view of one salary month: payable vs settled via payments."""
    records = StaffPayroll.query.filter_by(month_year=month_year).all()
    total = _money(sum(r.net_salary or 0 for r in records))
    paid = _money(sum(r.paid_amount for r in records))
    partially = sum(1 for r in records
                    if 0 < r.paid_amount + 1e-9 < (r.net_salary or 0) - 1e-9)
    fully = sum(1 for r in records
                if r.net_salary and r.paid_amount + 1e-9 >= r.net_salary)
    return {'total': total, 'paid': paid, 'pending': _money(total - paid),
            'count': len(records), 'paid_count': fully, 'partial_count': partially,
            'unpaid_count': len(records) - fully - partially}


def salary_remaining_total():
    """Every rupee of generated salary not yet paid, school-wide (accrual).

    Includes months still in progress: a payroll month counts from the moment
    its rows are generated until payments cover it.  Never part of Cash Out
    or Net Position — it is reported so nothing owed to staff stays invisible.
    """
    total_payable = (db.session.query(
        db.func.coalesce(db.func.sum(StaffPayroll.net_salary_paisa), 0)).scalar()) or 0
    paid = (db.session.query(
        db.func.coalesce(db.func.sum(SalaryPayment.amount_paisa), 0))
        .filter(SalaryPayment.is_void.is_(False)).scalar()) or 0
    return _money((total_payable - paid) / 100.0)


def expense_breakdown(start, end):
    if not start or not end:
        return []
    # Salaries are their own card (Salaries Paid); the breakdown covers the
    # other expense categories only.
    from app.services.expense_service import RESERVED_SALARIES_CATEGORY
    rows = (db.session.query(
                ExpenseCategory.name,
                db.func.coalesce(db.func.sum(Expense.amount_paisa), 0),
                db.func.count(Expense.id))
            .join(Expense, Expense.category_id == ExpenseCategory.id)
            .filter(Expense.is_void.is_(False),
                    ExpenseCategory.name != RESERVED_SALARIES_CATEGORY,
                    Expense.date >= start, Expense.date <= end)
            .group_by(ExpenseCategory.id)
            .order_by(db.func.sum(Expense.amount_paisa).desc())
            .all())
    return [{'name': name, 'total': _money(total / 100.0), 'count': count}
            for name, total, count in rows]


def payroll_rows(month_year):
    return (StaffPayroll.query
            .join(TeacherModel)
            .filter(StaffPayroll.month_year == month_year)
            .order_by(TeacherModel.teacher_name).all())

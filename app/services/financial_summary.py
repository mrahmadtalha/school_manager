"""Financial overview: fee revenue vs payroll + expenses, net position and trends."""
import csv
import io
from datetime import date, timedelta

from app.database import db
from app.models import (Expense, ExpenseCategory, FeeTransaction, OtherIncome,
                        Purchase, Sale, SalaryPayment,
                        StaffPayroll, TeacherModel, TXN_PAYMENT, TXN_REFUND)
from app.services.payroll_service import (month_bounds, month_label, parse_month,
                                          recent_month_keys, shift_month)


def short_label(month_year):
    parsed = parse_month(month_year)
    return date(parsed[0], parsed[1], 1).strftime('%b %Y') if parsed else ''


def _money(value):
    return round(float(value or 0), 2)


def _inventory_enabled():
    """Phase 3b gate: inventory/sales UI and metrics only exist when enabled."""
    from flask import current_app
    return bool(current_app.config.get('FEATURE_INVENTORY_SALES', False))


# --------------------------------------------------------------------------- #
# Core numbers
# --------------------------------------------------------------------------- #

def _cash_date_column():
    """Explicit cash date where present, created date as legacy fallback."""
    return db.func.coalesce(FeeTransaction.payment_date,
                            db.func.date(FeeTransaction.created_at))


def fee_collections(start, end):
    """Cash In from fees: payments received in the window (by explicit payment
    date), minus refunds. Voided rows are never counted."""
    if not start or not end:
        return 0.0
    cash_date = _cash_date_column()
    rows = FeeTransaction.query.filter(
        FeeTransaction.txn_type.in_((TXN_PAYMENT, TXN_REFUND)),
        FeeTransaction.is_void.is_(False),
        cash_date >= start.isoformat(),
        cash_date <= end.isoformat(),
    ).all()
    total = sum((r.amount or 0) if r.txn_type == TXN_PAYMENT else -(r.amount or 0)
                for r in rows)
    return _money(total)


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


def _total_outstanding():
    """All receivables: charges + adjustments minus settled (payments, write-offs)."""
    from app.models import FeePaymentAllocation
    charged = (db.session.query(
                   db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
               .filter(FeeTransaction.is_void.is_(False),
                       FeeTransaction.txn_type.in_(('charge', 'adjustment'))).scalar()) or 0
    settled = (db.session.query(
                   db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
               .filter(FeePaymentAllocation.is_void.is_(False)).scalar()) or 0
    return _money((charged - settled) / 100.0)


def former_students_summary():
    """Count + total dues of former students, and the written-off total."""
    from app.models import FeePaymentAllocation, StudentModel, TXN_WRITEOFF
    from app.models.fees import to_rupees
    students = StudentModel.query.filter_by(is_active=False).all()
    rows = []
    total = 0.0
    for student in students:
        charged = (db.session.query(
                       db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
                   .filter(FeeTransaction.student_id == student.id,
                           FeeTransaction.is_void.is_(False),
                           FeeTransaction.txn_type.in_(('charge', 'adjustment'))).scalar()) or 0
        settled = (db.session.query(
                       db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
                   .join(FeeTransaction,
                         FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
                   .filter(FeeTransaction.student_id == student.id,
                           FeePaymentAllocation.is_void.is_(False)).scalar()) or 0
        balance = round((charged - settled) / 100.0, 2)
        if balance > 0:
            rows.append({'student': student, 'balance': balance})
            total = _money(total + balance)
    written_off = (db.session.query(
                       db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
                   .filter(FeeTransaction.is_void.is_(False),
                           FeeTransaction.txn_type == TXN_WRITEOFF).scalar()) or 0
    rows.sort(key=lambda item: -item['balance'])
    from app.models import STUDENT_STATUS_LABELS
    by_status = {}
    for item in rows:
        status = item['student'].status or 'struck_off'
        entry = by_status.setdefault(status, {'count': 0, 'total': 0.0,
                                              'label': STUDENT_STATUS_LABELS.get(status, status)})
        entry['count'] += 1
        entry['total'] = _money(entry['total'] + item['balance'])
    return {'count': len(rows), 'total': total, 'rows': rows,
            'by_status': by_status,
            'written_off': _money(to_rupees(written_off))}


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


def fee_month_overview(month_key):
    """One month's fee picture: expected, collected, remaining, rate.

    'collected' counts only money that settled THIS month's own charges;
    money received in the month that settled OLDER months is reported as
    arrears recovery and never as this month's collection.
    """
    split = collection_split(month_key)
    expected = _money(((db.session.query(
        db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
        .filter(FeeTransaction.is_void.is_(False),
                FeeTransaction.txn_type.in_(('charge', 'adjustment')),
                FeeTransaction.month_year == month_label(month_key)).scalar()) or 0)
        / 100.0)
    collected = split['current']
    remaining = _money(max(0.0, expected - collected))
    rate = round(collected * 100.0 / expected, 1) if expected > 0 else None
    return {'month': month_key, 'label': month_label(month_key),
            'expected': expected, 'collected': collected,
            'arrears': split['arrears'], 'remaining': remaining, 'rate': rate}


def student_outstanding_rows(class_id=None, section_id=None, month_year=None,
                             status_filter='active'):
    """Student-wise outstanding dues for the money page's filtered list.

    ``month_year`` ('YYYY-MM') limits the look to that month's own fee
    record; without it the figure is the student's full ledger outstanding.
    ``status_filter``: 'active' (default), 'former' (left students) or 'all'.
    """
    from app.models import STUDENT_STATUS_LABELS, StudentModel
    from app.services.fee_ledger import (student_month_outstanding_paisa,
                                         student_outstanding_paisa)

    query = StudentModel.query
    if status_filter == 'former':
        query = query.filter(StudentModel.is_active.is_(False))
    elif status_filter != 'all':
        query = query.filter(StudentModel.is_active.is_(True))
    if class_id:
        query = query.filter(StudentModel.class_id == class_id)
    if section_id:
        query = query.filter(StudentModel.section_id == section_id)

    label = month_label(month_year) if month_year and parse_month(month_year) else None
    rows = []
    for student in query.order_by(StudentModel.student_name).all():
        if label:
            # Ledger truth, not the derived fee-record cache: the dues list
            # must always agree with the rest of the summary.
            outstanding = round(student_month_outstanding_paisa(student.id, label)
                                / 100.0, 2)
        else:
            outstanding = round(student_outstanding_paisa(student.id) / 100.0, 2)
        if outstanding <= 0:
            continue    # a dues list shows students who actually owe money
        rows.append({
            'student': student,
            'class_name': student.class_info.name if student.class_info else '—',
            'section_name': (student.section_info.name if student.section_info
                             else '—'),
            'status_label': STUDENT_STATUS_LABELS.get(student.status, student.status),
            'leaving_date': student.leaving_date,
            'outstanding': outstanding,
        })
    rows.sort(key=lambda item: -item['outstanding'])
    return rows


def _label_for_key(month_year):
    """'2026-09' -> 'September 2026' (the ledger's month label format)."""
    parsed = parse_month(month_year)
    return date(parsed[0], parsed[1], 1).strftime('%B %Y') if parsed else month_year


def collection_split(month_year):
    """Current-month collection vs arrears recovered, by allocation target.

    'current' = payments (by payment date in the month) that settled charges of
    the same month; 'arrears' = payments that settled OLDER months' charges.
    Arrears recovery is never counted as current-month fee revenue.
    """
    from app.models import FeePaymentAllocation
    start, end = month_bounds(month_year)
    if not start:
        return {'current': 0.0, 'arrears': 0.0}
    charge_alias = db.aliased(FeeTransaction)
    cash_date = _cash_date_column()
    rows = (db.session.query(FeePaymentAllocation.amount_paisa, charge_alias.month_year)
            .join(FeeTransaction, FeePaymentAllocation.payment_txn_id == FeeTransaction.id)
            .join(charge_alias, FeePaymentAllocation.charge_txn_id == charge_alias.id)
            .filter(FeeTransaction.txn_type == TXN_PAYMENT,
                    FeeTransaction.is_void.is_(False),
                    FeePaymentAllocation.is_void.is_(False),
                    cash_date >= start.isoformat(),
                    cash_date <= end.isoformat())
            .all())
    label = _label_for_key(month_year)
    current = arrears = 0
    for amount_paisa, charge_month in rows:
        if charge_month == label:
            current += amount_paisa
        else:
            arrears += amount_paisa
    return {'current': _money(current / 100.0), 'arrears': _money(arrears / 100.0)}

def month_snapshot(month_year):
    """One month on BOTH bases, clearly labelled.

    Cash basis:  Cash In (fee collections net of refunds) minus Cash Out (all
                 expenses, of which salaries are the payroll-fed part) gives
                 the Net Position.
    Accrual:     Fees Remaining (receivables) and Salary Remaining (payables)
                 are reported separately, never mixed into Net Position.
    """
    start, end = month_bounds(month_year)
    cash_in_fees = fee_collections(start, end)
    from app.services.other_income_service import month_total
    other_income = month_total(start, end)
    # Admission-fee receipts are part of other_income (already inside cash_in);
    # reported on their own line only, never added again.
    from app.services.admission_fee import income_total as admission_income_total
    admission_fees = admission_income_total(start, end)
    from app.services import inventory_service
    sales_revenue, sales_cogs = inventory_service.month_sales_totals(start, end)
    purchases = inventory_service.month_purchase_totals(start, end)
    cash_in = _money(cash_in_fees + other_income + sales_revenue)
    expenses_paid = expenses_total(start, end)
    cash_out = _money(expenses_paid + purchases)
    salaries_paid = salaries_paid_total(start, end)
    payroll = payroll_snapshot(month_year)
    split = collection_split(month_year)
    # The dues that arose from this month itself (ledger, paisa).
    month_outstanding = month_fee_buckets(start, end)['outstanding']
    return {
        'month': month_year,
        'label': month_label(month_year),
        'start': start,
        'end': end,
        'admission_fees': admission_fees,
        # cash basis
        'revenue': cash_in,
        'cash_in': cash_in,
        'fee_income': cash_in_fees,
        'other_income': other_income,
        'sales': sales_revenue,
        'sales_cogs': sales_cogs,
        'gross_profit': _money(sales_revenue - sales_cogs),
        'purchases': purchases,
        'expenses': expenses_paid,
        'cash_out': cash_out,
        'salaries_paid': salaries_paid,
        'other_expenses': _money(expenses_paid - salaries_paid),
        'net': _money(cash_in - cash_out),
        'net_position': _money(cash_in - cash_out),
        # Operating view: Revenue − Salaries − Operating Expenses − COGS.
        'operating_position': _money(cash_in - expenses_paid - sales_cogs),
        # accrual (separate)
        'fee_collected_current': split['current'],
        'arrears_recovered': split['arrears'],
        'fees_remaining': _total_outstanding(),
        'fees_remaining_period': _money(
            sum(month_outstanding.values()) / 100.0),
        'payroll': payroll['total'],
        'payroll_paid': payroll['paid'],
        'payroll_pending': payroll['pending'],
        'payroll_count': payroll['count'],
        'payroll_paid_count': payroll['paid_count'],
        'payroll_partial_count': payroll['partial_count'],
        'payroll_unpaid_count': payroll['unpaid_count'],
        'costs': cash_out,
    }


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


def trend_series(end_month, count=6):
    series = []
    for month in recent_month_keys(end_month, count):
        snapshot = month_snapshot(month)
        series.append({
            'month': month,
            'label': short_label(month),
            'revenue': snapshot['revenue'],
            'payroll': snapshot['payroll'],
            'expenses': snapshot['expenses'],
            'net': snapshot['net'],
        })
    return series


# --------------------------------------------------------------------------- #
# Period comparison
#
# A "period" is either one month ('2026-09') or a whole year / academic
# session ('year:2026', 'session:2026-2027').  Comparing periods is done from
# a single window aggregation rather than one snapshot per period, so showing
# twelve months costs three grouped queries instead of thirty-six.
# --------------------------------------------------------------------------- #

def session_bounds(start_year):
    """April-to-March academic session starting in ``start_year``."""
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def current_session_start_year(today=None):
    """Academic sessions run April-March, matching the rest of the app."""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def months_in_range(start, end):
    """Every 'YYYY-MM' key touched by the inclusive date range."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append('%04d-%02d' % (year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def all_months_in_period(period):
    """Every calendar month a period spans (a month period spans exactly one)."""
    return months_in_range(period['start'], period['end'])


def period_descriptor(key):
    """Parse one period key into a descriptor, or None when it is invalid.

    Accepted forms:
      '2026-09'            -> a single month
      'year:2026'          -> the calendar year (Jan-Dec)
      'session:2026-2027'  -> the academic session (Apr 2026 - Mar 2027)
    """
    key = (key or '').strip()
    if not key:
        return None

    if key.startswith('session:'):
        raw = key.split(':', 1)[1].strip()
        try:
            start_year = int(raw.split('-')[0])
        except (ValueError, IndexError):
            return None
        if not 2000 <= start_year <= 2100:
            return None
        start, end = session_bounds(start_year)
        return {'key': key, 'kind': 'session', 'start': start, 'end': end,
                'label': 'Session %d-%d' % (start_year, start_year + 1),
                'short_label': 'Session %d-%02d' % (start_year, (start_year + 1) % 100)}

    if key.startswith('year:'):
        raw = key.split(':', 1)[1].strip()
        try:
            year = int(raw)
        except ValueError:
            return None
        if not 2000 <= year <= 2100:
            return None
        return {'key': key, 'kind': 'year', 'start': date(year, 1, 1),
                'end': date(year, 12, 31), 'label': str(year),
                'short_label': str(year)}

    if parse_month(key):
        start, end = month_bounds(key)
        return {'key': key, 'kind': 'month', 'start': start, 'end': end,
                'label': month_label(key), 'short_label': short_label(key)}

    return None


def _window_totals(start, end):
    """Per-month cash-in / salaries-paid / expenses across a window (7 queries).

    Four core buckets (fee revenue, expenses, salary payments, payroll accrual)
    plus the Phase 3 additions (other income, sales, purchases) — one grouped
    query each, so the cost stays flat as the period count grows.

    Mirrors ``dashboard_service.account_book``: aggregate in SQL grouped by
    month, then read the periods out of the result.  Cash figures use the
    explicit payment dates; the payroll accrual (payable) is kept separately.
    """
    cash_date = _cash_date_column()
    revenue_rows = (db.session.query(
            db.func.strftime('%Y-%m', cash_date),
            db.func.coalesce(db.func.sum(
                db.case((FeeTransaction.txn_type == TXN_PAYMENT,
                         FeeTransaction.amount_paisa), else_=0)), 0),
            db.func.coalesce(db.func.sum(
                db.case((FeeTransaction.txn_type == TXN_REFUND,
                         FeeTransaction.amount_paisa), else_=0)), 0))
        .filter(FeeTransaction.txn_type.in_((TXN_PAYMENT, TXN_REFUND)),
                FeeTransaction.is_void.is_(False),
                cash_date >= start.isoformat(),
                cash_date <= end.isoformat())
        .group_by(db.func.strftime('%Y-%m', cash_date)).all())
    revenue = {key: _money((paid - refunded) / 100.0)
               for key, paid, refunded in revenue_rows}

    expense_rows = (db.session.query(
            db.func.strftime('%Y-%m', Expense.date),
            db.func.coalesce(db.func.sum(Expense.amount_paisa), 0))
        .filter(Expense.is_void.is_(False),
                Expense.date >= start, Expense.date <= end)
        .group_by(db.func.strftime('%Y-%m', Expense.date)).all())
    expenses = {key: _money(value / 100.0) for key, value in expense_rows}

    salary_rows = (db.session.query(
            db.func.strftime('%Y-%m', SalaryPayment.payment_date),
            db.func.coalesce(db.func.sum(SalaryPayment.amount_paisa), 0))
        .filter(SalaryPayment.is_void.is_(False),
                SalaryPayment.payment_date >= start,
                SalaryPayment.payment_date <= end)
        .group_by(db.func.strftime('%Y-%m', SalaryPayment.payment_date)).all())
    salaries = {key: _money(value / 100.0) for key, value in salary_rows}

    payroll_rows_ = (db.session.query(
            StaffPayroll.month_year,
            db.func.coalesce(db.func.sum(StaffPayroll.net_salary_paisa), 0))
        .filter(StaffPayroll.month_year >= start.strftime('%Y-%m'),
                StaffPayroll.month_year <= end.strftime('%Y-%m'))
        .group_by(StaffPayroll.month_year).all())
    payroll = {key: {'total': _money(total / 100.0),
                     'paid': salaries.get(key, 0.0), 'count': 0}
               for key, total in payroll_rows_}

    other_rows = (db.session.query(
            db.func.strftime('%Y-%m', OtherIncome.income_date),
            db.func.coalesce(db.func.sum(OtherIncome.amount_paisa), 0))
        .filter(OtherIncome.is_void.is_(False),
                OtherIncome.income_date >= start,
                OtherIncome.income_date <= end)
        .group_by(db.func.strftime('%Y-%m', OtherIncome.income_date)).all())
    other_income = {key: _money(value / 100.0) for key, value in other_rows}

    # Inventory (Phase 3b): sales receipts + their snapshotted COGS, and the
    # purchase payments.  Purchases are stock replenishment — they are Cash
    # Out but never Expenses; their cost re-enters as COGS when items sell.
    sales_rows = (db.session.query(
            db.func.strftime('%Y-%m', Sale.sale_date),
            db.func.coalesce(db.func.sum(Sale.total_price_paisa), 0),
            db.func.coalesce(db.func.sum(Sale.total_cost_paisa), 0))
        .filter(Sale.sale_date >= start, Sale.sale_date <= end)
        .group_by(db.func.strftime('%Y-%m', Sale.sale_date)).all())
    sales_revenue = {key: _money(price / 100.0)
                     for key, price, cogs in sales_rows}
    sales_cogs = {key: _money(cogs / 100.0)
                  for key, price, cogs in sales_rows}

    purchase_rows = (db.session.query(
            db.func.strftime('%Y-%m', Purchase.purchase_date),
            db.func.coalesce(db.func.sum(Purchase.total_cost_paisa), 0))
        .filter(Purchase.purchase_date >= start,
                Purchase.purchase_date <= end)
        .group_by(db.func.strftime('%Y-%m', Purchase.purchase_date)).all())
    purchases = {key: _money(value / 100.0) for key, value in purchase_rows}

    return {'revenue': revenue, 'expenses': expenses, 'payroll': payroll,
            'other_income': other_income, 'sales_revenue': sales_revenue,
            'sales_cogs': sales_cogs, 'purchases': purchases}


def period_snapshot(period, revenue, expenses, payroll, outstanding=None,
                    other_income=None, sales=None, sales_cogs=None,
                    purchases=None):
    """Turn pre-aggregated month buckets into one period's figures.

    ``net`` is the CASH basis: Cash In (fee collections, other income and
    sales receipts) − Cash Out (expenses, which include the payroll-fed
    Salaries rows, plus inventory purchase payments).  The payroll accrual
    (payable) is reported separately as ``payroll`` / ``payroll_pending``.
    ``outstanding`` (optional per-ledger-month paisa buckets from
    :func:`month_fee_buckets`) enables ``fees_remaining_period`` — the dues
    that arose from the period's own months.

    The operating side (Revenue − Salaries − Operating Expenses − COGS) is
    reported as ``operating_position`` — never mixed into the cash figures.
    """
    months = all_months_in_period(period)
    revenue_total = _money(sum(revenue.get(m, 0.0) for m in months))
    other_income_total = _money(sum((other_income or {}).get(m, 0.0)
                                    for m in months))
    sales_total = _money(sum((sales or {}).get(m, 0.0) for m in months))
    cogs_total = _money(sum((sales_cogs or {}).get(m, 0.0) for m in months))
    purchases_total = _money(sum((purchases or {}).get(m, 0.0) for m in months))
    cash_in_total = _money(revenue_total + other_income_total + sales_total)
    expenses_sum = _money(sum(expenses.get(m, 0.0) for m in months))
    payroll_total = _money(sum(payroll.get(m, {}).get('total', 0.0) for m in months))
    payroll_paid = _money(sum(payroll.get(m, {}).get('paid', 0.0) for m in months))
    payroll_count = sum(payroll.get(m, {}).get('count', 0) for m in months)
    salaries_paid = _money(sum(payroll.get(m, {}).get('paid', 0.0)
                               for m in months))

    monthly = []
    if period['kind'] in ('year', 'session'):
        for month in months:
            month_payroll = payroll.get(month, {})
            month_revenue = revenue.get(month, 0.0)
            month_expenses = expenses.get(month, 0.0)
            monthly.append({
                'month': month,
                'label': short_label(month),
                'revenue': month_revenue,
                'payroll': month_payroll.get('total', 0.0),
                'expenses': month_expenses,
                'net': _money(month_revenue - month_expenses),
            })

    return {
        'key': period['key'],
        'label': period['label'],
        'short_label': period['short_label'],
        'kind': period['kind'],
        'start': period['start'],
        'end': period['end'],
        'months': months,
        'month_count': len(months),
        'revenue': cash_in_total,
        'fee_income': revenue_total,
        'other_income': other_income_total,
        'sales': sales_total,
        'sales_cogs': cogs_total,
        'gross_profit': _money(sales_total - cogs_total),
        'purchases': purchases_total,
        'expenses': expenses_sum,
        'payroll': payroll_total,
        'payroll_paid': payroll_paid,
        'payroll_pending': _money(payroll_total - payroll_paid),
        'payroll_count': payroll_count,
        'salaries_paid': salaries_paid,
        'other_expenses': _money(expenses_sum - salaries_paid),
        'fees_remaining_period': _money(
            sum((outstanding or {}).get(m, 0) for m in months) / 100.0),
        'cash_in': cash_in_total,
        'cash_out': _money(expenses_sum + purchases_total),
        'net': _money(cash_in_total - expenses_sum - purchases_total),
        'net_position': _money(cash_in_total - expenses_sum - purchases_total),
        # Operating view: Revenue − Salaries − Operating Expenses − COGS.
        # Stock bought but not yet sold sits here as the cash-vs-operating
        # gap; it is never folded into Net Position.
        'operating_position': _money(cash_in_total - expenses_sum - cogs_total),
        'monthly': monthly,
    }


def period_snapshots(period_keys):
    """Snapshot every requested period using one aggregation over their span."""
    periods = [p for p in (period_descriptor(key) for key in period_keys or []) if p]
    if not periods:
        return []
    start = min(p['start'] for p in periods)
    end = max(p['end'] for p in periods)
    buckets = _window_totals(start, end)
    outstanding = month_fee_buckets(start, end)['outstanding']
    return [period_snapshot(period, buckets['revenue'], buckets['expenses'],
                            buckets['payroll'],
                            outstanding=outstanding,
                            other_income=buckets['other_income'],
                            sales=buckets['sales_revenue'],
                            sales_cogs=buckets['sales_cogs'],
                            purchases=buckets['purchases'])
            for period in periods]


#: Metrics shown in the comparison grid: (key, label, help text).
COMPARISON_METRICS = (
    ('revenue', 'Cash In — Fee Collections', 'Fee payments received in the period (cash)'),
    ('payroll', 'Salaries Paid (Cash)', 'Salary payments made in the period (cash)'),
    ('expenses', 'Cash Out — All Expenses', 'All expenses paid, salaries included (cash)'),
    ('payroll_accrual', 'Salary Payable (Accrual)', 'Net salaries recorded for the period'),
    ('net', 'Net Position', 'Cash In minus Cash Out'),
)


def comparison_rows(snapshots):
    """Metric rows for the comparison grid.

    Each row carries one value per period plus, when exactly two periods are
    selected, how much the second differs from the first.
    """
    show_difference = len(snapshots) == 2
    rows = []
    for key, label, help_text in COMPARISON_METRICS:
        values = [snapshot.get('payroll' if key == 'payroll_accrual' else key, 0.0)
                  for snapshot in snapshots]
        row = {'key': key, 'label': label, 'help': help_text, 'amounts': values}
        if show_difference:
            before, after = values[0], values[1]
            change = _money(after - before)
            if before:
                percent = round((change / abs(before)) * 100, 1)
            else:
                percent = None if not after else 100.0
            row['difference'] = change
            row['difference_percent'] = percent
            row['direction'] = 'up' if change > 0 else ('down' if change < 0 else 'flat')
            # For costs a rise is worse; the template decides the colour.
            row['higher_is_better'] = key in ('revenue', 'net')
        rows.append(row)
        if key == 'revenue' and _inventory_enabled():
            # Phase 3b: sales receipts sit inside Cash In — show them apart.
            values = [snapshot.get('sales', 0.0) for snapshot in snapshots]
            row = {'key': 'sales', 'label': 'of which Sales (inventory)',
                   'help': 'Uniform/book/stationery sales receipts, included in Cash In',
                   'amounts': values}
            if show_difference:
                before, after = values[0], values[1]
                change = _money(after - before)
                row['difference'] = change
                row['difference_percent'] = (
                    round((change / abs(before)) * 100, 1) if before
                    else (None if not after else 100.0))
                row['direction'] = ('up' if change > 0
                                    else ('down' if change < 0 else 'flat'))
                row['higher_is_better'] = True
            rows.append(row)

    highlight = []
    if show_difference:
        first, second = snapshots
        highlight = [
            {'label': 'Net position', 'first': first['net'], 'second': second['net'],
             'change': _money(second['net'] - first['net']),
             'improved': second['net'] >= first['net']},
        ]
    return {'rows': rows, 'show_difference': show_difference,
            'highlight': highlight}


def comparison_totals(snapshots):
    """Column totals across all selected periods (the TOTAL column)."""
    return {
        'label': 'Total',
        'revenue': _money(sum(s['revenue'] for s in snapshots)),
        'payroll': _money(sum(s['payroll'] for s in snapshots)),
        'expenses': _money(sum(s['expenses'] for s in snapshots)),
        'sales': _money(sum(s.get('sales', 0.0) for s in snapshots)),
        'cash_out': _money(sum(s['cash_out'] for s in snapshots)),
        'net': _money(sum(s['net'] for s in snapshots)),
    }


def comparison_csv(snapshots, rows, totals=None):
    """CSV with one column per period (plus a difference column for two)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Financial Summary — Period Comparison'])
    writer.writerow(['Period'] + [s['label'] for s in snapshots] +
                    (['Difference'] if len(snapshots) == 2 else []) +
                    (['Total'] if totals else []))
    writer.writerow(['Period length (months)'] +
                    [s['month_count'] for s in snapshots] +
                    ([''] if len(snapshots) == 2 else []) +
                    ([''] if totals else []))
    writer.writerow([])
    for row in rows:
        line = [row['label']] + ['%.2f' % v for v in row['amounts']]
        if len(snapshots) == 2:
            line.append('%.2f' % row['difference'])
        if totals:
            line.append('%.2f' % totals.get(row['key'], 0.0))
        writer.writerow(line)
    writer.writerow([])
    writer.writerow(['Monthly detail'])
    writer.writerow(['Period', 'Month', 'Fee Collections', 'Staff Payroll',
                     'Operational Expenses', 'Net'])
    for snapshot in snapshots:
        if snapshot['monthly']:
            for month in snapshot['monthly']:
                writer.writerow([snapshot['label'], month['label'],
                                 '%.2f' % month['revenue'],
                                 '%.2f' % month['payroll'],
                                 '%.2f' % month['expenses'],
                                 '%.2f' % month['net']])
        else:
            writer.writerow([snapshot['label'], snapshot['label'],
                             '%.2f' % snapshot['revenue'],
                             '%.2f' % snapshot['payroll'],
                             '%.2f' % snapshot['expenses'],
                             '%.2f' % snapshot['net']])
    return buffer.getvalue()


def comparison_pdf(snapshots, rows, totals=None, root_path=None):
    """Branded landscape PDF of the period comparison."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CTitle', parent=styles['Heading1'], fontSize=15,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('CSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=6)

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('FINANCIAL COMPARISON — %s'
                  % escape(', '.join(s['label'] for s in snapshots)).upper(), sub_style),
    ]
    story.append(Spacer(1, 8))

    show_difference = len(snapshots) == 2
    header = ['Metric'] + [s['label'] for s in snapshots]
    if show_difference:
        header.append('Difference')
    if totals:
        header.append('Total')
    data = [header]
    for row in rows:
        line = [row['label']] + ['{:,.0f}'.format(v) for v in row['amounts']]
        if show_difference:
            line.append('{:,.0f}'.format(row['difference']))
        if totals:
            line.append('{:,.0f}'.format(totals.get(row['key'], 0.0)))
        data.append(line)

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#f8fafc')]),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Net Position (cash basis) = Cash In (fee collections) - Cash Out (expenses, salaries included).',
        styles['Normal']))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=28,
                            leftMargin=28, topMargin=26, bottomMargin=26)
    doc.build(story)
    output.seek(0)
    return output


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

def report_csv(snapshot, breakdown, payroll_list):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Financial Summary', snapshot['label']])
    writer.writerow(['Fee Collections (Revenue)', '%.2f' % snapshot['revenue']])
    writer.writerow(['Staff Payroll (Net)', '%.2f' % snapshot['payroll']])
    writer.writerow(['Operational Expenses', '%.2f' % snapshot['expenses']])
    writer.writerow(['Net Surplus / (Deficit)', '%.2f' % snapshot['net']])
    writer.writerow([])
    writer.writerow(['Expense Breakdown'])
    writer.writerow(['Category', 'Entries', 'Total (Rs)'])
    for row in breakdown:
        writer.writerow([row['name'], row['count'], '%.2f' % row['total']])
    writer.writerow([])
    writer.writerow(['Payroll'])
    writer.writerow(['Teacher', 'Net Salary (Rs)', 'Status', 'Payment Date'])
    for record in payroll_list:
        teacher_name = record.teacher.teacher_name if record.teacher else ''
        writer.writerow([
            teacher_name,
            '%.2f' % (record.net_salary or 0),
            record.payment_status or '',
            record.payment_date.isoformat() if record.payment_date else '',
        ])
    return buffer.getvalue()


def report_pdf(snapshot, breakdown, payroll_list, root_path=None):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('FTitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('FSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=6)
    section_style = ParagraphStyle('FSection', parent=styles['Normal'], fontSize=11,
                                   fontName='Helvetica-Bold',
                                   textColor=colors.HexColor('#0f172a'),
                                   spaceBefore=10, spaceAfter=4)

    def money(value):
        return '{:,.2f}'.format(value or 0)

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('MONTHLY FINANCIAL SUMMARY — %s'
                  % escape(snapshot['label']).upper(), sub_style),
    ]
    tail = ' | '.join([p for p in (school.get('address') or '',
                                   school.get('phone') or '') if p])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))
    story.append(Spacer(1, 8))

    summary_rows = [
        ['Fee Collections (Revenue)', money(snapshot['revenue'])],
        ['Staff Payroll (Net)', money(snapshot['payroll'])],
        ['  — Paid', money(snapshot['payroll_paid'])],
        ['  — Pending', money(snapshot['payroll_pending'])],
        ['Operational Expenses', money(snapshot['expenses'])],
        ['Net Surplus / (Deficit)', money(snapshot['net'])],
    ]
    summary_table = Table(summary_rows, colWidths=[360, 192])
    summary_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(summary_table)

    story.append(Paragraph('Expense Breakdown', section_style))
    breakdown_rows = [['Category', 'Entries', 'Total (Rs.)']]
    for row in breakdown:
        breakdown_rows.append([row['name'], str(row['count']), money(row['total'])])
    if len(breakdown_rows) == 1:
        breakdown_rows.append(['No expenses recorded', '', ''])
    breakdown_table = Table(breakdown_rows, colWidths=[280, 80, 192])
    breakdown_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(breakdown_table)

    story.append(Paragraph('Payroll', section_style))
    payroll_table_rows = [['Teacher', 'Net Salary (Rs.)', 'Status', 'Payment Date']]
    for record in payroll_list:
        teacher_name = record.teacher.teacher_name if record.teacher else '—'
        payroll_table_rows.append([
            teacher_name,
            money(record.net_salary),
            record.payment_status or '',
            record.payment_date.strftime('%d %b %Y') if record.payment_date else '—',
        ])
    if len(payroll_table_rows) == 1:
        payroll_table_rows.append(['No payroll records for this month', '', '', ''])
    payroll_table = Table(payroll_table_rows, colWidths=[200, 112, 90, 150])
    payroll_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(payroll_table)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        'Net Position (cash basis) = Cash In (fee collections) − Cash Out (expenses, salaries included).',
        styles['Normal']))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output


# --------------------------------------------------------------------------- #
# Phase 2b: comparisons, alerts, insights, revenue impact
# --------------------------------------------------------------------------- #

def month_fee_buckets(start, end):
    """Per-ledger-month charged and outstanding paisa for a date range.

    Charged = active charges + adjustments; outstanding = charged minus every
    settling allocation (payments and write-offs) against that month's
    charges.  The shared engine's fees-remaining source.
    """
    from app.models import FeePaymentAllocation
    keys = months_in_range(start, end)
    if not keys:
        return {'charged': {}, 'outstanding': {}}
    labels = [month_label(key) for key in keys]
    charged_by_label = dict(db.session.query(
        FeeTransaction.month_year,
        db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
        .filter(FeeTransaction.is_void.is_(False),
                FeeTransaction.txn_type.in_(('charge', 'adjustment')),
                FeeTransaction.month_year.in_(labels))
        .group_by(FeeTransaction.month_year).all())
    settled_by_label = dict(db.session.query(
        FeeTransaction.month_year,
        db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
        .join(FeePaymentAllocation,
              FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
        .filter(FeeTransaction.is_void.is_(False),
                FeeTransaction.month_year.in_(labels),
                FeePaymentAllocation.is_void.is_(False))
        .group_by(FeeTransaction.month_year).all())
    # Ledger rows use month labels ('October 2026'); map each label back to
    # the engine's 'YYYY-MM' key so the buckets line up with the period months.
    key_by_label = {month_label(k): k for k in keys}
    charged_by_key = {key_by_label.get(m, ''): int(v or 0)
                      for m, v in charged_by_label.items()}
    settled_by_key = {key_by_label.get(m, ''): int(v or 0)
                      for m, v in settled_by_label.items()}
    charged = {k: charged_by_key.get(k, 0) for k in keys}
    outstanding = {k: max(0, charged[k] - settled_by_key.get(k, 0))
                   for k in keys}
    return {'charged': charged, 'outstanding': outstanding}


def _billed_students_count(start, end):
    """Distinct students billed (charged/adjusted) inside the date range."""
    labels = [month_label(key) for key in months_in_range(start, end)]
    if not labels:
        return 0
    return (db.session.query(
                db.func.count(db.func.distinct(FeeTransaction.student_id)))
            .filter(FeeTransaction.is_void.is_(False),
                    FeeTransaction.txn_type.in_(('charge', 'adjustment')),
                    FeeTransaction.month_year.in_(labels)).scalar()) or 0


def _formers_left_count(start, end):
    """Students whose leaving date falls inside the date range."""
    from app.models import StudentModel
    return (StudentModel.query
            .filter(StudentModel.is_active.is_(False),
                    StudentModel.leaving_date >= start,
                    StudentModel.leaving_date <= end).count())


def _period_fee_collection(period):
    """(own-month collections, arrears recovered) summed over a period."""
    collected = arrears = 0.0
    for key in all_months_in_period(period):
        split = collection_split(key)
        collected += split['current']
        arrears += split['arrears']
    return _money(collected), _money(arrears)


def _comparison_metric_rows(current, previous, no_earlier_data):
    """Metric rows for one comparison, with plain-language changes."""
    money_metrics = [
        ('Cash In', 'cash_in'),
        ('Fee Collection', 'fee_collection'),
    ]
    if _inventory_enabled():
        # Sales receipts are inside Cash In; show them apart (Phase 3b).
        money_metrics.append(('of which Sales (inventory)', 'sales'))
    money_metrics += [
        ('Cash Out', 'cash_out'),
        ('Salaries Paid', 'salaries_paid'),
        ('Other Expenses', 'other_expenses'),
        ('Net Position', 'net'),
        ('Fees Remaining at period end', 'fees_remaining_period'),
    ]
    count_metrics = (
        ('Students billed', 'students_billed'),
        ('Former students (left in period)', 'formers_left'),
    )
    rows = []
    for name, key in money_metrics:
        cur = _money(current.get(key) or 0.0)
        prev = _money(previous.get(key) or 0.0)
        change = _money(cur - prev)
        pct = None
        if no_earlier_data:
            change_text = 'No earlier data'
        elif prev == 0:
            change_text = 'new this period' if cur > 0 else 'unchanged'
        else:
            pct = round(change * 100.0 / prev, 1)
            word = 'higher' if change > 0 else 'lower'
            change_text = 'Rs %s %s (%s%%)' % (
                '{:,.2f}'.format(abs(change)), word, '{:,.1f}'.format(abs(pct)))
        rows.append({'name': name, 'kind': 'money', 'current': cur,
                     'previous': prev, 'change': change, 'pct': pct,
                     'change_text': change_text, 'no_earlier_data': no_earlier_data})
    for name, key in count_metrics:
        cur = int(current.get(key) or 0)
        prev = int(previous.get(key) or 0)
        change = cur - prev
        if no_earlier_data:
            change_text = 'No earlier data'
        elif change == 0:
            change_text = 'unchanged'
        else:
            change_text = '%d more' % change if change > 0 else '%d fewer' % (-change)
        rows.append({'name': name, 'kind': 'count', 'current': cur,
                     'previous': prev, 'change': change, 'pct': None,
                     'change_text': change_text, 'no_earlier_data': no_earlier_data})
    return rows


def build_comparison(title, current_desc, previous_desc):
    """One comparison: two periods through the shared engine + metric rows."""
    start = min(current_desc['start'], previous_desc['start'])
    end = max(current_desc['end'], previous_desc['end'])
    window = _window_totals(start, end)
    buckets = month_fee_buckets(start, end)
    current = period_snapshot(current_desc, window['revenue'], window['expenses'],
                              window['payroll'],
                              outstanding=buckets['outstanding'],
                              other_income=window['other_income'],
                              sales=window['sales_revenue'],
                              sales_cogs=window['sales_cogs'],
                              purchases=window['purchases'])
    previous = period_snapshot(previous_desc, window['revenue'], window['expenses'],
                               window['payroll'],
                               outstanding=buckets['outstanding'],
                               other_income=window['other_income'],
                               sales=window['sales_revenue'],
                               sales_cogs=window['sales_cogs'],
                               purchases=window['purchases'])
    for snap, desc in ((current, current_desc), (previous, previous_desc)):
        collected, arrears = _period_fee_collection(desc)
        snap['fee_collection'] = collected
        snap['arrears_recovered_period'] = arrears
        snap['students_billed'] = _billed_students_count(desc['start'], desc['end'])
        snap['formers_left'] = _formers_left_count(desc['start'], desc['end'])
    no_earlier_data = (
        previous['cash_in'] == 0 and previous['cash_out'] == 0
        and previous['payroll'] == 0
        and all(buckets['charged'].get(m, 0) == 0
                for m in all_months_in_period(previous_desc)))
    return {'title': title,
            'current': current, 'previous': previous,
            'rows': _comparison_metric_rows(current, previous, no_earlier_data),
            'no_earlier_data': no_earlier_data}


def summary_comparisons(month_year, range_start=None, range_end=None):
    """The three Phase 2b comparisons for the summary page."""
    packs = []
    prev_month = shift_month(month_year, -1)
    packs.append(build_comparison(
        'This month vs previous month',
        period_descriptor(month_year), period_descriptor(prev_month)))

    session_year = current_session_start_year(
        date(int(month_year[:4]), int(month_year[5:]), 1))
    packs.append(build_comparison(
        'This session vs previous session',
        period_descriptor('session:%d' % session_year),
        period_descriptor('session:%d' % (session_year - 1))))

    custom = None
    try:
        start = date.fromisoformat(range_start) if range_start else None
        end = date.fromisoformat(range_end) if range_end else None
    except (TypeError, ValueError):
        start = end = None
    if start and end and start <= end:
        length = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        current_desc = {'key': 'custom:current', 'kind': 'custom',
                        'start': start, 'end': end,
                        'label': '%s to %s' % (start.strftime('%d %b %Y'),
                                               end.strftime('%d %b %Y')),
                        'short_label': start.strftime('%d %b')}
        previous_desc = {'key': 'custom:previous', 'kind': 'custom',
                         'start': prev_start, 'end': prev_end,
                         'label': '%s to %s' % (prev_start.strftime('%d %b %Y'),
                                                prev_end.strftime('%d %b %Y')),
                         'short_label': prev_start.strftime('%d %b')}
        custom = build_comparison('Custom range vs preceding period',
                                  current_desc, previous_desc)
    return packs, custom


def summary_alerts(month_year):
    """Rule-based, plain-wording alerts for the summary page."""
    from flask import current_app

    drop_pct_threshold = current_app.config.get('ALERT_COLLECTION_DROP_PCT', 10)
    rise_pct_threshold = current_app.config.get('ALERT_EXPENSE_RISE_PCT', 20)
    min_change = current_app.config.get('ALERT_MIN_CHANGE_RUPEES', 1000)

    alerts = []
    snap = month_snapshot(month_year)
    buckets = month_fee_buckets(snap['start'], snap['end'])
    month_outstanding = _money(sum(buckets['outstanding'].values()) / 100.0)
    prev_key = shift_month(month_year, -1)
    prev_snap = month_snapshot(prev_key)
    prev_has_data = (prev_snap['cash_in'] or prev_snap['cash_out']
                     or prev_snap['payroll']
                     or any(buckets['charged'].get(m, 0)
                            for m in all_months_in_period(prev_snap)))

    if month_outstanding > 0:
        alerts.append({
            'kind': 'warning',
            'text': 'Rs %s of this month\'s fees is still remaining.'
                    % '{:,.2f}'.format(month_outstanding),
            'url': '/financials/student-outstanding?month=%s' % month_year,
            'link_text': 'See who owes'})
    total_outstanding = _total_outstanding()
    older_arrears = _money(max(0.0, total_outstanding - month_outstanding))
    if older_arrears > 0:
        alerts.append({
            'kind': 'warning',
            'text': 'Rs %s of older arrears is still recoverable.'
                    % '{:,.2f}'.format(older_arrears),
            'url': '/financials/student-outstanding',
            'link_text': 'See the dues list'})

    former = former_students_summary()
    if former['count'] > 0:
        alerts.append({
            'kind': 'warning',
            'text': '%d former student(s) owe Rs %s.'
                    % (former['count'], '{:,.2f}'.format(former['total'])),
            'url': '/financials/student-outstanding?status=former',
            'link_text': 'View their dues'})

    salary_unpaid = salary_remaining_total()
    if salary_unpaid > 0:
        alerts.append({
            'kind': 'warning',
            'text': 'Rs %s of salary is still unpaid.'
                    % '{:,.2f}'.format(salary_unpaid),
            'url': '/payroll',
            'link_text': 'Open payroll'})

    split = collection_split(month_year)
    if split['arrears'] > 0:
        alerts.append({
            'kind': 'info',
            'text': 'Rs %s of older arrears was recovered this month.'
                    % '{:,.2f}'.format(split['arrears']),
            'url': '/fees',
            'link_text': 'Open fees'})

    current_collection = split['current']
    previous_collection = collection_split(prev_key)['current']
    if prev_has_data and previous_collection > 0:
        drop = previous_collection - current_collection
        drop_pct = round(drop * 100.0 / previous_collection, 1)
        if drop > 0 and drop_pct >= drop_pct_threshold and drop >= min_change:
            alerts.append({
                'kind': 'warning',
                'text': 'Fee collection is %s%% lower than last month.'
                        % '{:,.1f}'.format(drop_pct),
                'url': '/fees',
                'link_text': 'Open fees'})

    current_categories = {row['name']: row['total']
                          for row in expense_breakdown(snap['start'], snap['end'])}
    previous_categories = {row['name']: row['total']
                           for row in expense_breakdown(prev_snap['start'],
                                                        prev_snap['end'])}
    for name, total in current_categories.items():
        previous_total = previous_categories.get(name, 0.0)
        rise = total - previous_total
        if previous_total > 0 and rise > 0:
            rise_pct = round(rise * 100.0 / previous_total, 1)
            if rise_pct >= rise_pct_threshold and rise >= min_change:
                alerts.append({
                    'kind': 'warning',
                    'text': '%s expenses are up %s%% vs last month (+Rs %s).'
                            % (name, '{:,.1f}'.format(rise_pct),
                               '{:,.2f}'.format(rise)),
                    'url': '/expenses',
                    'link_text': 'Open expenses'})

    if _inventory_enabled():
        from app.services import inventory_service
        low = inventory_service.low_stock_list()
        if low:
            names = ', '.join('%s (%d left)' % (p.name, p.stock_qty)
                              for p in low[:3])
            more = ' and %d more' % (len(low) - 3) if len(low) > 3 else ''
            alerts.append({
                'kind': 'warning',
                'text': 'Low stock: %s%s.' % (names, more),
                'url': '/inventory',
                'link_text': 'Open inventory'})
    return alerts


def summary_insights(month_year):
    """A short 'What changed' text built only from real numbers."""
    snap = month_snapshot(month_year)
    buckets = month_fee_buckets(snap['start'], snap['end'])
    prev_key = shift_month(month_year, -1)
    prev_snap = month_snapshot(prev_key)
    prev_has_data = (prev_snap['cash_in'] or prev_snap['cash_out']
                     or prev_snap['payroll']
                     or any(buckets['charged'].get(m, 0)
                            for m in all_months_in_period(prev_snap)))
    if not prev_has_data:
        return {'enough_history': False, 'lines': ['Not enough history yet.']}

    lines = []
    current_collection, _ = _period_fee_collection(
        period_descriptor(month_year))
    previous_collection, _ = _period_fee_collection(
        period_descriptor(prev_key))
    if previous_collection > 0:
        change_pct = round((current_collection - previous_collection) * 100.0
                           / previous_collection, 1)
        if change_pct >= 0:
            lines.append('Fee collection is %s%% higher than last month.'
                         % '{:,.1f}'.format(change_pct))
        else:
            lines.append('Fee collection is %s%% lower than last month.'
                         % '{:,.1f}'.format(-change_pct))
    net_change = _money(snap['net'] - prev_snap['net'])
    if net_change >= 0:
        lines.append('Net Position improved by Rs %s (cash basis).'
                     % '{:,.2f}'.format(net_change))
    else:
        lines.append('Net Position fell by Rs %s (cash basis).'
                     % '{:,.2f}'.format(-net_change))

    current_categories = {row['name']: row['total']
                          for row in expense_breakdown(snap['start'], snap['end'])}
    previous_categories = {row['name']: row['total']
                           for row in expense_breakdown(prev_snap['start'],
                                                        prev_snap['end'])}
    biggest = None
    for name, total in current_categories.items():
        previous_total = previous_categories.get(name, 0.0)
        if previous_total > 0:
            rise_pct = round((total - previous_total) * 100.0 / previous_total, 1)
            if rise_pct > 0 and (biggest is None or rise_pct > biggest[1]):
                biggest = (name, rise_pct)
    if biggest:
        lines.append('%s is up %s%% vs last month.' % (biggest[0],
                                                       '{:,.1f}'.format(biggest[1])))
    total_outstanding = _total_outstanding()
    if total_outstanding > 0:
        lines.append('About Rs %s in fees is still outstanding (estimated).'
                     % '{:,.2f}'.format(total_outstanding))
    salary_unpaid = salary_remaining_total()
    if salary_unpaid > 0:
        lines.append('Rs %s of salary is still unpaid (estimated).'
                     % '{:,.2f}'.format(salary_unpaid))
    return {'enough_history': True, 'lines': lines}


def former_revenue_impact():
    """Estimated monthly revenue impact of students who left (estimate only).

    Sums the monthly fee of former students, SLC Issued and Struck Off shown
    separately.  Graduated students are expected to leave, so they are not
    part of the impact.
    """
    from app.models import STUDENT_STATUS_LABELS, StudentModel
    impact = {}
    for status in ('slc_issued', 'struck_off'):
        students = (StudentModel.query
                    .filter_by(is_active=False, status=status).all())
        entry = {'label': STUDENT_STATUS_LABELS.get(status, status),
                 'count': 0, 'monthly': 0.0}
        for student in students:
            if (student.monthly_fee or 0) > 0:
                entry['count'] += 1
                entry['monthly'] = _money(entry['monthly'] + student.monthly_fee)
        impact[status] = entry
    return impact

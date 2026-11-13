"""Snapshots: one month or one period with cash in, cash out and net, and the trend series."""

from app.database import db
from app.models import (Expense, FeeTransaction, OtherIncome, Sale, SalaryPayment, StaffPayroll,
                        TXN_PAYMENT, TXN_REFUND)
from app.services.payroll_service import month_bounds, month_label, recent_month_keys

from .common import _cash_date_column, _money, short_label
from .costs import expenses_total, payroll_snapshot, salaries_paid_total
from .fees import (_total_outstanding, collection_split, fee_collections, month_fee_buckets)
from .periods import all_months_in_period, period_descriptor


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
    stock = inventory_service.month_sales_breakdown(start, end)
    sales_revenue, sales_cogs = stock['sales'], stock['cogs']
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
        # Stock given inside admission packages is paid for by the admission
        # fee: its cost is shown on its own and is NOT a loss on items sold.
        'package_cogs': stock['package_cogs'],
        'direct_cogs': stock['direct_cogs'],
        'gross_profit': _money(sales_revenue - stock['direct_cogs']),
        'purchases': purchases,
        'supplier_dues': _money(inventory_service.total_supplier_dues_paisa() / 100.0),
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
            db.func.coalesce(db.func.sum(Sale.total_cost_paisa), 0),
            db.func.coalesce(db.func.sum(db.case(
                (Sale.source == 'admission', Sale.total_cost_paisa), else_=0)), 0))
        .filter(Sale.sale_date >= start, Sale.sale_date <= end,
                Sale.is_void.is_(False))
        .group_by(db.func.strftime('%Y-%m', Sale.sale_date)).all())
    sales_revenue = {key: _money(price / 100.0)
                     for key, price, cogs, package in sales_rows}
    sales_cogs = {key: _money(cogs / 100.0)
                  for key, price, cogs, package in sales_rows}
    package_cogs = {key: _money(package / 100.0)
                    for key, price, cogs, package in sales_rows}

    # Cash out to suppliers = paid on the purchase day + later instalments.
    # The unpaid part stays a supplier due (see inventory_service.supplier_dues).
    from app.services import inventory_service
    purchases = inventory_service.purchase_payment_buckets(start, end)

    return {'revenue': revenue, 'expenses': expenses, 'payroll': payroll,
            'other_income': other_income, 'sales_revenue': sales_revenue,
            'sales_cogs': sales_cogs, 'package_cogs': package_cogs,
            'purchases': purchases}


def period_snapshot(period, revenue, expenses, payroll, outstanding=None,
                    other_income=None, sales=None, sales_cogs=None,
                    purchases=None, package_cogs=None):
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
    package_total = _money(sum((package_cogs or {}).get(m, 0.0) for m in months))
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
        'package_cogs': package_total,
        'gross_profit': _money(sales_total - (cogs_total - package_total)),
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
                            purchases=buckets['purchases'],
                            package_cogs=buckets['package_cogs'])
            for period in periods]

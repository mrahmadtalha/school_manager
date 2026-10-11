"""Financial baseline snapshot (raw SQL, schema-adaptive).

Works against BOTH the pre-migration schema (float rupee columns) and the
post-migration schema (integer paisa columns), so the same script produces the
before/after comparison for the financial v2 migration.

Usage:
    python scripts/financial_baseline.py <db_path> [--json out.json]

Printed/JSON numbers:
  Old logic (as the summary computed them before Phase 1):
    per-month + total: fee collections by created_at UTC month, operational
    expenses by date, payroll payable/paid by salary month+status, net.
  Ledger facts (schema-independent):
    charged / paid / outstanding across the whole ledger, payment count,
    former-student outstanding, per-student balance total.
  New logic (only when the migrated schema is present):
    cash-in by payment_date, cash-out, net position, allocation coverage
    (allocated vs unallocated credit), salary payments total.
"""

import json
import sqlite3
import sys
from collections import defaultdict

MONTHS_ORDER = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5,
                'June': 6, 'July': 7, 'August': 8, 'September': 9, 'October': 10,
                'November': 11, 'December': 12}


def month_key(label):
    """'September 2026' -> '2026-09' (unparseable -> '????-??')."""
    try:
        month_name, year = label.split()
        return '%s-%02d' % (year, MONTHS_ORDER[month_name])
    except (ValueError, KeyError, AttributeError):
        return '????-??'


def columns(conn, table):
    return [row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()]


def money_expr(conn, table, column):
    """SQL expression returning rupees (float) whichever schema is present."""
    cols = columns(conn, table)
    if f'{column}_paisa' in cols:
        return f'COALESCE({column}_paisa, 0) / 100.0'
    return f'COALESCE({column}, 0)'


def scalar(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def snapshot(db_path):
    conn = sqlite3.connect(str(db_path))
    out = {'db': str(db_path)}

    amt = money_expr(conn, 'fee_transactions', 'amount')
    due = money_expr(conn, 'fee_records', 'amount_due')
    paid = money_expr(conn, 'fee_records', 'amount_paid')
    exp = money_expr(conn, 'expenses', 'amount')
    net_sal = money_expr(conn, 'staff_payroll', 'net_salary')
    has_payment_date = 'payment_date' in columns(conn, 'fee_transactions')
    out['schema'] = 'v2 (paisa + payment_date)' if has_payment_date else 'v1 (float, created_at only)'

    # ---- ledger facts (schema-independent) --------------------------------
    out['charged_total'] = round(scalar(conn, f"""
        SELECT COALESCE(SUM({amt}), 0) FROM fee_transactions
        WHERE is_void = 0 AND txn_type IN ('charge', 'adjustment')"""), 2)
    out['payments_total'] = round(scalar(conn, f"""
        SELECT COALESCE(SUM({amt}), 0) FROM fee_transactions
        WHERE is_void = 0 AND txn_type = 'payment'"""), 2)
    out['payments_count'] = scalar(conn, """
        SELECT COUNT(*) FROM fee_transactions
        WHERE is_void = 0 AND txn_type = 'payment'""")
    out['refunds_total'] = round(scalar(conn, f"""
        SELECT COALESCE(SUM({amt}), 0) FROM fee_transactions
        WHERE is_void = 0 AND txn_type = 'refund'"""), 2)
    out['writeoffs_total'] = round(scalar(conn, f"""
        SELECT COALESCE(SUM({amt}), 0) FROM fee_transactions
        WHERE is_void = 0 AND txn_type = 'writeoff'"""), 2)
    out['outstanding_total'] = round(out['charged_total'] - out['payments_total']
                                     + out['refunds_total'] - out['writeoffs_total'], 2)
    out['voided_rows'] = scalar(conn, 'SELECT COUNT(*) FROM fee_transactions WHERE is_void = 1')

    # ---- old-logic monthly windows ----------------------------------------
    months = defaultdict(lambda: {'collections': 0.0, 'expenses': 0.0,
                                  'payroll_total': 0.0, 'payroll_paid': 0.0})
    for month_label_value, total in conn.execute(f"""
            SELECT strftime('%Y-%m', created_at), COALESCE(SUM({amt}), 0)
            FROM fee_transactions
            WHERE is_void = 0 AND txn_type = 'payment'
            GROUP BY 1"""):
        months[month_label_value]['collections'] = round(total, 2)
    for day, total in conn.execute(f"""
            SELECT strftime('%Y-%m', date), COALESCE(SUM({exp}), 0)
            FROM expenses GROUP BY 1"""):
        months[day]['expenses'] = round(total, 2)
    for month, total, paid_total in conn.execute(f"""
            SELECT month_year, COALESCE(SUM({net_sal}), 0),
                   COALESCE(SUM(CASE WHEN payment_status = 'Paid' THEN {net_sal} ELSE 0 END), 0)
            FROM staff_payroll GROUP BY month_year"""):
        months[month]['payroll_total'] = round(total, 2)
        months[month]['payroll_paid'] = round(paid_total, 2)

    report_months = {}
    for key in sorted(months):
        m = months[key]
        m['net_old'] = round(m['collections'] - m['expenses'] - m['payroll_total'], 2)
        report_months[key] = m
    out['months'] = report_months
    out['totals_old'] = {
        'collections': round(sum(m['collections'] for m in months.values()), 2),
        'expenses': round(sum(m['expenses'] for m in months.values()), 2),
        'payroll_total': round(sum(m['payroll_total'] for m in months.values()), 2),
        'payroll_paid': round(sum(m['payroll_paid'] for m in months.values()), 2),
        'net_old': round(sum(m['net_old'] for m in months.values()), 2),
    }

    # ---- payroll facts -----------------------------------------------------
    out['payroll_rows'] = scalar(conn, 'SELECT COUNT(*) FROM staff_payroll')
    out['payroll_paid_rows'] = scalar(conn, """
        SELECT COUNT(*) FROM staff_payroll WHERE payment_status = 'Paid'""")

    # ---- former students with dues ----------------------------------------
    out['former_students_with_dues'] = scalar(conn, """
        SELECT COUNT(DISTINCT s.id) FROM students s
        JOIN fee_transactions t ON t.student_id = s.id AND t.is_void = 0
        WHERE s.is_active = 0""")
    out['former_student_balance'] = round(scalar(conn, f"""
        SELECT COALESCE(SUM(bal), 0) FROM (
            SELECT s.id, SUM(CASE WHEN t.txn_type = 'payment' THEN -{amt} ELSE {amt} END) AS bal
            FROM students s JOIN fee_transactions t ON t.student_id = s.id
            WHERE s.is_active = 0 AND t.is_void = 0
            GROUP BY s.id HAVING bal > 0)"""), 2)

    # ---- new-logic facts (present only after migration) --------------------
    if has_payment_date:
        out['cash_in_by_payment_date'] = round(scalar(conn, f"""
            SELECT COALESCE(SUM({amt}), 0) FROM fee_transactions
            WHERE is_void = 0 AND txn_type = 'payment'
              AND payment_date IS NOT NULL"""), 2)
        out['payments_missing_date'] = scalar(conn, """
            SELECT COUNT(*) FROM fee_transactions
            WHERE txn_type = 'payment' AND is_void = 0 AND payment_date IS NULL""")
        if 'fee_payment_allocations' in [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
            out['allocations_total'] = round(scalar(conn, """
                SELECT COALESCE(SUM(a.amount_paisa), 0) / 100.0
                FROM fee_payment_allocations a WHERE a.is_void = 0"""), 2)
            out['allocations_count'] = scalar(conn,
                                              'SELECT COUNT(*) FROM fee_payment_allocations WHERE is_void = 0')
            out['unallocated_credit'] = round(out['payments_total'] - out['allocations_total'], 2)
        if 'salary_payments' in [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
            out['salary_payments_total'] = round(scalar(conn, """
                SELECT COALESCE(SUM(amount_paisa), 0) / 100.0
                FROM salary_payments WHERE is_void = 0"""), 2)
            out['salary_payments_count'] = scalar(conn,
                                                  'SELECT COUNT(*) FROM salary_payments WHERE is_void = 0')
        out['cash_out_total'] = out['totals_old']['expenses']
        out['net_position'] = round(out['cash_in_by_payment_date'] - out['cash_out_total'], 2)
    conn.close()
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    db_path = sys.argv[1]
    report = snapshot(db_path)

    json_path = None
    if '--json' in sys.argv:
        json_path = sys.argv[sys.argv.index('--json') + 1]
        with open(json_path, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)

    print('=== Financial baseline: %s' % db_path)
    print('schema: %s' % report['schema'])
    for key in ('charged_total', 'payments_total', 'payments_count', 'refunds_total',
                'writeoffs_total', 'outstanding_total', 'voided_rows',
                'payroll_rows', 'payroll_paid_rows',
                'former_students_with_dues', 'former_student_balance'):
        if key in report:
            print('%-28s %s' % (key, report[key]))
    print('-- old-logic totals --')
    for key, value in report['totals_old'].items():
        print('%-28s %s' % (key, value))
    for key in ('cash_in_by_payment_date', 'payments_missing_date', 'allocations_total',
                'allocations_count', 'unallocated_credit', 'salary_payments_total',
                'salary_payments_count', 'net_position'):
        if key in report:
            print('%-28s %s' % (key, report[key]))
    if json_path:
        print('JSON written to %s' % json_path)


if __name__ == '__main__':
    main()

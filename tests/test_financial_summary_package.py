"""``app/services/financial_summary`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
financial code ships obfuscated.  These tests pin what must not break: every file
stays small, and every name the routes, dashboard, assistant and tests used before
(private helpers and the month helpers from payroll included) is still available
from ``app.services.financial_summary``.
"""

import sys
from pathlib import Path

from app.services import financial_summary

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'financial_summary'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

NAMES = (
    'short_label', '_money', '_inventory_enabled', '_cash_date_column',
    'fee_collections', 'salaries_paid_total', 'expenses_total', 'payroll_snapshot',
    '_total_outstanding', 'former_students_summary', 'salary_remaining_total',
    'fee_month_overview', 'student_outstanding_rows', '_label_for_key',
    'collection_split', 'month_snapshot', 'expense_breakdown', 'payroll_rows',
    'trend_series', 'session_bounds', 'current_session_start_year', 'months_in_range',
    'all_months_in_period', 'period_descriptor', '_window_totals', 'period_snapshot',
    'period_snapshots', 'COMPARISON_METRICS', 'comparison_rows', 'comparison_totals',
    'comparison_csv', 'comparison_pdf', 'report_csv', 'report_pdf',
    'month_fee_buckets', '_billed_students_count', '_formers_left_count',
    '_period_fee_collection', '_comparison_metric_rows', 'build_comparison',
    'summary_comparisons', 'summary_alerts', 'summary_insights',
    'former_revenue_impact', 'month_bounds', 'month_label', 'parse_month',
    'recent_month_keys', 'shift_month',
)


def test_financial_summary_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'financial_summary.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 8
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_name_is_still_available():
    assert [name for name in NAMES if not hasattr(financial_summary, name)] == []


def test_the_original_import_lines_still_work():
    from app.services.financial_summary import (_window_totals, collection_split,  # noqa: F401
                                                month_snapshot, period_descriptor,
                                                period_snapshot)
    assert month_snapshot.__module__.endswith('financial_summary.snapshots')

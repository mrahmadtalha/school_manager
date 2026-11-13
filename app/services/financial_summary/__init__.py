"""Financial overview: fee revenue vs payroll + expenses, net position and trends."""

# This package replaces the former single file ``financial_summary.py``.  Every name the
# rest of the application and the tests used before (private helpers too) is
# re-exported here, so ``from app.services.financial_summary import ...`` keeps working.

from .common import (  # noqa: F401
    short_label, _money, _inventory_enabled, _cash_date_column, _label_for_key,
)
from .periods import (  # noqa: F401
    session_bounds, current_session_start_year, months_in_range, all_months_in_period,
    period_descriptor,
)
from .fees import (  # noqa: F401
    fee_collections, _total_outstanding, former_students_summary, fee_month_overview,
    student_outstanding_rows, collection_split, month_fee_buckets,
    _billed_students_count, _formers_left_count, _period_fee_collection,
    former_revenue_impact,
)
from .costs import (  # noqa: F401
    salaries_paid_total, expenses_total, payroll_snapshot, salary_remaining_total,
    expense_breakdown, payroll_rows,
)
from .snapshots import (  # noqa: F401
    month_snapshot, trend_series, _window_totals, period_snapshot, period_snapshots,
)
from .comparison import (  # noqa: F401
    COMPARISON_METRICS, comparison_rows, comparison_totals, _comparison_metric_rows,
    build_comparison, summary_comparisons,
)
from .insights import (  # noqa: F401
    summary_alerts, summary_insights,
)
from .exports import (  # noqa: F401
    comparison_csv, comparison_pdf, report_csv, report_pdf,
)

# Names re-exported from payroll_service because callers use them as ``financial_summary.month_label`` etc.
from app.services.payroll_service import (  # noqa: E402,F401
    month_bounds, month_label, parse_month, recent_month_keys, shift_month)

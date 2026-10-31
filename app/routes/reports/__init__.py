"""Reports module (split into focused sub-modules; every name is re-exported here)."""

from app.routes.reports.core import (  # noqa: F401
    _format_result_date,
    _class_results_evaluation,
    _class_results_summary,
    _load_result_remarks,
    _fit_report_on_one_page,
)
from app.routes.reports.hub import (  # noqa: F401
    reports_root,
    _HUB_TABS,
    _HUB_MONTHS,
    _hub_filters,
    _hub_kpis,
    _hub_exam_pass,
    _hub_attendance_chart,
    _hub_academic_chart,
    _hub_fee_chart,
    reports_hub,
    _hub_period_suffix,
    _hub_fee_months,
    _fee_status,
    _hub_class_label,
    _hub_money,
)
from app.routes.reports.exports import (  # noqa: F401
    _HUB_EXPORT_FORMATS,
    _hub_export_guard,
    _collect_fee_export_rows,
    _defaulter_export_rows,
    _collection_export_rows,
    _discount_export_rows,
    _salary_register_rows,
    _position_export_rows,
    _hub_pdf_cell,
    _hub_simple_table_pdf,
    _hub_export_file,
    hub_export_fee_ledger,
    hub_export_defaulters,
    hub_export_collections,
    hub_export_discounts,
    hub_export_salary_register,
    hub_export_positions,
    _broad_sheet_subject_cols,
    hub_export_broad_sheet,
    hub_export_allocation_matrix,
)
from app.routes.reports.class_results import (  # noqa: F401
    class_results_matrix,
    save_class_result_remarks,
    export_class_tabulation_pdf,
    _build_class_tabulation_doc,
    export_class_results_excel,
    export_class_results_csv,
)
from app.routes.reports.cards import (  # noqa: F401
    student_report_card_pdf,
    export_all_report_cards_pdf,
    _build_student_report_story,
)

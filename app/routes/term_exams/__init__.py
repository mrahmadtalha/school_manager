"""term_exams routes (split into focused sub-modules; every name is re-exported here)."""

from app.routes.term_exams.exams import (  # noqa: F401
    STATUS_COLORS,
    _parse_date,
    _current_session_label,
    _term_exam_types,
    _marks_filled_for,
    _progress_state,
    _exam_rows,
    examinations_page,
    examinations_create,
    examinations_detail,
    examinations_schedule,
    examinations_date_sheet,
    examinations_date_sheet_pdf,
    _ordinal,
    build_tabulation,
    _tabulation_header,
    examinations_tabulation,
    examinations_tabulation_csv,
)
from app.routes.term_exams.results import (  # noqa: F401
    examinations_tabulation_xlsx,
    _build_tabulation_pdf,
    examinations_tabulation_pdf,
    _result_cards,
    examinations_result_card,
    examinations_result_cards_all,
    examinations_publish,
    examinations_unpublish,
)

"""Students module (split into focused sub-modules; every name is re-exported here)."""

from app.routes.students.helpers import (  # noqa: F401
    _student_filters,
    _apply_student_filters,
    _dues_balances,
    _parse_gender,
    _parse_optional_date,
    _student_sponsor_values,
    _student_form_context,
    _NEWLINE_WS,
    collapse_ws,
    _num_text,
    _student_edit_map,
    _render_students_page,
    _student_fee_values,
    _import_admission_enabled,
)
from app.routes.students.crud import (  # noqa: F401
    students_list,
    add_student,
    edit_student,
    transfer_student_section,
    delete_student,
    archived_students_list,
    restore_student,
    restore_all_students,
    student_photo,
)
from app.routes.students.documents import (  # noqa: F401
    student_detailed_report,
    student_admission_form,
    student_report_pdf,
    student_transcript_pdf,
)
from app.routes.students.exports import (  # noqa: F401
    _student_export_context,
    export_students_csv,
    students_template_excel,
    export_students_excel,
    export_students_pdf,
)
from app.routes.students.importing import (  # noqa: F401
    STUDENT_EXAMPLE_KEYS,
    _roll_conflict_text,
    import_students,
)

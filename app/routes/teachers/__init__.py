"""teachers routes (split into focused sub-modules; every name is re-exported here)."""

from app.routes.teachers.crud import (  # noqa: F401
    _optional_str,
    _optional_float,
    _optional_date,
    _multi_values,
    _assigned_classes_from_form,
    _teacher_assignment_views,
    _DESIGNATION_GROUPS,
    _TODAY_STATES,
    _designation_group,
    _staff_overview,
    next_teacher_id,
    teachers_list,
    teacher_profile,
    add_teacher,
    edit_teacher,
    delete_teacher,
    archived_teachers_list,
    restore_teacher,
    _teacher_export_context,
)
from app.routes.teachers.exports import (  # noqa: F401
    export_teachers_csv,
    TEACHER_EXAMPLE_KEYS,
    teachers_template_excel,
    export_teachers_excel,
    export_teachers_pdf,
    _digits_only,
    import_teachers,
    restore_all_teachers,
    teacher_photo,
)

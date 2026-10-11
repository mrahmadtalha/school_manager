"""Tests for the "show all fields" data view on the Student / Teacher pages.

Covers:
* every available field (mandatory or optional, built-in or custom) is present
  as a column in the list table,
* the column picker UI exists and offers "show all" / "reset",
* exports honour a ``cols=`` selection, and can still export *all* fields.
"""

import csv
import io
import re
from datetime import date

from app.database import db
from app.models import (
    ClassModel, SchoolSettings, StudentModel, SubjectModel, TeacherModel,
)
from app.models.settings import set_custom_fields
from app.services import record_view


def _add_student(class_id, roll, name='Test Student', **kwargs):
    student = StudentModel(
        roll_number=roll, student_name=name, father_name='Father Name',
        guardian_phone='03001234567', address='Some Street, City',
        class_id=class_id, monthly_fee=2500.0, **kwargs)
    db.session.add(student)
    db.session.flush()
    return student


def _add_teacher():
    teacher = TeacherModel(
        teacher_id_str='T-900', teacher_name='View Teacher',
        qualification='MSc', is_active=True, monthly_salary=45000.0,
        salary=45000.0, designation='Senior Teacher', gender='Female',
        cnic='36302-1234567-1', contact_number='03211234567',
        emergency_contact_number='03007654321', address='Teacher Street',
        previous_experience_years=4.0, previous_salary=35000.0,
        date_of_birth=date(1990, 6, 10), joining_date=date(2024, 1, 15),
    )
    db.session.add(teacher)
    db.session.flush()
    return teacher


# ==========================================
# FIELD REGISTRY
# ==========================================

def test_registry_exposes_every_model_field(app):
    with app.app_context():
        student_keys = record_view.selectable_keys('student')
        teacher_keys = record_view.selectable_keys('teacher')

        # Every student/teacher model column that is meaningful to show.
        for expected in ('roll_number', 'student_name', 'father_name', 'sponsor_type',
                         'sponsor_cnic', 'guardian_phone', 'address', 'monthly_fee',
                         'status', 'leaving_reason', 'leaving_date', 'date_of_birth',
                         'gender', 'admission_number', 'admission_date', 'class',
                         'section', 'class_fee', 'discount_type', 'discount_value',
                         'is_active'):
            assert expected in student_keys, expected
        for expected in ('teacher_id_str', 'teacher_name', 'joining_date',
                         'qualification', 'salary_type', 'monthly_salary',
                         'hourly_rate', 'assigned_classes', 'assigned_subjects',
                         'cnic', 'address', 'contact_number',
                         'emergency_contact_number', 'previous_experience_years',
                         'previous_salary', 'date_of_birth', 'designation', 'gender',
                         'is_active'):
            assert expected in teacher_keys, expected

        # Many more fields than the handful the table used to show.
        assert len(student_keys) > 20
        assert len(teacher_keys) > 20


def test_registry_marks_mandatory_fields(app):
    with app.app_context():
        specs = {spec.key: spec for spec in record_view.field_specs('student')}
        assert specs['student_name'].required is True
        assert specs['father_name'].required is True
        assert specs['guardian_phone'].required is True
        assert specs['address'].required is True
        assert specs['class'].required is True
        # Optional fields are present but not marked mandatory.
        assert specs['gender'].required is False
        assert specs['sponsor_cnic'].required is False


def test_custom_fields_become_viewable_columns(app):
    with app.app_context():
        set_custom_fields('student', [
            {'name': 'blood_group', 'label': 'Blood Group', 'type': 'text'},
            {'name': 'house', 'label': 'House', 'type': 'text', 'is_mandatory': True},
        ])
        specs = {spec.key: spec for spec in record_view.field_specs('student')}
        assert 'custom:blood_group' in specs
        assert specs['custom:blood_group'].label == 'Blood Group'
        assert specs['custom:house'].required is True

        # And the value is read back off the record.
        class_obj = ClassModel(name='Class C')
        db.session.add(class_obj)
        db.session.flush()
        student = _add_student(class_obj.id, 3001,
                               custom_fields_data='{"blood_group": "O+", "house": "Red"}')
        db.session.commit()
        assert record_view.display_value(specs['custom:blood_group'], student, {}) == 'O+'
        picker = record_view.picker_payload('student')
        assert any(f['key'] == 'custom:blood_group'
                   for group in picker['groups'] for f in group['fields'])


def test_parse_selected_columns_defaults_and_unknown_keys(app):
    with app.app_context():
        all_keys = record_view.selectable_keys('student')
        # Absent / empty / 'all' => every field.
        assert record_view.parse_selected_columns('student', None) == all_keys
        assert record_view.parse_selected_columns('student', '') == all_keys
        assert record_view.parse_selected_columns('student', 'all') == all_keys
        # A subset keeps the canonical order and drops unknown keys.
        subset = record_view.parse_selected_columns(
            'student', 'guardian_phone,student_name,not_a_field')
        assert subset == ['student_name', 'guardian_phone']
        # Duplicates collapse.
        assert record_view.parse_selected_columns('student', 'gender,gender') == ['gender']


def test_export_specs_drop_view_only_columns(app):
    with app.app_context():
        keys = [spec.key for spec in record_view.export_specs('student', 'all')]
        assert 'photo' not in keys          # view-only column
        assert 'student_name' in keys


def test_value_formatting_covers_kinds(app):
    with app.app_context():
        class_obj = ClassModel(name='Class D')
        db.session.add(class_obj)
        db.session.flush()
        student = _add_student(
            class_obj.id, 4001,
            gender='Female', date_of_birth=date(2015, 4, 20),
            admission_number='ADM-1', admission_date=date(2024, 4, 1))
        db.session.commit()
        specs = {spec.key: spec for spec in record_view.field_specs('student')}
        assert record_view.display_value(specs['date_of_birth'], student, {}) == '20 Apr 2015'
        assert record_view.display_value(specs['monthly_fee'], student, {}) == 'Rs. 2,500'
        assert record_view.display_value(specs['is_active'], student, {}) == 'Yes'
        # Empty optional values never render blank in the table.
        assert record_view.display_value(specs['sponsor_cnic'], student, {}) == '—'
        # ...but stay blank in spreadsheet exports.
        assert record_view.plain_value(specs['sponsor_cnic'], student, {}) == ''
        assert record_view.excel_value(specs['monthly_fee'], student, {}) == 2500.0


# ==========================================
# PAGE RENDERING
# ==========================================

def test_students_page_renders_every_field_column(admin_client, app, seed):
    with app.app_context():
        _add_student(seed['class_id'], 5001, 'Column Check')
        db.session.commit()
        expected_keys = record_view.selectable_keys('student')

    body = admin_client.get('/students').get_data(as_text=True)
    for key in expected_keys:
        assert f'data-col="{key}"' in body, f'missing column: {key}'
    # Fields that used to be invisible are now real columns.
    for label in ('Sponsor Type', 'Admission No', 'Leaving Date', 'Discount Type'):
        assert label in body, label


def test_students_page_has_column_picker_with_show_all(admin_client, app, seed):
    body = admin_client.get('/students').get_data(as_text=True)
    assert 'data-column-picker="student"' in body
    assert 'data-column-preset="all"' in body
    assert 'Show all fields' in body
    assert 'data-column-preset="default"' in body
    # One checkbox per field.
    with app.app_context():
        for key in record_view.selectable_keys('student'):
            assert f'data-col-toggle="{key}"' in body, key


def test_teachers_page_renders_every_field_column(admin_client, app):
    with app.app_context():
        _add_teacher()
        db.session.commit()
        expected_keys = record_view.selectable_keys('teacher')

    body = admin_client.get('/teachers').get_data(as_text=True)
    for key in expected_keys:
        assert f'data-col="{key}"' in body, f'missing column: {key}'
    for label in ('Designation', 'Emergency Contact', 'Previous Experience (Years)',
                  'Hourly Rate', 'CNIC'):
        assert label in body, label
    assert 'data-column-picker="teacher"' in body
    assert 'Show all fields' in body


def test_students_table_columns_match_header_order(admin_client, app, seed):
    """The header and the body must describe the same columns in the same order."""
    with app.app_context():
        _add_student(seed['class_id'], 5002, 'Order Check')
        db.session.commit()

    body = admin_client.get('/students').get_data(as_text=True)
    table_html = body.split('id="studentTable"', 1)[1]
    header_keys = re.findall(r'data-col="([^"]+)"', table_html.split('</thead>', 1)[0])
    first_row = table_html.split('<tbody', 1)[1].split('</tr>', 1)[0]
    row_keys = re.findall(r'data-col="([^"]+)"', first_row)
    assert header_keys == row_keys
    assert header_keys[0] == 'photo'
    assert header_keys[-1] == 'actions'


# ==========================================
# EXPORTS
# ==========================================

def test_student_csv_export_all_fields_by_default(admin_client, app, seed):
    with app.app_context():
        _add_student(seed['class_id'], 6001, 'Export All')
        db.session.commit()
        expected = record_view.headers(record_view.export_specs('student', 'all'))

    text = admin_client.get('/students/export/csv').get_data(as_text=True)
    header = next(csv.reader(io.StringIO(text)))
    assert header == expected
    # Mandatory fields are marked, and wide/optional fields are included.
    assert 'Student Name *' in header
    assert 'Sponsor Type' in header
    assert 'Admission No' in header
    assert 'Leaving Reason' in header
    assert 'Export All' in text


def test_student_csv_export_honours_selected_columns(admin_client, app, seed):
    with app.app_context():
        _add_student(seed['class_id'], 6002, 'Subset Export')
        db.session.commit()

    text = admin_client.get(
        '/students/export/csv?cols=student_name,guardian_phone,admission_number'
    ).get_data(as_text=True)
    header = next(csv.reader(io.StringIO(text)))
    assert header == ['Student Name *', 'Phone *', 'Admission No']
    assert 'Admission Date' not in text
    assert 'Monthly Fee' not in text


def test_student_excel_and_pdf_respect_columns(admin_client, app, seed):
    with app.app_context():
        _add_student(seed['class_id'], 6003, 'Excel Subset')
        db.session.commit()

    xlsx = admin_client.get('/students/export/excel?cols=student_name,monthly_fee')
    assert xlsx.status_code == 200
    assert xlsx.data[:2] == b'PK'

    pdf = admin_client.get('/students/export/pdf?cols=student_name,monthly_fee')
    assert pdf.status_code == 200
    assert pdf.data.startswith(b'%PDF')

    # All-fields exports stay valid too.
    assert admin_client.get('/students/export/excel?cols=all').data[:2] == b'PK'
    assert admin_client.get('/students/export/pdf?cols=all').data.startswith(b'%PDF')


def test_student_export_keeps_filters_with_columns(admin_client, app, seed):
    with app.app_context():
        other_class = ClassModel(name='Class Z')
        db.session.add(other_class)
        db.session.flush()
        _add_student(seed['class_id'], 6004, 'In Filtered Class')
        _add_student(other_class.id, 6005, 'Outside Cost')
        db.session.commit()

    text = admin_client.get(
        f'/students/export/csv?class_id={seed["class_id"]}&cols=student_name'
    ).get_data(as_text=True)
    assert 'In Filtered Class' in text
    assert 'Outside Cost' not in text


def test_teacher_csv_export_all_fields_and_subset(admin_client, app):
    with app.app_context():
        _add_teacher()
        db.session.commit()
        expected = record_view.headers(record_view.export_specs('teacher', 'all'))

    full = admin_client.get('/teachers/export/csv').get_data(as_text=True)
    header = next(csv.reader(io.StringIO(full)))
    assert header == expected
    assert 'Name *' in header
    assert 'Designation' in header
    assert 'Emergency Contact' in header
    assert 'View Teacher' in full

    subset = admin_client.get(
        '/teachers/export/csv?cols=teacher_name,designation,monthly_salary'
    ).get_data(as_text=True)
    header = next(csv.reader(io.StringIO(subset)))
    assert header == ['Name *', 'Designation', 'Salary (PKR)']
    assert 'Emergency Contact' not in subset


def test_teacher_excel_and_pdf_exports_valid(admin_client, app):
    with app.app_context():
        _add_teacher()
        db.session.commit()

    assert admin_client.get('/teachers/export/excel').data[:2] == b'PK'
    assert admin_client.get('/teachers/export/pdf').data.startswith(b'%PDF')
    assert admin_client.get('/teachers/export/excel?cols=teacher_name').data[:2] == b'PK'
    assert admin_client.get('/teachers/export/pdf?cols=all').data.startswith(b'%PDF')


def test_students_table_columns_match_header_order(admin_client, app, seed):
    """The header and the body must describe the same columns in the same order."""
    with app.app_context():
        _add_student(seed['class_id'], 5002, 'Order Check')
        db.session.commit()

    body = admin_client.get('/students').get_data(as_text=True)
    table_html = body.split('id="studentTable"', 1)[1]
    header_keys = re.findall(r'data-col="([^"]+)"', table_html.split('</thead>', 1)[0])
    first_row = table_html.split('<tbody', 1)[1].split('</tr>', 1)[0]
    row_keys = re.findall(r'data-col="([^"]+)"', first_row)
    assert header_keys == row_keys
    assert header_keys[0] == 'photo'
    assert header_keys[-1] == 'actions'


def test_picker_javascript_payload_is_valid_json(admin_client, app, seed):
    """The picker script must receive parseable data or it silently breaks."""
    import json

    body = admin_client.get('/students').get_data(as_text=True)
    for name in ('ENTITY', 'TABLE_ID', 'EXPORT_URLS', 'DEFAULT_KEYS', 'ALL_KEYS'):
        match = re.search(rf'var {name} = (.+?);', body)
        assert match, f'{name} not found in the rendered page'
        json.loads(match.group(1))          # raises if the payload is malformed


def test_picker_javascript_payload_is_valid_json_teachers(admin_client, app):
    import json

    with app.app_context():
        _add_teacher()
        db.session.commit()
    body = admin_client.get('/teachers').get_data(as_text=True)
    for name in ('ENTITY', 'TABLE_ID', 'EXPORT_URLS', 'DEFAULT_KEYS', 'ALL_KEYS'):
        match = re.search(rf'var {name} = (.+?);', body)
        assert match, f'{name} not found in the rendered page'
        json.loads(match.group(1))


# ==========================================
# COMPACT / SCROLLABLE TABLE LAYOUT
# ==========================================

def _interface_css(app):
    import os
    with open(os.path.join(app.root_path, 'static', 'style.css'), encoding='utf-8') as handle:
        return handle.read()


def test_long_text_columns_are_marked_for_truncation(app):
    """Long free-text fields must be width-capped rather than stretching the table."""
    with app.app_context():
        specs = {spec.key: spec for spec in record_view.field_specs('student')}
        assert specs['address'].truncate is True
        assert specs['leaving_reason'].truncate is True
        assert 'col-truncate' in record_view.column_css(specs['address'])
        # Short, predictable columns are deliberately not truncating.
        assert specs['roll_number'].truncate is False
        assert 'col-truncate' not in record_view.column_css(specs['roll_number'])

        teacher_specs = {spec.key: spec for spec in record_view.field_specs('teacher')}
        assert teacher_specs['address'].truncate is True
        assert 'col-truncate' in record_view.column_css(teacher_specs['address'])


def test_custom_fields_truncate_because_their_length_is_unknown(app):
    with app.app_context():
        set_custom_fields('student', [
            {'name': 'notes', 'label': 'Notes', 'type': 'text'}])
        specs = {spec.key: spec for spec in record_view.field_specs('student')}
        spec = specs['custom:notes']
        assert spec.truncate is True
        # The colon is not a legal raw CSS class character, so it is replaced.
        classes = record_view.column_css(spec)
        assert 'col-custom-notes' in classes
        assert 'col-truncate' in classes
        assert ':' not in classes


def test_column_css_marks_numeric_date_and_bool_columns(app):
    with app.app_context():
        specs = {spec.key: spec for spec in record_view.field_specs('student')}
        assert 'col-num' in record_view.column_css(specs['monthly_fee'])
        assert 'col-num' in record_view.column_css(specs['dues'])
        assert 'col-date' in record_view.column_css(specs['date_of_birth'])
        assert 'col-bool' in record_view.column_css(specs['is_active'])
        assert 'col-image' in record_view.column_css(specs['photo'])
        # No duplicated class tokens.
        for key, spec in specs.items():
            tokens = record_view.column_css(spec).split()
            assert len(tokens) == len(set(tokens)), f'duplicate class on {key}: {tokens}'


def test_pages_apply_column_classes_and_hover_titles(admin_client, app, seed):
    with app.app_context():
        class_obj = db.session.get(ClassModel, seed['class_id'])
        db.session.add(StudentModel(
            roll_number=7101, student_name='Layout Student',
            father_name='Layout Father', guardian_phone='03001234567',
            address='A deliberately long address that would otherwise stretch the table',
            class_id=class_obj.id, monthly_fee=2500.0))
        db.session.add(TeacherModel(
            teacher_id_str='T-556', teacher_name='Layout Teacher',
            qualification='MSc', is_active=True, monthly_salary=45000.0,
            salary=45000.0,
            address='A deliberately long teacher address for the compact layout'))
        db.session.commit()

    students = admin_client.get('/students').get_data(as_text=True)
    assert 'col-address col-truncate' in students
    assert 'col-actions no-sort' in students
    # The full value stays reachable on hover for capped columns.
    assert 'title="A deliberately long address that would otherwise stretch the table"' in students

    teachers = admin_client.get('/teachers').get_data(as_text=True)
    assert 'col-address col-truncate' in teachers
    assert 'title="A deliberately long teacher address for the compact layout"' in teachers


def test_wide_tables_opt_into_horizontal_scrolling(admin_client, app, seed):
    with app.app_context():
        db.session.add(TeacherModel(
            teacher_id_str='T-557', teacher_name='Scroll Teacher',
            qualification='MSc', is_active=True, monthly_salary=45000.0,
            salary=45000.0))
        db.session.commit()

    body = admin_client.get('/students').get_data(as_text=True)
    table_tag = re.search(r'<table[^>]*id="studentTable"[^>]*>', body).group(0)
    assert 'data-scroll-x="true"' in table_tag

    teachers = admin_client.get('/teachers').get_data(as_text=True)
    teacher_tag = re.search(r'<table[^>]*id="teacherTable"[^>]*>', teachers).group(0)
    assert 'data-scroll-x="true"' in teacher_tag

    # The toolbar (export + column picker) sits outside the scroll region, so it
    # cannot be pushed out of view by a wide table.
    toolbar_at = body.index('data-column-picker="student"')
    table_at = body.index('id="studentTable"')
    assert toolbar_at < table_at


def test_stylesheet_implements_compact_and_scroll_rules(app):
    css = _interface_css(app)
    # Long fields are width-capped and the full text is kept on hover.
    assert '.table-panel .col-truncate' in css
    assert 'max-width: 15rem' in css
    assert 'overflow-wrap: anywhere' in css
    # Compact type and padding.
    assert '.table-panel .table > :not(caption) > * > *' in css
    assert 'font-size: 0.875rem' in css
    assert 'font-size: 0.7rem' in css
    # Horizontal scrolling that keeps the controls in place.
    assert 'dataTables_scrollBody' in css
    assert 'overflow-x: auto' in css
    # Actions remain reachable while scrolling sideways.
    assert 'position: sticky' in css
    # The panel must not create a scroll container that would break sticky.
    assert 'overflow: clip' in css
    # No duplicated rule blocks (guard against sloppy edits).
    for selector in ('.table-panel .col-image {', '.table-panel .col-truncate {'):
        assert css.count(selector) == 1, f'{selector} declared {css.count(selector)} times'


def test_scrollable_tables_are_not_nested_in_table_responsive(admin_client, app, seed):
    """scrollX already provides the scroll region; a second wrapper adds a
    second scrollbar and can push the controls around."""
    body = admin_client.get('/students').get_data(as_text=True)
    before_table = body[:body.index('id="studentTable"')]
    # The nearest wrapper for the scrolled table must not be table-responsive.
    assert 'card-body table-responsive p-0' not in before_table
    assert 'card-body p-0' in before_table


def test_datatables_init_does_not_add_a_second_scroll_wrapper(app):
    import os
    with open(os.path.join(app.root_path, 'templates', 'base.html'), encoding='utf-8') as handle:
        base = handle.read()
    assert 'options.scrollX = true' in base
    assert 'scrollCollapse' in base
    # No hand-rolled extra wrapper around the table.
    assert 'dt-scroll-wrap' not in base


def test_scrollx_option_is_wired_in_the_shared_datatable_init(app):
    import os
    with open(os.path.join(app.root_path, 'templates', 'base.html'), encoding='utf-8') as handle:
        base = handle.read()
    assert 'scrollX' in base
    assert "data('scroll-x')" in base


def test_custom_field_is_exportable(admin_client, app, seed):
    with app.app_context():
        set_custom_fields('student', [
            {'name': 'blood_group', 'label': 'Blood Group', 'type': 'text'}])
        _add_student(seed['class_id'], 6006, 'Custom Export',
                     custom_fields_data='{"blood_group": "AB+"}')
        db.session.commit()

    default = admin_client.get('/students/export/csv').get_data(as_text=True)
    assert 'Blood Group' in next(csv.reader(io.StringIO(default)))

    text = admin_client.get('/students/export/csv?cols=custom:blood_group').get_data(as_text=True)
    assert next(csv.reader(io.StringIO(text))) == ['Blood Group']
    assert 'AB+' in text

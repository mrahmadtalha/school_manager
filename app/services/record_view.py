"""Single source of truth for "which fields does a student / teacher have".

The Student and Teacher pages must be able to show *every* available field
(mandatory or optional, including school-defined custom fields), let the user
choose how many columns to display, and export either the columns currently on
screen or all available fields.

Both the list templates and the export builders read their columns from here so
the view and the exports can never drift apart.  The ``FieldSpec`` shape mirrors
``app.services.data_import`` (which does the same job for the import templates)
so the two stay easy to reason about together.
"""

from decimal import Decimal

from app.models.settings import get_custom_fields

#: Custom-field columns are keyed ``custom:<name>`` so they can never collide
#: with a built-in column key.
CUSTOM_PREFIX = 'custom:'

ENTITIES = ('student', 'teacher')


class FieldSpec:
    """One viewable / exportable column of a student or teacher record."""

    def __init__(self, key, label, group='Basic', required=False, kind='text',
                 getter=None, export=True, default_visible=False, truncate=False):
        self.key = key
        self.label = label
        self.group = group
        self.required = required
        self.kind = kind          # text | date | money | number | bool | image
        self.getter = getter      # callable(record, extras) -> raw value
        self.export = export      # False for view-only columns (e.g. Photo)
        self.default_visible = default_visible
        # True for long free-text columns (address, notes, custom fields): the
        # table caps their width and ellipsises, with the full value on hover.
        self.truncate = truncate


# --------------------------------------------------------------------------- #
# value helpers
# --------------------------------------------------------------------------- #

def _attr(name):
    """Getter for a plain model attribute."""
    def getter(record, extras):
        return getattr(record, name, None)
    return getter


def _extra(name):
    """Getter for a per-row value supplied by the list route (e.g. dues)."""
    def getter(record, extras):
        value = (extras or {}).get(name)
        if isinstance(value, dict):
            return value.get(record.id)
        return value
    return getter


def _teacher_assignment(field):
    """Getter for one piece of the teacher assignment view."""
    def getter(record, extras):
        view = (extras or {}).get('assignment_map', {}).get(record.id)
        if not view:
            return None
        value = view.get(field) if isinstance(view, dict) else getattr(view, field, None)
        if isinstance(value, (list, tuple)):
            return ', '.join(str(item) for item in value) or None
        return value or None
    return getter


def _class_name(record, extras):
    class_obj = getattr(record, 'class_info', None)
    return getattr(class_obj, 'name', None)


def _section_name(record, extras):
    section = getattr(record, 'section_info', None)
    return getattr(section, 'name', None)


# --------------------------------------------------------------------------- #
# student fields
# --------------------------------------------------------------------------- #

def student_fields():
    """Every student column, in display order."""
    return [
        FieldSpec('photo', 'Photo', 'Basic', kind='image',
                  getter=_attr('photo_filename'), export=False,
                  default_visible=True),
        FieldSpec('roll_number', 'Roll No', 'Basic', kind='number',
                  getter=_attr('roll_number'), default_visible=True),
        FieldSpec('student_name', 'Student Name', 'Basic', required=True,
                  getter=_attr('student_name'), default_visible=True),
        FieldSpec('father_name', 'Father / Guardian Name', 'Basic', required=True,
                  getter=_attr('father_name'), default_visible=True),
        FieldSpec('class', 'Class', 'Class', required=True,
                  getter=_class_name, default_visible=True),
        FieldSpec('section', 'Section', 'Class', getter=_section_name),
        FieldSpec('sponsor_type', 'Sponsor Type', 'Basic',
                  getter=_attr('sponsor_type')),
        FieldSpec('sponsor_cnic', 'Sponsor CNIC', 'Basic',
                  getter=_attr('sponsor_cnic')),
        FieldSpec('guardian_phone', 'Phone', 'Contact', required=True,
                  getter=_attr('guardian_phone'), default_visible=True),
        FieldSpec('address', 'Address', 'Contact', required=True,
                  getter=_attr('address'), truncate=True),
        FieldSpec('gender', 'Gender', 'Basic', getter=_attr('gender')),
        FieldSpec('date_of_birth', 'Date of Birth', 'Basic', kind='date',
                  getter=_attr('date_of_birth')),
        FieldSpec('admission_number', 'Admission No', 'Admission',
                  getter=_attr('admission_number')),
        FieldSpec('admission_date', 'Admission Date', 'Admission', kind='date',
                  getter=_attr('admission_date')),
        FieldSpec('status', 'Status', 'Record', getter=_attr('status')),
        FieldSpec('monthly_fee', 'Monthly Fee', 'Fees', kind='money',
                  getter=_attr('monthly_fee'), default_visible=True),
        FieldSpec('dues', 'Dues', 'Fees', kind='money',
                  getter=_extra('dues_map'), default_visible=True),
        FieldSpec('class_fee', 'Class Fee (before discount)', 'Fees', kind='money',
                  getter=_attr('class_fee')),
        FieldSpec('discount_type', 'Discount Type', 'Fees',
                  getter=_attr('discount_type')),
        FieldSpec('discount_value', 'Discount Value', 'Fees', kind='number',
                  getter=_attr('discount_value')),
        FieldSpec('leaving_date', 'Leaving Date', 'Record', kind='date',
                  getter=_attr('leaving_date')),
        FieldSpec('leaving_reason', 'Leaving Reason', 'Record',
                  getter=_attr('leaving_reason'), truncate=True),
        FieldSpec('is_active', 'Active', 'Record', kind='bool',
                  getter=_attr('is_active')),
    ]


# --------------------------------------------------------------------------- #
# teacher fields
# --------------------------------------------------------------------------- #

def teacher_fields():
    """Every teacher column, in display order."""
    return [
        FieldSpec('photo', 'Photo', 'Basic', kind='image',
                  getter=_attr('photo_filename'), export=False,
                  default_visible=True),
        FieldSpec('teacher_id_str', 'Teacher ID', 'Basic', kind='number',
                  getter=_attr('teacher_id_str'), default_visible=True),
        FieldSpec('teacher_name', 'Name', 'Basic', required=True,
                  getter=_attr('teacher_name'), default_visible=True),
        FieldSpec('qualification', 'Qualification', 'Basic', required=True,
                  getter=_attr('qualification'), default_visible=True),
        FieldSpec('designation', 'Designation', 'Basic',
                  getter=_attr('designation')),
        FieldSpec('gender', 'Gender', 'Basic', getter=_attr('gender')),
        FieldSpec('date_of_birth', 'Date of Birth', 'Basic', kind='date',
                  getter=_attr('date_of_birth')),
        FieldSpec('cnic', 'CNIC', 'Contact', getter=_attr('cnic')),
        FieldSpec('contact_number', 'Phone', 'Contact',
                  getter=_attr('contact_number')),
        FieldSpec('emergency_contact_number', 'Emergency Contact', 'Contact',
                  getter=_attr('emergency_contact_number')),
        FieldSpec('address', 'Address', 'Contact', getter=_attr('address'),
                  truncate=True),
        FieldSpec('joining_date', 'Joining Date', 'Employment', required=True,
                  kind='date', getter=_attr('joining_date'),
                  default_visible=True),
        FieldSpec('salary_type', 'Salary Type', 'Salary',
                  getter=_attr('salary_type')),
        FieldSpec('monthly_salary', 'Salary (PKR)', 'Salary', kind='money',
                  getter=lambda r, e: (r.monthly_salary or r.salary or 0),
                  default_visible=True),
        FieldSpec('hourly_rate', 'Hourly Rate', 'Salary', kind='money',
                  getter=_attr('hourly_rate')),
        FieldSpec('previous_experience_years', 'Previous Experience (Years)',
                  'History', kind='number',
                  getter=_attr('previous_experience_years')),
        FieldSpec('previous_salary', 'Previous Salary', 'History', kind='money',
                  getter=_attr('previous_salary')),
        FieldSpec('assigned_classes', 'Assigned Classes', 'Assignment',
                  getter=_teacher_assignment('classes')),
        FieldSpec('assigned_subjects', 'Assigned Subjects', 'Assignment',
                  getter=_teacher_assignment('subjects')),
        FieldSpec('assigned_class', 'Assigned Class (label)', 'Assignment',
                  getter=_attr('assigned_class')),
        FieldSpec('is_active', 'Active', 'Record', kind='bool',
                  getter=_attr('is_active')),
    ]


# --------------------------------------------------------------------------- #
# registry assembly
# --------------------------------------------------------------------------- #

def custom_field_specs(entity, custom_fields=()):
    """Turn school-defined custom fields into viewable / exportable columns."""
    specs = []
    for field in custom_fields or ():
        if not isinstance(field, dict):
            continue
        name = (field.get('name') or '').strip()
        label = (field.get('label') or name).strip()
        if not name or not label:
            continue
        kind = field.get('type') or 'text'
        specs.append(FieldSpec(
            CUSTOM_PREFIX + name, label, 'Custom',
            required=bool(field.get('is_mandatory')),
            kind={'number': 'number'}.get(kind, 'text'),
            getter=_custom_value(name),
            truncate=True))
    return specs


def _custom_value(name):
    from app.services.custom_fields import parse_custom_fields_json

    def getter(record, extras):
        values = parse_custom_fields_json(getattr(record, 'custom_fields_data', None))
        return values.get(name)
    return getter


def field_specs(entity, custom_fields=None):
    """All field specs for ``entity`` ('student' or 'teacher'), custom included."""
    if entity == 'student':
        specs = student_fields()
    elif entity == 'teacher':
        specs = teacher_fields()
    else:
        raise ValueError(f'Unknown entity: {entity!r}')
    if custom_fields is None:
        custom_fields = get_custom_fields(entity)
    return specs + custom_field_specs(entity, custom_fields)


# --------------------------------------------------------------------------- #
# selection parsing / payloads for the templates
# --------------------------------------------------------------------------- #

def selectable_keys(entity, custom_fields=None):
    return [spec.key for spec in field_specs(entity, custom_fields)]


def parse_selected_columns(entity, raw, custom_fields=None):
    """Parse a ``cols`` query value into a list of known field keys.

    ``None`` / empty / ``'all'`` mean *every* field.  Unknown keys are dropped,
    duplicates are collapsed, and the original field order is preserved so an
    export always reads left-to-right the way the table does.
    """
    specs = field_specs(entity, custom_fields)
    keys = [spec.key for spec in specs]
    if raw is None:
        return keys
    if isinstance(raw, (list, tuple)):
        requested = [str(item or '').strip() for item in raw]
    else:
        text = str(raw).strip()
        if not text or text.lower() == 'all':
            return keys
        requested = [part.strip() for part in text.split(',')]
    if any(part.lower() == 'all' for part in requested if part):
        return keys
    wanted = {part for part in requested if part}
    return [key for key in keys if key in wanted]


def export_specs(entity, raw, custom_fields=None):
    """The field specs an export should contain (view-only columns dropped)."""
    specs = field_specs(entity, custom_fields)
    by_key = {spec.key: spec for spec in specs}
    return [by_key[key] for key in parse_selected_columns(entity, raw, custom_fields)
            if by_key[key].export]


def picker_payload(entity, custom_fields=None, selected=None):
    """Context for the column-picker partial (checkbox list grouped by field group)."""
    specs = field_specs(entity, custom_fields)
    if selected:
        selected_keys = set(parse_selected_columns(entity, list(selected), custom_fields))
    else:
        selected_keys = {spec.key for spec in specs if spec.default_visible}
    default_keys = {spec.key for spec in specs if spec.default_visible}

    # Group by first appearance so the picker reads like the form does
    # (group members are not necessarily contiguous in `specs`).
    grouped = {}
    order = []
    for spec in specs:
        if spec.group not in grouped:
            grouped[spec.group] = []
            order.append(spec.group)
        grouped[spec.group].append({
            'key': spec.key,
            'label': spec.label,
            'required': spec.required,
            'selected': spec.key in selected_keys,
            'default': spec.key in default_keys,
            'export': spec.export,
        })
    groups = [{'name': name, 'fields': grouped[name]} for name in order]
    return {
        'entity': entity,
        'groups': groups,
        'columns': [field for group in groups for field in group['fields']],
    }


# --------------------------------------------------------------------------- #
# value formatting
# --------------------------------------------------------------------------- #

EMPTY = '—'


def _is_empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _money(value):
    try:
        return f'{float(value):,.0f}'
    except (TypeError, ValueError):
        return str(value)


def display_value(spec, record, extras=None):
    """Human-readable cell text for the HTML table (never blank, never raising)."""
    try:
        raw = spec.getter(record, extras) if spec.getter else None
    except Exception:
        raw = None
    if _is_empty(raw):
        return EMPTY
    if spec.kind == 'date':
        return raw.strftime('%d %b %Y') if hasattr(raw, 'strftime') else str(raw)
    if spec.kind == 'money':
        return f'Rs. {_money(raw)}'
    if spec.kind == 'bool':
        return 'Yes' if raw else 'No'
    if spec.kind == 'number':
        return f'{raw:g}' if isinstance(raw, (int, float, Decimal)) else str(raw)
    return str(raw)


def plain_value(spec, record, extras=None):
    """Export text value (blank when empty, so spreadsheets stay clean)."""
    try:
        raw = spec.getter(record, extras) if spec.getter else None
    except Exception:
        raw = None
    if _is_empty(raw):
        return ''
    if spec.kind == 'date':
        return raw.isoformat() if hasattr(raw, 'isoformat') else str(raw)
    if spec.kind == 'bool':
        return 'Yes' if raw else 'No'
    if spec.kind in ('money', 'number'):
        return _money(raw) if spec.kind == 'money' else str(raw)
    return str(raw)


def excel_value(spec, record, extras=None):
    """Cell value for XLSX: keep numbers numeric so they can be summed."""
    try:
        raw = spec.getter(record, extras) if spec.getter else None
    except Exception:
        raw = None
    if _is_empty(raw):
        return ''
    if spec.kind in ('money', 'number'):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return str(raw)
    if spec.kind == 'date':
        return raw.isoformat() if hasattr(raw, 'isoformat') else str(raw)
    if spec.kind == 'bool':
        return 'Yes' if raw else 'No'
    return str(raw)


def build_rows(records, specs, extras=None, value_func=plain_value):
    """Rows of text values for a set of records and export specs."""
    return [[value_func(spec, record, extras) for spec in specs]
            for record in records]


def headers(specs):
    """Column headings; mandatory fields are marked with an asterisk."""
    return [f'{spec.label} *' if spec.required else spec.label for spec in specs]


def column_css(spec):
    """CSS classes for a field's <th>/<td>.

    Keeps the templates free of layout logic and gives the tests a single
    place to assert the compact-table behaviour against.
    """
    classes = ['col-' + spec.key.replace(':', '-')]
    if spec.kind == 'image':
        classes.append('col-image')
    elif spec.kind in ('money', 'number'):
        classes.append('col-num')
    elif spec.kind == 'date':
        classes.append('col-date')
    elif spec.kind == 'bool':
        classes.append('col-bool')
    if spec.truncate:
        # Long free text: capped width + ellipsis, full value on hover.
        classes.append('col-truncate')
    return ' '.join(classes)


ACTIONS_COL_CLASS = 'col-actions no-sort'


def label_map(entity, custom_fields=None):
    return {spec.key: spec.label for spec in field_specs(entity, custom_fields)}

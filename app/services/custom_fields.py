"""Helpers for school-defined custom fields on students and teachers.

Field definitions live in ``system_settings`` under the keys
``student_custom_fields`` / ``teacher_custom_fields`` as a JSON list of
``{"name": ..., "label": ..., "type": ...}`` objects.  Record values are stored
on each student/teacher row in ``custom_fields_data`` as a JSON object keyed by
the (sanitized) field name.

Custom-field inputs in record forms use the ``custom_<name>`` naming convention
so they can never collide with built-in form fields.
"""

import json

#: Prefix used for custom-field inputs in student/teacher forms.
CUSTOM_FIELD_INPUT_PREFIX = 'custom_'


def parse_custom_fields_json(raw):
    """Return the stored custom-field values as a dict (never raises)."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_custom_field_values(form, fields):
    """Extract posted custom-field values for the given field definitions.

    Values are returned keyed by field name.  Empty values are omitted so a
    cleared input removes the stored value; fields that are no longer defined
    in settings are not collected (and are dropped the next time the record is
    saved).
    """
    values = {}
    for field in fields or ():
        if not isinstance(field, dict):
            continue
        name = (field.get('name') or '').strip()
        if not name:
            continue
        raw = form.get(CUSTOM_FIELD_INPUT_PREFIX + name)
        value = (raw or '').strip()
        if value:
            values[name] = value
    return values


def missing_required_custom_fields(form, fields):
    """Labels for mandatory custom fields that have no submitted value."""
    missing = []
    for field in fields or ():
        if not isinstance(field, dict) or not field.get('is_mandatory'):
            continue
        name = (field.get('name') or '').strip()
        if name and not (form.get(CUSTOM_FIELD_INPUT_PREFIX + name) or '').strip():
            missing.append((field.get('label') or name).strip())
    return missing


def prefixed_custom_values(values):
    """Reshape a values dict into the ``custom_<name>`` form-field naming."""
    return {CUSTOM_FIELD_INPUT_PREFIX + name: value
            for name, value in (values or {}).items()}


def serialize_custom_field_values(values):
    """Serialize a values dict for storage; ``None`` when nothing is set."""
    return json.dumps(values, ensure_ascii=False) if values else None


def has_custom_field_input(form):
    """True when the submission carries at least one custom-field input."""
    return any(key.startswith(CUSTOM_FIELD_INPUT_PREFIX) for key in form)


def parse_json_list(raw):
    """Return a stored JSON list (never raises); empty list on anything else."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []

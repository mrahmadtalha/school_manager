"""Event-driven WhatsApp automation definitions.

This module separates the automation policy from the message content so new
triggers can be added in one place without touching the attendance logic.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict


EVENT_TEMPLATES: Dict[str, str] = {
    'attendance_absent': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "This is to inform you that your child {student_name} was marked *ABSENT* on {date_value}.\n\n"
        "Please contact the school for further information.\n\n"
        "Regards,\nSchool Management"
    ),
    'attendance_late': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "This is to inform you that your child {student_name} arrived *LATE* on {date_value}.\n\n"
        "Please ensure timely arrival in the future.\n\n"
        "Regards,\nSchool Management"
    ),
    'result': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "Result update for {student_name}:\n"
        "Obtained: *{obtained}/{total}*\n"
        "Percentage: *{percentage}%*\n"
        "Grade: *{grade}*\n\n"
        "Regards,\nSchool Management"
    ),
    'fee_due': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "This is a reminder that the fee for {student_name} is due.\n"
        "Amount due: *{amount_due}*\n"
        "Due date: {date_value}\n\n"
        "Please make the payment at the earliest convenience.\n\n"
        "Regards,\nSchool Management"
    ),
    'fee_overdue': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "This is a reminder that the outstanding fee for {student_name} remains unpaid.\n"
        "Outstanding amount: *{amount_due}*\n"
        "Please settle it as soon as possible.\n\n"
        "Regards,\nSchool Management"
    ),
    'school_notice': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "School notice: {notice}\n\n"
        "Date: {date_value}\n\n"
        "Regards,\nSchool Management"
    ),
}


def normalize_event_date(value: Any) -> date | None:
    """Convert a date-like value into a Python date instance."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            return None

    return None


def build_event_context(student: Any, trigger: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create the shared context used by all automation events."""
    merged = dict(context or {})
    merged.setdefault('student_name', getattr(student, 'student_name', 'Student'))
    merged.setdefault('date', getattr(student, 'date', None))

    normalized = normalize_event_date(merged.get('date'))
    if normalized is not None:
        merged['date'] = normalized
        merged['date_value'] = normalized.isoformat()
    else:
        merged['date'] = None
        merged['date_value'] = 'today'

    return merged


def render_event_message(trigger: str, context: Dict[str, Any], template_override: str | None = None) -> str:
    """Render a message body using the event registry.

    template_override, when given, takes priority over the built-in
    EVENT_TEMPLATES entry — this is how a user's custom template saved
    in AutomationSettings actually gets used.
    """
    template = template_override or EVENT_TEMPLATES.get(trigger)
    if not template:
        return f"School update for {context.get('student_name', 'Student')}: {context.get('date_value', 'today')}"

    payload = {
        'student_name': context.get('student_name', 'Student'),
        'date': context.get('date', None),
        'date_value': context.get('date_value', context.get('date', 'today')),
        'grade': context.get('grade', ''),
        'obtained': context.get('obtained', ''),
        'total': context.get('total', ''),
        'percentage': context.get('percentage', ''),
        'test_type': context.get('test_type', 'Test'),
        'amount_due': context.get('amount_due', ''),
        'notice': context.get('notice', 'Important notice'),
    }
    return template.format(**payload)


def get_supported_triggers() -> list[str]:
    """Return the list of registered automation trigger names."""
    return list(EVENT_TEMPLATES.keys())
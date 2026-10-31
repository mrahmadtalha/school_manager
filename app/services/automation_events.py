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
        "This is to inform you that your child {student_name} arrived *LATE* on {date_value}{late_at}.\n\n"
        "Please ensure timely arrival in the future.\n\n"
        "Regards,\nSchool Management"
    ),
    'attendance_correction': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "Correction: the earlier message saying your child {student_name} was *ABSENT* "
        "on {date_value} was sent before the student arrived. "
        "Your child reached school{late_at}.\n\n"
        "We are sorry for the confusion.\n\n"
        "Regards,\nSchool Management"
    ),
    'result': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "Result update for {student_name} ({test_type} Test, {date_value}):\n"
        "Obtained: *{obtained}/{total}*\n"
        "Percentage: *{percentage}%*\n"
        "Grade: *{grade}*\n\n"
        "Regards,\nSchool Management"
    ),
    'test_result': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "Result summary for {student_name} ({test_title}, {date_value}):\n\n"
        "{subjects}\n\n"
        "Total: *{obtained}/{total}*\n"
        "Percentage: *{percentage}%*\n"
        "Grade: *{grade}*\n"
        "Class average: {class_average}%\n\n"
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
    'fee_reminder': (
        "Assalam-o-Alaikum,\n\nDear Parent,\n\n"
        "This is a reminder that the fee for {student_name} for {month_year} is outstanding.\n"
        "Outstanding amount: *{amount_due}*\n\n"
        "Please make the payment at the earliest convenience.\n\n"
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


def format_clock(value: Any) -> str:
    """'08:47' / '08:47:30' (as stored by attendance) -> '8:47 AM'; '' if unusable."""
    text = str(value or '').strip()
    if not text:
        return ''
    for pattern in ('%H:%M:%S', '%H:%M'):
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return parsed.strftime('%I:%M %p').lstrip('0')
    return text


def _late_at(context: Dict[str, Any]) -> str:
    """' at *10:45 AM*' for a late arrival, '' when no time is known.

    Only the clear arrival time is written. A figure such as "135 minutes late"
    confuses parents, so the number of minutes is never put in the message.
    """
    clock = format_clock(context.get('late_time'))
    if not clock:
        return ''
    return f' at *{clock}*'


def render_event_message(trigger: str, context: Dict[str, Any], template_override: str | None = None) -> str:
    """Render a message body using the event registry.

    template_override, when given, takes priority over the built-in
    EVENT_TEMPLATES entry — this is how a user's custom template saved
    in AutomationSettings actually gets used.
    """
    template = template_override or EVENT_TEMPLATES.get(trigger)
    if not template:
        return f"School update for {context.get('student_name', 'Student')}: {context.get('date_value', 'today')}"

    late_at = _late_at(context) if trigger in ('attendance_late', 'attendance_correction') else ''
    if (trigger == 'attendance_late' and '{late_at}' not in template
            and '{late_time}' not in template and '{date_value}' in template):
        # A template saved before the arrival time existed: add it right after the date.
        template = template.replace('{date_value}', '{date_value}{late_at}', 1)
    elif trigger == 'attendance_late' and '{date}' in template and '{late_at}' not in template \
            and '{late_time}' not in template:
        if '({date})' in template:
            template = template.replace('({date})', '({date}){late_at}', 1)
        else:
            template = template.replace('{date}', '{date}{late_at}', 1)
    payload = {
        'late_at': late_at,
        'late_time': format_clock(context.get('late_time')),
        'late_minutes': context.get('late_minutes') or '',
        'student_name': context.get('student_name', 'Student'),
        'date': context.get('date', None),
        'date_value': context.get('date_value', context.get('date', 'today')),
        'grade': context.get('grade', ''),
        'obtained': context.get('obtained', ''),
        'total': context.get('total', ''),
        'percentage': context.get('percentage', ''),
        'test_type': context.get('test_type', 'Test'),
        'test_title': context.get('test_title', context.get('test_type', 'Test')),
        'subjects': context.get('subjects', ''),
        'class_average': context.get('class_average', ''),
        'position': context.get('position', ''),
        'class_size': context.get('class_size', ''),
        'amount_due': context.get('amount_due', ''),
        'month_year': context.get('month_year', ''),
        'notice': context.get('notice', 'Important notice'),
    }
    return template.format(**payload)


def get_supported_triggers() -> list[str]:
    """Return the list of registered automation trigger names."""
    return list(EVENT_TEMPLATES.keys())
"""Utilities for WhatsApp notification automation.

This module keeps the policy decisions in Python so the UI and queue can use
one consistent behavior for:
- full automation mode
- human approval mode
- one-by-one delayed sending to reduce WhatsApp ban risk
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict

from app.services.automation_events import (
    build_event_context,
    normalize_event_date,
    render_event_message,
)


def normalize_whatsapp_number(phone: str) -> str:
    """Normalize a local or international phone number to WhatsApp format."""
    value = (phone or '').strip()
    if not value:
        return ''

    digits = ''.join(ch for ch in value if ch.isdigit())
    if not digits:
        return ''

    if digits.startswith('92'):
        return digits

    if digits.startswith('0'):
        digits = '92' + digits[1:]

    return digits


def build_whatsapp_message(trigger: str, context: Dict[str, Any]) -> str:
    """Build the content for a WhatsApp notification."""
    prepared = build_event_context(None, trigger, context)
    return render_event_message(trigger, prepared, _get_custom_template(trigger))


def _get_custom_template(trigger: str) -> str | None:
    """Look up the user's saved custom template for this trigger, if any."""
    from app.models import AutomationSettings

    field_map = {
        'attendance_absent': 'template_absent',
        'attendance_late': 'template_late',
        'result': 'template_result',
    }
    field = field_map.get(trigger)
    if not field:
        return None

    settings = AutomationSettings.get()
    value = getattr(settings, field, None)
    return value.strip() if value and value.strip() else None


def get_delivery_mode_policy(mode: str) -> Dict[str, Any]:
    """Return the sending policy for a selected automation mode.

    Modes:
    - auto: fully automated, send immediately, may batch
    - approval: require human review before sending
    - delayed: send one-by-one with human-paced delay to reduce ban risk
    """
    mode = (mode or '').lower()

    if mode == 'auto':
        return {
            'requires_approval': False,
            'send_all_at_once': True,
            'delay_seconds': 0,
            'one_by_one': False,
            'safe_mode': False,
        }

    if mode == 'delayed':
        return {
            'requires_approval': False,
            'send_all_at_once': False,
            'delay_seconds': 20,
            'one_by_one': True,
            'safe_mode': True,
        }

    return {
        'requires_approval': True,
        'send_all_at_once': False,
        'delay_seconds': 15,
        'one_by_one': True,
        'safe_mode': True,
    }


def queue_automation_message(student: Any, trigger: str, context: Dict[str, Any], mode: str | None = None):
    """Queue a message according to the configured automation mode."""
    from app.database import db
    from app.models import AutomationSettings, MessageQueue

    if not student or not getattr(student, 'guardian_phone', None):
        return None

    settings = AutomationSettings.get()
    if not settings.enabled:
        return None

    event_settings = {
        'attendance_absent': getattr(settings, 'notify_absent', True),
        'attendance_late': getattr(settings, 'notify_late', True),
        'result': getattr(settings, 'notify_results', False),
    }
    if not event_settings.get(trigger, True):
        return None

    final_mode = (mode or settings.mode or 'approval').lower()
    policy = get_delivery_mode_policy(final_mode)

    phone = normalize_whatsapp_number(student.guardian_phone)
    if not phone:
        return None

    message_context = build_event_context(student, trigger, context)
    ref_date_value = normalize_event_date(message_context.get('date'))

    message = build_whatsapp_message(trigger, message_context)
    queue_item = MessageQueue(
        phone=phone,
        message=message,
        status='approved' if not policy['requires_approval'] else 'pending',
        trigger=trigger,
        student_id=getattr(student, 'id', None),
        ref_date=ref_date_value,
    )
    db.session.add(queue_item)
    db.session.commit()
    return queue_item
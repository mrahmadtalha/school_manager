"""Fee reminders for defaulters.

Turns the fee-reconciliation data into queued WhatsApp reminders for the
guardians of students with an outstanding balance.  This is a supervised,
admin-triggered action: messages are queued as ``pending`` (one per student per
month, never duplicated) and then follow the normal automation flow (review,
sending, delivery logs) from the /automation page.
"""

from datetime import datetime

from app.database import db
from app.models import MessageQueue
from app.services.audit import log_action
from app.services.fee_ledger import reconcile
from app.services.whatsapp_automation import (
    build_whatsapp_message,
    normalize_whatsapp_number,
)

TRIGGER = 'fee_reminder'

# A reminder in one of these states already covers the student for the month.
_ACTIVE_STATUSES = ('pending', 'approved', 'sending', 'sent')


def month_start(month_year):
    """'September 2026' -> date(2026, 9, 1); ``None`` for unknown formats."""
    try:
        return datetime.strptime((month_year or '').strip(), '%B %Y').date().replace(day=1)
    except (TypeError, ValueError):
        return None


def defaulter_rows(month_year, class_id=None):
    """Active students with an outstanding balance for ``month_year``.

    Uses the same ledger-derived figures the reconciliation page shows.
    """
    rows, _totals, _discrepancies = reconcile(month_year)
    defaulters = []
    for row in rows:
        student = row['student']
        if not student.is_active:
            continue
        if class_id is not None and student.class_id != class_id:
            continue
        if row['balance'] <= 0.004:  # ignore floating-point dust on settled months
            continue
        defaulters.append(row)
    defaulters.sort(key=lambda row: (row['student'].class_id or 0,
                                     (row['student'].student_name or '').lower()))
    return defaulters


def _active_reminder(student_id, ref_date):
    """The existing queue item that covers this student for the month, if any."""
    return (MessageQueue.query
            .filter(MessageQueue.student_id == student_id,
                    MessageQueue.trigger == TRIGGER,
                    MessageQueue.ref_date == ref_date,
                    MessageQueue.status.in_(_ACTIVE_STATUSES))
            .first())


def fee_reminder_status(month_year, class_id=None):
    """``(awaiting, already_queued)`` splits of the month's defaulters.

    ``already_queued`` entries are defaulter rows plus a ``reminder_status``
    key describing the existing queue item.
    """
    start = month_start(month_year)
    awaiting, already = [], []
    for row in defaulter_rows(month_year, class_id=class_id):
        existing = _active_reminder(row['student'].id, start) if start is not None else None
        if existing is None:
            awaiting.append(row)
        else:
            enriched = dict(row)
            enriched['reminder_status'] = existing.status
            already.append(enriched)
    return awaiting, already


def count_without_phone(rows):
    """How many rows in a defaulter list have no usable guardian phone."""
    return sum(1 for row in rows
               if not normalize_whatsapp_number(row['student'].guardian_phone or ''))


def queue_fee_reminders(month_year, class_id=None):
    """Queue one pending reminder per defaulter; safe to run repeatedly.

    Returns a summary dict with ``queued``, ``skipped_existing``,
    ``skipped_no_phone`` and ``defaulters`` counts.
    """
    start = month_start(month_year)
    if start is None:
        raise ValueError(f'Unknown month "{month_year}" (expected e.g. "September 2026").')

    awaiting, already = fee_reminder_status(month_year, class_id=class_id)
    summary = {
        'month_year': month_year,
        'queued': 0,
        'skipped_existing': len(already),
        'skipped_no_phone': 0,
        'defaulters': len(awaiting) + len(already),
    }

    for row in awaiting:
        student = row['student']
        phone = normalize_whatsapp_number(student.guardian_phone or '')
        if not phone:
            summary['skipped_no_phone'] += 1
            continue

        message = build_whatsapp_message(TRIGGER, {
            'student_name': student.student_name,
            'month_year': month_year,
            'amount_due': f'Rs. {row["balance"]:,.0f}',
            'date': start,
        })
        # Queued directly (not via queue_automation_message): this admin action
        # is explicit and deduplicated above; the item still follows the normal
        # pending -> approved -> sent flow on the automation page.
        db.session.add(MessageQueue(
            phone=phone,
            message=message,
            status='pending',
            trigger=TRIGGER,
            student_id=student.id,
            ref_date=start,
        ))
        summary['queued'] += 1

    if summary['queued']:
        log_action('reminder', entity_type='MessageQueue',
                   summary=(f'Queued {summary["queued"]} fee reminder(s) '
                            f'for {month_year}'))
    db.session.commit()
    return summary

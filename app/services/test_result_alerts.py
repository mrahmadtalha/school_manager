"""WhatsApp result-summary alerts for class tests.

One message per student summarising every subject of a test batch (same
title + date + class). Messages go through ``queue_automation_message`` so the
school's chosen mode (auto / approval / delayed one-by-one), the "Notify
Results" switch, the license and the master automation switch all apply
exactly as they do for absent / late alerts.
"""
from __future__ import annotations

from app.models import AutomationSettings, MessageQueue, StudentMarkModel
from app.services.whatsapp_automation import (
    _whatsapp_licensed,
    build_whatsapp_message,
    normalize_whatsapp_number,
    queue_automation_message,
)

TRIGGER = 'test_result'
_ACTIVE = ('pending', 'approved', 'sending', 'sending_auto', 'sent')


def _fmt(value):
    return '%g' % round(float(value), 1)


def _student_summary(student, tests, marks):
    """Return (lines, obtained, total, complete) for one student."""
    lines, obtained, total = [], 0.0, 0.0
    for test in tests:
        mark = marks.get((student.id, test.id))
        name = test.subject_info.name if test.subject_info else 'Subject'
        if mark is None:
            return [], 0.0, 0.0, False          # paper not entered yet
        if mark.is_absent:
            lines.append('%s: Absent' % name)
            continue
        pct = (mark.marks_obtained / test.total_marks * 100) if test.total_marks else 0
        lines.append('%s: %s/%s (%s%%)' % (
            name, _fmt(mark.marks_obtained), _fmt(test.total_marks), _fmt(pct)))
        obtained += mark.marks_obtained
        total += test.total_marks
    return lines, obtained, total, True


def result_alerts_off_reason():
    """Why result alerts cannot be queued right now, or None when they can."""
    settings = AutomationSettings.get()
    if not settings.enabled:
        return 'WhatsApp automation is switched off in Settings.'
    if not settings.notify_results:
        return '"Results" alerts are switched off in WhatsApp Settings.'
    if not _whatsapp_licensed():
        return 'WhatsApp automation is not included in the license.'
    return None


def queue_test_result_alerts(tests, students):
    """Queue one summary message per student for a batch of tests.

    Returns a dict of counters plus ``off_reason`` (None when sending is on).
    """
    from app.models.settings import calculate_grade

    result = {'queued': 0, 'duplicate': 0, 'no_phone': 0, 'incomplete': 0,
              'all_absent': 0, 'off_reason': None}
    result['off_reason'] = result_alerts_off_reason()
    if result['off_reason']:
        return result
    if not tests:
        return result

    marks = {(m.student_id, m.test_id): m for m in
             StudentMarkModel.query.filter(
                 StudentMarkModel.test_id.in_([t.id for t in tests])).all()}

    summaries = {}
    for student in students:
        lines, obtained, total, complete = _student_summary(student, tests, marks)
        if not complete:
            result['incomplete'] += 1
        elif total <= 0:
            result['all_absent'] += 1
        else:
            summaries[student.id] = (lines, obtained, total, obtained / total * 100)

    percentages = sorted((s[3] for s in summaries.values()), reverse=True)
    class_average = sum(percentages) / len(percentages) if percentages else 0
    test = tests[0]
    test_date = test.test_date.isoformat() if test.test_date else None

    for student in students:
        if student.id not in summaries:
            continue
        if not normalize_whatsapp_number(student.guardian_phone or ''):
            result['no_phone'] += 1
            continue
        lines, obtained, total, pct = summaries[student.id]
        context = {
            'student_name': student.student_name,
            'date': test_date,
            'test_title': test.test_title,
            'test_type': test.test_type,
            'subjects': '\n'.join(lines),
            'obtained': _fmt(obtained),
            'total': _fmt(total),
            'percentage': _fmt(pct),
            'grade': calculate_grade(pct),
            'class_average': _fmt(class_average),
            'position': 1 + sum(1 for p in percentages if p > pct),
            'class_size': len(percentages),
        }
        # Same marks => same text => never queued twice; corrected marks => new text.
        text = build_whatsapp_message(TRIGGER, context)
        if (MessageQueue.query.filter_by(student_id=student.id, trigger=TRIGGER,
                                         message=text)
                .filter(MessageQueue.status.in_(_ACTIVE)).first()):
            result['duplicate'] += 1
            continue
        if queue_automation_message(student, TRIGGER, context):
            result['queued'] += 1
    return result


def describe(result):
    """One-line flash text for a result dict."""
    if result['off_reason']:
        return 'No WhatsApp results queued: %s' % result['off_reason']
    parts = ['%d WhatsApp result message(s) queued' % result['queued']]
    for key, label in (('duplicate', 'already sent/queued'),
                       ('incomplete', 'marks not fully entered'),
                       ('no_phone', 'no guardian number'),
                       ('all_absent', 'absent in every paper')):
        if result[key]:
            parts.append('%d %s' % (result[key], label))
    return parts[0] + (' (skipped: ' + ', '.join(parts[1:]) + ')' if len(parts) > 1 else '') + '.'

"""Handlers: today's attention items, how-to answers, and the intent -> handler table."""

from datetime import date

from app.database import db
from app.models import TeacherModel
from app.services.payroll_service import month_label, current_month_key

from .constants import PAYROLL_REMINDER_DAY, log
from .formatting import _link, _links, _reply
from .handlers_attendance import _is_working_day, h_attendance, h_low_attendance
from .handlers_core import (h_class_strength, h_help, h_students_count, h_teachers_count, h_today_summary)
from .handlers_finance import (h_class_fees, h_compare, h_expenses, h_fees_collected, h_fees_due, h_fees_payments,
                               h_profit, h_salary)
from .handlers_people import (h_birthdays, h_new_admissions, h_student_info, h_teacher_info)


def h_attention(ctx):
    """One short to-do list built from the numbers the software already has."""
    from app.services import dashboard_service
    from app.services.financial_summary import payroll_snapshot, summary_alerts

    today = date.today()
    lines, links = [], []

    attendance = dashboard_service.today_attendance()
    if _is_working_day(today):
        students = attendance['student']
        if students['expected'] and not students['marked']:
            lines.append(ctx.t('Student attendance has not been marked today.',
                               'Aaj ki student attendance abhi mark nahi hui.'))
            links.append(_link('Daily attendance', 'main.student_attendance'))
        elif students['not_marked']:
            lines.append(ctx.t(
                'Attendance is still missing for %d students today.',
                'Aaj %d students ki attendance baqi hai.')
                % students['not_marked'])
            links.append(_link('Daily attendance', 'main.student_attendance'))
        teachers = attendance['teacher']
        if teachers['expected'] and not teachers['marked']:
            lines.append(ctx.t('Teacher attendance has not been marked today.',
                               'Aaj ki teacher attendance abhi mark nahi hui.'))
            links.append(_link('Teacher attendance', 'main.teacher_attendance'))
    absent = attendance['student']['counts']['Absent']
    if absent:
        lines.append(ctx.t('%d students are absent today (ask "aaj kaun absent '
                           'hai?" for names and phone numbers).',
                           'Aaj %d students ghair hazir hain ("aaj kaun absent '
                           'hai?" se naam aur phone dekhein).') % absent)

    if today.day >= PAYROLL_REMINDER_DAY \
            and TeacherModel.query.filter_by(is_active=True).count():
        snap = payroll_snapshot(current_month_key())
        if not snap['count']:
            lines.append(ctx.t('Payroll for %s has not been generated yet.',
                               '%s ki payroll abhi generate nahi hui.')
                         % month_label(current_month_key()))
            links.append(_link('Payroll', 'main.payroll_page'))

    try:
        alerts = summary_alerts(current_month_key())
    except Exception:  # pragma: no cover - degrade, do not fail the answer
        db.session.rollback()
        log.exception('assistant: summary alerts failed')
        alerts = []
    seen_urls = set()
    for alert in alerts[:5]:
        lines.append(alert['text'])
        url = alert.get('url')
        if url and url not in seen_urls:
            seen_urls.add(url)
            links.append({'label': alert.get('link_text') or 'Open',
                          'url': url})

    try:
        birthdays_today = dashboard_service.birthdays()['today']
    except Exception:  # pragma: no cover
        db.session.rollback()
        birthdays_today = []
    if birthdays_today:
        names = ', '.join(entry['name'] for entry in birthdays_today[:5])
        lines.append(ctx.t('Birthday today: %s.', 'Aaj ki birthday: %s.')
                     % names)

    links = _links(*links)[:5]
    if not lines:
        return _reply('attention', ctx.t(
            'Nothing needs attention right now. Attendance is done and there '
            'are no alerts.',
            'Abhi kisi cheez par tawajjuh ki zaroorat nahi. Attendance mukammal '
            'hai aur koi alert nahi.'),
            suggestions=['defaulters kaun hain?'])
    text = ctx.t('Things that need attention:', 'In cheezon par tawajjuh dein:')
    text += '\n' + '\n'.join('%d. %s' % (i, line)
                             for i, line in enumerate(lines, 1))
    return _reply('attention', text, links=links,
                  suggestions=['defaulters kaun hain?',
                               'aaj kis kis ne fees di?'])


def h_howto(ctx, intent):
    guide = intent['guide']
    steps = guide['steps_ur'] if ctx.lang == 'ur' else guide['steps_en']
    title = guide['title_ur'] if ctx.lang == 'ur' else guide['title_en']
    text = title + ':\n' + '\n'.join('%d. %s' % (i, s)
                                     for i, s in enumerate(steps, 1))
    return _reply(intent['id'], text,
                  links=_links(_link(guide['link_label'], guide['endpoint'])))


HANDLERS = {
    'help': h_help,
    'today_summary': h_today_summary,
    'students_count': h_students_count,
    'teachers_count': h_teachers_count,
    'class_strength': h_class_strength,
    'attendance': h_attendance,
    'fees_collected': h_fees_collected,
    'fees_due': h_fees_due,
    'expenses': h_expenses,
    'profit': h_profit,
    'salary': h_salary,
    'student_info': h_student_info,
    'attention': h_attention,
    'birthdays': h_birthdays,
    'low_attendance': h_low_attendance,
    'class_fees': h_class_fees,
    'compare': h_compare,
    'new_admissions': h_new_admissions,
    'fees_payments': h_fees_payments,
    'teacher_info': h_teacher_info,
}

"""Efficient, indexed aggregations for the executive dashboard.

Every widget runs as a small aggregate query (COUNT / SUM / GROUP BY) so the
home page stays a single fast request.  ``build_context`` isolates each widget
behind its own try/except: a failing widget degrades to an "unavailable" state
instead of taking the whole dashboard down.
"""
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.database import db
from app.models import (AttendanceModel, ClassModel, Expense, FeeRecordModel,
                        FeeTransaction, SchoolSettings, StaffPayroll,
                        StudentEnrollment, StudentModel, STUDENT_STATUS_LABELS,
                        SubjectModel, TeacherModel, TestModel)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------- #

def _academic_session_start(today=None):
    """April-boundary academic year start (mirrors app.services.id_documents)."""
    today = today or date.today()
    year = today.year if today.month >= 4 else today.year - 1
    return date(year, 4, 1)


def current_session_label():
    school = SchoolSettings.query.first()
    label = (getattr(school, 'academic_session', '') or '').strip()
    if label:
        return label
    from app.services.id_documents import academic_session
    return academic_session()


def _session_window_start(label, today=None):
    """Best-effort session start from the label (e.g. '2026-2027'); April fallback."""
    today = today or date.today()
    match = re.search(r'(20\d{2})', label or '')
    if match:
        year = int(match.group(1))
        if year <= today.year and date(year, 4, 1) <= today:
            return date(year, 4, 1)
    return _academic_session_start(today)


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #

def active_counts():
    return {
        'students': StudentModel.query.filter_by(is_active=True).count(),
        'teachers': TeacherModel.query.filter_by(is_active=True).count(),
        'classes': ClassModel.query.count(),
        'subjects': SubjectModel.query.count(),
    }


def today_attendance():
    """One GROUP BY gives both student and staff status counts for today."""
    today = date.today()
    rows = (db.session.query(AttendanceModel.target_type, AttendanceModel.status,
                             func.count(AttendanceModel.id))
            .filter(AttendanceModel.date == today)
            .group_by(AttendanceModel.target_type, AttendanceModel.status)
            .all())
    expected = {'student': StudentModel.query.filter_by(is_active=True).count(),
                'teacher': TeacherModel.query.filter_by(is_active=True).count()}

    result = {}
    for target in ('student', 'teacher'):
        counts = {'Present': 0, 'Late': 0, 'Leave': 0, 'Absent': 0}
        for row_target, status, number in rows:
            if row_target == target and status in counts:
                counts[status] = int(number)
        marked = sum(counts.values())
        result[target] = {
            'counts': counts,
            'marked': marked,
            'expected': expected[target],
            'not_marked': max(0, expected[target] - marked),
            'pct': round(counts['Present'] * 100.0 / marked, 1) if marked else None,
            'segments': ({key: round(value * 100.0 / marked, 2)
                          for key, value in counts.items()} if marked else {}),
        }
    return result


def fee_overview():
    """Bill-month basis: billed vs collected, balance, advance, settlement %."""
    from app.services.fee_ledger import current_month
    month = current_month()
    # NOTE: scalar two-argument max() is SQLite syntax (this app is SQLite-only).
    row = (db.session.query(
                func.coalesce(func.sum(FeeRecordModel.amount_due), 0.0),
                func.coalesce(func.sum(FeeRecordModel.amount_paid), 0.0),
                func.coalesce(func.sum(func.max(
                    FeeRecordModel.amount_due - FeeRecordModel.amount_paid, 0)), 0.0),
                func.coalesce(func.sum(func.max(
                    FeeRecordModel.amount_paid - FeeRecordModel.amount_due, 0)), 0.0),
           )
           .filter(FeeRecordModel.month_year == month)
           .one())
    billed, collected, balance, advance = (float(value or 0) for value in row)
    settled = billed - balance
    return {
        'month': month,
        'billed': round(billed, 2),
        'collected': round(collected, 2),
        'balance': round(balance, 2),
        'advance': round(advance, 2),
        'settled': round(settled, 2),
        'pct': round(settled * 100.0 / billed, 1) if billed else None,
    }


def expense_overview():
    today = date.today()
    start = today.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)

    def total_between(start_day, end_day):
        value = (db.session.query(func.coalesce(func.sum(Expense.amount), 0.0))
                 .filter(Expense.date >= start_day, Expense.date <= end_day)
                 .scalar())
        return round(float(value or 0), 2)

    current_total = total_between(start, next_month - timedelta(days=1))
    prev_total = total_between(prev_start, prev_end)
    return {
        'month_total': current_total,
        'prev_total': prev_total,
        'delta_pct': (round((current_total - prev_total) * 100.0 / prev_total, 1)
                      if prev_total else None),
    }


def account_book():
    """Month + session net results and a 6-month series (3 grouped queries)."""
    from app.services.financial_summary import short_label
    from app.services.payroll_service import recent_month_keys

    today = date.today()
    session_start = _academic_session_start(today)
    session_key = session_start.strftime('%Y-%m')
    current_key = '%04d-%02d' % (today.year, today.month)
    months6 = recent_month_keys(current_key, 6)

    first_key = months6[0]
    series_start = min(session_start,
                       date(int(first_key[:4]), int(first_key[5:7]), 1))
    series_start_dt = datetime.combine(series_start, datetime.min.time())

    revenue_rows = (db.session.query(
            func.strftime('%Y-%m', FeeTransaction.created_at),
            func.coalesce(func.sum(FeeTransaction.amount), 0.0))
        .filter(FeeTransaction.txn_type == 'payment',
                FeeTransaction.is_void.is_(False),
                FeeTransaction.created_at >= series_start_dt)
        .group_by(func.strftime('%Y-%m', FeeTransaction.created_at)).all())
    revenue_by_month = {key: round(float(value or 0), 2)
                        for key, value in revenue_rows}

    expense_rows = (db.session.query(
            func.strftime('%Y-%m', Expense.date),
            func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.date >= series_start)
        .group_by(func.strftime('%Y-%m', Expense.date)).all())
    expense_by_month = {key: round(float(value or 0), 2)
                        for key, value in expense_rows}

    payroll_rows = (db.session.query(
            StaffPayroll.month_year,
            func.coalesce(func.sum(StaffPayroll.net_salary), 0.0))
        .filter(StaffPayroll.month_year >= series_start.strftime('%Y-%m'))
        .group_by(StaffPayroll.month_year).all())
    payroll_by_month = {key: round(float(value or 0), 2)
                        for key, value in payroll_rows}

    series = []
    for key in months6:
        revenue = revenue_by_month.get(key, 0.0)
        costs = round(expense_by_month.get(key, 0.0)
                      + payroll_by_month.get(key, 0.0), 2)
        series.append({'month': key, 'label': short_label(key),
                       'revenue': revenue, 'costs': costs,
                       'net': round(revenue - costs, 2)})

    session_revenue = sum(v for k, v in revenue_by_month.items() if k >= session_key)
    session_expenses = sum(v for k, v in expense_by_month.items() if k >= session_key)
    session_payroll = sum(v for k, v in payroll_by_month.items() if k >= session_key)
    return {
        'month_net': series[-1]['net'] if series else 0.0,
        'session_net': round(session_revenue - session_expenses - session_payroll, 2),
        'series': series,
        'session_label': current_session_label(),
        'current_key': current_key,
    }


def left_students(limit=5):
    """Students who left during the current session (label first, date fallback)."""
    label = current_session_label()
    window_start = _session_window_start(label)
    today = date.today()

    closed_rows = (db.session.query(StudentEnrollment.student_id,
                                    StudentEnrollment.end_date,
                                    StudentEnrollment.class_name)
                   .filter(StudentEnrollment.session_label == label,
                           StudentEnrollment.end_date.isnot(None))
                   .order_by(StudentEnrollment.end_date.desc()).all())
    closed_map = {}
    for student_id, end_date, class_name in closed_rows:
        closed_map.setdefault(student_id, {'end_date': end_date,
                                           'class_name': class_name})

    candidates = (StudentModel.query
                  .filter(StudentModel.is_active.is_(False),
                          StudentModel.status != 'enrolled')
                  .all())
    rows = []
    for student in candidates:
        info = closed_map.get(student.id)
        if info is None:
            if not (student.leaving_date
                    and window_start <= student.leaving_date <= today):
                continue
            info = {'end_date': student.leaving_date,
                    'class_name': (student.class_info.name
                                   if student.class_info else None)}
        rows.append({'student': student, 'end_date': info['end_date'],
                     'class_name': info['class_name'],
                     'status_label': STUDENT_STATUS_LABELS.get(student.status,
                                                               student.status)})
    rows.sort(key=lambda item: (item['end_date'] or date.min), reverse=True)

    counts = {'slc_issued': 0, 'graduated': 0, 'struck_off': 0}
    for row in rows:
        if row['student'].status in counts:
            counts[row['student'].status] += 1
    return {'counts': counts, 'total': len(rows), 'recent': rows[:limit],
            'session_label': label}


def birthdays():
    """Upcoming birthdays: today / next 7 days / rest of the month."""
    today = date.today()
    horizon = today + timedelta(days=7)
    month_codes = ['%02d' % today.month, '%02d' % (today.month % 12 + 1)]

    todays, soon, later = [], [], []

    def _occurrence(dob):
        try:
            occurrence = date(today.year, dob.month, dob.day)
        except ValueError:
            occurrence = date(today.year, dob.month, 28)  # Feb 29 fallback
        if occurrence < today:
            try:
                occurrence = occurrence.replace(year=occurrence.year + 1)
            except ValueError:
                occurrence = date(occurrence.year + 1, dob.month, 28)
        return occurrence

    def _classify(entry):
        if entry['date'] == today:
            todays.append(entry)
        elif entry['date'] <= horizon:
            soon.append(entry)
        elif entry['date'].month == today.month and entry['date'].year == today.year:
            later.append(entry)

    student_records = (StudentModel.query
                       .filter(StudentModel.is_active.is_(True),
                               StudentModel.date_of_birth.isnot(None),
                               func.strftime('%m', StudentModel.date_of_birth)
                               .in_(month_codes))
                       .limit(1000).all())
    for student in student_records:
        dob = student.date_of_birth
        occurrence = _occurrence(dob)
        _classify({
            'name': student.student_name or '',
            'kind': 'Student',
            'meta': student.class_info.name if student.class_info else '',
            'date': occurrence,
            'age': (occurrence.year - dob.year) if dob.year > 1900 else None,
        })

    teacher_records = (TeacherModel.query
                       .filter(TeacherModel.is_active.is_(True),
                               TeacherModel.date_of_birth.isnot(None),
                               func.strftime('%m', TeacherModel.date_of_birth)
                               .in_(month_codes))
                       .limit(1000).all())
    for teacher in teacher_records:
        dob = teacher.date_of_birth
        occurrence = _occurrence(dob)
        _classify({
            'name': teacher.teacher_name or '',
            'kind': 'Teacher',
            'meta': teacher.teacher_id_str or '',
            'date': occurrence,
            'age': (occurrence.year - dob.year) if dob.year > 1900 else None,
        })

    total_with_dob = (
        StudentModel.query.filter(StudentModel.is_active.is_(True),
                                  StudentModel.date_of_birth.isnot(None)).count()
        + TeacherModel.query.filter(TeacherModel.is_active.is_(True),
                                    TeacherModel.date_of_birth.isnot(None)).count())

    def sort_key(entry):
        return entry['date']

    todays.sort(key=sort_key)
    soon.sort(key=sort_key)
    later.sort(key=sort_key)
    return {'today': todays, 'soon': soon[:8], 'later': later[:8],
            'month_label': today.strftime('%B %Y'),
            'has_any': bool(todays or soon or later),
            'total_with_dob': total_with_dob}


def recent_activity():
    students = (StudentModel.query.filter_by(is_active=True)
                .order_by(StudentModel.id.desc()).limit(3).all())
    tests = TestModel.query.order_by(TestModel.id.desc()).limit(3).all()
    return {'students': students, 'tests': tests}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def _safe(worker, *args, **kwargs):
    try:
        return worker(*args, **kwargs)
    except Exception:  # pragma: no cover - defensive per-widget isolation
        logger.exception('dashboard: %s failed', getattr(worker, '__name__', worker))
        return None


def build_context(is_admin):
    """All dashboard data; financial widgets are computed for admins only."""
    context = {
        'is_admin': bool(is_admin),
        'counts': _safe(active_counts),
        'attendance': _safe(today_attendance),
        'birthdays': _safe(birthdays),
        'left_students': _safe(left_students),
        'recent': _safe(recent_activity),
    }
    if is_admin:
        context['fees'] = _safe(fee_overview)
        context['expenses'] = _safe(expense_overview)
        context['account_book'] = _safe(account_book)
        if context['account_book']:
            context['chart_payload'] = {'series': context['account_book']['series']}
    return context

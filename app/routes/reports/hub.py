"""Reports hub: filters, KPIs, charts and shared hub helpers."""

import calendar
from datetime import datetime, date
from flask import render_template, request, redirect, url_for
from flask_login import current_user
from sqlalchemy import case, func
from app.database import db
from app.models import (
    ClassModel,
    StudentModel,
    SchoolSettings,
    TeacherModel,
    AttendanceModel,
    FeeRecordModel,
    FeeTransaction,
    TermExam,
)
from app.routes import main

from app.routes.reports.core import _class_results_evaluation


# ==========================================
# REPORTS & ANALYTICS HUB
# ==========================================
@main.route('/reports')
def reports_root():
    return redirect(url_for('main.reports_hub'))


_HUB_TABS = ('analytics', 'finance', 'academic', 'operations')


_HUB_MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December')


def _hub_filters():
    """Parse the shared filter bar (month / year / class / tab) for the hub."""
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
    except (TypeError, ValueError):
        year = today.year
    if year < 2000 or year > 2100:
        year = today.year

    month_token = (request.args.get('month') or '').strip().lower()
    all_months = month_token == 'all'
    if all_months:
        month = today.month if year == today.year else 12
    else:
        try:
            month = int(month_token) if month_token else today.month
        except ValueError:
            month = today.month
        if month < 1 or month > 12:
            month = today.month

    if all_months:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        month_label = 'All of %d' % year
    else:
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        month_label = '%s %d' % (_HUB_MONTHS[month - 1], year)
    fee_month_label = '%s %d' % (_HUB_MONTHS[month - 1], year)

    class_id = request.args.get('class_id', type=int)
    classes = ClassModel.query.all()
    if class_id and not any(c.id == class_id for c in classes):
        class_id = None

    tab = (request.args.get('tab') or 'analytics').strip().lower()
    if tab not in _HUB_TABS:
        tab = 'analytics'
    if getattr(current_user, 'is_accountant', False):
        # Accountants only ever see the Finance tab.
        tab = 'finance'
    elif tab == 'finance' and not getattr(current_user, 'finance_access', False):
        tab = 'analytics'

    return {
        'year': year, 'month': month, 'all_months': all_months,
        'start_date': start_date, 'end_date': end_date,
        'month_label': month_label, 'fee_month_label': fee_month_label,
        'class_id': class_id, 'classes': classes, 'tab': tab,
    }


def _hub_kpis(filters, finance_access):
    """SQL-aggregated KPI values for the Analytics tab."""
    kpis = {
        'active_students': StudentModel.query.filter_by(is_active=True).count(),
        'active_staff': TeacherModel.query.filter_by(is_active=True).count(),
        'attendance_pct': None,
        'exam_pass_pct': None,
        'dues': None,
        'collected': None,
    }

    att_q = AttendanceModel.query.filter(
        AttendanceModel.target_type == 'student',
        AttendanceModel.date >= filters['start_date'],
        AttendanceModel.date <= filters['end_date'])
    if filters['class_id']:
        att_q = att_q.filter(AttendanceModel.class_id == filters['class_id'])
    att_total = att_q.count()
    from app.services.attendance_service import attended_statuses
    att_present = att_q.filter(AttendanceModel.status.in_(attended_statuses())).count()
    kpis['attendance_pct'] = round(att_present / att_total * 100, 1) if att_total else None

    if finance_access:
        fee_q = (db.session.query(
                    func.coalesce(func.sum(func.min(FeeRecordModel.amount_paid_paisa,
                                                   FeeRecordModel.amount_due_paisa)), 0.0),
                    func.coalesce(func.sum(func.max(FeeRecordModel.amount_due_paisa -
                                                   FeeRecordModel.amount_paid_paisa, 0.0)), 0.0))
                 .join(StudentModel, StudentModel.id == FeeRecordModel.student_id)
                 .filter(StudentModel.is_active.is_(True)))
        if filters['class_id']:
            fee_q = fee_q.filter(StudentModel.class_id == filters['class_id'])
        if not filters['all_months']:
            fee_q = fee_q.filter(FeeRecordModel.month_year == filters['fee_month_label'])
        collected, dues_open = fee_q.one()
        kpis['dues'] = float(dues_open or 0) / 100.0
        kpis['collected'] = float(collected or 0) / 100.0
    return kpis


def _hub_exam_pass(filters):
    class_ids = ([filters['class_id']] if filters['class_id']
                 else [c.id for c in filters['classes']])
    scored = 0
    passed = 0
    for cid in class_ids:
        _, class_tests, matrix_data, _ = _class_results_evaluation(cid)
        for row in matrix_data:
            if row['total_max'] > 0:
                scored += 1
                if row['is_pass']:
                    passed += 1
    return round(passed / scored * 100, 1) if scored else None


def _hub_attendance_chart(filters):
    from app.services.attendance_service import attended_statuses
    if filters['all_months']:
        expr = func.strftime('%m', AttendanceModel.date)
    else:
        expr = func.strftime('%d', AttendanceModel.date)
    q = (db.session.query(expr.label('bucket'),
                          func.count(AttendanceModel.id),
                          func.sum(case((AttendanceModel.status.in_(attended_statuses()), 1), else_=0)))
         .filter(AttendanceModel.target_type == 'student',
                 AttendanceModel.date >= filters['start_date'],
                 AttendanceModel.date <= filters['end_date']))
    if filters['class_id']:
        q = q.filter(AttendanceModel.class_id == filters['class_id'])
    rows = q.group_by('bucket').order_by('bucket').all()
    labels, values = [], []
    for bucket, total, present in rows:
        present = present or 0
        if filters['all_months']:
            try:
                labels.append(_HUB_MONTHS[int(bucket) - 1][:3])
            except (TypeError, ValueError, IndexError):
                labels.append(str(bucket))
        else:
            labels.append(str(int(bucket)))
        values.append(round(present / total * 100, 1) if total else 0)
    return {'labels': labels, 'values': values}


def _hub_academic_chart(filters):
    labels, values = [], []
    if filters['class_id']:
        _, class_tests, matrix_data, _ = _class_results_evaluation(filters['class_id'])
        subject_cols = {}
        for t in class_tests:
            subj = t.subject_info
            key = subj.id if subj else ('unknown', t.id)
            col = subject_cols.setdefault(key, {
                'label': subj.name if subj else 'Unknown', 'test_ids': set(), 'max': 0.0})
            col['test_ids'].add(t.id)
            col['max'] += float(t.total_marks or 0)
        marks_by_test = {t.id: float(t.total_marks or 0) for t in class_tests}
        for col in subject_cols.values():
            pcts = []
            for row in matrix_data:
                obtained = 0.0
                sat_max = 0.0
                seen = False
                for tid in col['test_ids']:
                    val = row['scores'].get(tid)
                    if val is not None:
                        obtained += val
                        sat_max += marks_by_test.get(tid, 0.0)
                        seen = True
                if seen and sat_max > 0:
                    pcts.append(obtained / sat_max * 100)
            labels.append(col['label'])
            values.append(round(sum(pcts) / len(pcts), 1) if pcts else 0)
    else:
        for c in filters['classes']:
            _, class_tests, matrix_data, _ = _class_results_evaluation(c.id)
            scored = [row['percentage'] for row in matrix_data if row['total_max'] > 0]
            labels.append(c.name)
            values.append(round(sum(scored) / len(scored), 1) if scored else 0)
    return {'labels': labels, 'values': values}


def _hub_fee_chart(filters):
    q = (db.session.query(
            ClassModel.name,
            func.coalesce(func.sum(func.min(FeeRecordModel.amount_paid_paisa,
                                           FeeRecordModel.amount_due_paisa)), 0.0),
            func.coalesce(func.sum(func.max(FeeRecordModel.amount_due_paisa -
                                           FeeRecordModel.amount_paid_paisa, 0.0)), 0.0))
         .join(StudentModel, StudentModel.class_id == ClassModel.id)
         .join(FeeRecordModel, FeeRecordModel.student_id == StudentModel.id)
         .filter(StudentModel.is_active.is_(True)))
    if not filters['all_months']:
        q = q.filter(FeeRecordModel.month_year == filters['fee_month_label'])
    if filters['class_id']:
        q = q.filter(ClassModel.id == filters['class_id'])
    rows = [(name, (paid or 0) / 100.0, (due or 0) / 100.0)
            for name, paid, due in
            q.group_by(ClassModel.id).order_by(ClassModel.id).all()]
    return {
        'labels': [r[0] for r in rows],
        'collected': [float(r[1] or 0) for r in rows],
        'outstanding': [float(r[2] or 0) for r in rows],
    }


@main.route('/reports/hub', methods=['GET'])
def reports_hub():
    # Back-compat: old module-switched hub URLs redirect to the closest tab.
    module = (request.args.get('module') or '').strip()
    if module:
        tab_for_module = {'overview': 'analytics', 'attendance': 'operations',
                          'students': 'operations', 'teachers': 'operations',
                          'results': 'academic', 'fees': 'finance'}
        args = request.args.to_dict()
        args.pop('module', None)
        args['tab'] = tab_for_module.get(module, 'analytics')
        return redirect(url_for('main.reports_hub', **args))

    filters = _hub_filters()
    is_admin = bool(getattr(current_user, 'is_admin', False))
    is_accountant = bool(getattr(current_user, 'is_accountant', False))
    finance_access = bool(getattr(current_user, 'finance_access', False))
    school = SchoolSettings.query.first()
    session_label = ((school.academic_session or '').strip()
                     if school and school.academic_session else 'N/A')

    kpis = _hub_kpis(filters, finance_access)
    kpis['exam_pass_pct'] = _hub_exam_pass(filters)

    charts = {
        'attendance': _hub_attendance_chart(filters),
        'academic': _hub_academic_chart(filters),
    }
    if finance_access:
        charts['fee'] = _hub_fee_chart(filters)

    hub_exams = TermExam.query.order_by(TermExam.id.desc()).limit(50).all()

    return render_template('reports_hub.html',
                           tab=filters['tab'],
                           year=filters['year'], month=filters['month'],
                           all_months=filters['all_months'],
                           month_label=filters['month_label'],
                           selected_class_id=filters['class_id'],
                           start_date_str=filters['start_date'].strftime('%Y-%m-%d'),
                           end_date_str=filters['end_date'].strftime('%Y-%m-%d'),
                           classes=filters['classes'],
                           months=_HUB_MONTHS,
                           session_label=session_label,
                           is_admin=is_admin,
                           is_accountant=is_accountant,
                           finance_access=finance_access,
                           term_exams=hub_exams,
                           kpis=kpis, charts=charts)


def _hub_period_suffix(filters):
    if filters['all_months']:
        return 'all_%d' % filters['year']
    return filters['fee_month_label'].replace(' ', '_')


def _hub_fee_months(filters):
    """Fee month labels ("September 2026") covered by the current filters."""
    if not filters['all_months']:
        return [filters['fee_month_label']]
    labels = {row[0] for row in
              db.session.query(FeeTransaction.month_year).distinct().all() if row[0]}
    wanted = []
    for label in labels:
        try:
            if datetime.strptime(label, '%B %Y').year == filters['year']:
                wanted.append(label)
        except ValueError:
            continue
    return sorted(wanted, key=lambda value: datetime.strptime(value, '%B %Y'))


def _fee_status(charged, paid):
    if charged <= 0 and paid <= 0:
        return 'Pending'
    if paid + 0.001 >= charged > 0:
        return 'Paid'
    if paid > 0:
        return 'Partial'
    return 'Pending'


def _hub_class_label(filters):
    for class_obj in filters['classes']:
        if class_obj.id == filters['class_id']:
            return class_obj.name
    return None


def _hub_money(value):
    return 'Rs. {:,.2f}'.format(float(value or 0))

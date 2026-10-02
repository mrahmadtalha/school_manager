import io
import calendar
import csv
import pandas as pd
from datetime import datetime, date, timedelta
from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash, 
    send_file, 
    Response,
    abort,
)
from flask_login import current_user
from sqlalchemy import case, func
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.database import db
from app.models import (
    ClassModel, SectionModel, SubjectModel, StudentModel,
    TestModel, StudentMarkModel, SchoolSettings,
    TeacherModel, AttendanceModel, FeeRecordModel, StudentRemark,
    FeeTransaction, StaffPayroll, TermExam
)
from app.routes import main


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
    att_present = att_q.filter(AttendanceModel.status == 'Present').count()
    kpis['attendance_pct'] = round(att_present / att_total * 100, 1) if att_total else None

    if finance_access:
        fee_q = (db.session.query(
                    func.coalesce(func.sum(func.min(FeeRecordModel.amount_paid,
                                                   FeeRecordModel.amount_due)), 0.0),
                    func.coalesce(func.sum(func.max(FeeRecordModel.amount_due -
                                                   FeeRecordModel.amount_paid, 0.0)), 0.0))
                 .join(StudentModel, StudentModel.id == FeeRecordModel.student_id)
                 .filter(StudentModel.is_active.is_(True)))
        if filters['class_id']:
            fee_q = fee_q.filter(StudentModel.class_id == filters['class_id'])
        if not filters['all_months']:
            fee_q = fee_q.filter(FeeRecordModel.month_year == filters['fee_month_label'])
        collected, dues_open = fee_q.one()
        kpis['dues'] = float(dues_open or 0)
        kpis['collected'] = float(collected or 0)
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
    if filters['all_months']:
        expr = func.strftime('%m', AttendanceModel.date)
    else:
        expr = func.strftime('%d', AttendanceModel.date)
    q = (db.session.query(expr.label('bucket'),
                          func.count(AttendanceModel.id),
                          func.sum(case((AttendanceModel.status == 'Present', 1), else_=0)))
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
        for col in subject_cols.values():
            pcts = []
            for row in matrix_data:
                obtained = 0.0
                seen = False
                for tid in col['test_ids']:
                    val = row['scores'].get(tid)
                    if val is not None:
                        obtained += val
                        seen = True
                if seen and col['max'] > 0:
                    pcts.append(obtained / col['max'] * 100)
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
            func.coalesce(func.sum(func.min(FeeRecordModel.amount_paid,
                                           FeeRecordModel.amount_due)), 0.0),
            func.coalesce(func.sum(func.max(FeeRecordModel.amount_due -
                                           FeeRecordModel.amount_paid, 0.0)), 0.0))
         .join(StudentModel, StudentModel.class_id == ClassModel.id)
         .join(FeeRecordModel, FeeRecordModel.student_id == StudentModel.id)
         .filter(StudentModel.is_active.is_(True)))
    if not filters['all_months']:
        q = q.filter(FeeRecordModel.month_year == filters['fee_month_label'])
    if filters['class_id']:
        q = q.filter(ClassModel.id == filters['class_id'])
    rows = q.group_by(ClassModel.id).order_by(ClassModel.id).all()
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



# ==========================================
# HUB UNIVERSAL EXPORT CENTER
# ==========================================

_HUB_EXPORT_FORMATS = ('pdf', 'xlsx', 'csv')


def _hub_export_guard(fmt):
    if fmt not in _HUB_EXPORT_FORMATS:
        abort(404)


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


def _collect_fee_export_rows(filters):
    """Per-student charged / paid / balance totals for the filter scope."""
    query = StudentModel.query.filter_by(is_active=True)
    if filters['class_id']:
        query = query.filter(StudentModel.class_id == filters['class_id'])
    students = query.order_by(StudentModel.roll_number).all()

    months = _hub_fee_months(filters)
    charged, paid = {}, {}
    if students and months:
        transactions = (FeeTransaction.query
                        .filter(FeeTransaction.student_id.in_([s.id for s in students]),
                                FeeTransaction.month_year.in_(months),
                                FeeTransaction.is_void.is_(False))
                        .all())
        for transaction in transactions:
            if transaction.txn_type == 'payment':
                paid[transaction.student_id] = (paid.get(transaction.student_id, 0.0)
                                                + (transaction.amount or 0.0))
            else:
                charged[transaction.student_id] = (charged.get(transaction.student_id, 0.0)
                                                   + (transaction.amount or 0.0))

    rows = []
    for student in students:
        due = round(charged.get(student.id, 0.0), 2)
        received = round(paid.get(student.id, 0.0), 2)
        rows.append({
            'student': student,
            'class_name': student.class_info.name if student.class_info else '',
            'charged': due,
            'paid': received,
            'balance': round(due - received, 2),
            'status': _fee_status(due, received),
        })
    return rows


def _defaulter_export_rows(filters):
    """Outstanding balances; canonical figures from the fee reminder service."""
    from app.services.fee_reminders import defaulter_rows

    if not filters['all_months']:
        return defaulter_rows(filters['fee_month_label'], class_id=filters['class_id'])
    rows = [row for row in _collect_fee_export_rows(filters) if row['balance'] > 0.004]
    rows.sort(key=lambda row: (row['student'].class_id or 0,
                               (row['student'].student_name or '').lower()))
    return rows


def _collection_export_rows(filters):
    buckets = {}
    for row in _collect_fee_export_rows(filters):
        key = row['student'].class_id
        bucket = buckets.setdefault(key, {
            'class_name': row['class_name'], 'students': 0,
            'charged': 0.0, 'paid': 0.0, 'outstanding': 0.0})
        bucket['students'] += 1
        bucket['charged'] = round(bucket['charged'] + row['charged'], 2)
        bucket['paid'] = round(bucket['paid'] + row['paid'], 2)
        bucket['outstanding'] = round(bucket['outstanding'] + max(row['balance'], 0.0), 2)
    rows = sorted(buckets.values(), key=lambda bucket: (bucket['class_name'] or '').lower())
    for bucket in rows:
        bucket['rate'] = (round(bucket['paid'] / bucket['charged'] * 100, 1)
                          if bucket['charged'] > 0 else 0.0)
    return rows


def _discount_export_rows(filters):
    query = (StudentModel.query
             .filter(StudentModel.is_active.is_(True),
                     StudentModel.discount_value.isnot(None),
                     StudentModel.discount_value > 0))
    if filters['class_id']:
        query = query.filter(StudentModel.class_id == filters['class_id'])
    rows = []
    for student in query.order_by(StudentModel.roll_number).all():
        base = float(student.class_fee or 0.0)
        value = float(student.discount_value or 0.0)
        discount_type = (student.discount_type or '').strip().lower()
        if discount_type == 'percentage':
            amount = round(base * value / 100.0, 2)
            label = '%g%%' % value
        else:
            amount = round(min(value, base) if base else value, 2)
            label = 'Rs. ' + '{:,.0f}'.format(value)
        rows.append({
            'student': student,
            'class_name': student.class_info.name if student.class_info else '',
            'base': base,
            'label': label,
            'amount': amount,
            'net': round(base - amount, 2) if base else float(student.monthly_fee or 0.0),
        })
    return rows


def _salary_register_rows(filters):
    if filters['all_months']:
        return (StaffPayroll.query
                .join(TeacherModel, StaffPayroll.teacher_id == TeacherModel.id)
                .filter(StaffPayroll.month_year.like('%04d-%%' % filters['year']))
                .order_by(StaffPayroll.month_year, TeacherModel.teacher_name)
                .all())
    month_key = '%04d-%02d' % (filters['year'], filters['month'])
    return (StaffPayroll.query
            .join(TeacherModel, StaffPayroll.teacher_id == TeacherModel.id)
            .filter(StaffPayroll.month_year == month_key)
            .order_by(TeacherModel.teacher_name)
            .all())


def _position_export_rows(class_id, test_type=''):
    _, class_tests, matrix_data, _ = _class_results_evaluation(class_id, test_type)
    rows = []
    for row in matrix_data:
        student = row['student']
        rows.append({
            'rank': row['rank'],
            'roll': student.roll_number if student.roll_number is not None else '—',
            'name': student.student_name or '',
            'obtained': row['total_obtained'],
            'max': row['total_max'],
            'pct': row['percentage'],
            'grade': row['overall_grade'],
            'status': row['status'],
        })
    return rows, len(class_tests)


def _hub_class_label(filters):
    for class_obj in filters['classes']:
        if class_obj.id == filters['class_id']:
            return class_obj.name
    return None


def _hub_money(value):
    return 'Rs. {:,.2f}'.format(float(value or 0))


def _hub_pdf_cell(value, kind):
    if value is None or value == '':
        return '—'
    if kind == 'money':
        return _hub_money(value)
    if kind == 'pct':
        return '{:g}%'.format(float(value))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _hub_simple_table_pdf(title, subtitle, headers, rows, root_path=None,
                          landscape_mode=False, col_align=None, col_weights=None,
                          cell_formats=None, footer_note=None, signature_block=False):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('HTitle', parent=styles['Heading1'], fontSize=15,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    meta_style = ParagraphStyle('HMeta', parent=styles['Normal'], fontSize=8.5,
                                alignment=1, textColor=colors.HexColor('#475569'),
                                spaceAfter=4)
    doc_style = ParagraphStyle('HDoc', parent=styles['Heading2'], fontSize=11.5,
                               alignment=1, textColor=colors.HexColor('#1f2a44'),
                               spaceBefore=4, spaceAfter=1)
    head_style = ParagraphStyle('HHead', parent=styles['Normal'], fontSize=7.5,
                                leading=9, alignment=1, textColor=colors.white)
    align_map = {'LEFT': 0, 'CENTER': 1, 'RIGHT': 2}
    cell_styles = []
    for index in range(len(headers)):
        align = 'LEFT'
        if col_align and index < len(col_align):
            align = col_align[index]
        cell_styles.append(ParagraphStyle(
            'HCell%d' % index, parent=styles['Normal'], fontSize=7.5, leading=9,
            alignment=align_map.get(align, 0)))

    story = [Paragraph(escape(str(school['name'])), title_style)]
    tail = ' | '.join([part for part in (school.get('address') or '',
                                         school.get('phone') or '') if part])
    if tail:
        story.append(Paragraph(escape(tail), meta_style))
    story.append(Paragraph(escape(title).upper(), doc_style))
    if subtitle:
        story.append(Paragraph(escape(subtitle), meta_style))
    story.append(Spacer(1, 7))

    body = [[Paragraph('<b>%s</b>' % escape(str(header)), head_style)
             for header in headers]]
    formats = cell_formats or [None] * len(headers)
    for row in rows:
        body.append([
            Paragraph(escape(_hub_pdf_cell(value,
                                           formats[index] if index < len(formats) else None)),
                      cell_styles[index])
            for index, value in enumerate(row)])
    if len(body) == 1:
        body.append([Paragraph('No rows for the current filters.', cell_styles[0])] +
                    [Paragraph('', cell_styles[0])] * (len(headers) - 1))

    page = landscape(letter) if landscape_mode else letter
    content_width = page[0] - 52.0
    weights = col_weights if (col_weights and len(col_weights) == len(headers)) \
        else [1.0] * len(headers)
    scale = content_width / float(sum(weights))
    col_widths = [weight * scale for weight in weights]

    table = Table(body, colWidths=col_widths, repeatRows=1)
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2a44')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]
    for row_index in range(1, len(body)):
        if row_index % 2 == 0:
            style_commands.append(('BACKGROUND', (0, row_index), (-1, row_index),
                                   colors.HexColor('#f4f7fb')))
    table.setStyle(TableStyle(style_commands))
    story.append(table)

    if footer_note:
        story.append(Spacer(1, 7))
        story.append(Paragraph(footer_note, ParagraphStyle(
            'HFooter', parent=styles['Normal'], fontSize=8.5, alignment=1,
            textColor=colors.HexColor('#2d3748'))))
    if signature_block:
        story.append(Spacer(1, 30))
        sign_table = Table(
            [['_________________________', '_________________________'],
             ['Class Teacher', 'Principal']],
            colWidths=[content_width / 2.0, content_width / 2.0])
        sign_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#475569')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(sign_table)
    story.append(Spacer(1, 9))
    story.append(Paragraph('Generated on %s' % datetime.now().strftime('%d %b %Y, %I:%M %p'),
                           ParagraphStyle('HGen', parent=styles['Normal'], fontSize=7.5,
                                          alignment=1, textColor=colors.HexColor('#94a3b8'))))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=page, rightMargin=26, leftMargin=26,
                            topMargin=24, bottomMargin=24)
    doc.build(story)
    output.seek(0)
    return output


def _hub_export_file(fmt, download_name, title, subtitle, headers, rows,
                     col_align=None, col_weights=None, cell_formats=None,
                     landscape_mode=False, footer_note=None, signature_block=False):
    _hub_export_guard(fmt)
    if fmt == 'csv':
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(['' if cell is None else cell for cell in row])
        return Response(buffer.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition':
                                 'attachment; filename=%s.csv' % download_name})
    if fmt == 'xlsx':
        frame = pd.DataFrame(rows, columns=headers)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            frame.to_excel(writer, index=False, sheet_name='Export')
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name='%s.xlsx' % download_name)
    from flask import current_app
    output = _hub_simple_table_pdf(title, subtitle, headers, rows,
                                   root_path=current_app.root_path,
                                   landscape_mode=landscape_mode,
                                   col_align=col_align, col_weights=col_weights,
                                   cell_formats=cell_formats, footer_note=footer_note,
                                   signature_block=signature_block)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name='%s.pdf' % download_name)


@main.route('/reports/exports/fee-ledger/<fmt>', methods=['GET'])
def hub_export_fee_ledger(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    rows = _collect_fee_export_rows(filters)
    headers = ['Roll No', 'Student', 'Class', 'Billed (Rs)', 'Paid (Rs)',
               'Balance (Rs)', 'Status']
    data = [[row['student'].roll_number, row['student'].student_name,
             row['class_name'], row['charged'], row['paid'], row['balance'],
             row['status']] for row in rows]
    total_charged = round(sum(row['charged'] for row in rows), 2)
    total_paid = round(sum(row['paid'] for row in rows), 2)
    class_label = _hub_class_label(filters)
    subtitle = '%s — %s' % (filters['month_label'],
                            ('Class %s' % class_label) if class_label else 'All classes')
    footer = ('Billed: <b>%s</b> &nbsp;&middot;&nbsp; Collected: <b>%s</b> '
              '&nbsp;&middot;&nbsp; Outstanding: <b>%s</b>'
              % (_hub_money(total_charged), _hub_money(total_paid),
                 _hub_money(round(total_charged - total_paid, 2))))
    return _hub_export_file(
        fmt, 'fee_ledger_%s' % _hub_period_suffix(filters),
        'Monthly Fee Ledger', subtitle, headers, data,
        col_align=['CENTER', 'LEFT', 'LEFT', 'RIGHT', 'RIGHT', 'RIGHT', 'CENTER'],
        col_weights=[1.7, 4.4, 3.0, 2.6, 2.4, 2.6, 2.5],
        cell_formats=[None, None, None, 'money', 'money', 'money', None],
        footer_note=footer)


@main.route('/reports/exports/defaulters/<fmt>', methods=['GET'])
def hub_export_defaulters(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    rows = _defaulter_export_rows(filters)
    headers = ['Roll No', 'Student', 'Father Name', 'Class', 'Guardian Phone',
               'Billed (Rs)', 'Paid (Rs)', 'Balance (Rs)']
    data = [[row['student'].roll_number, row['student'].student_name,
             row['student'].father_name,
             row['student'].class_info.name if row['student'].class_info else '',
             row['student'].guardian_phone or '',
             row['charged'], row['paid'], row['balance']] for row in rows]
    total_due = round(sum(row['balance'] for row in rows), 2)
    class_label = _hub_class_label(filters)
    subtitle = '%s — %s' % (filters['month_label'],
                            ('Class %s' % class_label) if class_label else 'All classes')
    footer = ('Defaulters: <b>%d</b> &nbsp;&middot;&nbsp; Total Outstanding: <b>%s</b>'
              % (len(rows), _hub_money(total_due)))
    return _hub_export_file(
        fmt, 'defaulters_%s' % _hub_period_suffix(filters),
        'Fee Defaulter Directory', subtitle, headers, data,
        col_align=['CENTER', 'LEFT', 'LEFT', 'LEFT', 'CENTER',
                   'RIGHT', 'RIGHT', 'RIGHT'],
        col_weights=[1.6, 3.8, 3.8, 2.6, 3.2, 2.3, 2.1, 2.3],
        cell_formats=[None, None, None, None, None, 'money', 'money', 'money'],
        footer_note=footer)


@main.route('/reports/exports/collections/<fmt>', methods=['GET'])
def hub_export_collections(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    rows = _collection_export_rows(filters)
    headers = ['Class', 'Active Students', 'Billed (Rs)', 'Collected (Rs)',
               'Outstanding (Rs)', 'Collection Rate']
    data = [[row['class_name'], row['students'], row['charged'], row['paid'],
             row['outstanding'], row['rate']] for row in rows]
    total_charged = round(sum(row['charged'] for row in rows), 2)
    total_paid = round(sum(row['paid'] for row in rows), 2)
    total_out = round(sum(row['outstanding'] for row in rows), 2)
    class_label = _hub_class_label(filters)
    subtitle = '%s — %s' % (filters['month_label'],
                            ('Class %s' % class_label) if class_label else 'All classes')
    footer = ('Billed: <b>%s</b> &nbsp;&middot;&nbsp; Collected: <b>%s</b> '
              '&nbsp;&middot;&nbsp; Outstanding: <b>%s</b>'
              % (_hub_money(total_charged), _hub_money(total_paid),
                 _hub_money(total_out)))
    return _hub_export_file(
        fmt, 'collection_summary_%s' % _hub_period_suffix(filters),
        'Fee Collection Summary', subtitle, headers, data,
        col_align=['LEFT', 'CENTER', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT'],
        col_weights=[4.0, 2.4, 3.0, 3.0, 3.0, 2.8],
        cell_formats=[None, None, 'money', 'money', 'money', 'pct'],
        footer_note=footer)


@main.route('/reports/exports/discounts/<fmt>', methods=['GET'])
def hub_export_discounts(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    rows = _discount_export_rows(filters)
    headers = ['Roll No', 'Student', 'Class', 'Base Fee (Rs)', 'Discount',
               'Discount Amount (Rs)', 'Net Monthly Fee (Rs)']
    data = [[row['student'].roll_number, row['student'].student_name,
             row['class_name'], row['base'], row['label'], row['amount'],
             row['net']] for row in rows]
    total_discount = round(sum(row['amount'] for row in rows), 2)
    class_label = _hub_class_label(filters)
    subtitle = '%s — %s' % (filters['month_label'],
                            ('Class %s' % class_label) if class_label else 'All classes')
    footer = ('Students on discount: <b>%d</b> &nbsp;&middot;&nbsp; '
              'Total monthly discount value: <b>%s</b>'
              % (len(rows), _hub_money(total_discount)))
    return _hub_export_file(
        fmt, 'discount_summary_%s' % _hub_period_suffix(filters),
        'Fee Discount Summary', subtitle, headers, data,
        col_align=['CENTER', 'LEFT', 'LEFT', 'RIGHT', 'CENTER', 'RIGHT', 'RIGHT'],
        col_weights=[1.7, 4.2, 3.0, 2.6, 2.2, 3.0, 3.0],
        cell_formats=[None, None, None, 'money', None, 'money', 'money'],
        footer_note=footer)


@main.route('/reports/exports/salary-register/<fmt>', methods=['GET'])
def hub_export_salary_register(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    records = _salary_register_rows(filters)

    def staff_id(record):
        teacher = record.teacher
        return getattr(teacher, 'teacher_id_str', None) or (teacher.id if teacher else '')

    def staff_name(record):
        return record.teacher.teacher_name if record.teacher else ''

    if filters['all_months']:
        headers = ['Month', 'Staff ID', 'Staff', 'Base (Rs)', 'Bonus (Rs)',
                   'Deductions (Rs)', 'Net (Rs)', 'Status']
        data = [[record.month_year, staff_id(record), staff_name(record),
                 record.base_salary or 0, record.bonus or 0,
                 record.deductions or 0, record.net_salary or 0,
                 record.payment_status or 'Pending'] for record in records]
        col_align = ['CENTER', 'CENTER', 'LEFT', 'RIGHT', 'RIGHT', 'RIGHT',
                     'RIGHT', 'CENTER']
        col_weights = [2.2, 2.0, 3.6, 2.4, 2.2, 2.6, 2.4, 2.2]
        cell_formats = [None, None, None, 'money', 'money', 'money', 'money', None]
        download = 'salary_register_%d' % filters['year']
    else:
        headers = ['Staff ID', 'Staff', 'Base (Rs)', 'Bonus (Rs)',
                   'Deductions (Rs)', 'Net (Rs)', 'Status', 'Paid On']
        data = [[staff_id(record), staff_name(record),
                 record.base_salary or 0, record.bonus or 0,
                 record.deductions or 0, record.net_salary or 0,
                 record.payment_status or 'Pending',
                 record.payment_date.strftime('%d %b %Y') if record.payment_date else '']
                for record in records]
        col_align = ['CENTER', 'LEFT', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT',
                     'CENTER', 'CENTER']
        col_weights = [2.0, 4.0, 2.6, 2.3, 2.7, 2.6, 2.3, 2.7]
        cell_formats = [None, None, 'money', 'money', 'money', 'money', None, None]
        download = 'salary_register_%04d_%02d' % (filters['year'], filters['month'])

    total_net = round(sum((record.net_salary or 0) for record in records), 2)
    paid_count = sum(1 for record in records
                     if (record.payment_status or '') == 'Paid')
    footer = ('Records: <b>%d</b> &nbsp;&middot;&nbsp; Paid: <b>%d</b> '
              '&nbsp;&middot;&nbsp; Total Net Payroll: <b>%s</b>'
              % (len(records), paid_count, _hub_money(total_net)))
    return _hub_export_file(
        fmt, download, 'Staff Salary Register', filters['month_label'],
        headers, data, col_align=col_align, col_weights=col_weights,
        cell_formats=cell_formats, footer_note=footer)


@main.route('/reports/exports/positions/<fmt>', methods=['GET'])
def hub_export_positions(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    if not filters['class_id']:
        flash('Select a class to export the position list.', 'warning')
        return redirect(url_for('main.reports_hub', tab='academic'))
    class_obj = ClassModel.query.get(filters['class_id'])
    if class_obj is None:
        abort(404)
    test_type = (request.args.get('test_type') or '').strip()
    rows, tests_count = _position_export_rows(filters['class_id'], test_type)
    headers = ['Position', 'Roll No', 'Student', 'Obtained', 'Max',
               'Percentage', 'Grade', 'Result']
    data = [[row['rank'], row['roll'], row['name'], row['obtained'], row['max'],
             row['pct'], row['grade'], row['status']] for row in rows]
    scored = [row for row in rows if row['max'] > 0]
    average = (round(sum(row['pct'] for row in scored) / len(scored), 1)
               if scored else 0.0)
    passed = sum(1 for row in rows if row['status'] == 'Pass')
    subtitle = 'Class %s · %d assessment(s)%s' % (
        class_obj.name, tests_count, (' · %s' % test_type) if test_type else '')
    footer = ('Students: <b>%d</b> &nbsp;&middot;&nbsp; Class Average: <b>%g%%</b> '
              '&nbsp;&middot;&nbsp; Passed: <b>%d</b>'
              % (len(rows), average, passed))
    safe_name = ''.join(ch if (ch.isalnum() or ch in ' -_') else '_'
                        for ch in (class_obj.name or 'class')).strip().replace(' ', '_')
    return _hub_export_file(
        fmt, 'position_list_%s' % safe_name, 'Merit / Position List', subtitle,
        headers, data,
        col_align=['CENTER', 'CENTER', 'LEFT', 'RIGHT', 'RIGHT', 'RIGHT',
                   'CENTER', 'CENTER'],
        col_weights=[2.2, 2.0, 4.6, 2.4, 1.8, 2.6, 1.8, 2.0],
        cell_formats=[None, None, None, None, None, 'pct', None, None],
        footer_note=footer)


def _broad_sheet_subject_cols(class_tests):
    subject_cols = []
    index = {}
    for test in class_tests:
        subject = test.subject_info
        key = ('subject', subject.id) if subject else ('unknown', test.id)
        if key not in index:
            col = {'label': subject.name if subject else 'Unknown',
                   'test_ids': set(), 'max': 0.0}
            index[key] = col
            subject_cols.append(col)
        index[key]['test_ids'].add(test.id)
        index[key]['max'] += float(test.total_marks or 0)
    return subject_cols


@main.route('/reports/exports/broad-sheet/<fmt>', methods=['GET'])
def hub_export_broad_sheet(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    if not filters['class_id']:
        flash('Select a class to export the broad sheet.', 'warning')
        return redirect(url_for('main.reports_hub', tab='academic'))
    class_obj = ClassModel.query.get(filters['class_id'])
    if class_obj is None:
        abort(404)
    test_type = (request.args.get('test_type') or '').strip()
    _, class_tests, matrix_data, _ = _class_results_evaluation(filters['class_id'],
                                                               test_type)
    subject_cols = _broad_sheet_subject_cols(class_tests)

    school = SchoolSettings.query.first()
    session_value = (school.academic_session or '').strip() if school else ''
    remarks_map = _load_result_remarks(filters['class_id'], test_type, session_value)

    headers = (['#', 'Roll', 'Student'] +
               [col['label'] for col in subject_cols] +
               ['Total', 'Max', '%', 'Grade', 'Pos.', 'Result', 'Remarks'])
    data = []
    for line_no, row in enumerate(matrix_data, 1):
        student = row['student']
        line = [line_no,
                student.roll_number if student.roll_number is not None else '—',
                student.student_name or '']
        for col in subject_cols:
            obtained = 0.0
            has_marks = False
            for test_id in col['test_ids']:
                value = row['scores'].get(test_id)
                if value is not None:
                    obtained += value
                    has_marks = True
            if not has_marks:
                line.append('')
            else:
                number = float(obtained)
                line.append(int(number) if number.is_integer() else round(number, 1))
        line += [row['total_obtained'], row['total_max'], row['percentage'],
                 row['overall_grade'], row['rank'], row['status'],
                 remarks_map.get(student.id, '') or '']
        data.append(line)

    scored = [row for row in matrix_data if row['total_max'] > 0]
    average = (round(sum(row['percentage'] for row in scored) / len(scored), 1)
               if scored else 0.0)
    passed = sum(1 for row in matrix_data if row['status'] == 'Pass')
    subtitle = 'Class %s · Session %s · %d assessment(s)%s' % (
        class_obj.name, session_value or '—', len(class_tests),
        (' · %s' % test_type) if test_type else '')
    footer = ('Students: <b>%d</b> &nbsp;&middot;&nbsp; Class Average: <b>%g%%</b> '
              '&nbsp;&middot;&nbsp; Passed: <b>%d</b>'
              % (len(matrix_data), average, passed))
    subject_weight = max(1.6, min(2.6, 16.0 / max(len(subject_cols), 1)))
    weights = [1.3, 1.7, 4.2]
    weights += [subject_weight] * len(subject_cols)
    weights += [2.2, 2.0, 1.8, 1.8, 1.6, 1.8, 5.5]
    aligns = ['CENTER', 'CENTER', 'LEFT']
    aligns += ['CENTER'] * len(subject_cols)
    aligns += ['CENTER', 'CENTER', 'CENTER', 'CENTER', 'CENTER', 'CENTER', 'LEFT']
    formats = [None, None, None]
    formats += [None] * len(subject_cols)
    formats += [None, None, 'pct', None, None, None, None]
    safe_name = ''.join(ch if (ch.isalnum() or ch in ' -_') else '_'
                        for ch in (class_obj.name or 'class')).strip().replace(' ', '_')
    return _hub_export_file(
        fmt, 'broad_sheet_%s' % safe_name, 'Class Broad Sheet', subtitle,
        headers, data, col_align=aligns, col_weights=weights,
        cell_formats=formats, landscape_mode=True, footer_note=footer,
        signature_block=True)


@main.route('/reports/exports/allocation-matrix/<fmt>', methods=['GET'])
def hub_export_allocation_matrix(fmt):
    _hub_export_guard(fmt)
    filters = _hub_filters()
    query = (SubjectModel.query
             .join(ClassModel, SubjectModel.class_id == ClassModel.id)
             .order_by(ClassModel.id, SubjectModel.name))
    if filters['class_id']:
        query = query.filter(SubjectModel.class_id == filters['class_id'])
    subjects = query.all()

    headers = ['Class', 'Subject', 'Assigned Teacher', 'Teacher ID', 'Status']
    data = []
    assigned = 0
    for subject in subjects:
        teacher = subject.teacher
        if teacher is not None:
            assigned += 1
        data.append([
            subject.class_info.name if subject.class_info else '',
            subject.name or '',
            teacher.teacher_name if teacher is not None else 'Unassigned',
            (getattr(teacher, 'teacher_id_str', '') or '') if teacher is not None else '',
            'Active' if getattr(subject, 'is_active', True) else 'Archived',
        ])

    class_label = _hub_class_label(filters)
    scope = ('Class %s' % class_label) if class_label else 'All classes'
    subtitle = '%s · %d subject(s)' % (scope, len(subjects))
    footer = ('Assigned: <b>%d / %d</b> &nbsp;&middot;&nbsp; Unassigned: <b>%d</b>'
              % (assigned, len(subjects), len(subjects) - assigned))
    download = 'subject_allocation'
    if class_label:
        safe_name = ''.join(ch if (ch.isalnum() or ch in ' -_') else '_'
                            for ch in class_label).strip().replace(' ', '_')
        download += '_%s' % safe_name
    return _hub_export_file(
        fmt, download, 'Subject-Teacher Allocation Matrix', subtitle,
        headers, data,
        col_align=['LEFT', 'LEFT', 'LEFT', 'CENTER', 'CENTER'],
        col_weights=[3.0, 4.2, 4.4, 2.2, 2.2],
        cell_formats=[None, None, None, None, None],
        footer_note=footer)


def _format_result_date(value):
    value = (value or '').strip()
    if not value:
        return ''
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(value, fmt).strftime('%d %b %Y')
        except ValueError:
            continue
    return value


def _class_results_evaluation(class_id, test_type=''):
    """Shared evaluation for the class-results page and the PDF exports.

    Returns (test_types, class_tests, matrix_data, marks_map). Each matrix row
    carries scores/grades per test, totals, percentage, overall grade,
    pass/fail status and a competition rank by total marks obtained.
    """
    from app.models.settings import calculate_grade

    all_tests = (TestModel.query.filter_by(class_id=class_id)
                 .order_by(TestModel.test_date).all())
    test_types = sorted(set(t.test_type for t in all_tests if t.test_type))
    class_tests = [t for t in all_tests if not test_type or t.test_type == test_type]

    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    test_ids = [t.id for t in class_tests]
    all_marks = (StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all()
                 if test_ids else [])
    marks_map = {(m.student_id, m.test_id): m for m in all_marks}

    matrix_data = []
    for s in students:
        student_row = {'student': s, 'scores': {}, 'grades': {}}
        total_obtained = 0.0
        total_max = 0.0

        for t in class_tests:
            m = marks_map.get((s.id, t.id))
            if m:
                student_row['scores'][t.id] = m.marks_obtained
                student_row['grades'][t.id] = m.grade
                total_obtained += m.marks_obtained
            else:
                student_row['scores'][t.id] = None
                student_row['grades'][t.id] = None
            total_max += t.total_marks

        overall_pct = (total_obtained / total_max * 100) if total_max > 0 else 0.0
        ov_grade = calculate_grade(overall_pct) if total_max > 0 else 'N/A'
        is_pass = bool(total_max > 0 and ov_grade != 'F')

        student_row['total_obtained'] = total_obtained
        student_row['total_max'] = total_max
        student_row['percentage'] = round(overall_pct, 1)
        student_row['overall_grade'] = ov_grade
        student_row['is_pass'] = is_pass
        student_row['status'] = 'Pass' if is_pass else ('Fail' if total_max > 0 else 'N/A')
        matrix_data.append(student_row)

    # Rank by total marks obtained; students on equal totals share the position.
    matrix_data.sort(key=lambda x: x['total_obtained'], reverse=True)
    rank = 0
    prev_total = None
    for i, row in enumerate(matrix_data, 1):
        if prev_total is None or row['total_obtained'] != prev_total:
            rank = i
            prev_total = row['total_obtained']
        row['rank'] = rank

    return test_types, class_tests, matrix_data, marks_map


def _class_results_summary(matrix_data, class_tests):
    scored = [r for r in matrix_data if r['total_max'] > 0]
    percentages = [r['percentage'] for r in scored]
    pass_count = sum(1 for r in scored if r['is_pass'])
    return {
        'total_students': len(matrix_data),
        'total_tests': len(class_tests),
        'class_avg': round(sum(percentages) / len(percentages), 1) if percentages else 0,
        'pass_rate': round((pass_count / len(scored)) * 100, 1) if scored else 0,
        'pass_count': pass_count,
        'top_scorer': matrix_data[0]['student'].student_name if matrix_data else '—',
        'top_pct': matrix_data[0]['percentage'] if matrix_data else 0,
    }


def _load_result_remarks(class_id, test_type, session_value):
    rows = StudentRemark.query.filter_by(class_id=class_id,
                                         test_type=(test_type or ''),
                                         session=(session_value or '')).all()
    return {r.student_id: r.remarks for r in rows}


@main.route('/reports/class-results', methods=['GET'])
def class_results_matrix():
    selected_class_id = request.args.get('class_id', type=int)
    selected_type     = (request.args.get('test_type') or '').strip()
    session_param     = (request.args.get('session') or '').strip()
    announce_param    = (request.args.get('announce_date') or '').strip()
    classes = ClassModel.query.all()

    if not selected_class_id and classes:
        return redirect(url_for('main.class_results_matrix', class_id=classes[0].id))

    # Header metadata — defaults come from the global configuration on the
    # Settings page; explicit query params override them for ad-hoc exports.
    school = SchoolSettings.query.first()
    global_session = (school.academic_session or '').strip() if school else ''
    global_announce = (school.result_announcement_date or '').strip() if school else ''
    session_value = session_param or global_session
    announce_value = announce_param or global_announce or date.today().isoformat()
    announce_display = _format_result_date(announce_value)

    test_types, class_tests, matrix_data, marks_map = [], [], [], {}
    summary = {}
    if selected_class_id:
        test_types, class_tests, matrix_data, marks_map = _class_results_evaluation(
            selected_class_id, selected_type)
        remarks_map = _load_result_remarks(selected_class_id, selected_type, session_value)
        for row in matrix_data:
            row['remarks'] = remarks_map.get(row['student'].id, '')
        if matrix_data:
            summary = _class_results_summary(matrix_data, class_tests)

    return render_template('class_results.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           selected_type=selected_type,
                           session_value=session_value,
                           announce_value=announce_value,
                           announce_display=announce_display,
                           test_types=test_types,
                           class_tests=class_tests,
                           matrix_data=matrix_data,
                           summary=summary)


@main.route('/reports/class-results/remarks', methods=['POST'])
def save_class_result_remarks():
    class_id = request.form.get('class_id', type=int)
    test_type = (request.form.get('test_type') or '').strip()
    session_value = (request.form.get('session') or '').strip()
    announce_date = (request.form.get('announce_date') or '').strip()

    params = {'class_id': class_id} if class_id else {}
    if test_type:
        params['test_type'] = test_type
    if session_value:
        params['session'] = session_value
    if announce_date:
        params['announce_date'] = announce_date

    if not class_id:
        flash('Please select a class first.', 'warning')
        return redirect(url_for('main.class_results_matrix', **params))

    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    for s in students:
        field = 'remark_%d' % s.id
        if field not in request.form:
            continue
        value = (request.form.get(field) or '').strip()
        existing = StudentRemark.query.filter_by(student_id=s.id, class_id=class_id,
                                                 test_type=test_type,
                                                 session=session_value).first()
        if value:
            if existing:
                existing.remarks = value
            else:
                db.session.add(StudentRemark(student_id=s.id, class_id=class_id,
                                             test_type=test_type,
                                             session=session_value, remarks=value))
        elif existing:
            db.session.delete(existing)

    db.session.commit()
    flash('Teacher remarks saved.', 'success')
    return redirect(url_for('main.class_results_matrix', **params))

@main.route('/reports/student/<int:student_id>/pdf')
def student_report_card_pdf(student_id):
    student = StudentModel.query.get_or_404(student_id)
    class_id_param = request.args.get('class_id', type=int)
    test_type = (request.args.get('test_type') or '').strip()
    session_value = (request.args.get('session') or '').strip()
    announce_value = (request.args.get('announce_date') or '').strip()
    if not session_value or not announce_value:
        school = SchoolSettings.query.first()
        if not session_value:
            session_value = (school.academic_session or '').strip() if school else ''
        if not announce_value:
            announce_value = (school.result_announcement_date or '').strip() if school else ''
    announce_value = announce_value or date.today().isoformat()

    marks = StudentMarkModel.query.filter_by(student_id=student.id).all()
    evaluation = None
    if class_id_param:
        _, class_tests, matrix_data, marks_map = _class_results_evaluation(class_id_param, test_type)
        row = next((r for r in matrix_data if r['student'].id == student.id), None)
        if row:
            remarks_map = _load_result_remarks(class_id_param, test_type, session_value)
            evaluation = {
                'session': session_value,
                'exam_type': test_type,
                'announce_display': _format_result_date(announce_value),
                'status': row['status'],
                'overall_grade': row['overall_grade'],
                'rank': row['rank'],
                'total_students': len(matrix_data),
                'percentage': row['percentage'],
                'total_obtained': row['total_obtained'],
                'total_max': row['total_max'],
                'remarks': remarks_map.get(student.id, ''),
            }
            test_ids = {t.id for t in class_tests}
            marks = [m for m in marks if m.test_id in test_ids]
    
    from flask import current_app
    import os
    
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = _build_student_report_story(student, marks, current_app.root_path, evaluation=evaluation)
    doc.build(story)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'report_card_{student.roll_number}_{student.student_name}.pdf'
    )

@main.route('/reports/class-results/pdf-all')
def export_all_report_cards_pdf():
    selected_class_id = request.args.get('class_id', type=int)
    test_type = (request.args.get('test_type') or '').strip()
    session_value = (request.args.get('session') or '').strip()
    announce_value = (request.args.get('announce_date') or '').strip()
    if not session_value or not announce_value:
        school = SchoolSettings.query.first()
        if not session_value:
            session_value = (school.academic_session or '').strip() if school else ''
        if not announce_value:
            announce_value = (school.result_announcement_date or '').strip() if school else ''
    announce_value = announce_value or date.today().isoformat()
    if not selected_class_id:
        flash('Please select a class first.', 'warning')
        return redirect(url_for('main.class_results_matrix'))

    class_obj = ClassModel.query.get_or_404(selected_class_id)
    students  = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()

    _, class_tests, matrix_data, marks_map = _class_results_evaluation(selected_class_id, test_type)
    remarks_map = _load_result_remarks(selected_class_id, test_type, session_value)
    rows_by_student = {row['student'].id: row for row in matrix_data}
    announce_display = _format_result_date(announce_value)

    from flask import current_app
    import os

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    for si, student in enumerate(students):
        row = rows_by_student.get(student.id)
        evaluation = None
        if row:
            evaluation = {
                'session': session_value,
                'exam_type': test_type,
                'announce_display': announce_display,
                'status': row['status'],
                'overall_grade': row['overall_grade'],
                'rank': row['rank'],
                'total_students': len(matrix_data),
                'percentage': row['percentage'],
                'total_obtained': row['total_obtained'],
                'total_max': row['total_max'],
                'remarks': remarks_map.get(student.id, ''),
            }
        marks = [marks_map[(student.id, t.id)] for t in class_tests
                 if (student.id, t.id) in marks_map]
        
        story.extend(_build_student_report_story(student, marks, current_app.root_path,
                                                 evaluation=evaluation))
        
        if si < len(students) - 1:
            story.append(PageBreak())

    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'all_report_cards_{class_obj.name}.pdf')


@main.route('/reports/class-results/pdf-class', methods=['GET'])
def export_class_tabulation_pdf():
    """Official consolidated class result sheet (single-page landscape matrix)."""
    selected_class_id = request.args.get('class_id', type=int)
    test_type = (request.args.get('test_type') or '').strip()
    session_value = (request.args.get('session') or '').strip()
    announce_value = (request.args.get('announce_date') or '').strip()
    if not session_value or not announce_value:
        school = SchoolSettings.query.first()
        if not session_value:
            session_value = (school.academic_session or '').strip() if school else ''
        if not announce_value:
            announce_value = (school.result_announcement_date or '').strip() if school else ''
    announce_value = announce_value or date.today().isoformat()
    if not selected_class_id:
        flash('Please select a class first.', 'warning')
        return redirect(url_for('main.class_results_matrix'))

    class_obj = ClassModel.query.get_or_404(selected_class_id)
    _, class_tests, matrix_data, _ = _class_results_evaluation(selected_class_id, test_type)
    summary = _class_results_summary(matrix_data, class_tests) if matrix_data else {}

    # Subject-wise columns: aggregate the filtered tests per subject.
    subject_cols = []
    index = {}
    for t in class_tests:
        subj = t.subject_info
        key = ('subject', subj.id) if subj else ('unknown', t.id)
        if key not in index:
            col = {'label': subj.name if subj else 'Unknown', 'test_ids': set(), 'max': 0.0}
            index[key] = col
            subject_cols.append(col)
        index[key]['test_ids'].add(t.id)
        index[key]['max'] += float(t.total_marks or 0)

    output = io.BytesIO()
    _build_class_tabulation_doc(output, class_obj, subject_cols, matrix_data, summary,
                                session_value, _format_result_date(announce_value), test_type)
    output.seek(0)
    safe_name = ''.join(ch if (ch.isalnum() or ch in ' -_') else '_'
                        for ch in (class_obj.name or 'class')).strip().replace(' ', '_')
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'class_result_{safe_name}.pdf')


def _build_class_tabulation_doc(output, class_obj, subject_cols, matrix_data, summary,
                                session_value, announce_display, test_type):
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from xml.sax.saxutils import escape
    from flask import current_app
    import os

    styles = getSampleStyleSheet()
    school = SchoolSettings.query.first()
    school_name = (school.school_name if school and school.school_name
                   else 'School Management System')
    school_tagline = school.tagline if school and school.tagline else ''

    doc = SimpleDocTemplate(output, pagesize=landscape(letter),
                            rightMargin=24, leftMargin=24, topMargin=22, bottomMargin=22,
                            title='Class Result Sheet - %s' % class_obj.name)
    story = []

    title_style = ParagraphStyle('CT', parent=styles['Heading1'], fontSize=16,
                                 textColor=colors.HexColor('#2b6cb0'), alignment=1, spaceAfter=1)
    tag_style = ParagraphStyle('CS', parent=styles['Normal'], fontSize=9,
                               textColor=colors.HexColor('#718096'), alignment=1)
    sub_style = ParagraphStyle('CSub', parent=styles['Normal'], fontSize=9.5,
                               textColor=colors.HexColor('#1a365d'), alignment=1, spaceBefore=5)
    cell_style = ParagraphStyle('CC', parent=styles['Normal'], fontSize=7, leading=8.5)
    head_style = ParagraphStyle('CH', parent=styles['Normal'], fontSize=7, leading=8.5,
                                textColor=colors.white, alignment=1)

    logo_path = os.path.join(current_app.root_path, 'static', 'logo.png')
    school_block = [Paragraph('<b>%s</b>' % escape(school_name), title_style)]
    if school_tagline:
        school_block.append(Paragraph(escape(school_tagline), tag_style))
    if os.path.exists(logo_path):
        header_table = Table([[Image(logo_path, width=54, height=54), school_block]],
                             colWidths=[66, doc.width - 66],
                             style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
        story.append(header_table)
    else:
        story.extend(school_block)

    story.append(Paragraph('CONSOLIDATED CLASS RESULT SHEET', ParagraphStyle(
        'CT2', parent=styles['Heading2'], fontSize=12,
        textColor=colors.HexColor('#2d3748'), alignment=1, spaceBefore=7)))
    filter_note = (' &middot; Assessment: %s' % escape(test_type)) if test_type else ''
    story.append(Paragraph(
        'Class %s &middot; Academic Session %s &middot; Result announced %s%s'
        % (escape(str(class_obj.name)), escape(session_value or '&mdash;'),
           escape(announce_display or ''), filter_note), sub_style))
    story.append(Spacer(1, 9))

    col_headers = ['#', 'Roll', 'Student']
    for col in subject_cols:
        col_headers.append(Paragraph('%s<br/>(%s)' % (escape(col['label']),
                                                      int(col['max'])), head_style))
    col_headers += [Paragraph('Total', head_style), Paragraph('%', head_style),
                    Paragraph('Pos.', head_style)]

    data = [col_headers]
    for i, row in enumerate(matrix_data, 1):
        stu = row['student']
        line = [str(i), str(stu.roll_number if stu.roll_number is not None else '—'),
                Paragraph(escape(stu.student_name or ''), cell_style)]
        for col in subject_cols:
            obtained = 0.0
            has_marks = False
            for tid in col['test_ids']:
                val = row['scores'].get(tid)
                if val is not None:
                    obtained += val
                    has_marks = True
            if not has_marks:
                line.append('—')
            else:
                obtained = int(obtained) if float(obtained).is_integer() else round(obtained, 1)
                line.append(str(obtained))
        total_ob = row['total_obtained']
        total_mx = row['total_max']
        total_ob_s = int(total_ob) if float(total_ob).is_integer() else round(total_ob, 1)
        total_mx_s = int(total_mx) if float(total_mx).is_integer() else round(total_mx, 1)
        line += ['%s / %s' % (total_ob_s, total_mx_s), '%s%%' % row['percentage'],
                 str(row['rank'])]
        data.append(line)

    name_w, total_w, pct_w, pos_w = 116, 56, 34, 26
    fixed = 20 + 34 + name_w + total_w + pct_w + pos_w
    remaining = max(doc.width - fixed, 40)
    subj_w = (remaining / len(subject_cols)) if subject_cols else 0
    widths = [20, 34, name_w] + [subj_w] * len(subject_cols) + [total_w, pct_w, pos_w]
    scale = doc.width / float(sum(widths))
    widths = [w * scale for w in widths]

    table = Table(data, colWidths=widths, repeatRows=1)
    tstyle = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2a44')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            tstyle.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor('#f2f6fc')))
    table.setStyle(TableStyle(tstyle))
    story.append(table)

    if summary:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            'Class Average: <b>%s%%</b> &nbsp;&middot;&nbsp; Passed: <b>%s / %s (%s%%)</b> '
            '&nbsp;&middot;&nbsp; Top Scorer: <b>%s</b> (%s%%)'
            % (summary.get('class_avg', 0), summary.get('pass_count', 0),
               summary.get('total_students', 0), summary.get('pass_rate', 0),
               escape(summary.get('top_scorer', '—') or '—'), summary.get('top_pct', 0)),
            ParagraphStyle('CF', parent=styles['Normal'], fontSize=9, alignment=1,
                           textColor=colors.HexColor('#2d3748'))))

    story.append(Spacer(1, 6))
    story.append(Paragraph('Generated on %s' % datetime.now().strftime('%d %b %Y, %I:%M %p'),
                           ParagraphStyle('CG', parent=styles['Normal'], fontSize=7.5,
                                          alignment=1, textColor=colors.HexColor('#94a3b8'))))
    doc.build(story)


def _build_student_report_story(student, marks, root_path, evaluation=None):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from app.models import SchoolSettings
    from xml.sax.saxutils import escape
    import os
    from itertools import groupby
    
    story = []
    styles = getSampleStyleSheet()
    
    school = SchoolSettings.query.first()
    school_name = school.school_name if school else 'School Management System'
    school_tagline = school.tagline if school and school.tagline else ''
    
    # 1. Header Table (Logo + School Info)
    logo_path = os.path.join(root_path, 'static', 'logo.png')
    
    title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#2b6cb0'), spaceAfter=2, alignment=1)
    tag_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#718096'), alignment=1)
    report_title_style = ParagraphStyle('RT', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2d3748'), alignment=1, spaceBefore=10)
    
    school_info = [
        Paragraph(f"<b>{school_name}</b>", title_style),
        Paragraph(school_tagline, tag_style),
        Paragraph("OFFICIAL STUDENT REPORT CARD", report_title_style)
    ]
    
    if os.path.exists(logo_path):
        img = Image(logo_path, width=70, height=70)
        header_table = Table([[img, school_info]], colWidths=[80, 400])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ]))
        story.append(header_table)
    else:
        for p in school_info:
            story.append(p)
            
    if evaluation:
        meta_bits = []
        if evaluation.get('session'):
            meta_bits.append('Academic Session: ' + escape(str(evaluation['session'])))
        if evaluation.get('exam_type'):
            meta_bits.append('Exam Type: ' + escape(str(evaluation['exam_type'])))
        if evaluation.get('announce_display'):
            meta_bits.append('Result Announcement Date: ' + escape(str(evaluation['announce_display'])))
        if meta_bits:
            meta_style = ParagraphStyle('MetaRow', parent=styles['Normal'], fontSize=10,
                                        textColor=colors.HexColor('#2d3748'),
                                        alignment=1, spaceBefore=6)
            story.append(Paragraph(' | '.join(meta_bits), meta_style))

    story.append(Spacer(1, 15))
    
    # 2. Student Details Box
    detail_style = ParagraphStyle('D', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#2d3748'))
    details_data = [
        [Paragraph("<b>Student Name:</b>", detail_style), Paragraph(student.student_name, detail_style),
         Paragraph("<b>Roll Number:</b>", detail_style), Paragraph(str(student.roll_number), detail_style)],
        [Paragraph("<b>Father's Name:</b>", detail_style), Paragraph(student.father_name, detail_style),
         Paragraph("<b>Class:</b>", detail_style), Paragraph(student.class_info.name if student.class_info else 'N/A', detail_style)]
    ]
    details_table = Table(details_data, colWidths=[90, 180, 90, 180])
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#edf2f7')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 20))
    
    # 3. Marks Table
    table_data = [['Subject', 'Type', 'Max Marks', 'Obtained', 'Percentage', 'Grade']]
    
    # Group marks by exam batch (test_title + date)
    sorted_marks = sorted(marks, key=lambda m: (m.test_info.test_date or date.min, m.test_info.test_title))
    
    total_ob = 0.0
    total_mx = 0.0
    
    table_style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2b6cb0')), # Blue header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'), # Subject left aligned
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    
    current_row = 1
    
    for (date_val, title), group_marks in groupby(sorted_marks, key=lambda m: (m.test_info.test_date, m.test_info.test_title)):
        date_str = date_val.strftime('%d %B %Y') if date_val else ''
        batch_header = f"{title}  ({date_str})"
        table_data.append([batch_header, '', '', '', '', ''])
        table_style_commands.extend([
            ('SPAN', (0, current_row), (-1, current_row)),
            ('BACKGROUND', (0, current_row), (-1, current_row), colors.HexColor('#edf2f7')),
            ('TEXTCOLOR', (0, current_row), (-1, current_row), colors.HexColor('#2d3748')),
            ('FONTNAME', (0, current_row), (-1, current_row), 'Helvetica-Bold'),
            ('ALIGN', (0, current_row), (-1, current_row), 'LEFT'),
            ('LEFTPADDING', (0, current_row), (-1, current_row), 10),
        ])
        current_row += 1
        
        for m in group_marks:
            t = m.test_info
            subj_name = t.subject_info.name if t.subject_info else 'N/A'
            table_data.append([
                str(subj_name),
                str(t.test_type),
                str(t.total_marks),
                str(m.marks_obtained),
                f"{m.percentage}%",
                str(m.grade)
            ])
            bg_color = colors.HexColor('#ffffff') if current_row % 2 == 0 else colors.HexColor('#fcfcfc')
            table_style_commands.append(('BACKGROUND', (0, current_row), (-1, current_row), bg_color))
            
            total_ob += m.marks_obtained
            total_mx += t.total_marks
            current_row += 1
            
    if len(table_data) == 1:
        table_data.append(['No marks entered yet', '', '', '', '', ''])
        table_style_commands.append(('SPAN', (0, 1), (-1, 1)))
        current_row += 1
    else:
        overall_pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        table_data.append(['TOTAL / OVERALL', '', f'{total_mx}', f'{total_ob}', f'{round(overall_pct, 1)}%', ''])
        table_style_commands.extend([
            ('SPAN', (0, current_row), (1, current_row)),
            ('BACKGROUND', (0, current_row), (-1, current_row), colors.HexColor('#2d3748')),
            ('TEXTCOLOR', (0, current_row), (-1, current_row), colors.whitesmoke),
            ('FONTNAME', (0, current_row), (-1, current_row), 'Helvetica-Bold'),
        ])
        
    t = Table(table_data, colWidths=[150, 70, 70, 70, 80, 60])
    t.setStyle(TableStyle(table_style_commands))
    story.append(t)
    
    if evaluation:
        eval_style = ParagraphStyle('EvalCell', parent=styles['Normal'], fontSize=10,
                                    textColor=colors.HexColor('#2d3748'))
        status = str(evaluation.get('status') or 'N/A')
        status_color = {'Pass': '#2f855a', 'Fail': '#c53030'}.get(status, '#4a5568')
        remarks_text = escape(str(evaluation.get('remarks') or '')) or '-'
        eval_data = [
            [Paragraph('<b>Result:</b> <font color="%s"><b>%s</b></font>' % (status_color, status), eval_style),
             Paragraph('<b>Overall Grade:</b> %s' % escape(str(evaluation.get('overall_grade') or 'N/A')), eval_style),
             Paragraph('<b>Class Rank:</b> %s of %s' % (evaluation.get('rank', '-'), evaluation.get('total_students', '-')), eval_style),
             Paragraph('<b>Overall:</b> %s/%s (%s%%)' % ('%g' % float(evaluation.get('total_obtained') or 0),
                                                          '%g' % float(evaluation.get('total_max') or 0),
                                                          evaluation.get('percentage', 0)), eval_style)],
            [Paragraph('<b>Teacher Remarks:</b> %s' % remarks_text, eval_style), '', '', ''],
        ]
        eval_table = Table(eval_data, colWidths=[120, 130, 130, 100])
        eval_table.setStyle(TableStyle([
            ('SPAN', (0, 1), (-1, 1)),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(Spacer(1, 12))
        story.append(eval_table)

    story.append(Spacer(1, 50))
    sig_style = ParagraphStyle('Sig', parent=styles['Normal'], alignment=1, textColor=colors.HexColor('#4a5568'))
    sig_table = Table([
        [Paragraph("_______________________<br/>Class Teacher", sig_style), 
         Paragraph("_______________________<br/>Principal", sig_style)]
    ], colWidths=[250, 250])
    story.append(sig_table)
    
    return story

@main.route('/reports/class-results/export/excel', methods=['GET'])
def export_class_results_excel():
    selected_class_id = request.args.get('class_id', type=int)
    if not selected_class_id:
        return redirect(url_for('main.class_results_matrix'))
        
    class_obj = ClassModel.query.get_or_404(selected_class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()
    class_tests = TestModel.query.filter_by(class_id=selected_class_id).all()
    
    test_ids = [t.id for t in class_tests]
    all_marks = StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all() if test_ids else []
    marks_map = {(m.student_id, m.test_id): m for m in all_marks}
    
    data = []
    for s in students:
        row = {'Roll No': s.roll_number, 'Student Name': s.student_name, 'Father Name': s.father_name}
        total_ob = 0.0
        total_mx = 0.0
        for t in class_tests:
            m = marks_map.get((s.id, t.id))
            score_str = f"{m.marks_obtained} ({m.grade})" if m else "-"
            subj_name = t.subject_info.name if t.subject_info else 'Unknown'
            col_name = f"{t.test_title} - {subj_name} ({t.test_type})"
            row[col_name] = score_str
            if m: total_ob += m.marks_obtained
            total_mx += t.total_marks
            
        pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        row['Total Obtained'] = f"{total_ob} / {total_mx}"
        row['Percentage'] = f"{round(pct, 1)}%"
        data.append(row)
        
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'Class {class_obj.name} Results')
    output.seek(0)
    
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f'class_results_{class_obj.name}.xlsx')

@main.route('/reports/class-results/export/csv', methods=['GET'])
def export_class_results_csv():
    selected_class_id = request.args.get('class_id', type=int)
    if not selected_class_id:
        return redirect(url_for('main.class_results_matrix'))
        
    class_obj = ClassModel.query.get_or_404(selected_class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()
    class_tests = TestModel.query.filter_by(class_id=selected_class_id).all()
    
    test_ids = [t.id for t in class_tests]
    all_marks = StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all() if test_ids else []
    marks_map = {(m.student_id, m.test_id): m for m in all_marks}
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    headers = ['Roll No', 'Student Name', 'Father Name'] 
    for t in class_tests:
        subj_name = t.subject_info.name if t.subject_info else 'Unknown'
        headers.append(f"{t.test_title} - {subj_name} ({t.test_type})")
    headers.extend(['Total Obtained', 'Percentage'])
    writer.writerow(headers)
    
    for s in students:
        row = [s.roll_number, s.student_name, s.father_name]
        total_ob = 0.0
        total_mx = 0.0
        for t in class_tests:
            m = marks_map.get((s.id, t.id))
            row.append(f"{m.marks_obtained} ({m.grade})" if m else "-")
            if m: total_ob += m.marks_obtained
            total_mx += t.total_marks
            
        pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        row.extend([f"{total_ob} / {total_mx}", f"{round(pct, 1)}%"])
        writer.writerow(row)
        
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=class_results_{class_obj.name}.csv"})

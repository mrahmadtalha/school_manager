"""Reports hub exports (fee ledger, defaulters, collections, discounts, salary, positions, broad sheet)."""

import io
import csv
import pandas as pd
from datetime import datetime
from flask import request, redirect, url_for, flash, send_file, Response, abort
from app.database import db
from app.models import (
    ClassModel,
    SubjectModel,
    StudentModel,
    SchoolSettings,
    TeacherModel,
    FeeTransaction,
    StaffPayroll,
)
from app.routes import main
from app.services.marks import ABSENT_LABEL

from app.routes.reports.core import _class_results_evaluation, _load_result_remarks
from app.routes.reports.hub import (
    _fee_status,
    _hub_class_label,
    _hub_fee_months,
    _hub_filters,
    _hub_money,
    _hub_period_suffix,
)


_HUB_EXPORT_FORMATS = ('pdf', 'xlsx', 'csv')


def _hub_export_guard(fmt):
    if fmt not in _HUB_EXPORT_FORMATS:
        abort(404)


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
            'rank': row['rank_label'],
            'roll': student.roll_number if student.roll_number is not None else '—',
            'name': student.student_name or '',
            'obtained': row['total_obtained'],
            'max': row['total_max'],
            'pct': row['percentage'],
            'grade': row['overall_grade'],
            'status': row['status'],
        })
    return rows, len(class_tests)


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
    class_obj = db.session.get(ClassModel, filters['class_id'])
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
    class_obj = db.session.get(ClassModel, filters['class_id'])
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
                line.append(ABSENT_LABEL
                            if col['test_ids'] and all(row['absent'].get(t) for t in col['test_ids'])
                            else '')
            else:
                number = float(obtained)
                line.append(int(number) if number.is_integer() else round(number, 1))
        line += [row['total_obtained'], row['total_max'], row['percentage'],
                 row['overall_grade'], row['rank_label'], row['status'],
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

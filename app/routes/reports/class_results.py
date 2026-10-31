"""Class result matrix, remarks, tabulation sheet and class result exports."""

import io
import csv
import pandas as pd
from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash, send_file, Response
from app.database import db
from app.models import (
    ClassModel,
    StudentModel,
    TestModel,
    StudentMarkModel,
    SchoolSettings,
    StudentRemark,
)
from app.routes import main
from app.services.marks import ABSENT_LABEL, mark_is_absent

from app.models.settings import get_grading_scale
from app.routes.reports.core import (
    _class_results_evaluation,
    _class_results_summary,
    _format_result_date,
    _load_result_remarks,
)


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
                           grading_scale=get_grading_scale(),
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
                line.append(ABSENT_LABEL
                            if col['test_ids'] and all(row['absent'].get(t) for t in col['test_ids'])
                            else '—')
            else:
                obtained = int(obtained) if float(obtained).is_integer() else round(obtained, 1)
                line.append(str(obtained))
        total_ob = row['total_obtained']
        total_mx = row['total_max']
        total_ob_s = int(total_ob) if float(total_ob).is_integer() else round(total_ob, 1)
        total_mx_s = int(total_mx) if float(total_mx).is_integer() else round(total_mx, 1)
        if row['all_absent']:
            line += ['—', '—', '—']
        else:
            line += ['%s / %s' % (total_ob_s, total_mx_s), '%s%%' % row['percentage'],
                     row['rank_label']]
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
            subj_name = t.subject_info.name if t.subject_info else 'Unknown'
            col_name = f"{t.test_title} - {subj_name} ({t.test_type})"
            if mark_is_absent(m):
                row[col_name] = ABSENT_LABEL      # left out of totals
                continue
            score_str = f"{m.marks_obtained} ({m.grade})" if m else "-"
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
            if mark_is_absent(m):
                row.append(ABSENT_LABEL)          # left out of totals
                continue
            row.append(f"{m.marks_obtained} ({m.grade})" if m else "-")
            if m: total_ob += m.marks_obtained
            total_mx += t.total_marks
            
        pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        row.extend([f"{total_ob} / {total_mx}", f"{round(pct, 1)}%"])
        writer.writerow(row)
        
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=class_results_{class_obj.name}.csv"})

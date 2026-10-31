"""Student report cards (single and bulk PDF)."""

import io
from datetime import date
from flask import request, redirect, url_for, flash, send_file
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, PageBreak
from app.models import ClassModel, StudentModel, StudentMarkModel, SchoolSettings
from app.routes import main
from app.services.marks import ABSENT_LABEL

from app.routes.reports.core import (
    _class_results_evaluation,
    _fit_report_on_one_page,
    _format_result_date,
    _load_result_remarks,
)


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
                'rank': row['rank_label'],
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
    story = [_fit_report_on_one_page(
        doc, _build_student_report_story(student, marks, current_app.root_path, evaluation=evaluation))]
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
    students  = (StudentModel.query.filter_by(is_active=True, class_id=selected_class_id)
                 .order_by(StudentModel.roll_number).all())

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
                'rank': row['rank_label'],
                'total_students': len(matrix_data),
                'percentage': row['percentage'],
                'total_obtained': row['total_obtained'],
                'total_max': row['total_max'],
                'remarks': remarks_map.get(student.id, ''),
            }
        marks = [marks_map[(student.id, t.id)] for t in class_tests
                 if (student.id, t.id) in marks_map]
        
        # Each student's card is fitted onto exactly one page (see helper above).
        story.append(_fit_report_on_one_page(
            doc, _build_student_report_story(student, marks, current_app.root_path,
                                             evaluation=evaluation)))

        if si < len(students) - 1:
            story.append(PageBreak())

    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'all_report_cards_{class_obj.name}.pdf')


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
    # Optional student photo: an extra column only when a picture exists.
    from app.services import photos as _photos
    photo_buffer = _photos.square_image_buffer(
        _photos.photo_path('student', getattr(student, 'photo_filename', None)))
    detail_widths = [90, 180, 90, 180]
    if photo_buffer:
        detail_widths = [85, 150, 85, 150, 70]
        details_data[0].append(Image(photo_buffer, width=56, height=56))
        details_data[1].append('')
    details_table = Table(details_data, colWidths=detail_widths)
    details_style = [
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#edf2f7')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]
    if photo_buffer:
        details_style += [('SPAN', (4, 0), (4, 1)), ('VALIGN', (4, 0), (4, 1), 'MIDDLE'),
                          ('ALIGN', (4, 0), (4, 1), 'CENTER')]
    details_table.setStyle(TableStyle(details_style))
    story.append(details_table)
    story.append(Spacer(1, 20))
    
    # 3. Marks Table
    table_data = [['Subject', 'Type', 'Max Marks', 'Obtained', 'Percentage', 'Grade']]
    
    # Group marks by exam batch (test_title + date)
    sorted_marks = sorted(marks, key=lambda m: (m.test_info.test_date or date.min, m.test_info.test_title))
    
    total_ob = 0.0
    total_mx = 0.0
    absent_papers = 0
    
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
            if m.is_absent:
                # Absent: shown as ABS and left out of the totals below.
                table_data.append([
                    str(subj_name), str(t.test_type), str(t.total_marks),
                    ABSENT_LABEL, '—', ABSENT_LABEL,
                ])
                absent_papers += 1
            else:
                table_data.append([
                    str(subj_name),
                    str(t.test_type),
                    str(t.total_marks),
                    str(m.marks_obtained),
                    f"{m.percentage}%",
                    str(m.grade)
                ])
                total_ob += m.marks_obtained
                total_mx += t.total_marks
            bg_color = colors.HexColor('#ffffff') if current_row % 2 == 0 else colors.HexColor('#fcfcfc')
            table_style_commands.append(('BACKGROUND', (0, current_row), (-1, current_row), bg_color))
            current_row += 1
            
    if len(table_data) == 1:
        table_data.append(['No marks entered yet', '', '', '', '', ''])
        table_style_commands.append(('SPAN', (0, 1), (-1, 1)))
        current_row += 1
    else:
        overall_pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        if total_mx > 0:
            table_data.append(['TOTAL / OVERALL', '', f'{total_mx}', f'{total_ob}', f'{round(overall_pct, 1)}%', ''])
        else:
            table_data.append(['TOTAL / OVERALL', '', '—', '—', '—', ABSENT_LABEL])
        table_style_commands.extend([
            ('SPAN', (0, current_row), (1, current_row)),
            ('BACKGROUND', (0, current_row), (-1, current_row), colors.HexColor('#2d3748')),
            ('TEXTCOLOR', (0, current_row), (-1, current_row), colors.whitesmoke),
            ('FONTNAME', (0, current_row), (-1, current_row), 'Helvetica-Bold'),
        ])
        
    t = Table(table_data, colWidths=[150, 70, 70, 70, 80, 60])
    t.setStyle(TableStyle(table_style_commands))
    story.append(t)
    if absent_papers:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            'ABS = absent. %d paper(s) marked absent are not included in the total, '
            'percentage, grade or class rank.' % absent_papers,
            ParagraphStyle('AbsNote', parent=styles['Normal'], fontSize=8,
                           textColor=colors.HexColor('#92400e'))))
    
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

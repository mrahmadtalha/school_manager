import io
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
    Response
)
from sqlalchemy import func
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.database import db
from app.models import (
    ClassModel, SectionModel, SubjectModel, StudentModel, 
    TestModel, StudentMarkModel, SchoolSettings,
    TeacherModel, AttendanceModel, FeeRecordModel
)
from app.routes import main


# ==========================================
# REPORTS & ANALYTICS HUB
# ==========================================
@main.route('/reports/hub', methods=['GET'])
def reports_hub():
    module = request.args.get('module', 'overview')
    filter_type = request.args.get('filter_type', 'monthly')

    today = date.today()
    if filter_type == 'daily':
        start_date = end_date = today
    elif filter_type == 'weekly':
        start_date, end_date = today - timedelta(days=7), today
    elif filter_type == 'monthly':
        start_date, end_date = date(today.year, today.month, 1), today
    else:
        start_date_str = request.args.get('start_date', date(today.year, today.month, 1).strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    selected_class_id = request.args.get('class_id', type=int)
    classes = ClassModel.query.all()
    if not selected_class_id and classes:
        selected_class_id = classes[0].id

    report_data = {}
    if module == 'overview':
        active_students = StudentModel.query.filter_by(is_active=True).all()
        active_teachers = TeacherModel.query.filter_by(is_active=True).all()
        total_students = len(active_students)
        total_teachers = len(active_teachers)
        total_fee_collection = sum((student.monthly_fee or 0) for student in active_students)
        total_fee_records = FeeRecordModel.query.with_entities(func.coalesce(func.sum(FeeRecordModel.amount_paid), 0)).scalar() or 0

        attendance_records = AttendanceModel.query.filter(
            AttendanceModel.target_type == 'student',
            AttendanceModel.date >= start_date,
            AttendanceModel.date <= end_date
        ).all()
        attendance_total = len(attendance_records)
        attendance_present = sum(1 for record in attendance_records if record.status == 'Present')
        attendance_pct = round((attendance_present / attendance_total) * 100, 1) if attendance_total else 0

        mark_rows = StudentMarkModel.query.all()
        pass_count = sum(1 for mark in mark_rows if (mark.percentage or 0) >= 40)
        pass_rate = round((pass_count / len(mark_rows)) * 100, 1) if mark_rows else 0

        class_summary = []
        for class_obj in classes:
            class_students = StudentModel.query.filter_by(is_active=True, class_id=class_obj.id).count()
            class_summary.append({
                'name': class_obj.name,
                'students': class_students,
                'attendance': round((sum(1 for record in attendance_records if record.class_id == class_obj.id and record.status == 'Present') /
                    max(1, sum(1 for record in attendance_records if record.class_id == class_obj.id))) * 100, 1) if any(record.class_id == class_obj.id for record in attendance_records) else 0,
            })

        overview_students = []
        for student in active_students[:8]:
            latest_mark = StudentMarkModel.query.join(TestModel).filter(
                StudentMarkModel.student_id == student.id,
                TestModel.class_id == student.class_id
            ).order_by(TestModel.test_date.desc()).first()
            overview_students.append({
                'student': student,
                'latest_mark': latest_mark,
                'fee_status': 'Paid' if (student.monthly_fee or 0) <= 0 else 'Due' if (student.monthly_fee or 0) > 0 else 'Pending'
            })

        report_data = {
            'total_students': total_students,
            'total_teachers': total_teachers,
            'total_fee_collection': total_fee_collection,
            'fee_paid': total_fee_records,
            'attendance_pct': attendance_pct,
            'pass_rate': pass_rate,
            'class_summary': class_summary,
            'overview_students': overview_students,
            'school_name': SchoolSettings.query.first().school_name if SchoolSettings.query.first() else 'School Manager',
        }
    elif module == 'attendance':
        report_data['students'] = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all() if selected_class_id else []
        report_data['teachers'] = TeacherModel.query.filter_by(is_active=True).all()
    elif module == 'students':
        report_data['students'] = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all() if selected_class_id else StudentModel.query.filter_by(is_active=True).all()
    elif module == 'teachers':
        report_data['teachers'] = TeacherModel.query.filter_by(is_active=True).all()
    elif module == 'results':
        report_data['class_tests'] = TestModel.query.filter_by(class_id=selected_class_id).all() if selected_class_id else []
        report_data['students'] = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all() if selected_class_id else []
    elif module == 'fees':
        report_data['fees'] = FeeRecordModel.query.join(StudentModel).filter(StudentModel.class_id == selected_class_id).all() if selected_class_id else []

    return render_template('attendance_reports.html',
                           module=module,
                           filter_type=filter_type,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           classes=classes,
                           selected_class_id=selected_class_id,
                           report_data=report_data)

@main.route('/reports/class-results', methods=['GET'])
def class_results_matrix():
    selected_class_id = request.args.get('class_id', type=int)
    selected_type     = request.args.get('test_type', '')
    classes = ClassModel.query.all()

    if not selected_class_id and classes:
        return redirect(url_for('main.class_results_matrix', class_id=classes[0].id))

    class_tests = []
    matrix_data = []
    summary     = {}
    test_types  = []

    if selected_class_id:
        all_tests  = TestModel.query.filter_by(class_id=selected_class_id).order_by(TestModel.test_date).all()
        test_types = sorted(set(t.test_type for t in all_tests if t.test_type))
        class_tests = [t for t in all_tests if not selected_type or t.test_type == selected_type]

        students  = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()
        test_ids  = [t.id for t in class_tests]
        all_marks = StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all() if test_ids else []
        marks_map = {(m.student_id, m.test_id): m for m in all_marks}

        for s in students:
            student_row = {'student': s, 'scores': {}, 'grades': {}}
            total_obtained = 0.0
            total_max      = 0.0

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
            from app.models.settings import calculate_grade
            ov_grade = calculate_grade(overall_pct) if total_max > 0 else 'N/A'

            student_row['total_obtained'] = total_obtained
            student_row['total_max']      = total_max
            student_row['percentage']     = round(overall_pct, 1)
            student_row['overall_grade']  = ov_grade
            matrix_data.append(student_row)

        # Sort by percentage descending → assign rank
        matrix_data.sort(key=lambda x: x['percentage'], reverse=True)
        for i, row in enumerate(matrix_data, 1):
            row['rank'] = i

        # Summary stats
        if matrix_data:
            percentages  = [r['percentage'] for r in matrix_data if r['total_max'] > 0]
            pass_count   = sum(1 for p in percentages if p >= 40)
            summary = {
                'total_students': len(matrix_data),
                'total_tests':    len(class_tests),
                'class_avg':      round(sum(percentages) / len(percentages), 1) if percentages else 0,
                'pass_rate':      round((pass_count / len(percentages)) * 100, 1) if percentages else 0,
                'top_scorer':     matrix_data[0]['student'].student_name if matrix_data else '—',
                'top_pct':        matrix_data[0]['percentage'] if matrix_data else 0,
            }

    return render_template('class_results.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           selected_type=selected_type,
                           test_types=test_types,
                           class_tests=class_tests,
                           matrix_data=matrix_data,
                           summary=summary)

@main.route('/reports/student/<int:student_id>/pdf')
def student_report_card_pdf(student_id):
    student = StudentModel.query.get_or_404(student_id)
    marks = StudentMarkModel.query.filter_by(student_id=student.id).all()
    
    from flask import current_app
    import os
    
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = _build_student_report_story(student, marks, current_app.root_path)
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
    if not selected_class_id:
        flash('Please select a class first.', 'warning')
        return redirect(url_for('main.class_results_matrix'))

    class_obj = ClassModel.query.get_or_404(selected_class_id)
    students  = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()

    from flask import current_app
    import os

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    for si, student in enumerate(students):
        marks = StudentMarkModel.query.filter_by(student_id=student.id).all()
        # Filter marks to only include those for the selected class (in case student changed class)
        marks = [m for m in marks if m.test_info.class_id == selected_class_id]
        
        student_story = _build_student_report_story(student, marks, current_app.root_path)
        story.extend(student_story)
        
        if si < len(students) - 1:
            story.append(PageBreak())

    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'all_report_cards_{class_obj.name}.pdf')


def _build_student_report_story(student, marks, root_path):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from app.models import SchoolSettings
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

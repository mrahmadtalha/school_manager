import io
import csv
import pandas as pd
from datetime import datetime
from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash, 
    send_file, 
    Response
)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.database import db
from app.models import (
    StudentModel,
    ClassModel,
    SectionModel,
    AttendanceModel,
    TestModel,
    StudentMarkModel,
    FeeRecordModel,
    MessageQueue,
)
from app.routes import main


def delete_student_permanently(student):
    StudentMarkModel.query.filter_by(student_id=student.id).delete(synchronize_session=False)
    FeeRecordModel.query.filter_by(student_id=student.id).delete(synchronize_session=False)
    AttendanceModel.query.filter_by(target_type='student', target_id=student.id).delete(synchronize_session=False)

    for message in MessageQueue.query.filter_by(student_id=student.id).all():
        for delivery_log in message.delivery_logs:
            db.session.delete(delivery_log)
        db.session.delete(message)

    db.session.delete(student)
    db.session.commit()

# STUDENT MANAGEMENT & EXPORTS
# ==========================================
@main.route('/students')
@main.route('/students/')
def students_list():
    class_id = request.args.get('class_id', type=int)
    section_id = request.args.get('section_id', type=int)
    search = request.args.get('search', '').strip()

    query = StudentModel.query.filter_by(is_active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)
    if section_id:
        query = query.filter_by(section_id=section_id)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                StudentModel.student_name.ilike(like),
                StudentModel.roll_number.ilike(like),
                StudentModel.father_name.ilike(like),
                StudentModel.guardian_phone.ilike(like)
            )
        )
    students = query.order_by(StudentModel.student_name).all()
    classes = ClassModel.query.all()
    sections = SectionModel.query.filter_by(class_id=class_id).all() if class_id else []
    sections_by_class = {
        str(class_obj.id): [
            {'id': section.id, 'name': section.name}
            for section in sorted(class_obj.sections, key=lambda s: s.name)
        ]
        for class_obj in classes
    }
    return render_template('students.html', students=students, classes=classes,
                           sections=sections, sections_by_class=sections_by_class,
                           selected_class=class_id, selected_section=section_id, search=search)

@main.route('/students/add', methods=['POST'])
def add_student():
    try:
        roll_number = request.form.get('roll_number').strip()
        student_name = request.form.get('student_name')
        father_name = request.form.get('father_name')
        guardian_phone = request.form.get('guardian_phone')
        address = request.form.get('address')
        class_id = request.form.get('class_id')
        section_id = request.form.get('section_id')
        
        fee_input = request.form.get('monthly_fee')
        monthly_fee = float(fee_input) if fee_input and fee_input.strip() else None

        existing_student = StudentModel.query.filter_by(roll_number=roll_number).first()
        if existing_student:
            flash(f'Error: Roll Number "{roll_number}" is already assigned to another student.', 'danger')
            return redirect(url_for('main.students_list'))

        new_student = StudentModel(
            roll_number=roll_number,
            student_name=student_name,
            father_name=father_name,
            guardian_phone=guardian_phone,
            address=address,
            monthly_fee=monthly_fee,
            class_id=int(class_id),
            section_id=int(section_id) if section_id else None
        )
        
        db.session.add(new_student)
        db.session.commit()
        flash('Student added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding student: {str(e)}', 'danger')

    return redirect(url_for('main.students_list'))

@main.route('/students/edit/<int:id>', methods=['POST'])
def edit_student(id):
    try:
        student = StudentModel.query.get_or_404(id)
        student.roll_number = request.form.get('roll_number').strip()
        student.student_name = request.form.get('student_name')
        student.father_name = request.form.get('father_name')
        student.guardian_phone = request.form.get('guardian_phone')
        student.address = request.form.get('address')
        student.class_id = int(request.form.get('class_id'))
        
        fee_input = request.form.get('monthly_fee')
        student.monthly_fee = float(fee_input) if fee_input and fee_input.strip() else None
        
        sec_id = request.form.get('section_id')
        student.section_id = int(sec_id) if sec_id else None

        db.session.commit()
        flash('Student record updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating student: {str(e)}', 'danger')

    return redirect(url_for('main.students_list'))

@main.route('/students/delete/<int:id>', methods=['POST'])
def delete_student(id):
    try:
        student = StudentModel.query.get_or_404(id)
        student.is_active = False
        db.session.commit()
        flash(f'Student "{student.student_name}" moved to archive safely.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'danger')

    return redirect(url_for('main.students_list'))

@main.route('/students/archived')
def archived_students_list():
    archived = StudentModel.query.filter_by(is_active=False).all()
    return render_template('archived_students.html', students=archived)

@main.route('/students/restore/<int:id>', methods=['POST'])
def restore_student(id):
    try:
        student = StudentModel.query.get_or_404(id)
        student.is_active = True
        db.session.commit()
        flash(f'Student "{student.student_name}" has been restored successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring student: {str(e)}', 'danger')

    return redirect(url_for('main.archived_students_list'))

@main.route('/students/permanent-delete/<int:id>', methods=['POST'])
def permanent_delete_student(id):
    try:
        student = StudentModel.query.get_or_404(id)
        if student.is_active:
            flash('Error: Cannot permanently delete an active student.', 'danger')
            return redirect(url_for('main.students_list'))

        delete_student_permanently(student)
        flash(f'Student "{student.student_name}" has been permanently deleted from the system.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error permanent deleting student: {str(e)}', 'danger')

    return redirect(url_for('main.archived_students_list'))

@main.route('/students/<int:id>/report')
def student_detailed_report(id):
    student = StudentModel.query.get_or_404(id)
    attendance_records = AttendanceModel.query.filter_by(target_type='student', target_id=student.id).order_by(AttendanceModel.date.desc()).all()
    marks = StudentMarkModel.query.filter_by(student_id=student.id).join(TestModel).order_by(TestModel.test_date.desc()).all()

    total_records = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == 'Present')
    absent_count = sum(1 for r in attendance_records if r.status == 'Absent')
    late_count = sum(1 for r in attendance_records if r.status == 'Late')
    leave_count = sum(1 for r in attendance_records if r.status == 'Leave')

    overall_percentage = 0.0
    if marks:
        percentages = [m.percentage for m in marks if m.percentage is not None]
        overall_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0.0

    if overall_percentage >= 85:
        overall_grade = 'A+'
    elif overall_percentage >= 70:
        overall_grade = 'A'
    elif overall_percentage >= 60:
        overall_grade = 'B'
    elif overall_percentage >= 50:
        overall_grade = 'C'
    elif overall_percentage >= 40:
        overall_grade = 'D'
    else:
        overall_grade = 'F'

    summary = {
        'attendance_total': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'leave_count': leave_count,
        'overall_percentage': overall_percentage,
        'overall_grade': overall_grade,
        'best_test': max(marks, key=lambda m: (m.percentage or 0)).test_info.test_title if marks else 'N/A',
    }

    return render_template('student_report.html',
                           student=student,
                           attendance_records=attendance_records,
                           marks=marks,
                           summary=summary)

@main.route('/students/<int:id>/report/pdf')
def student_report_pdf(id):
    student = StudentModel.query.get_or_404(id)
    marks = StudentMarkModel.query.filter_by(student_id=student.id).join(TestModel).order_by(TestModel.test_date.asc()).all()
    attendance_records = AttendanceModel.query.filter_by(target_type='student', target_id=student.id).order_by(AttendanceModel.date.asc()).all()

    total_records = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == 'Present')
    absent_count = sum(1 for r in attendance_records if r.status == 'Absent')
    late_count = sum(1 for r in attendance_records if r.status == 'Late')
    leave_count = sum(1 for r in attendance_records if r.status == 'Leave')

    percentages = [m.percentage for m in marks if m.percentage is not None]
    overall_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0.0

    if overall_percentage >= 85:
        overall_grade = 'A+'
    elif overall_percentage >= 70:
        overall_grade = 'A'
    elif overall_percentage >= 60:
        overall_grade = 'B'
    elif overall_percentage >= 50:
        overall_grade = 'C'
    elif overall_percentage >= 40:
        overall_grade = 'D'
    else:
        overall_grade = 'F'

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=8, alignment=1, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#475569'), spaceAfter=12, alignment=1)
    label_style = ParagraphStyle('LabelStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), leading=12)

    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    school_name = school.school_name if school else 'School Management System'

    story.append(Paragraph(f"{school_name}", title_style))
    story.append(Paragraph('Student Performance Report Card', subtitle_style))
    story.append(Paragraph(f"<b>Student:</b> {student.student_name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Roll No:</b> {student.roll_number} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Class:</b> {student.class_info.name if student.class_info else 'N/A'} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Father:</b> {student.father_name}", label_style))

    metric_data = [
        ['Overall %', f'{overall_percentage}%'],
        ['Grade', overall_grade],
        ['Present', str(present_count)],
        ['Absent', str(absent_count)],
        ['Late', str(late_count)],
        ['Leave', str(leave_count)],
    ]
    metric_table = Table(metric_data, colWidths=[75, 65], rowHeights=28)
    metric_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('BACKGROUND', (0, 0), (0, 5), colors.HexColor('#dbeafe')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#dcfce7')),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#fef3c7')),
    ]))
    story.append(Spacer(1, 8))
    story.append(metric_table)
    story.append(Spacer(1, 12))

    table_data = [['Test', 'Type', 'Subject', 'Date', 'Obtained', '%', 'Grade']]
    for mark in marks:
        test = mark.test_info
        table_data.append([
            test.test_title if test else 'N/A',
            test.test_type if test else 'N/A',
            test.subject_info.name if test and test.subject_info else 'N/A',
            str(test.test_date) if test else 'N/A',
            str(mark.marks_obtained),
            f"{mark.percentage}%" if mark.percentage is not None else '—',
            mark.grade or '—'
        ])

    table = Table(table_data, colWidths=[110, 55, 80, 70, 55, 45, 45])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ]))
    story.append(table)
    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f'{student.roll_number}_{student.student_name}_result_card.pdf')

@main.route('/students/export/csv')
def export_students_csv():
    students = StudentModel.query.filter_by(is_active=True).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll Number', 'Student Name', 'Father Name', 'Class', 'Section', 'Guardian Phone', 'Address'])
    
    for s in students:
        class_name = s.class_info.name if s.class_info else 'N/A'
        section_name = s.section_info.name if s.section_info else 'N/A'
        writer.writerow([s.roll_number, s.student_name, s.father_name, class_name, section_name, s.guardian_phone, s.address])
    
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=students_report.csv"})

@main.route('/students/template/excel')
def students_template_excel():
    template_data = [{
        'Roll Number': '101',
        'Student Name': 'Ali Khan',
        'Father Name': 'Ahmad Khan',
        'Class': 'Class 1',
        'Section': 'A',
        'Guardian Phone': '+923001234567',
        'Address': 'Main Bazaar, City'
    }]
    df = pd.DataFrame(template_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students Template')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='students_import_template.xlsx')


@main.route('/students/export/excel')
def export_students_excel():
    students = StudentModel.query.filter_by(is_active=True).all()
    data = [{
        'Roll Number': s.roll_number,
        'Student Name': s.student_name,
        'Father Name': s.father_name,
        'Class': s.class_info.name if s.class_info else 'N/A',
        'Section': s.section_info.name if s.section_info else 'N/A',
        'Guardian Phone': s.guardian_phone,
        'Address': s.address
    } for s in students]
    
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')
    output.seek(0)
    
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='students_report.xlsx')

@main.route('/students/export/pdf')
def export_students_pdf():
    students = StudentModel.query.filter_by(is_active=True).all()
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1a202c'), spaceAfter=15, alignment=1)
    
    story.append(Paragraph("School Management System — Student Report", title_style))
    story.append(Spacer(1, 10))
    
    table_data = [['Roll No', 'Student Name', 'Father Name', 'Class', 'Phone']]
    for s in students:
        table_data.append([str(s.roll_number), str(s.student_name), str(s.father_name), str(s.class_info.name if s.class_info else 'N/A'), str(s.guardian_phone)])
        
    t = Table(table_data, colWidths=[70, 130, 130, 80, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(t)
    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name='students_report.pdf')


@main.route('/students/import', methods=['POST'])
def import_students():
    import io
    file = request.files.get('import_file')
    if not file or not file.filename:
        flash('No file selected.', 'warning')
        return redirect(url_for('main.students_list'))

    ext = file.filename.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'csv':
            import csv as csv_module
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv_module.DictReader(stream)
            rows = list(reader)
        elif ext in ('xlsx', 'xls'):
            df = pd.read_excel(file)
            df.columns = df.columns.str.strip()
            rows = df.to_dict(orient='records')
        else:
            flash('Only .xlsx or .csv files are supported.', 'danger')
            return redirect(url_for('main.students_list'))
    except Exception as e:
        flash(f'Could not read file: {str(e)}', 'danger')
        return redirect(url_for('main.students_list'))

    class_map = {c.name.strip().lower(): c for c in ClassModel.query.all()}
    section_map = {}
    for sec in SectionModel.query.all():
        section_map[(sec.class_id, sec.name.strip().lower())] = sec

    added = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            roll     = str(row.get('Roll Number', '') or '').strip()
            name     = str(row.get('Student Name', '') or '').strip()
            father   = str(row.get('Father Name', '') or '').strip()
            cls_name = str(row.get('Class', '') or '').strip()
            sec_name = str(row.get('Section', '') or '').strip()
            phone    = str(row.get('Guardian Phone', '') or '').strip()
            address  = str(row.get('Address', '') or '').strip()

            if not roll or not name:
                errors.append(f'Row {i}: Roll Number or Student Name is empty — skipped.')
                skipped += 1
                continue

            if StudentModel.query.filter_by(roll_number=roll).first():
                errors.append(f'Row {i}: Roll No {roll} ({name}) already exists — skipped.')
                skipped += 1
                continue

            cls_obj = class_map.get(cls_name.lower())
            if not cls_obj:
                errors.append(f'Row {i}: Class "{cls_name}" not found — {name} skipped.')
                skipped += 1
                continue

            sec_obj = section_map.get((cls_obj.id, sec_name.lower())) if sec_name else None

            student = StudentModel(
                roll_number    = roll,
                student_name   = name,
                father_name    = father,
                class_id       = cls_obj.id,
                section_id     = sec_obj.id if sec_obj else None,
                guardian_phone = phone,
                address        = address,
                is_active      = True
            )
            db.session.add(student)
            added += 1

        except Exception as e:
            errors.append(f'Row {i}: Error — {str(e)}')
            skipped += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Database error while saving: {str(e)}', 'danger')
        return redirect(url_for('main.students_list'))

    flash(f'Import complete — {added} student(s) added, {skipped} skipped.',
          'success' if added > 0 else 'warning')
    for err in errors[:10]:
        flash(err, 'warning')
    if len(errors) > 10:
        flash(f'...and {len(errors) - 10} more warnings not shown.', 'secondary')

    return redirect(url_for('main.students_list'))


@main.route('/students/restore-all', methods=['POST'])
def restore_all_students():
    count = StudentModel.query.filter_by(is_active=False).update({'is_active': True})
    db.session.commit()
    flash(f'{count} student(s) restored successfully.', 'success')
    return redirect(url_for('main.archived_students_list'))


@main.route('/students/delete-all-permanent', methods=['POST'])
def delete_all_students_permanent():
    students = StudentModel.query.filter_by(is_active=False).all()
    count = len(students)
    for student in students:
        delete_student_permanently(student)
    flash(f'{count} student(s) permanently deleted.', 'danger')
    return redirect(url_for('main.archived_students_list'))



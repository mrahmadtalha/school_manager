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
from app.models import TeacherModel, SubjectModel, ClassModel
from app.routes import main

# ==========================================
# TEACHER MANAGEMENT & EXPORTS
# ==========================================
@main.route('/teachers')
def teachers_list():
    search = request.args.get('search', '').strip()
    query = TeacherModel.query.filter_by(is_active=True)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                TeacherModel.teacher_name.ilike(like),
                TeacherModel.teacher_id_str.ilike(like),
                TeacherModel.qualification.ilike(like),
                TeacherModel.assigned_class.ilike(like)
            )
        )
    teachers = query.order_by(TeacherModel.teacher_name).all()
    classes = ClassModel.query.all()
    return render_template('teachers.html', teachers=teachers, classes=classes, search=search)

@main.route('/teachers/add', methods=['POST'])
def add_teacher():
    try:
        teacher_id_str = request.form.get('teacher_id_str').strip()
        teacher_name = request.form.get('teacher_name')
        joining_date_str = request.form.get('joining_date')
        joining_date = datetime.strptime(joining_date_str, '%Y-%m-%d') if joining_date_str else datetime.utcnow()
        qualification = request.form.get('qualification')
        salary_type = request.form.get('salary_type', 'monthly').strip().lower()
        monthly_salary = float(request.form.get('monthly_salary') or 0)
        hourly_rate = float(request.form.get('hourly_rate') or 0)
        salary = float(request.form.get('salary') or 0)
        if salary_type == 'hourly':
            hourly_rate = float(request.form.get('hourly_rate') or salary or 0)
            monthly_salary = 0.0
            salary = hourly_rate
        else:
            monthly_salary = float(request.form.get('monthly_salary') or salary or 0)
            hourly_rate = 0.0
            salary = monthly_salary
        assigned_class = request.form.get('assigned_class')

        existing_teacher = TeacherModel.query.filter_by(teacher_id_str=teacher_id_str).first()
        if existing_teacher:
            flash(f'Error: Teacher ID "{teacher_id_str}" already exists.', 'danger')
            return redirect(url_for('main.teachers_list'))

        new_teacher = TeacherModel(
            teacher_id_str=teacher_id_str,
            teacher_name=teacher_name,
            joining_date=joining_date,
            qualification=qualification,
            salary=salary,
            salary_type=salary_type,
            monthly_salary=monthly_salary,
            hourly_rate=hourly_rate,
            assigned_class=assigned_class
        )
        db.session.add(new_teacher)
        db.session.commit()
        flash('Teacher added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding teacher: {str(e)}', 'danger')

    return redirect(url_for('main.teachers_list'))

@main.route('/teachers/edit/<int:id>', methods=['POST'])
def edit_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        teacher.teacher_id_str = request.form.get('teacher_id_str').strip()
        teacher.teacher_name = request.form.get('teacher_name')
        
        joining_date_str = request.form.get('joining_date')
        if joining_date_str:
            teacher.joining_date = datetime.strptime(joining_date_str, '%Y-%m-%d')
            
        teacher.qualification = request.form.get('qualification')
        teacher.salary_type = request.form.get('salary_type', teacher.salary_type or 'monthly').strip().lower()
        teacher.monthly_salary = float(request.form.get('monthly_salary') or 0)
        teacher.hourly_rate = float(request.form.get('hourly_rate') or 0)
        salary = float(request.form.get('salary') or 0)
        if teacher.salary_type == 'hourly':
            teacher.hourly_rate = float(request.form.get('hourly_rate') or salary or 0)
            teacher.monthly_salary = 0.0
            teacher.salary = teacher.hourly_rate
        else:
            teacher.monthly_salary = float(request.form.get('monthly_salary') or salary or 0)
            teacher.hourly_rate = 0.0
            teacher.salary = teacher.monthly_salary
        teacher.assigned_class = request.form.get('assigned_class')

        db.session.commit()
        flash('Teacher record updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating teacher: {str(e)}', 'danger')

    return redirect(url_for('main.teachers_list'))

@main.route('/teachers/delete/<int:id>', methods=['POST'])
def delete_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        teacher.is_active = False
        db.session.commit()
        flash(f'Teacher "{teacher.teacher_name}" moved to archive safely.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting teacher: {str(e)}', 'danger')

    return redirect(url_for('main.teachers_list'))

@main.route('/teachers/archived')
def archived_teachers_list():
    archived = TeacherModel.query.filter_by(is_active=False).all()
    return render_template('archived_teachers.html', teachers=archived)

@main.route('/teachers/restore/<int:id>', methods=['POST'])
def restore_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        teacher.is_active = True
        db.session.commit()
        flash(f'Teacher "{teacher.teacher_name}" has been restored successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring teacher: {str(e)}', 'danger')

    return redirect(url_for('main.archived_teachers_list'))

@main.route('/teachers/permanent-delete/<int:id>', methods=['POST'])
def permanent_delete_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        db.session.delete(teacher)
        db.session.commit()
        flash('Teacher permanently deleted from the system.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('main.archived_teachers_list'))

@main.route('/teachers/export/csv')
def export_teachers_csv():
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Teacher ID', 'Teacher Name', 'Joining Date', 'Qualification', 'Salary', 'Assigned Class'])
    for t in teachers:
        writer.writerow([t.teacher_id_str, t.teacher_name, t.joining_date.strftime('%Y-%m-%d'), t.qualification, t.salary, t.assigned_class])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=teachers_report.csv"})

@main.route('/teachers/template/excel')
def teachers_template_excel():
    template_data = [{
        'Teacher ID': 'T001',
        'Teacher Name': 'Ayesha Malik',
        'Joining Date': '2024-01-15',
        'Qualification': 'M.A English',
        'Salary': '45000',
        'Assigned Class': 'Class 5'
    }]
    df = pd.DataFrame(template_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Teachers Template')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='teachers_import_template.xlsx')


@main.route('/teachers/export/excel')
def export_teachers_excel():
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    data = [{
        'Teacher ID': t.teacher_id_str,
        'Teacher Name': t.teacher_name,
        'Joining Date': t.joining_date.strftime('%Y-%m-%d'),
        'Qualification': t.qualification,
        'Salary': t.salary,
        'Assigned Class': t.assigned_class
    } for t in teachers]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Teachers')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='teachers_report.xlsx')

@main.route('/teachers/export/pdf')
def export_teachers_pdf():
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1a202c'), spaceAfter=15, alignment=1)
    story.append(Paragraph("School Management System — Teacher Report", title_style))
    story.append(Spacer(1, 10))
    table_data = [['ID', 'Name', 'Joining Date', 'Qualification', 'Salary', 'Class']]
    for t in teachers:
        table_data.append([str(t.teacher_id_str), str(t.teacher_name), t.joining_date.strftime('%Y-%m-%d'), str(t.qualification), str(t.salary), str(t.assigned_class)])
    t = Table(table_data, colWidths=[60, 110, 80, 110, 70, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name='teachers_report.pdf')


@main.route('/teachers/import', methods=['POST'])
def import_teachers():
    import io
    file = request.files.get('import_file')
    if not file or not file.filename:
        flash('No file selected.', 'warning')
        return redirect(url_for('main.teachers_list'))

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
            return redirect(url_for('main.teachers_list'))
    except Exception as e:
        flash(f'Could not read file: {str(e)}', 'danger')
        return redirect(url_for('main.teachers_list'))

    added = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            tid        = str(row.get('Teacher ID', '') or '').strip()
            name       = str(row.get('Teacher Name', '') or '').strip()
            joining    = str(row.get('Joining Date', '') or '').strip()
            qual       = str(row.get('Qualification', '') or '').strip()
            salary_str = str(row.get('Salary', '') or '').strip()
            assigned   = str(row.get('Assigned Class', '') or '').strip()

            if not tid or not name:
                errors.append(f'Row {i}: Teacher ID or Name is empty — skipped.')
                skipped += 1
                continue

            if TeacherModel.query.filter_by(teacher_id_str=tid).first():
                errors.append(f'Row {i}: Teacher ID {tid} ({name}) already exists — skipped.')
                skipped += 1
                continue

            try:
                joining_date = datetime.strptime(joining, '%Y-%m-%d') if joining else datetime.utcnow()
            except ValueError:
                try:
                    joining_date = datetime.strptime(joining, '%d/%m/%Y')
                except Exception:
                    joining_date = datetime.utcnow()

            try:
                salary = float(salary_str) if salary_str else 0.0
            except ValueError:
                salary = 0.0

            teacher = TeacherModel(
                teacher_id_str = tid,
                teacher_name   = name,
                joining_date   = joining_date,
                qualification  = qual,
                salary         = salary,
                assigned_class = assigned,
                is_active      = True
            )
            db.session.add(teacher)
            added += 1

        except Exception as e:
            errors.append(f'Row {i}: Error — {str(e)}')
            skipped += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Database error while saving: {str(e)}', 'danger')
        return redirect(url_for('main.teachers_list'))

    msg = f'Import complete — {added} teacher(s) added, {skipped} skipped.'
    flash(msg, 'success' if added > 0 else 'warning')
    for err in errors[:10]:
        flash(err, 'warning')
    if len(errors) > 10:
        flash(f'...and {len(errors) - 10} more warnings not shown.', 'secondary')

    return redirect(url_for('main.teachers_list'))


@main.route('/teachers/restore-all', methods=['POST'])
def restore_all_teachers():
    count = TeacherModel.query.filter_by(is_active=False).update({'is_active': True})
    db.session.commit()
    flash(f'{count} teacher(s) restored successfully.', 'success')
    return redirect(url_for('main.archived_teachers_list'))


@main.route('/teachers/delete-all-permanent', methods=['POST'])
def delete_all_teachers_permanent():
    teachers = TeacherModel.query.filter_by(is_active=False).all()
    count = len(teachers)
    for t in teachers:
        db.session.delete(t)
    db.session.commit()
    flash(f'{count} teacher(s) permanently deleted.', 'danger')
    return redirect(url_for('main.archived_teachers_list'))


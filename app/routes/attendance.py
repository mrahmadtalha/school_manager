from datetime import datetime, date
from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash, 
    send_file, 
    Response,
    session
)

from app.database import db
from app.models import (
    StudentModel, TeacherModel, ClassModel, AttendanceModel
)
from app.routes import main
from app.services import attendance_export as exporter
from app.services.attendance_service import (
    build_student_attendance_summary,
    build_teacher_attendance_summary,
    save_student_attendance,
    save_teacher_attendance,
    set_attendance_lock_status,
    get_daily_student_attendance,
    get_daily_teacher_attendance
)

# ==========================================
# TEACHER ATTENDANCE
# ==========================================

@main.route('/attendance/teachers', methods=['GET', 'POST'])
def teacher_attendance():
    selected_date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        selected_date_str = request.form.get('date')
        attendance_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        save_teacher_attendance(attendance_date, request.form, teachers)
        flash('Teacher attendance saved successfully!', 'success')
        return redirect(url_for('main.teacher_attendance', date=selected_date_str))
        
    records = AttendanceModel.query.filter_by(date=attendance_date, target_type='teacher').all()
    attendance_map = {r.target_id: r.status for r in records}

    return render_template('teacher_attendance.html', 
                           teachers=teachers, selected_date=selected_date_str,
                           attendance_map=attendance_map)


@main.route('/attendance/teachers/summary', methods=['GET'])
def teacher_attendance_summary():
    today = date.today()
    default_start = date(today.year, today.month, 1).strftime('%Y-%m-%d')
    default_end = today.strftime('%Y-%m-%d')
    
    start_date_str = request.args.get('start_date', default_start)
    end_date_str = request.args.get('end_date', default_end)
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    summary = build_teacher_attendance_summary(start_date, end_date)

    return render_template('teacher_attendance_summary.html',
                           start_date=start_date_str,
                           end_date=end_date_str,
                           dates_list=summary['dates_list'],
                           matrix_data=summary['matrix_data'])


# ==========================================
# STUDENT ATTENDANCE & LOCKING
# ==========================================

@main.route('/attendance/students', methods=['GET', 'POST'])
def student_attendance():
    classes = ClassModel.query.all()
    selected_class_id = request.args.get('class_id', type=int) or request.form.get('class_id', type=int)
    
    date_str = request.args.get('date') or request.form.get('date')
    attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    
    if not selected_class_id and classes:
        selected_class_id = classes[0].id
        
    students = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all() if selected_class_id else []
    
    if request.method == 'POST':
        try:
            absent_students, next_class = save_student_attendance(
                selected_class_id, attendance_date, request.form, classes
            )
            session['last_absentees'] = [
                {'name': s.student_name, 'phone': s.guardian_phone, 'roll': s.roll_number} 
                for s in absent_students
            ]
            session.modified = True
            
            flash(f'Attendance saved & locked! {len(absent_students)} absent.', 'warning' if absent_students else 'success')

            if next_class:
                flash(f'Now taking attendance for: {next_class.name}', 'info')
                return redirect(url_for('main.student_attendance',
                                        class_id=next_class.id,
                                        date=attendance_date.strftime('%Y-%m-%d')))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving attendance: {str(e)}', 'danger')

        return redirect(url_for('main.student_attendance',
                                class_id=selected_class_id,
                                date=attendance_date.strftime('%Y-%m-%d')))

    existing_records = AttendanceModel.query.filter_by(
        target_type='student',
        date=attendance_date,
        class_id=selected_class_id
    ).all() if selected_class_id else []
    
    attendance_map = {r.target_id: r.status for r in existing_records}
    late_time_map  = {r.target_id: (r.late_time if hasattr(r, 'late_time') else '') for r in existing_records}
    is_locked      = any(getattr(r, 'is_locked', False) for r in existing_records)
    absent_students = [
        student for student in students
        if attendance_map.get(student.id) == 'Absent'
    ]
    absent_students_payload = [
        {
            'id': student.id,
            'student_name': student.student_name,
            'guardian_phone': student.guardian_phone,
            'roll_number': student.roll_number,
        }
        for student in absent_students
    ]

    return render_template('student_attendance.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           students=students,
                           attendance_date=attendance_date.strftime('%Y-%m-%d'),
                           selected_date=attendance_date.strftime('%Y-%m-%d'),
                           existing_attendance=attendance_map,
                           attendance_map=attendance_map,
                           late_time_map=late_time_map,
                           is_locked=is_locked,
                           absent_students=absent_students_payload)


@main.route('/attendance/lock', methods=['POST'])
def lock_attendance():
    class_id = request.form.get('class_id', type=int)
    date_str = request.form.get('date')
    action   = request.form.get('action', 'lock')
    locked   = (action == 'lock')
    attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    set_attendance_lock_status(class_id, attendance_date, locked)
    
    msg = 'Attendance unlocked — you can now edit.' if not locked else 'Attendance locked.'
    flash(msg, 'warning' if not locked else 'success')
    return redirect(url_for('main.student_attendance', class_id=class_id, date=date_str))


# ==========================================
# ATTENDANCE SUMMARY & REPORTS
# ==========================================

@main.route('/attendance/summary', methods=['GET'])
def attendance_summary():
    today = date.today()
    default_start = date(today.year, today.month, 1).strftime('%Y-%m-%d')
    default_end = today.strftime('%Y-%m-%d')
    
    start_date_str = request.args.get('start_date', default_start)
    end_date_str = request.args.get('end_date', default_end)
    selected_class_id = request.args.get('class_id', type=int)
    
    classes = ClassModel.query.all()
    if not selected_class_id and classes:
        return redirect(url_for('main.attendance_summary',
                                class_id=classes[0].id,
                                start_date=start_date_str,
                                end_date=end_date_str))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    summary = build_student_attendance_summary(selected_class_id, start_date, end_date) if selected_class_id else {
        'dates_list': [], 'matrix_data': []
    }

    return render_template('attendance_summary.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           dates_list=summary['dates_list'],
                           matrix_data=summary['matrix_data'],
                           stats=summary.get('kpi_stats', {}))


# ==========================================
# EXPORTS: CLASS ATTENDANCE SHEETS
# ==========================================

@main.route('/attendance/export/pdf/<int:class_id>')
def export_class_attendance_pdf(class_id):
    class_obj = ClassModel.query.get_or_404(class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    attendance_map, late_time_map = get_daily_student_attendance(class_id, attendance_date)
    
    pdf_buffer = exporter.generate_class_attendance_pdf(class_obj, students, selected_date, attendance_map, late_time_map)
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, 
                     download_name=f'attendance_sheet_{class_obj.name}_{selected_date}.pdf')


@main.route('/attendance/export/excel/<int:class_id>')
def export_class_attendance_excel(class_id):
    class_obj = ClassModel.query.get_or_404(class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    attendance_map, late_time_map = get_daily_student_attendance(class_id, attendance_date)
    
    excel_buffer = exporter.generate_class_attendance_excel(class_obj, students, attendance_map, late_time_map)
    return send_file(excel_buffer, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                     as_attachment=True, download_name=f'attendance_sheet_{class_obj.name}_{selected_date}.xlsx')


@main.route('/attendance/export/csv/<int:class_id>')
def export_class_attendance_csv(class_id):
    class_obj = ClassModel.query.get_or_404(class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    attendance_map, late_time_map = get_daily_student_attendance(class_id, attendance_date)
    
    csv_data = exporter.generate_class_attendance_csv(students, attendance_map, late_time_map)
    return Response(csv_data, mimetype="text/csv", 
                    headers={"Content-Disposition": f"attachment;filename=attendance_sheet_{class_obj.name}_{selected_date}.csv"})


# ==========================================
# EXPORTS: TEACHER ATTENDANCE SHEETS
# ==========================================

@main.route('/attendance/teachers/export/pdf')
def export_teacher_attendance_pdf():
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    attendance_map = get_daily_teacher_attendance(attendance_date)
    
    pdf_buffer = exporter.generate_teacher_attendance_pdf(teachers, selected_date, attendance_map)
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, 
                     download_name=f'teacher_attendance_sheet_{selected_date}.pdf')


@main.route('/attendance/teachers/export/excel')
def export_teacher_attendance_excel():
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    attendance_map = get_daily_teacher_attendance(attendance_date)
    
    excel_buffer = exporter.generate_teacher_attendance_excel(teachers, attendance_map)
    return send_file(excel_buffer, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                     as_attachment=True, download_name=f'teacher_attendance_sheet_{selected_date}.xlsx')


@main.route('/attendance/teachers/export/csv')
def export_teacher_attendance_csv():
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    attendance_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    attendance_map = get_daily_teacher_attendance(attendance_date)
    
    csv_data = exporter.generate_teacher_attendance_csv(teachers, attendance_map)
    return Response(csv_data, mimetype="text/csv", 
                    headers={"Content-Disposition": f"attachment;filename=teacher_attendance_sheet_{selected_date}.csv"})


# ==========================================
# EXPORTS: ATTENDANCE SUMMARY MATRIX
# ==========================================

@main.route('/attendance/summary/export/excel', methods=['GET'])
def export_attendance_summary_excel():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    selected_class_id = request.args.get('class_id', type=int)
    
    if not selected_class_id or not start_date_str or not end_date_str:
        return redirect(url_for('main.attendance_summary'))
        
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    summary = build_student_attendance_summary(selected_class_id, start_date, end_date)
    excel_buffer = exporter.generate_summary_excel(
        summary['class_obj'], summary['students'], summary['taken_dates'], summary['attendance_lookup']
    )
    
    return send_file(
        excel_buffer, 
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        as_attachment=True, 
        download_name=f"attendance_summary_{summary['class_obj'].name}_{start_date}_to_{end_date}.xlsx"
    )


@main.route('/attendance/summary/export/csv', methods=['GET'])
def export_attendance_summary_csv():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    selected_class_id = request.args.get('class_id', type=int)
    
    if not selected_class_id or not start_date_str or not end_date_str:
        return redirect(url_for('main.attendance_summary'))
        
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    summary = build_student_attendance_summary(selected_class_id, start_date, end_date)
    csv_data = exporter.generate_summary_csv(
        summary['students'], summary['taken_dates'], summary['attendance_lookup']
    )
    
    return Response(
        csv_data, 
        mimetype="text/csv", 
        headers={"Content-Disposition": f"attachment;filename=attendance_summary_{summary['class_obj'].name}_{start_date}_to_{end_date}.csv"}
    )


@main.route('/attendance/summary/export/pdf', methods=['GET'])
def export_attendance_summary_pdf():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    selected_class_id = request.args.get('class_id', type=int)
    
    if not selected_class_id or not start_date_str or not end_date_str:
        return redirect(url_for('main.attendance_summary'))
        
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    summary = build_student_attendance_summary(selected_class_id, start_date, end_date)
    pdf_buffer = exporter.generate_summary_pdf(
        summary['class_obj'], summary['students'], summary['taken_dates'], summary['attendance_lookup'],
        start_date, end_date
    )
    
    return send_file(
        pdf_buffer, 
        mimetype='application/pdf', 
        as_attachment=True, 
        download_name=f"attendance_summary_{summary['class_obj'].name}.pdf"
    )
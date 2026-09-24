from datetime import datetime, date, timedelta
from app.database import db
from app.models import (
    StudentModel, TeacherModel, ClassModel, AttendanceModel, SchoolSettings
)
from app.services.teacher_payroll import get_school_working_days
from app.services.whatsapp_automation import queue_automation_message

def build_student_attendance_summary(class_id, start_date, end_date):
    """
    Computes attendance summary and day-by-day matrix for students of a given class.
    """
    class_obj = ClassModel.query.get_or_404(class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    settings = SchoolSettings.query.first() or type('DefaultSettings', (), {'weekend_off': True, 'custom_off_days': ''})()

    all_dates = get_school_working_days(start_date, end_date, settings)

    records = AttendanceModel.query.filter(
        AttendanceModel.class_id == class_id,
        AttendanceModel.target_type == 'student',
        AttendanceModel.date >= start_date,
        AttendanceModel.date <= end_date
    ).all()
    
    attendance_lookup = {(r.target_id, r.date): r.status for r in records}
    taken_dates = sorted(set(r.date for r in records))
    active_dates = taken_dates if taken_dates else all_dates
    
    matrix_data = []
    for idx, s in enumerate(students, 1):
        row = {'sr': idx, 'student': s, 'daily_status': {}}
        for d in active_dates:
            row['daily_status'][d] = attendance_lookup.get((s.id, d), '—')
        p_count = sum(1 for v in row['daily_status'].values() if v == 'Present')
        a_count = sum(1 for v in row['daily_status'].values() if v == 'Absent')
        l_count = sum(1 for v in row['daily_status'].values() if v == 'Late')
        taken = sum(1 for v in row['daily_status'].values() if v != '—')
        row['p_count'] = p_count
        row['a_count'] = a_count
        row['l_count'] = l_count
        row['percentage'] = round((p_count / taken) * 100, 1) if taken > 0 else 0
        row['is_at_risk'] = bool(taken > 0 and row['percentage'] < 75.0)
        matrix_data.append(row)
        
    total_students = len(students)
    percentages = [row['percentage'] for row in matrix_data if len(taken_dates) > 0]
    avg_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0
    perfect_count = sum(1 for row in matrix_data if row['percentage'] == 100.0 and len(taken_dates) > 0)
    at_risk_count = sum(1 for row in matrix_data if row['is_at_risk'])

    kpi_stats = {
        'total_students': total_students,
        'avg_percentage': avg_percentage,
        'perfect_count': perfect_count,
        'at_risk_count': at_risk_count,
        'days_recorded': len(taken_dates)
    }

    return {
        'class_obj': class_obj,
        'students': students,
        'dates_list': active_dates,
        'taken_dates': taken_dates,
        'attendance_lookup': attendance_lookup,
        'matrix_data': matrix_data,
        'kpi_stats': kpi_stats
    }

def build_teacher_attendance_summary(start_date, end_date):
    """
    Computes attendance summary and day-by-day matrix for all active teachers.
    """
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    settings = SchoolSettings.query.first() or type('DefaultSettings', (), {'weekend_off': True, 'custom_off_days': ''})()

    all_dates = get_school_working_days(start_date, end_date, settings)

    records = AttendanceModel.query.filter(
        AttendanceModel.target_type == 'teacher',
        AttendanceModel.date >= start_date,
        AttendanceModel.date <= end_date
    ).all()
    
    attendance_lookup = {(r.target_id, r.date): r.status for r in records}
    taken_dates = sorted(set(r.date for r in records))
    active_dates = taken_dates if taken_dates else []

    matrix_data = []
    for idx, t in enumerate(teachers, 1):
        row = {'sr': idx, 'teacher': t, 'daily_status': {}}
        for d in active_dates:
            row['daily_status'][d] = attendance_lookup.get((t.id, d), '—')
        p_count = sum(1 for v in row['daily_status'].values() if v == 'Present')
        a_count = sum(1 for v in row['daily_status'].values() if v == 'Absent')
        l_count = sum(1 for v in row['daily_status'].values() if v == 'Late')
        taken = sum(1 for v in row['daily_status'].values() if v != '—')
        row['p_count'] = p_count
        row['a_count'] = a_count
        row['l_count'] = l_count
        row['percentage'] = round((p_count / taken) * 100, 1) if taken > 0 else 0
        matrix_data.append(row)

    return {
        'teachers': teachers,
        'dates_list': active_dates,
        'matrix_data': matrix_data
    }

def save_student_attendance(selected_class_id, attendance_date, form_dict, classes):
    """
    Processes the submitted student attendance form, persists records,
    locks the session, and returns list of absent students and the next class.
    """
    absent_students = []
    for key, status in form_dict.items():
        if 'status' in key.lower():
            parts = key.replace('[', '_').replace(']', '').split('_')
            student_id = None
            for p in parts:
                if p.isdigit():
                    student_id = int(p)
                    break

            if student_id:
                record = AttendanceModel.query.filter_by(
                    target_type='student',
                    target_id=student_id,
                    date=attendance_date
                ).first()

                late_time = form_dict.get(f'late_time_{student_id}', '').strip()
                previous_status = record.status if record else None
                if record:
                    record.status = status
                    record.class_id = selected_class_id
                    if status == 'Late' and late_time:
                        record.late_time = late_time
                else:
                    record = AttendanceModel(
                        target_type='student',
                        target_id=student_id,
                        class_id=selected_class_id,
                        date=attendance_date,
                        status=status,
                        late_time=late_time if status == 'Late' else None
                    )
                    db.session.add(record)

                student = StudentModel.query.get(student_id)
                if student and status.strip().capitalize() == 'Absent' and (not record or previous_status != status):
                    absent_students.append(student)
                    queue_automation_message(
                        student,
                        'attendance_absent',
                        {'student_name': student.student_name, 'date': attendance_date.isoformat()},
                    )
                elif student and status.strip().capitalize() == 'Late' and (not record or previous_status != status):
                    queue_automation_message(
                        student,
                        'attendance_late',
                        {'student_name': student.student_name, 'date': attendance_date.isoformat()},
                    )

    db.session.commit()
    
    # Auto-lock attendance after saving
    for r in AttendanceModel.query.filter_by(
        target_type='student', class_id=selected_class_id,
        date=attendance_date).all():
        r.is_locked = True
    db.session.commit()

    # Identify the next class in sequence
    next_class = None
    for i, c in enumerate(classes):
        if c.id == selected_class_id and i + 1 < len(classes):
            next_class = classes[i + 1]
            break
            
    return absent_students, next_class

def save_teacher_attendance(attendance_date, form_dict, teachers):
    """
    Processes and persists teacher attendance records from form submission.
    """
    for teacher in teachers:
        status = form_dict.get(f'status_{teacher.id}', 'Present')
        record = AttendanceModel.query.filter_by(
            date=attendance_date, target_type='teacher', target_id=teacher.id
        ).first()
        
        if record:
            record.status = status
        else:
            new_record = AttendanceModel(
                date=attendance_date, target_type='teacher',
                target_id=teacher.id, status=status
            )
            db.session.add(new_record)
    db.session.commit()

def set_attendance_lock_status(class_id, attendance_date, locked):
    """
    Sets the is_locked flag for all student attendance records for a class on a date.
    """
    records = AttendanceModel.query.filter_by(
        target_type='student', class_id=class_id,
        date=attendance_date
    ).all()
    for r in records:
        r.is_locked = locked
    db.session.commit()

def get_daily_student_attendance(class_id, attendance_date):
    """
    Retrieves the attendance mapping and late times for a class on a given date.
    """
    records = AttendanceModel.query.filter_by(
        target_type='student',
        class_id=class_id,
        date=attendance_date
    ).all()
    attendance_map = {r.target_id: r.status for r in records}
    late_time_map = {r.target_id: r.late_time for r in records if getattr(r, 'late_time', None)}
    return attendance_map, late_time_map

def get_daily_teacher_attendance(attendance_date):
    """
    Retrieves the attendance mapping for active teachers on a given date.
    """
    records = AttendanceModel.query.filter_by(
        target_type='teacher',
        date=attendance_date
    ).all()
    return {r.target_id: r.status for r in records}


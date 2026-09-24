from datetime import date
from flask import render_template
from app.database import db
from app.models import (
    ClassModel, SubjectModel, TeacherModel, 
    StudentModel, AttendanceModel, TestModel, FeeRecordModel
)
from app.routes import main
from app.routes.settings import get_whatsapp_service_status

# ==========================================
# DASHBOARD
# ==========================================
@main.route('/')
def dashboard():
    today = date.today()
    current_month_str = today.strftime('%B %Y')
    
    # Core Counts
    total_students = StudentModel.query.filter_by(is_active=True).count()
    total_teachers = TeacherModel.query.filter_by(is_active=True).count()
    total_classes = ClassModel.query.count()
    total_subjects = SubjectModel.query.count()
    
    # Today's Attendance Overview
    today_attendance_count = AttendanceModel.query.filter_by(date=today, target_type='student', status='Present').count()
    
    # Fee Collection Stats for Current Month
    month_fees = FeeRecordModel.query.filter_by(month_year=current_month_str).all()
    total_collected = sum([f.amount_paid for f in month_fees])
    total_pending_fees = sum([f.amount_due - f.amount_paid for f in month_fees if f.amount_due > f.amount_paid])
    
    # Recent Activities
    recent_students = StudentModel.query.filter_by(is_active=True).order_by(StudentModel.id.desc()).limit(5).all()
    recent_tests = TestModel.query.order_by(TestModel.id.desc()).limit(5).all()

    whatsapp_status = get_whatsapp_service_status()

    return render_template('dashboard.html', 
                           total_students=total_students,
                           total_teachers=total_teachers,
                           total_classes=total_classes,
                           total_subjects=total_subjects,
                           today_attendance_count=today_attendance_count,
                           total_collected=total_collected,
                           total_pending_fees=total_pending_fees,
                           recent_students=recent_students,
                           recent_tests=recent_tests,
                           current_month=current_month_str,
                           whatsapp_status=whatsapp_status)# ==========================================

from datetime import date

from flask import jsonify, redirect, render_template, url_for
from flask_login import current_user

from app.database import db
from app.models import (
    AttendanceModel, ClassModel, FeeRecordModel, ROLE_PARENT, StudentModel,
    SubjectModel, TeacherModel, TestModel,
)
from app.routes import main
from app.routes.settings import get_whatsapp_service_status


@main.route('/healthz')
def healthz():
    """Unauthenticated liveness probe used by the smoke test and monitoring."""
    from app.models import AdminUser
    return jsonify({
        'ok': True,
        'database': 'up',
        'users': AdminUser.query.count(),
        'students': StudentModel.query.count(),
    })


@main.route('/')
def dashboard():
    if getattr(current_user, 'role', None) == ROLE_PARENT:
        return redirect(url_for('main.portal'))

    today = date.today()
    current_month_str = today.strftime('%B %Y')

    total_students = StudentModel.query.filter_by(is_active=True).count()
    total_teachers = TeacherModel.query.filter_by(is_active=True).count()
    total_classes = ClassModel.query.count()
    total_subjects = SubjectModel.query.count()

    today_attendance_count = AttendanceModel.query.filter_by(
        date=today, target_type='student', status='Present').count()

    month_fees = FeeRecordModel.query.filter_by(month_year=current_month_str).all()
    total_collected = round(sum(f.amount_paid or 0.0 for f in month_fees), 2)
    total_pending_fees = round(
        sum((f.amount_due or 0.0) - (f.amount_paid or 0.0) for f in month_fees
            if (f.amount_due or 0.0) > (f.amount_paid or 0.0)), 2)

    recent_students = (StudentModel.query.filter_by(is_active=True)
                       .order_by(StudentModel.id.desc()).limit(5).all())
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
                           whatsapp_status=whatsapp_status)

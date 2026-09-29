"""Role-based access control.

Access is **deny by default**: an endpoint that is not explicitly listed as
public or as reachable by a role is restricted to administrators.  The guard is
installed once as a ``before_request`` handler, so new routes are protected
unless they are deliberately opened up here.
"""

import time
from functools import wraps

from flask import abort, current_app, jsonify, redirect, request, url_for
from flask_login import current_user

from app.models.admin import ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER

__all__ = [
    'ROLE_ADMIN', 'ROLE_TEACHER', 'ROLE_PARENT',
    'PUBLIC_ENDPOINTS', 'ROUTE_ROLES', 'role_required', 'role_allowed',
    'install_role_guard', 'login_attempts', 'register_failed_login',
    'clear_failed_logins', 'is_login_locked',
]

# Endpoints reachable without any login.
PUBLIC_ENDPOINTS = {
    'auth.login',
    'auth.setup_admin',
    'static',
    'main.healthz',
    None,
}

# Endpoints any authenticated role may reach.
SHARED_ENDPOINTS = {
    'main.dashboard',
    'main.portal',
    'auth.logout',
    'auth.change_password',
}

# Endpoints teachers may reach in addition to SHARED_ENDPOINTS.
TEACHER_ENDPOINTS = {
    # students
    'main.students_list', 'main.add_student', 'main.edit_student', 'main.delete_student',
    'main.archived_students_list', 'main.student_detailed_report', 'main.student_report_pdf',
    'main.student_history', 'main.export_students_csv', 'main.students_template_excel',
    'main.export_students_excel', 'main.export_students_pdf', 'main.import_students',
    # teachers
    'main.teachers_list', 'main.add_teacher', 'main.edit_teacher', 'main.archived_teachers_list',
    'main.export_teachers_csv', 'main.teachers_template_excel', 'main.export_teachers_excel',
    'main.export_teachers_pdf', 'main.import_teachers',
    # classes (read-only for teachers)
    'main.classes_list',
    # attendance
    'main.teacher_attendance', 'main.teacher_attendance_summary', 'main.student_attendance',
    'main.lock_attendance', 'main.attendance_summary',
    'main.export_class_attendance_pdf', 'main.export_class_attendance_excel',
    'main.export_class_attendance_csv', 'main.export_teacher_attendance_pdf',
    'main.export_teacher_attendance_excel', 'main.export_teacher_attendance_csv',
    'main.export_attendance_summary_excel', 'main.export_attendance_summary_csv',
    'main.export_attendance_summary_pdf',
    # examinations / marks
    'main.tests_list', 'main.add_test', 'main.enter_batch_marks', 'main.test_types_list',
    'main.add_test_type', 'main.edit_test_type', 'main.delete_test_type',
    # reports
    'main.reports_hub', 'main.class_results_matrix', 'main.student_report_card_pdf',
    'main.export_all_report_cards_pdf', 'main.export_class_results_excel',
    'main.export_class_results_csv',
    # documents
    'main.documents_hub', 'main.export_student_id_cards', 'main.export_teacher_id_cards',
    'main.export_certificates',
}

ROUTE_ROLES = {}
for _endpoint in SHARED_ENDPOINTS:
    ROUTE_ROLES[_endpoint] = {ROLE_ADMIN, ROLE_TEACHER, ROLE_PARENT}
for _endpoint in TEACHER_ENDPOINTS - SHARED_ENDPOINTS:
    ROUTE_ROLES[_endpoint] = {ROLE_ADMIN, ROLE_TEACHER}


def role_allowed(endpoint, role):
    if endpoint in PUBLIC_ENDPOINTS:
        return True
    allowed = ROUTE_ROLES.get(endpoint)
    if allowed is None:
        # Deny by default for anything not explicitly shared.
        allowed = {ROLE_ADMIN}
    return (role or ROLE_ADMIN) in allowed


def role_required(*roles):
    """Decorator enforcing membership of ``roles`` on a view function."""
    allowed = set(roles) or {ROLE_ADMIN}

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            role = getattr(current_user, 'role', None) if current_user.is_authenticated else None
            if not current_user.is_authenticated or (role or ROLE_ADMIN) not in allowed:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def install_role_guard(app):
    @app.before_request
    def _enforce_roles():
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            # require_login() turns this into a redirect to the login page.
            return None
        role = getattr(current_user, 'role', None) or ROLE_ADMIN
        if role_allowed(endpoint, role):
            return None
        abort(403)


# -- login throttling (in-process, single-worker only) -------------------

login_attempts = {}


def _now():
    return time.time()


def _prune(username, window):
    bucket = [ts for ts in login_attempts.get(username, []) if _now() - ts < window]
    login_attempts[username] = bucket
    return bucket


def is_login_locked(username, max_attempts=None, window=None):
    max_attempts = max_attempts or current_app.config.get('LOGIN_MAX_ATTEMPTS', 5)
    window = window or current_app.config.get('LOGIN_LOCKOUT_SECONDS', 300)
    return len(_prune(username, window)) >= max_attempts


def register_failed_login(username):
    window = current_app.config.get('LOGIN_LOCKOUT_SECONDS', 300)
    bucket = _prune(username, window)
    bucket.append(_now())


def clear_failed_logins(username):
    login_attempts.pop(username, None)


def lockout_seconds_remaining(username, window=None):
    window = window or current_app.config.get('LOGIN_LOCKOUT_SECONDS', 300)
    bucket = _prune(username, window)
    if not bucket:
        return 0
    return max(1, int(window - (_now() - min(bucket))))

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

from app.models.admin import (ROLE_ACCOUNTANT, ROLE_ADMIN, ROLE_OWNER,
                             ROLE_PARENT, ROLE_TEACHER)

__all__ = [
    'ROLE_ADMIN', 'ROLE_TEACHER', 'ROLE_PARENT', 'ROLE_OWNER', 'ROLE_ACCOUNTANT',
    'PUBLIC_ENDPOINTS', 'ROUTE_ROLES', 'role_required', 'role_allowed',
    'install_role_guard', 'login_attempts', 'register_failed_login',
    'clear_failed_logins', 'is_login_locked', 'password_problem',
]

# Endpoints reachable without any login.
PUBLIC_ENDPOINTS = {
    'auth.login',
    'auth.setup_admin',
    'static',
    'main.healthz',
    # The route itself decides who may use it: open on a fresh install (so the
    # first license can be activated), administrators only afterwards.
    'main.license_page',
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
    'main.student_history', 'main.student_transcript_pdf', 'main.export_students_csv', 'main.students_template_excel',
    'main.export_students_excel', 'main.export_students_pdf', 'main.import_students',
    # teachers
    'main.teachers_list', 'main.add_teacher', 'main.edit_teacher', 'main.archived_teachers_list',
    'main.teacher_profile',
    'main.export_teachers_csv', 'main.teachers_template_excel', 'main.export_teachers_excel',
    'main.export_teachers_pdf', 'main.import_teachers',
    # classes (read-only for teachers)
    'main.classes_list', 'main.class_timetable',
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
    # term examinations (view + marks entry; create/publish stay admin-only)
    'main.examinations_page', 'main.examinations_detail',
    'main.examinations_date_sheet', 'main.examinations_date_sheet_pdf',
    'main.examinations_tabulation', 'main.examinations_tabulation_csv',
    'main.examinations_tabulation_xlsx', 'main.examinations_tabulation_pdf',
    # reports
    'main.reports_hub', 'main.class_results_matrix', 'main.student_report_card_pdf',
    'main.export_all_report_cards_pdf', 'main.export_class_results_excel',
    'main.export_class_results_csv', 'main.export_class_tabulation_pdf',
    'main.hub_export_positions', 'main.hub_export_broad_sheet',
    'main.hub_export_allocation_matrix',
    # documents
    'main.documents_hub', 'main.export_student_id_cards', 'main.export_teacher_id_cards',
    'main.export_certificates',
}

# Endpoints accountants may reach: the money modules.  Administration
# actions inside those modules (bulk class-fee rewrite, WhatsApp fee
# reminders, expense categories) intentionally stay administrator-only.
ACCOUNTANT_ENDPOINTS = {
    # fees - collections, vouchers, ledgers, reconciliation
    'main.fees_list', 'main.pay_fee', 'main.fee_receipt', 'main.fee_student_ledger',
    'main.fees_reconciliation',
    # expenses - daily logger + exports (category management stays admin-only)
    'main.expenses_list', 'main.expenses_add', 'main.expenses_edit',
    'main.expenses_delete', 'main.expenses_export_csv', 'main.expenses_export_pdf',
    # payroll - salaries
    'main.payroll_page', 'main.payroll_generate', 'main.payroll_mark_paid',
    'main.payroll_mark_pending', 'main.payroll_mark_all_paid',
    'main.payroll_payslip_pdf',
    # financials
    'main.financials_summary', 'main.financials_export_csv',
    'main.financials_export_pdf',
    # reports hub - Finance tab and the financial export downloads
    'main.reports_hub', 'main.hub_export_fee_ledger', 'main.hub_export_defaulters',
    'main.hub_export_collections', 'main.hub_export_discounts',
    'main.hub_export_salary_register',
}

# Endpoints the owner (Principal) may reach - the read-only executive views.
OWNER_ENDPOINTS = {
    'main.executive_dashboard', 'main.executive_summary_pdf',
}

ROUTE_ROLES = {}
for _endpoint in SHARED_ENDPOINTS:
    ROUTE_ROLES[_endpoint] = {ROLE_ADMIN, ROLE_TEACHER, ROLE_PARENT,
                              ROLE_OWNER, ROLE_ACCOUNTANT}
for _endpoint in TEACHER_ENDPOINTS - SHARED_ENDPOINTS:
    ROUTE_ROLES[_endpoint] = {ROLE_ADMIN, ROLE_TEACHER}
for _endpoint in ACCOUNTANT_ENDPOINTS:
    ROUTE_ROLES.setdefault(_endpoint, set()).update({ROLE_ADMIN, ROLE_ACCOUNTANT})
for _endpoint in OWNER_ENDPOINTS:
    ROUTE_ROLES.setdefault(_endpoint, set()).update({ROLE_ADMIN, ROLE_OWNER})


def password_problem(password):
    """Return a message when ``password`` fails the complexity policy, else None.

    Policy: at least 8 characters, including at least one letter and one number.
    """
    if len(password) < 8:
        return 'Password must be at least 8 characters.'
    if not any(ch.isalpha() for ch in password):
        return 'Password must contain at least one letter.'
    if not any(ch.isdigit() for ch in password):
        return 'Password must contain at least one number.'
    return None


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

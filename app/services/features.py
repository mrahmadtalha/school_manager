"""Feature catalog: which parts of School Manager a license switches on or off.

This module is deliberately plain Python (no Flask, no database) so that the
vendor dashboard can load it by file path, exactly like ``licensing.py``.  The
catalog is the single list the dashboard shows as checkboxes and the
application enforces at run time.

How a license uses it
---------------------
* A license key may carry ``"features": ["expenses", "payroll", ...]``.  Only
  the listed features are available to that school.
* A key WITHOUT a ``features`` field (every key issued before this release) is
  a legacy key: everything stays switched on, exactly as before.
* Core modules (students, teachers, classes, fees, users, settings, backup,
  license) are always on and are not in the catalog.

Enforcement lives in ``app/license_guard.py`` (one before_request check using
:func:`feature_for_endpoint`) and in the sidebar (``has_feature`` template
helper), so a disabled feature disappears from the menu AND cannot be reached
by typing its address.
"""

# (key, label, description, group)
FEATURE_CATALOG = (
    ('expenses', 'Expenses',
     'Daily expense logger, categories and exports.', 'Finance'),
    ('payroll', 'Payroll',
     'Staff salaries, pay runs and payslips.', 'Finance'),
    ('financial_reports', 'Financial overview & insights',
     'Income/expense summary, comparisons and financial insights.', 'Finance'),
    ('inventory_other_income', 'Inventory, sales & other income',
     'Uniform/book stock and sales, plus non-fee income.', 'Finance'),
    ('admission_fees', 'Admission fees',
     'Admission fee register, receipts and concessions.', 'Finance'),
    ('executive', 'Principal / Owner dashboard',
     'Read-only executive dashboard for the owner role.', 'Finance'),
    ('attendance', 'Attendance',
     'Student and teacher attendance, summaries and exports.', 'Academics'),
    ('qr_attendance', 'QR attendance',
     'Gate guard phone app scans student QR ID cards and marks attendance; daily QR report.', 'Academics'),
    ('exams', 'Exams, marks & results',
     'Tests, term examinations, class results and report cards.', 'Academics'),
    ('documents', 'ID cards & certificates',
     'Student/teacher ID cards and certificates.', 'Academics'),
    ('timetable', 'Timetable',
     'Timetable sheet builder and printouts.', 'Academics'),
    ('parent_portal', 'Parent portal',
     'Parent / guardian logins to see their own children.', 'Communication'),
    ('whatsapp', 'WhatsApp automation',
     'Automatic and broadcast WhatsApp messages, fee reminders.', 'Communication'),
    ('assistant', 'School assistant',
     'Built-in question-and-answer assistant.', 'Tools'),
    ('data_import', 'Bulk data import',
     'Import students and teachers from Excel/CSV.', 'Tools'),
    ('data_export', 'Data export',
     'Download lists and sheets as Excel / CSV / PDF (students, fees, attendance, results ...).', 'Tools'),
    ('language_switch', 'Urdu / English switch',
     'The language button in the sidebar; without it the school stays in English.', 'Tools'),
    ('audit_log_view', 'Audit log viewer',
     'Lets the school open and export its Audit Log. The log is ALWAYS recorded; this only controls viewing.', 'Tools'),
)

#: Features added after the first release.  A key issued before they existed does not
#: list them, so they stay ON for those keys (nothing a school had is taken away).
FEATURES_ADDED_LATER = ('data_export', 'language_switch', 'audit_log_view')

ALL_FEATURES = tuple(item[0] for item in FEATURE_CATALOG)
FEATURE_LABELS = {key: label for key, label, _desc, _group in FEATURE_CATALOG}

#: Whole route modules that belong to one feature.
MODULE_FEATURES = {
    'app.routes.expenses': 'expenses',
    'app.routes.payroll': 'payroll',
    'app.routes.financials': 'financial_reports',
    'app.routes.inventory': 'inventory_other_income',
    'app.routes.other_income': 'inventory_other_income',
    'app.routes.admission_fees': 'admission_fees',
    'app.routes.executive': 'executive',
    'app.routes.attendance': 'attendance',
    'app.routes.qr_attendance': 'qr_attendance',
    'app.routes.examinations': 'exams',
    'app.routes.term_exams': 'exams',
    'app.routes.documents': 'documents',
    'app.routes.timetable_sheet': 'timetable',
    'app.routes.portal': 'parent_portal',
    'app.routes.assistant': 'assistant',
    'app.routes.audit': 'audit_log_view',
}

#: Single endpoints that live inside shared modules (reports, settings, ...).
ENDPOINT_FEATURES = {
    # WhatsApp
    'main.automation_panel': 'whatsapp',
    'main.whatsapp_status': 'whatsapp',
    'main.whatsapp_qr': 'whatsapp',
    'main.whatsapp_integration': 'whatsapp',
    'main.whatsapp_test_message': 'whatsapp',
    'main.whatsapp_pending_messages': 'whatsapp',
    'main.whatsapp_update_status': 'whatsapp',
    'main.whatsapp_authorize_send': 'whatsapp',
    'main.fee_reminders': 'whatsapp',
    'main.fee_reminders_queue': 'whatsapp',
    # Results / report cards that live in the shared reports module
    'main.class_results_matrix': 'exams',
    'main.save_class_result_remarks': 'exams',
    'main.export_class_results_csv': 'exams',
    'main.export_class_results_excel': 'exams',
    'main.export_class_tabulation_pdf': 'exams',
    'main.export_all_report_cards_pdf': 'exams',
    'main.student_report_card_pdf': 'exams',
    'main.hub_export_positions': 'exams',
    'main.hub_export_broad_sheet': 'exams',
    'main.hub_export_allocation_matrix': 'exams',
    # Data import
    'main.import_students': 'data_import',
    'main.import_teachers': 'data_import',
}


def is_export_endpoint(endpoint):
    """True for list / sheet download endpoints (their name contains "export")."""
    return bool(endpoint) and 'export' in endpoint.split('.')[-1].lower()


def feature_for_endpoint(endpoint, module=None):
    """Return the feature key guarding ``endpoint`` (or None for core pages)."""
    if not endpoint:
        return None
    feature = ENDPOINT_FEATURES.get(endpoint)
    if feature:
        return feature
    return MODULE_FEATURES.get(module or '')


def normalize_features(value):
    """Clean a features list: known keys only, catalog order, no duplicates.

    ``None`` stays ``None`` (legacy key = everything on).
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',')]
    wanted = {str(item).strip() for item in (value or [])}
    return [key for key in ALL_FEATURES if key in wanted]


# -- user roles -------------------------------------------------------------
# (key, label, description).  The administrator role is always on, otherwise a school
# could be locked out of its own software.
ROLE_CATALOG = (
    ('admin', 'Administrator', 'Full control of the school. Always on.'),
    ('teacher', 'Teacher', 'Marks attendance and enters marks for own classes.'),
    ('accountant', 'Accountant', 'Fees, receipts, expenses and payroll.'),
    ('owner', 'Principal / Owner', 'Read-only executive dashboard and reports.'),
    ('parent', 'Parent', 'Parent portal logins (own children only).'),
    ('guard', 'Gate Guard', 'Guard phone app that scans student QR ID cards.'),
)
ALL_ROLES = tuple(item[0] for item in ROLE_CATALOG)
ALWAYS_ON_ROLES = ('admin',)
ROLE_LABELS_VENDOR = {key: label for key, label, _desc in ROLE_CATALOG}


def normalize_roles(value):
    """Clean a roles list: known keys only, catalog order, admin always included.

    ``None`` stays ``None`` (legacy key = every role on).
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',')]
    wanted = {str(item).strip() for item in (value or [])} | set(ALWAYS_ON_ROLES)
    return [key for key in ALL_ROLES if key in wanted]


# -- plan presets (starting points the dashboard can edit) ------------------

DEFAULT_PLANS = {
    'basic': {
        'label': 'Basic',
        'features': ['attendance', 'exams', 'documents', 'timetable', 'data_export'],
        'wa_daily': 0,
        'wa_monthly': 0,
    },
    'standard': {
        'label': 'Standard',
        'features': ['expenses', 'payroll', 'admission_fees', 'attendance',
                     'exams', 'documents', 'timetable', 'parent_portal',
                     'whatsapp', 'data_import', 'data_export', 'language_switch'],
        'wa_daily': 100,
        'wa_monthly': 2000,
    },
    'premium': {
        'label': 'Premium',
        'features': list(ALL_FEATURES),
        'wa_daily': 250,
        'wa_monthly': 5000,
    },
}

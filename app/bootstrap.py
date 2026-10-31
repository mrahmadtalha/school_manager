"""Application start-up: blueprints, default accounts, demo data and background jobs.

The schema migrations live in ``app.migrations``; every migration name is re-exported here so
``from app.bootstrap import migrate_...`` keeps working.
"""
import os
from werkzeug.security import generate_password_hash

from app.database import db
from app.models import ROLE_ADMIN, ROLE_TEACHER, ROLE_PARENT
from app.migrations.common import (  # noqa: F401  (re-exported for existing importers)
    _safety_backup,
    _sqlite_connection,
    _sqlite_db_path,
    _table_columns,
)
from app.migrations.accounts import (  # noqa: F401  (re-exported for existing importers)
    migrate_admin_schema,
    migrate_guardian_links,
    migrate_user_teacher_link_schema,
)
from app.migrations.attendance_qr import (  # noqa: F401  (re-exported for existing importers)
    migrate_attendance_schema,
    migrate_automation_schema,
    migrate_qr_config_schema,
)
from app.migrations.students import (  # noqa: F401  (re-exported for existing importers)
    migrate_student_enrollments,
    migrate_student_fee_schema,
    migrate_student_profile_schema,
    migrate_student_roll_schema,
    migrate_student_status_schema,
)
from app.migrations.teachers_classes import (  # noqa: F401  (re-exported for existing importers)
    LEGACY_DEFAULT_SUBJECT_KEYS,
    link_subjects_to_library,
    migrate_class_integrity_schema,
    migrate_subject_library_schema,
    migrate_teacher_profile_schema,
    migrate_teacher_schema,
    migrate_timetable_schema,
    seed_teaching_assignments,
)
from app.migrations.finance import (  # noqa: F401  (re-exported for existing importers)
    EXPENSES_TABLE_SQL,
    FEE_RECORDS_TABLE_SQL,
    FINANCIAL_V2_TABLES_SQL,
    STAFF_PAYROLL_TABLE_SQL,
    _admission_fee_columns,
    backfill_financial_v2,
    migrate_admission_fee_schema,
    migrate_expense_schema,
    migrate_financial_v2_schema,
    migrate_inventory_schema,
    migrate_payment_apply_month,
)
from app.migrations.exams_dashboard import (  # noqa: F401  (re-exported for existing importers)
    migrate_dashboard_schema,
    migrate_school_settings_schema,
    migrate_term_exam_schema,
    migrate_test_schema,
)


def register_blueprints(app):
    from app.auth import auth
    from app.routes import main

    app.register_blueprint(main)
    app.register_blueprint(auth)


def create_default_admin():
    from app.models import AdminUser

    if AdminUser.query.first():
        return

    username = os.environ.get('INITIAL_ADMIN_USERNAME') or os.environ.get('ADMIN_USERNAME')
    password = os.environ.get('INITIAL_ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD')

    if username and password:
        default = AdminUser(
            username=username,
            password_hash=generate_password_hash(password),
            role=ROLE_ADMIN,
            full_name='Administrator',
        )
        db.session.add(default)
        db.session.commit()
        print(f'Initial admin created — username: {username}')
        return

    print('No admin account configured. Set INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD or create one via /setup-admin.')


_auto_backup_started = False


def install_auto_backup(app):
    """Start the in-process automatic backup check (disabled for tests).

    Every check looks at the newest backup (manual or automatic) and writes a
    fresh rotating copy into ``instance/backups/auto`` when nothing has been
    backed up for ``AUTO_BACKUP_INTERVAL_HOURS`` (default 24).  The newest
    ``BACKUP_RETENTION_COUNT`` (default 30) automatic backups are kept;
    manual backups are never pruned.
    """
    global _auto_backup_started
    if app.config.get('TESTING') or _auto_backup_started:
        return
    if os.environ.get('AUTO_BACKUP_ENABLED', '1').strip().lower() in {'0', 'false', 'no', 'off'}:
        return

    import threading
    import time

    from app.services import db_backup

    def _loop():
        time.sleep(60)  # let short-lived scripts finish before the first check
        while True:
            try:
                db_path = _sqlite_db_path(app)
                if db_path and db_path != ':memory:' and os.path.exists(db_path):
                    summary = db_backup.backup_if_due(db_path=db_path)
                    if summary['created']:
                        print(f'Auto-backup created: {summary["created"]}')
                    for name in summary['pruned']:
                        print(f'Auto-backup pruned: {name}')
            except Exception as exc:  # the loop must never die
                print(f'WARNING: automatic backup check failed: {exc}')
            time.sleep(1800)

    threading.Thread(target=_loop, name='auto-backup', daemon=True).start()
    _auto_backup_started = True


_auto_absent_started = False


def install_auto_absent(app):
    """Start the in-process check that marks absentees after the cutoff time.

    Once a minute it asks ``qr_absent.run_auto_absent`` whether today's cutoff
    has passed and no check has run yet.  Disabled for tests (they call the
    service directly) and with ``AUTO_ABSENT_ENABLED=0``.  Because the check is
    "cutoff passed and not done yet", opening School Manager after the cutoff
    still runs it once for that day.
    """
    global _auto_absent_started
    if app.config.get('TESTING') or _auto_absent_started:
        return
    if os.environ.get('AUTO_ABSENT_ENABLED', '1').strip().lower() in {'0', 'false', 'no', 'off'}:
        return

    import threading
    import time

    def _loop():
        time.sleep(45)
        while True:
            try:
                from app.services import qr_absent
                with app.app_context():
                    outcome = qr_absent.run_auto_absent()
                    if outcome and outcome.get('ran'):
                        print(f'Auto-absent: {outcome["status"]} ({outcome["marked"]} marked)')
            except Exception as exc:  # the loop must never die
                print(f'WARNING: auto-absent check failed: {exc}')
            time.sleep(60)

    threading.Thread(target=_loop, name='auto-absent', daemon=True).start()
    _auto_absent_started = True


def ensure_school_settings():
    from app.models import SchoolSettings

    if not SchoolSettings.query.first():
        db.session.add(SchoolSettings(school_name='School Manager'))
        db.session.commit()


def seed_demo_data(student_count=60, teacher_count=8, default_monthly_fee=2500.0):
    """Legacy entry point kept for compatibility — delegates to the generator.

    The advanced generator (app/services/seed_generator.py) supersedes the old
    inline classes/teachers/students seeding; this wrapper produces a short
    3-month demo history when called without explicit options.
    """
    from app.services.seed_generator import SeedConfig, run_seed

    run_seed(SeedConfig(
        student_count=max(0, int(student_count)),
        teacher_count=max(0, int(teacher_count)),
        monthly_fee=float(default_monthly_fee),
        months=3,
    ))


def ensure_demo_accounts(default_password=None):
    """Create one teacher and one parent demo account when missing."""
    from app.models import AdminUser, GuardianStudentLink, StudentModel

    password = default_password or os.environ.get('DEFAULT_DEMO_PASSWORD')

    if not AdminUser.query.filter_by(username='teacher1').first():
        teacher_user = AdminUser(username='teacher1', role=ROLE_TEACHER, full_name='Demo Teacher')
        teacher_user.set_password(password)
        db.session.add(teacher_user)

    first_student = (StudentModel.query.filter_by(is_active=True)
                     .order_by(StudentModel.id).first())
    if first_student and not AdminUser.query.filter_by(username='parent1').first():
        parent_user = AdminUser(
            username='parent1',
            role=ROLE_PARENT,
            full_name=f'Guardian of {first_student.student_name}',
            student_id=first_student.id,
        )
        parent_user.set_password(password)
        db.session.add(parent_user)
        db.session.flush()
        db.session.add(GuardianStudentLink(user_id=parent_user.id,
                                           student_id=first_student.id))

    return password


def inject_school_settings(app):
    from app.models import SchoolSettings

    @app.context_processor
    def inject_school():
        school = SchoolSettings.query.first()
        return {'school': school,
                'features': {'inventory_sales': app.config.get('FEATURE_INVENTORY_SALES', False),
                             'advance_credit_writeoff':
                             app.config.get('FEATURE_ADVANCE_CREDIT_WRITEOFF', False)}}

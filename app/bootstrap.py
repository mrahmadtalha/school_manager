import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import generate_password_hash

from app.database import db
from app.models import ROLE_ADMIN, ROLE_TEACHER, ROLE_PARENT


@contextmanager
def _sqlite_connection(path):
    """Open a short-lived SQLite connection and always close it.

    ``with sqlite3.connect(...)`` only commits/rolls back - it does not close
    the connection, which leaks file handles (and blocks cleanup on Windows).
    """
    connection = sqlite3.connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


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


def _sqlite_db_path(app):
    """Resolve the SQLite file the app is actually configured to use."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if isinstance(uri, str) and uri.startswith('sqlite:///'):
        raw = uri[len('sqlite:///'):].split('?', 1)[0]
        if not raw or raw == ':memory:':
            return raw
        if os.path.isabs(raw) or (len(raw) > 1 and raw[1] == ':'):
            return os.path.normpath(raw)
        return os.path.normpath(os.path.join(app.root_path, raw))
    return os.path.join(app.instance_path, 'school.db')


def _table_columns(connection, table):
    """Column names for ``table``, or an empty list when it does not exist."""
    exists = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return []
    return [row[1] for row in connection.execute(f'PRAGMA table_info({table})').fetchall()]


def migrate_admin_schema(app):
    """Add role/parent-link columns to an existing admin_users table."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'admin_users')
        if not columns:
            return

        additions = [
            ('full_name', 'VARCHAR(120)'),
            ('role', "VARCHAR(20) DEFAULT 'admin'"),
            ('student_id', 'INTEGER'),
            ('is_active', 'BOOLEAN DEFAULT 1'),
            ('created_at', 'DATETIME'),
            ('last_login_at', 'DATETIME'),
        ]
        for name, ddl in additions:
            if name not in columns:
                connection.execute(f'ALTER TABLE admin_users ADD COLUMN {name} {ddl}')
                print(f'Migration: added {name} to admin_users')

        # Existing accounts predate roles; make them administrators.
        connection.execute("UPDATE admin_users SET role = 'admin' WHERE role IS NULL OR role = ''")
        connection.execute('UPDATE admin_users SET is_active = 1 WHERE is_active IS NULL')
        connection.commit()


def migrate_attendance_schema(app):
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'attendance')
        if not columns:
            return

        if 'is_locked' not in columns:
            connection.execute('ALTER TABLE attendance ADD COLUMN is_locked BOOLEAN DEFAULT 0')
            print('Migration: added is_locked to attendance')

        if 'late_time' not in columns:
            connection.execute('ALTER TABLE attendance ADD COLUMN late_time VARCHAR(10)')
            print('Migration: added late_time to attendance')
        if 'late_minutes' not in columns:
            connection.execute('ALTER TABLE attendance ADD COLUMN late_minutes INTEGER')
            print('Migration: added late_minutes to attendance')

        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_target_date ON attendance(target_type, target_id, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_class_date ON attendance(class_id, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_target_type_date ON attendance(target_type, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_students_class_active ON students(class_id, is_active)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_student_marks_test_student ON student_marks(test_id, student_id)')
        connection.commit()


def migrate_student_roll_schema(app):
    """Rebuild the students table: integer roll numbers, unique per class.

    Legacy databases store roll numbers as text (for example ``RN-1001``) under
    a single global unique index.  They are renumbered per class starting at
    ``FIRST_ROLL_NUMBER``; a backup of the database is written before the
    rebuild (see ``app/services/roll_numbers.py``).
    """
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:' or not os.path.exists(db_path):
        return

    from app.services.roll_numbers import FIRST_ROLL_NUMBER, migrate_students_table

    summary = migrate_students_table(db_path)
    if not summary:
        return

    print('Migration: students table rebuilt - roll numbers are now plain integers '
          f'unique per class, renumbered from {FIRST_ROLL_NUMBER} '
          f'({summary["students_total"]} students across {len(summary["per_class"])} classes).')
    if summary.get('backup_path'):
        print(f'Migration: pre-migration backup written to {summary["backup_path"]}')


def migrate_guardian_links(app):
    """Backfill the guardian_students link table from the legacy student_id column.

    Older databases link a parent account to a single child through
    ``admin_users.student_id``.  That column is kept, but reading code uses the
    link table, so every legacy link is mirrored once (idempotent).
    """
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:' or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        if not _table_columns(connection, 'guardian_students'):
            return

        legacy = connection.execute(
            'SELECT a.id, a.student_id FROM admin_users a '
            'WHERE a.student_id IS NOT NULL AND NOT EXISTS ('
            '    SELECT 1 FROM guardian_students g '
            '    WHERE g.user_id = a.id AND g.student_id = a.student_id)'
        ).fetchall()
        for user_id, student_id in legacy:
            connection.execute(
                'INSERT INTO guardian_students (user_id, student_id) VALUES (?, ?)',
                (user_id, student_id),
            )
            print(f'Migration: linked student {student_id} to guardian account {user_id}')

        missing_primary = connection.execute(
            'SELECT a.id, MIN(g.student_id) FROM admin_users a '
            'JOIN guardian_students g ON g.user_id = a.id '
            'WHERE a.student_id IS NULL GROUP BY a.id'
        ).fetchall()
        for user_id, student_id in missing_primary:
            connection.execute(
                'UPDATE admin_users SET student_id = ? WHERE id = ?',
                (student_id, user_id),
            )
            print(f'Migration: set primary student {student_id} for guardian account {user_id}')

        connection.commit()


def migrate_automation_schema(app):
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        queue_columns = _table_columns(connection, 'message_queue')
        if 'retry_count' not in queue_columns and queue_columns:
            connection.execute('ALTER TABLE message_queue ADD COLUMN retry_count INTEGER DEFAULT 0')
            print('Migration: added retry_count to message_queue')

        automation_columns = _table_columns(connection, 'automation_settings')
        if automation_columns:
            additions = (
                ('last_successful_send_at', 'DATETIME'),
                ('integration_method', "VARCHAR(20) NOT NULL DEFAULT 'qr_scan'"),
                ('whatsapp_api_token', 'TEXT'),
                ('whatsapp_phone_number_id', 'VARCHAR(100)'),
                ('whatsapp_business_account_id', 'VARCHAR(100)'),
                ('notify_fee_reminders', 'BOOLEAN DEFAULT 1'),
                ('notify_fee_receipts', 'BOOLEAN DEFAULT 0'),
            )
            for name, ddl in additions:
                if name not in automation_columns:
                    connection.execute(
                        f'ALTER TABLE automation_settings ADD COLUMN {name} {ddl}')
                    print(f'Migration: added {name} to automation_settings')

        delivery_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_logs'"
        ).fetchone()
        if not delivery_table:
            connection.execute('''
                CREATE TABLE delivery_logs (
                    id INTEGER PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_msg TEXT,
                    details TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(message_id) REFERENCES message_queue(id)
                )
            ''')
            print('Migration: created delivery_logs table')

        connection.commit()


def migrate_teacher_schema(app):
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        teacher_columns = _table_columns(connection, 'teachers')
        if not teacher_columns:
            return
        if 'salary_type' not in teacher_columns:
            connection.execute("ALTER TABLE teachers ADD COLUMN salary_type VARCHAR(20) DEFAULT 'monthly'")
            print('Migration: added salary_type to teachers')
        if 'monthly_salary' not in teacher_columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN monthly_salary FLOAT DEFAULT 0')
            print('Migration: added monthly_salary to teachers')
        if 'hourly_rate' not in teacher_columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN hourly_rate FLOAT DEFAULT 0')
            print('Migration: added hourly_rate to teachers')

        for column, ddl in (
            ('cnic', 'VARCHAR(30)'),
            ('address', 'TEXT'),
            ('contact_number', 'VARCHAR(30)'),
            ('emergency_contact_number', 'VARCHAR(30)'),
            ('previous_experience_years', 'FLOAT'),
            ('previous_salary', 'FLOAT'),
            ('assigned_classes', 'TEXT'),
            ('assigned_subjects', 'TEXT'),
        ):
            if column not in teacher_columns:
                connection.execute(f'ALTER TABLE teachers ADD COLUMN {column} {ddl}')
                print(f'Migration: added {column} to teachers')

        connection.commit()


def migrate_teacher_profile_schema(app):
    """Teacher profile extras: designation/gender columns + salary normalization."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'teachers')
        if not columns:
            return
        if 'designation' not in columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN designation VARCHAR(80)')
            print('Migration: added designation to teachers')
        if 'gender' not in columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN gender VARCHAR(20)')
            print('Migration: added gender to teachers')

        # Salary normalization: monthly_salary is the single source of truth;
        # backfill it once from the legacy salary column where it is still empty.
        cursor = connection.execute(
            'UPDATE teachers SET monthly_salary = salary '
            'WHERE (monthly_salary IS NULL OR monthly_salary = 0) '
            "AND salary > 0 AND COALESCE(salary_type, 'monthly') != 'hourly'")
        if cursor.rowcount:
            print('Migration: backfilled monthly_salary from salary for %d teacher(s)'
                  % cursor.rowcount)

        if not connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                ('idx_teachers_is_active',)).fetchone():
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_teachers_is_active ON teachers(is_active)')
            print('Migration: created index idx_teachers_is_active')

        connection.commit()


def migrate_class_integrity_schema(app):
    """Class integrity: subject archiving column, indexes and unique name guards."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        subject_columns = _table_columns(connection, 'subjects')
        if subject_columns:
            if 'is_active' not in subject_columns:
                connection.execute('ALTER TABLE subjects ADD COLUMN is_active BOOLEAN DEFAULT 1')
                print('Migration: added is_active to subjects')
            connection.execute('UPDATE subjects SET is_active = 1 WHERE is_active IS NULL')

        def _has_index(name):
            return connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
            ).fetchone()

        for index_name, statement in (
            ('idx_sections_class', 'CREATE INDEX IF NOT EXISTS idx_sections_class ON sections(class_id)'),
            ('idx_subjects_class', 'CREATE INDEX IF NOT EXISTS idx_subjects_class ON subjects(class_id)'),
            ('uq_sections_class_name',
             'CREATE UNIQUE INDEX IF NOT EXISTS uq_sections_class_name ON sections(class_id, name)'),
            ('uq_subjects_class_name',
             'CREATE UNIQUE INDEX IF NOT EXISTS uq_subjects_class_name ON subjects(class_id, name)'),
        ):
            if _has_index(index_name):
                continue
            try:
                connection.execute(statement)
                print('Migration: created index %s' % index_name)
            except Exception as exc:  # duplicate data present — skip, app layer still guards
                print('Migration: skipped %s (%s)' % (index_name, exc))

        connection.commit()


def migrate_timetable_schema(app):
    """Optional subject-teacher mapping: subjects.teacher_id column (timetable_slots
    table is created automatically by db.create_all())."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        subject_columns = _table_columns(connection, 'subjects')
        if subject_columns and 'teacher_id' not in subject_columns:
            connection.execute('ALTER TABLE subjects ADD COLUMN teacher_id INTEGER')
            print('Migration: added teacher_id to subjects')
        connection.commit()


def migrate_user_teacher_link_schema(app):
    """Optional link between login accounts and teacher records (admin_users.teacher_id)."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'admin_users')
        if columns and 'teacher_id' not in columns:
            connection.execute('ALTER TABLE admin_users ADD COLUMN teacher_id INTEGER')
            print('Migration: added teacher_id to admin_users')
        connection.commit()


def migrate_school_settings_schema(app):
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        settings_columns = _table_columns(connection, 'school_settings')
        if not settings_columns:
            return
        if 'school_start_time' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN school_start_time VARCHAR(10) DEFAULT '08:30'")
            print('Migration: added school_start_time to school_settings')
        if 'attendance_grace_minutes' not in settings_columns:
            connection.execute('ALTER TABLE school_settings ADD COLUMN attendance_grace_minutes INTEGER DEFAULT 0')
            print('Migration: added attendance_grace_minutes to school_settings')
        if 'school_end_time' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN school_end_time VARCHAR(10) DEFAULT '15:00'")
            print('Migration: added school_end_time to school_settings')
        if 'weekend_off' not in settings_columns:
            connection.execute('ALTER TABLE school_settings ADD COLUMN weekend_off BOOLEAN DEFAULT 1')
            print('Migration: added weekend_off to school_settings')
        if 'custom_off_days' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN custom_off_days VARCHAR(200) DEFAULT ''")
            print('Migration: added custom_off_days to school_settings')
        if 'academic_session' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN academic_session VARCHAR(50) DEFAULT ''")
            print('Migration: added academic_session to school_settings')
        if 'result_announcement_date' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN result_announcement_date VARCHAR(20) DEFAULT ''")
            print('Migration: added result_announcement_date to school_settings')

        connection.commit()


def migrate_student_fee_schema(app):
    """Add class-fee / discount columns (classes.monthly_fee, students.class_fee, ...)."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        class_columns = _table_columns(connection, 'classes')
        if class_columns and 'monthly_fee' not in class_columns:
            connection.execute('ALTER TABLE classes ADD COLUMN monthly_fee FLOAT')
            print('Migration: added monthly_fee to classes')

        student_columns = _table_columns(connection, 'students')
        if student_columns:
            if 'class_fee' not in student_columns:
                connection.execute('ALTER TABLE students ADD COLUMN class_fee FLOAT')
                print('Migration: added class_fee to students')
            if 'discount_type' not in student_columns:
                connection.execute('ALTER TABLE students ADD COLUMN discount_type VARCHAR(20)')
                print('Migration: added discount_type to students')
            if 'discount_value' not in student_columns:
                connection.execute('ALTER TABLE students ADD COLUMN discount_value FLOAT')
                print('Migration: added discount_value to students')

        connection.commit()


def migrate_student_status_schema(app):
    """Add the student status lifecycle columns and backfill archived students.

    Older databases only had the ``is_active`` flag; students archived before
    the status lifecycle existed are backfilled to ``slc_issued`` so the
    archive always carries an explicit status.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        student_columns = _table_columns(connection, 'students')
        if not student_columns:
            return
        if 'status' not in student_columns:
            connection.execute("ALTER TABLE students ADD COLUMN status VARCHAR(20) DEFAULT 'enrolled'")
            print('Migration: added status to students')
            cursor = connection.execute("UPDATE students SET status = 'slc_issued' WHERE is_active = 0")
            if cursor.rowcount:
                print(f'Migration: backfilled slc_issued for {cursor.rowcount} archived student(s)')
        if 'leaving_reason' not in student_columns:
            connection.execute('ALTER TABLE students ADD COLUMN leaving_reason VARCHAR(200)')
            print('Migration: added leaving_reason to students')
        if 'leaving_date' not in student_columns:
            connection.execute('ALTER TABLE students ADD COLUMN leaving_date DATE')
            print('Migration: added leaving_date to students')

        connection.commit()


def migrate_student_enrollments(app):
    """Backfill a class-enrollment snapshot for students that have none."""
    from app.models import StudentEnrollment, StudentModel
    from app.services.enrollments import close_open_enrollment, start_enrollment

    with app.app_context():
        existing_ids = {row[0] for row in
                        db.session.query(StudentEnrollment.student_id).distinct().all()}
        query = StudentModel.query
        if existing_ids:
            query = query.filter(StudentModel.id.notin_(existing_ids))
        missing = query.all()
        if not missing:
            return
        for student in missing:
            start_enrollment(student, reason='backfill', start_date=None, end_previous=False)
            if not student.is_active:
                close_open_enrollment(student, end_date=student.leaving_date)
        db.session.commit()
        print(f'Migration: backfilled enrollment history for {len(missing)} student(s)')


def migrate_student_profile_schema(app):
    """Student profile extras: gender, admission fields, status index."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'students')
        if columns:
            if 'gender' not in columns:
                connection.execute('ALTER TABLE students ADD COLUMN gender VARCHAR(10)')
                print('Migration: added gender to students')
            if 'admission_number' not in columns:
                connection.execute('ALTER TABLE students ADD COLUMN admission_number VARCHAR(40)')
                print('Migration: added admission_number to students')
            if 'admission_date' not in columns:
                connection.execute('ALTER TABLE students ADD COLUMN admission_date DATE')
                print('Migration: added admission_date to students')
            if 'sponsor_type' not in columns:
                connection.execute("ALTER TABLE students ADD COLUMN sponsor_type VARCHAR(20) NOT NULL DEFAULT 'Father'")
                print('Migration: added sponsor_type to students')
            if 'sponsor_cnic' not in columns:
                connection.execute('ALTER TABLE students ADD COLUMN sponsor_cnic VARCHAR(20)')
                print('Migration: added sponsor_cnic to students')
            index_row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_students_status'").fetchone()
            if not index_row:
                connection.execute(
                    'CREATE INDEX IF NOT EXISTS idx_students_status ON students(status)')
                print('Migration: created index idx_students_status')
        connection.commit()


def migrate_term_exam_schema(app):
    """Split evaluation: term-exam columns, scope seeds and indexes."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        test_columns = _table_columns(connection, 'tests')
        if test_columns:
            if 'term_exam_id' not in test_columns:
                connection.execute('ALTER TABLE tests ADD COLUMN term_exam_id INTEGER')
                print('Migration: added term_exam_id to tests')
            if 'start_time' not in test_columns:
                connection.execute('ALTER TABLE tests ADD COLUMN start_time VARCHAR(10)')
                print('Migration: added start_time to tests')
            if 'room' not in test_columns:
                connection.execute('ALTER TABLE tests ADD COLUMN room VARCHAR(60)')
                print('Migration: added room to tests')

        type_columns = _table_columns(connection, 'test_types')
        if type_columns and 'scope' not in type_columns:
            connection.execute('ALTER TABLE test_types ADD COLUMN scope VARCHAR(20)')
            print('Migration: added scope to test_types')

        # Seed scopes for well-known categories (idempotent).
        connection.execute(
            "UPDATE test_types SET scope='class_test' WHERE scope IS NULL "
            "AND lower(name) IN ('daily','weekly','monthly')")
        connection.execute(
            "UPDATE test_types SET scope='term_exam' WHERE scope IS NULL "
            "AND lower(name) IN ('mid-term','midterm','mid term','final','annual',"
            "'pre-board','preboard','pre board')")

        if type_columns:
            exists = connection.execute(
                "SELECT id FROM test_types WHERE lower(name) = 'pre-board'").fetchone()
            if not exists:
                connection.execute(
                    "INSERT INTO test_types (name, scope) VALUES ('Pre-Board', 'term_exam')")
                print('Migration: added Pre-Board test category')

        if test_columns:
            index_row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_tests_term_exam'").fetchone()
            if not index_row:
                connection.execute(
                    'CREATE INDEX IF NOT EXISTS idx_tests_term_exam ON tests(term_exam_id)')
                print('Migration: created index idx_tests_term_exam')

        connection.commit()


def migrate_test_schema(app):
    """Add per-category default marks to test types."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'test_types')
        if columns and 'default_marks' not in columns:
            connection.execute('ALTER TABLE test_types ADD COLUMN default_marks FLOAT')
            print('Migration: added default_marks to test_types')
        connection.commit()


def migrate_dashboard_schema(app):
    """Add date_of_birth columns and dashboard performance indexes."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        for table in ('students', 'teachers'):
            columns = _table_columns(connection, table)
            if columns and 'date_of_birth' not in columns:
                connection.execute('ALTER TABLE %s ADD COLUMN date_of_birth DATE' % table)
                print('Migration: added date_of_birth to %s' % table)

        index_specs = (
            ('students', 'idx_students_dob', 'students(date_of_birth)'),
            ('teachers', 'idx_teachers_dob', 'teachers(date_of_birth)'),
            ('expenses', 'idx_expenses_date', 'expenses(date)'),
            ('fee_records', 'idx_fee_records_month', 'fee_records(month_year)'),
            ('staff_payroll', 'idx_staff_payroll_month', 'staff_payroll(month_year)'),
        )
        for table, index_name, target in index_specs:
            if not _table_columns(connection, table):
                continue
            exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index_name,)).fetchone()
            if exists:
                continue
            connection.execute('CREATE INDEX IF NOT EXISTS %s ON %s' % (index_name, target))
            print('Migration: created index %s' % index_name)

        connection.commit()


def migrate_expense_schema(app):
    """Seed default expense categories when none exist yet."""
    from app.models import DEFAULT_EXPENSE_CATEGORIES, ExpenseCategory

    with app.app_context():
        if ExpenseCategory.query.count() > 0:
            return
        for name in DEFAULT_EXPENSE_CATEGORIES:
            db.session.add(ExpenseCategory(name=name))
        db.session.commit()
        print('Migration: seeded %d default expense categories'
              % len(DEFAULT_EXPENSE_CATEGORIES))


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


def ensure_school_settings():
    from app.models import SchoolSettings

    if not SchoolSettings.query.first():
        db.session.add(SchoolSettings(school_name='School Manager'))
        db.session.commit()


def seed_demo_data(student_count=60, teacher_count=8, default_monthly_fee=2500.0):
    from app.models import ClassModel, SectionModel, SubjectModel, TeacherModel, StudentModel, TestTypeModel

    class_names = [
        'Playgroup', 'Nursery', 'Class 1', 'Class 2', 'Class 3',
        'Class 4', 'Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10'
    ]
    subject_names = ['English', 'Urdu', 'Mathematics', 'Science', 'Islamiyat']
    test_types = ['Daily', 'Weekly', 'Monthly', 'Mid-Term', 'Final']

    classes = []
    for class_name in class_names:
        class_obj = ClassModel.query.filter_by(name=class_name).first()
        if class_obj is None:
            class_obj = ClassModel(name=class_name)
            db.session.add(class_obj)
            db.session.flush()
        classes.append(class_obj)

        for section_name in ['A', 'B']:
            if not SectionModel.query.filter_by(class_id=class_obj.id, name=section_name).first():
                db.session.add(SectionModel(name=section_name, class_id=class_obj.id))

        for subject_name in subject_names:
            if not SubjectModel.query.filter_by(class_id=class_obj.id, name=subject_name).first():
                db.session.add(SubjectModel(name=subject_name, class_id=class_obj.id))

    for test_name in test_types:
        if not TestTypeModel.query.filter_by(name=test_name).first():
            db.session.add(TestTypeModel(name=test_name))

    teacher_total = max(0, int(teacher_count))
    if TeacherModel.query.count() == 0 and teacher_total > 0:
        teacher_names = [
            'M. Akram', 'Ayesha Bibi', 'Tariq Mahmood', 'Sana Khan', 'Usman Ali',
            'Farah Nadeem', 'Ali Raza', 'Hina Malik', 'Bilal Ahmed', 'Maryam Noor',
            'Zahid Hassan', 'Nadia Shahid', 'Kashif Aslam', 'Saima Qureshi'
        ]
        for idx in range(teacher_total):
            teacher_name = teacher_names[idx % len(teacher_names)]
            assigned_class = classes[idx % len(classes)].name
            db.session.add(TeacherModel(
                teacher_id_str=f'T{idx + 1:03d}',
                teacher_name=teacher_name,
                joining_date=datetime.utcnow().date(),
                qualification='B.Ed / M.Ed',
                salary=35000 + (idx * 1500),
                assigned_class=assigned_class,
            ))

    student_total = max(0, int(student_count))
    if StudentModel.query.count() == 0 and student_total > 0:
        from app.services.roll_numbers import FIRST_ROLL_NUMBER

        first_names = ['Ali', 'Ahmed', 'Hassan', 'Hussain', 'Bilal', 'Ayesha', 'Fatima', 'Maryam', 'Hamza', 'Zain']
        last_names = ['Khan', 'Awan', 'Malik', 'Rana', 'Qureshi', 'Abbasi']
        class_list = ClassModel.query.order_by(ClassModel.id).all()
        if not class_list:
            class_list = classes

        next_rolls = {}
        for index in range(student_total):
            class_obj = class_list[index % len(class_list)]
            sections = SectionModel.query.filter_by(class_id=class_obj.id).order_by(SectionModel.id).all()
            section = sections[index % len(sections)] if sections else None
            first_name = first_names[index % len(first_names)]
            last_name = last_names[index % len(last_names)]
            next_roll = next_rolls.get(class_obj.id, FIRST_ROLL_NUMBER)
            next_rolls[class_obj.id] = next_roll + 1
            student = StudentModel(
                roll_number=next_roll,
                student_name=f'{first_name} {last_name}',
                father_name=f'Father of {first_name}',
                guardian_phone=f'+923{(300 + index) % 900:03d}{(1234567 + index) % 10000000:07d}',
                address='Main Bazaar, Sargodha',
                class_id=class_obj.id,
                section_id=section.id if section else None,
                monthly_fee=float(default_monthly_fee),
            )
            db.session.add(student)

    db.session.flush()

    ensure_demo_accounts()

    db.session.commit()


def ensure_demo_accounts(default_password=None):
    """Create one teacher and one parent demo account when missing."""
    from app.models import AdminUser, GuardianStudentLink, StudentModel

    password = default_password or os.environ.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'

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
        return {'school': school}

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
        if 'photo_filename' not in columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN photo_filename VARCHAR(120)')
            print('Migration: added photo_filename to teachers')

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


def drop_timetable_draft_table(app):
    """Drop the obsolesced ``timetable_drafts`` table.

    The draft preview/apply workflow was replaced by the redesigned Timetables
    page, which applies a generation immediately.  The table only ever held
    short-lived scratch payloads, so dropping it loses nothing.  A missing
    table is a no-op.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return
    with _sqlite_connection(db_path) as connection:
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='timetable_drafts'"
        ).fetchone()
        if exists:
            connection.execute('DROP TABLE timetable_drafts')
            connection.commit()
            print('Migration: dropped obsolete timetable_drafts table')


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


def migrate_subject_library_schema(app):
    """Global Subject Library (Phase 1): subjects.library_id column.

    The subject_library table itself is created by db.create_all().  When an
    existing database first gains the column, a safety backup is taken first
    and a one-time auto-link pass then connects every class subject to its
    library entry (see link_subjects_to_library).  Nothing is renamed,
    merged or deleted.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        subject_columns = _table_columns(connection, 'subjects')
        if subject_columns and 'library_id' not in subject_columns:
            from app.services.db_backup import backup_database
            backup = backup_database(db_path=db_path)
            print(f'Migration: safety backup before subject-library link: {backup}')
            connection.execute('ALTER TABLE subjects ADD COLUMN library_id INTEGER')
            print('Migration: added library_id to subjects')
        connection.commit()


# Class subjects historically auto-created for every new class; marked as the
# default selection in the Subject Library on the one-time linking pass.
LEGACY_DEFAULT_SUBJECT_KEYS = ('english', 'urdu', 'mathematics', 'islamiyat')


def link_subjects_to_library():
    """One-time auto-link of existing class subjects to the Subject Library.

    Guarded by the ``subject_library_linked`` system setting.  Every class
    subject is linked to the library entry with the same name
    (case-insensitive); the entry is created when missing, keeping the most
    common spelling already in use.  Afterwards the historic defaults
    (English, Urdu, Mathematics, Islamiyat) are marked as the default
    selection for new classes — only when nothing is marked yet, so school
    choices made later are never overwritten.
    """
    from app.models import SubjectLibrary, SubjectModel, SystemSettingModel

    flag = SystemSettingModel.query.filter_by(key='subject_library_linked').first()
    if flag and flag.value == '1':
        return
    if flag is None:
        flag = SystemSettingModel(key='subject_library_linked', value='1')
        db.session.add(flag)

    library_by_lower = {lib.name.strip().lower(): lib for lib in SubjectLibrary.query.all()}
    unlinked = SubjectModel.query.filter(SubjectModel.library_id.is_(None)).all()

    # Pick the most common spelling per subject name so the library entry
    # looks like what the school already types.
    casing_counts = {}
    for subject in unlinked:
        key = subject.name.strip().lower()
        casing_counts.setdefault(key, {})
        casing_counts[key][subject.name.strip()] = casing_counts[key].get(subject.name.strip(), 0) + 1

    for subject in unlinked:
        key = subject.name.strip().lower()
        library = library_by_lower.get(key)
        if library is None:
            name = max(casing_counts[key].items(), key=lambda item: item[1])[0]
            library = SubjectLibrary(name=name, is_active=True, is_default=False)
            db.session.add(library)
            db.session.flush()
            library_by_lower[key] = library
        subject.library_id = library.id

    if not SubjectLibrary.query.filter_by(is_default=True).first():
        for library in library_by_lower.values():
            if library.name.strip().lower() in LEGACY_DEFAULT_SUBJECT_KEYS:
                library.is_default = True

    db.session.commit()
    if unlinked:
        print(f'Subject Library: linked {len(unlinked)} existing class subject(s)')


def seed_teaching_assignments():
    """One-time seed of teaching assignments from legacy subjects.teacher_id links.

    Guarded by the ``teaching_assignments_seeded`` system setting.  Every class
    subject that has both a teacher and a library link gets one class-level
    (section NULL) TeachingAssignment.  From then on the assignments are kept
    in step by the subject edit/archive/restore flows.
    """
    from app.models import SubjectModel, TeachingAssignment, SystemSettingModel

    flag = SystemSettingModel.query.filter_by(key='teaching_assignments_seeded').first()
    if flag and flag.value == '1':
        return
    if flag is None:
        flag = SystemSettingModel(key='teaching_assignments_seeded', value='1')
        db.session.add(flag)

    created = 0
    subjects = (SubjectModel.query
                .filter(SubjectModel.teacher_id.isnot(None),
                        SubjectModel.library_id.isnot(None)).all())
    for subject in subjects:
        exists = TeachingAssignment.query.filter_by(
            teacher_id=subject.teacher_id, library_id=subject.library_id,
            class_id=subject.class_id, section_id=None).first()
        if exists is None:
            db.session.add(TeachingAssignment(
                teacher_id=subject.teacher_id, library_id=subject.library_id,
                class_id=subject.class_id, section_id=None, is_active=True))
            created += 1

    db.session.commit()
    if created:
        print(f'Teaching assignments: created {created} from existing subject teachers')


def migrate_timetable_section_schema(app):
    """Phase 3: timetable_slots.section_id + widened unique slot constraint.

    SQLite cannot alter a table constraint, so on the first run after this
    feature ships the table is rebuilt (with a safety backup first): a
    nullable ``section_id`` column is inserted and the uniqueness becomes
    (class, section, day, period).  Every existing row is copied with
    section_id NULL — class-level slots keep working exactly as before.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        slot_columns = _table_columns(connection, 'timetable_slots')
        if not slot_columns or 'section_id' in slot_columns:
            return

        from app.services.db_backup import backup_database
        backup = backup_database(db_path=db_path)
        print(f'Migration: safety backup before timetable sections rebuild: {backup}')

        # Carry over any indexes so nothing else depends on the old shape.
        connection.execute('''
            CREATE TABLE timetable_slots_new (
                id INTEGER NOT NULL PRIMARY KEY,
                class_id INTEGER NOT NULL,
                section_id INTEGER,
                day_of_week INTEGER NOT NULL,
                period_no INTEGER NOT NULL,
                subject_id INTEGER,
                CONSTRAINT uq_timetable_slot UNIQUE (class_id, section_id, day_of_week, period_no),
                FOREIGN KEY(class_id) REFERENCES classes (id),
                FOREIGN KEY(section_id) REFERENCES sections (id),
                FOREIGN KEY(subject_id) REFERENCES subjects (id)
            )
        ''')
        connection.execute('''
            INSERT INTO timetable_slots_new
                (id, class_id, section_id, day_of_week, period_no, subject_id)
            SELECT id, class_id, NULL, day_of_week, period_no, subject_id
            FROM timetable_slots
        ''')
        connection.execute('DROP TABLE timetable_slots')
        connection.execute('ALTER TABLE timetable_slots_new RENAME TO timetable_slots')
        print('Migration: rebuilt timetable_slots with section_id '
              f'({connection.total_changes} rows preserved)')


def migrate_timetable_redesign_schema(app):
    """Redesigned Timetables page: per-slot teacher override + chosen template.

    ``timetable_slots.teacher_id`` stores a manual/generator teacher for one
    cell (NULL = keep the subject's own teacher); ``timetable_master_configs.
    template_key`` remembers whether the school works with the teacher-wise
    matrix or the class weekly grid.  Both are plain column additions.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        slot_columns = _table_columns(connection, 'timetable_slots')
        if slot_columns and 'teacher_id' not in slot_columns:
            connection.execute('ALTER TABLE timetable_slots ADD COLUMN teacher_id INTEGER')
            print('Migration: added teacher_id to timetable_slots')

        master_columns = _table_columns(connection, 'timetable_master_configs')
        if master_columns and 'template_key' not in master_columns:
            connection.execute("ALTER TABLE timetable_master_configs "
                               "ADD COLUMN template_key VARCHAR(30)")
            print('Migration: added template_key to timetable_master_configs')
        connection.commit()


FINANCIAL_V2_TABLES_SQL = '''
-- fee_transactions: money -> integer paisa; adds payment_date (explicit cash
-- date), related_txn_id (refund -> original payment), void bookkeeping.
CREATE TABLE fee_transactions_new (
    id INTEGER NOT NULL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    month_year VARCHAR(20) NOT NULL,
    txn_type VARCHAR(20) NOT NULL,
    amount_paisa INTEGER NOT NULL DEFAULT 0,
    method VARCHAR(30),
    reference VARCHAR(80),
    note VARCHAR(255),
    is_void BOOLEAN NOT NULL DEFAULT 0,
    void_reason VARCHAR(255),
    voided_at DATETIME,
    voided_by_name VARCHAR(80),
    payment_date DATE,
    related_txn_id INTEGER,
    created_at DATETIME NOT NULL,
    created_by_id INTEGER,
    created_by_name VARCHAR(80) DEFAULT 'system',
    FOREIGN KEY(student_id) REFERENCES students (id),
    FOREIGN KEY(related_txn_id) REFERENCES fee_transactions (id)
)
'''

FEE_RECORDS_TABLE_SQL = '''
CREATE TABLE fee_records_new (
    id INTEGER NOT NULL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    month_year VARCHAR(20) NOT NULL,
    amount_due_paisa INTEGER NOT NULL DEFAULT 0,
    amount_paid_paisa INTEGER NOT NULL DEFAULT 0,
    amount_written_off_paisa INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    payment_date DATE,
    remarks VARCHAR(200),
    FOREIGN KEY(student_id) REFERENCES students (id)
)
'''

STAFF_PAYROLL_TABLE_SQL = '''
CREATE TABLE staff_payroll_new (
    id INTEGER NOT NULL PRIMARY KEY,
    teacher_id INTEGER NOT NULL,
    month_year VARCHAR(10) NOT NULL,
    base_salary_paisa INTEGER NOT NULL DEFAULT 0,
    bonus_paisa INTEGER NOT NULL DEFAULT 0,
    deductions_paisa INTEGER NOT NULL DEFAULT 0,
    net_salary_paisa INTEGER NOT NULL DEFAULT 0,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    payment_date DATE,
    payment_method VARCHAR(20),
    notes VARCHAR(255),
    generated_by VARCHAR(80) DEFAULT 'system',
    updated_by_id INTEGER,
    updated_by_name VARCHAR(80),
    working_days INTEGER,
    present_days INTEGER,
    absent_days INTEGER,
    late_days INTEGER,
    leave_days INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_staff_payroll_teacher_month UNIQUE (teacher_id, month_year),
    FOREIGN KEY(teacher_id) REFERENCES teachers (id)
)
'''

EXPENSES_TABLE_SQL = '''
CREATE TABLE expenses_new (
    id INTEGER NOT NULL PRIMARY KEY,
    category_id INTEGER NOT NULL,
    amount_paisa INTEGER NOT NULL DEFAULT 0,
    payment_method VARCHAR(20) NOT NULL DEFAULT 'Cash',
    date DATE NOT NULL,
    receipt_no VARCHAR(80),
    description VARCHAR(255),
    logged_by_id INTEGER,
    logged_by_name VARCHAR(80) DEFAULT 'system',
    updated_by_id INTEGER,
    updated_by_name VARCHAR(80),
    updated_at DATETIME,
    is_void BOOLEAN NOT NULL DEFAULT 0,
    void_reason VARCHAR(255),
    voided_at DATETIME,
    voided_by_name VARCHAR(80),
    created_at DATETIME NOT NULL,
    FOREIGN KEY(category_id) REFERENCES expense_categories (id)
)
'''


def migrate_financial_v2_schema(app):
    """Financial v2 (Phase 1): integer paisa storage + explicit cash dates.

    Converts the four money tables to integer paisa in one rebuild (SQLite
    cannot change column types), takes a safety backup first, and backfills
    the new columns from existing data:

    * ``fee_transactions``: + ``amount_paisa``, ``payment_date`` (backfilled
      from ``created_at`` shifted UTC -> PKT, +5 hours, for payments),
      ``related_txn_id``, void bookkeeping.
    * ``fee_records``: paisa totals + ``amount_written_off_paisa``.
    * ``staff_payroll``: paisa amounts + ``updated_by`` columns.
    * ``expenses``: paisa amount + void bookkeeping + ``updated_by`` columns.

    Follow-up backfills (payment allocations, salary payments + their Salaries
    expense rows) run once through :func:`backfill_financial_v2` after all
    tables exist.  No row is ever deleted; totals in rupees are unchanged.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        fee_cols = _table_columns(connection, 'fee_transactions')
        if not fee_cols or 'payment_date' in fee_cols:
            return  # fresh install or already migrated

        from app.services.db_backup import backup_database
        backup = backup_database(db_path=db_path)
        print(f'Migration: safety backup before financial v2 conversion: {backup}')

        connection.execute(FINANCIAL_V2_TABLES_SQL)
        connection.execute('''
            INSERT INTO fee_transactions_new
                (id, student_id, month_year, txn_type, amount_paisa, method,
                 reference, note, is_void, created_at, created_by_id,
                 created_by_name, payment_date)
            SELECT id, student_id, month_year, txn_type,
                   CAST(ROUND(COALESCE(amount, 0) * 100) AS INTEGER),
                   method, reference, note, is_void, created_at,
                   created_by_id, created_by_name,
                   CASE WHEN txn_type = 'payment'
                        THEN DATE(created_at, '+5 hours') END
            FROM fee_transactions
        ''')
        connection.execute('DROP TABLE fee_transactions')
        connection.execute('ALTER TABLE fee_transactions_new RENAME TO fee_transactions')

        connection.execute(FEE_RECORDS_TABLE_SQL)
        connection.execute('''
            INSERT INTO fee_records_new
                (id, student_id, month_year, amount_due_paisa, amount_paid_paisa,
                 amount_written_off_paisa, status, payment_date, remarks)
            SELECT id, student_id, month_year,
                   CAST(ROUND(COALESCE(amount_due, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(amount_paid, 0) * 100) AS INTEGER),
                   0, status, payment_date, remarks
            FROM fee_records
        ''')
        connection.execute('DROP TABLE fee_records')
        connection.execute('ALTER TABLE fee_records_new RENAME TO fee_records')

        connection.execute(STAFF_PAYROLL_TABLE_SQL)
        connection.execute('''
            INSERT INTO staff_payroll_new
                (id, teacher_id, month_year, base_salary_paisa, bonus_paisa,
                 deductions_paisa, net_salary_paisa, payment_status, payment_date,
                 payment_method, notes, generated_by, working_days, present_days,
                 absent_days, late_days, leave_days, created_at, updated_at)
            SELECT id, teacher_id, month_year,
                   CAST(ROUND(COALESCE(base_salary, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(bonus, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(deductions, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(net_salary, 0) * 100) AS INTEGER),
                   payment_status, payment_date, payment_method, notes,
                   generated_by, working_days, present_days, absent_days,
                   late_days, leave_days, created_at, updated_at
            FROM staff_payroll
        ''')
        connection.execute('DROP TABLE staff_payroll')
        connection.execute('ALTER TABLE staff_payroll_new RENAME TO staff_payroll')

        connection.execute(EXPENSES_TABLE_SQL)
        connection.execute('''
            INSERT INTO expenses_new
                (id, category_id, amount_paisa, payment_method, date, receipt_no,
                 description, logged_by_id, logged_by_name, created_at)
            SELECT id, category_id,
                   CAST(ROUND(COALESCE(amount, 0) * 100) AS INTEGER),
                   payment_method, date, receipt_no, description,
                   logged_by_id, logged_by_name, created_at
            FROM expenses
        ''')
        connection.execute('DROP TABLE expenses')
        connection.execute('ALTER TABLE expenses_new RENAME TO expenses')

        if 'is_system' not in _table_columns(connection, 'expense_categories'):
            connection.execute("ALTER TABLE expense_categories "
                               "ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT 0")
        # created_at is NOT NULL without a SQL default on legacy tables — supply it.
        connection.execute("INSERT OR IGNORE INTO expense_categories "
                           "(name, is_active, is_system, created_at) "
                           "VALUES ('Salaries', 1, 1, CURRENT_TIMESTAMP)")
        connection.execute('UPDATE expense_categories SET is_system = 1 '
                           "WHERE name = 'Salaries'")

        # A receipt / slip number may only be used by one active transaction.
        connection.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fee_txn_active_reference
            ON fee_transactions(reference)
            WHERE is_void = 0 AND reference IS NOT NULL AND reference <> ''
        ''')
        print('Migration: financial v2 conversion complete '
              '(paisa storage, payment_date backfilled UTC+5h, Salaries category reserved)')


def backfill_financial_v2():
    """One-time derivation of allocations and salary payments from legacy rows.

    Runs after the schema conversion (guard flag ``financial_v2_backfilled``):
    every payment is allocated across the student's outstanding charges
    (its own month first, then older months), every already-Paid payroll row
    gets a SalaryPayment plus its mirrored Salaries expense row, and every
    cached fee summary is recomputed from the new source of truth.
    """
    from datetime import datetime

    from app.models import (Expense, ExpenseCategory, FeeTransaction, SalaryPayment,
                            StaffPayroll, SystemSettingModel, TXN_PAYMENT)
    from app.services.fee_ledger import allocate_transaction, repair_summaries

    flag = SystemSettingModel.query.filter_by(key='financial_v2_backfilled').first()
    if flag and flag.value == '1':
        return
    if flag is None:
        flag = SystemSettingModel(key='financial_v2_backfilled', value='1')
        db.session.add(flag)

    payments = (FeeTransaction.query.filter_by(txn_type=TXN_PAYMENT, is_void=False)
                .order_by(FeeTransaction.created_at, FeeTransaction.id).all())
    for payment in payments:
        allocate_transaction(payment, actor='migration')

    salaries_category = (ExpenseCategory.query.filter_by(name='Salaries').first()
                         or ExpenseCategory(name='Salaries', is_system=True))
    if salaries_category.id is None:
        db.session.add(salaries_category)
        db.session.flush()
    for record in StaffPayroll.query.filter_by(payment_status='Paid').all():
        already = SalaryPayment.query.filter_by(payroll_id=record.id, is_void=False).first()
        if already is not None:
            continue
        payment_date = record.payment_date
        if payment_date is None:
            year, month = record.month_year.split('-')
            from calendar import monthrange
            payment_date = datetime(int(year), int(month), monthrange(int(year), int(month))[1]).date()
        payment = SalaryPayment(
            teacher_id=record.teacher_id, payroll_id=record.id,
            amount_paisa=record.net_salary_paisa, payment_date=payment_date,
            method=record.payment_method or 'Cash',
            note='Migrated from payroll payment status',
            created_by_name='migration')
        db.session.add(payment)
        db.session.flush()
        if salaries_category is not None:
            expense = Expense(
                category_id=salaries_category.id, amount_paisa=record.net_salary_paisa,
                payment_method=payment.method, date=payment_date,
                description='Salary payment (migrated): %s — %s' % (
                    record.teacher.teacher_name if record.teacher else record.teacher_id,
                    record.month_year),
                logged_by_name='migration')
            db.session.add(expense)
            db.session.flush()
            payment.expense_id = expense.id

    repair_summaries()
    db.session.commit()
    print('Financial v2 backfill: allocations + salary payments derived from legacy rows')


# NOTE: fee allocation repair is a deliberate, user-triggered action, not a
# startup step.  It writes ledger rows, so it lives on the Fee Reconciliation
# page (POST /fees/reconciliation/repair) and is never run automatically —
# launching the app must not modify financial data.


def migrate_payment_apply_month(app):
    """Option B allocation rule: add ``fee_transactions.apply_month``.

    The column is the per-transaction allocation override (NULL = default
    oldest-dues-first; a month label settles that month first).  The ALTER is
    additive and safe for SQLite.  Existing payment and write-off rows are
    stamped once with their own ``month_year`` — the rule they were originally
    allocated under — so a later refund re-allocates them exactly as before
    and no migrated figure moves.  New payments stay NULL (oldest-first).
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'fee_transactions')
        if not columns:
            return
        if 'apply_month' not in columns:
            connection.execute('ALTER TABLE fee_transactions '
                               'ADD COLUMN apply_month VARCHAR(20)')
            print('Migration: added apply_month to fee_transactions')

        from app.models import SystemSettingModel
        flag = SystemSettingModel.query.filter_by(
            key='payment_apply_month_stamped').first()
        if flag and flag.value == '1':
            return
        if flag is None:
            flag = SystemSettingModel(key='payment_apply_month_stamped', value='1')
            db.session.add(flag)
        updated = connection.execute(
            "UPDATE fee_transactions SET apply_month = month_year "
            "WHERE apply_month IS NULL AND txn_type IN ('payment', 'writeoff') "
            "AND month_year IS NOT NULL").rowcount
        connection.commit()
        db.session.commit()
        print('Migration: stamped %d existing payment/write-off row(s) '
              'with their original allocation month' % updated)


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
        if 'saturday_off' not in settings_columns:
            # Seed from the legacy weekend_off flag so existing installs keep
            # their Saturday behaviour when the toggle is split in two.
            connection.execute(
                'ALTER TABLE school_settings ADD COLUMN saturday_off BOOLEAN DEFAULT 1')
            connection.execute(
                'UPDATE school_settings SET saturday_off = weekend_off')
            print('Migration: added saturday_off to school_settings')
        if 'sunday_off' not in settings_columns:
            connection.execute(
                'ALTER TABLE school_settings ADD COLUMN sunday_off BOOLEAN DEFAULT 1')
            connection.execute(
                'UPDATE school_settings SET sunday_off = weekend_off')
            print('Migration: added sunday_off to school_settings')
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


def _admission_fee_columns():
    return {
        'students': [
            ('admission_fee_standard_paisa', 'INTEGER'),
            ('admission_fee_net_paisa', 'INTEGER'),
            ('admission_discount_type', 'VARCHAR(20)'),
            ('admission_discount_value', 'FLOAT'),
            ('admission_note', 'VARCHAR(200)'),
            ('admission_fee_date', 'DATE'),
            ('admission_fee_prior_paid_paisa', 'INTEGER'),
        ],
        'classes': [('admission_fee', 'FLOAT')],
        'school_settings': [('default_admission_fee', 'FLOAT')],
        'other_income': [
            ('student_id', 'INTEGER'),
            ('receipt_no', 'VARCHAR(40)'),
            ('payment_method', 'VARCHAR(20)'),
        ],
    }


def _safety_backup(app, db_path, label):
    """Copy the database aside before a schema change; never blocks startup."""
    try:
        from app.services import db_backup
        target = db_backup.backup_database(db_path)
        named = target.with_name('%s-%s%s' % (target.stem, label, target.suffix))
        target.rename(named)
        print('Migration: safety backup written to %s' % named)
        return named
    except Exception as error:  # pragma: no cover - best effort only
        print('Migration: WARNING - could not write a safety backup (%s)' % error)
        return None


def migrate_admission_fee_schema(app):
    """Add the admission-fee columns (all nullable, so nothing changes for
    existing rows: a student without an admission fee simply has none).

    Existing installs get a safety copy of the database first, but only when
    the schema really has to change and the school already holds students.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:' or not os.path.exists(db_path):
        return

    wanted = _admission_fee_columns()
    with _sqlite_connection(db_path) as connection:
        missing = []
        for table, columns in wanted.items():
            existing = _table_columns(connection, table)
            if not existing:
                continue
            missing.extend((table, name, sql_type) for name, sql_type in columns
                           if name not in existing)
        has_students = bool(_table_columns(connection, 'students')) and bool(
            connection.execute('SELECT 1 FROM students LIMIT 1').fetchone())

    if missing and has_students and (
            not app.config.get('TESTING') or app.config.get('PRE_MIGRATION_BACKUP')):
        _safety_backup(app, db_path, 'before-admission-fee')

    with _sqlite_connection(db_path) as connection:
        for table, name, sql_type in missing:
            connection.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, sql_type))
            print('Migration: added %s to %s' % (name, table))
        if _table_columns(connection, 'other_income'):
            connection.execute('CREATE INDEX IF NOT EXISTS idx_other_income_student '
                               'ON other_income (student_id)')
            connection.execute('CREATE INDEX IF NOT EXISTS idx_other_income_receipt '
                               'ON other_income (receipt_no)')
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
            if 'photo_filename' not in columns:
                connection.execute('ALTER TABLE students ADD COLUMN photo_filename VARCHAR(120)')
                print('Migration: added photo_filename to students')
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
    """Add per-category default marks to test types and the absent flag to marks."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'test_types')
        if columns and 'default_marks' not in columns:
            connection.execute('ALTER TABLE test_types ADD COLUMN default_marks FLOAT')
            print('Migration: added default_marks to test_types')
        mark_columns = _table_columns(connection, 'student_marks')
        if mark_columns and 'is_absent' not in mark_columns:
            connection.execute(
                'ALTER TABLE student_marks ADD COLUMN is_absent BOOLEAN NOT NULL DEFAULT 0')
            print('Migration: added is_absent to student_marks')
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

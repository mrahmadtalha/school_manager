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
        if 'last_successful_send_at' not in automation_columns and automation_columns:
            connection.execute('ALTER TABLE automation_settings ADD COLUMN last_successful_send_at DATETIME')
            print('Migration: added last_successful_send_at to automation_settings')

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
        if 'school_end_time' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN school_end_time VARCHAR(10) DEFAULT '15:00'")
            print('Migration: added school_end_time to school_settings')
        if 'weekend_off' not in settings_columns:
            connection.execute('ALTER TABLE school_settings ADD COLUMN weekend_off BOOLEAN DEFAULT 1')
            print('Migration: added weekend_off to school_settings')
        if 'custom_off_days' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN custom_off_days VARCHAR(200) DEFAULT ''")
            print('Migration: added custom_off_days to school_settings')

        connection.commit()


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

"""Schema migrations for student records, fees, status, enrolments and profile fields."""

import os

from app.database import db
from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns


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

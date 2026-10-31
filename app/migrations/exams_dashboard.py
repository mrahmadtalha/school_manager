"""Schema migrations for school settings, term exams, tests and the dashboard."""

import os

from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns


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
        if 'late_after_cutoff' not in settings_columns:
            connection.execute('ALTER TABLE school_settings ADD COLUMN late_after_cutoff BOOLEAN DEFAULT 1')
            print('Migration: added late_after_cutoff to school_settings')
        if 'late_counts_as_present' not in settings_columns:
            connection.execute('ALTER TABLE school_settings ADD COLUMN late_counts_as_present BOOLEAN DEFAULT 1')
            print('Migration: added late_counts_as_present to school_settings')
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

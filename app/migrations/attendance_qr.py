"""Schema migrations for attendance, QR attendance and WhatsApp automation tables."""

import os

from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns


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
        if 'qr_time' not in columns:
            connection.execute('ALTER TABLE attendance ADD COLUMN qr_time VARCHAR(10)')
            print('Migration: added qr_time to attendance')

        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_target_date ON attendance(target_type, target_id, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_class_date ON attendance(class_id, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_target_type_date ON attendance(target_type, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_students_class_active ON students(class_id, is_active)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_student_marks_test_student ON student_marks(test_id, student_id)')
        connection.commit()


def migrate_qr_config_schema(app):
    """Add the auto-absent settings to a qr_config table made by an older version."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'qr_config')
        if not columns:
            return
        additions = (
            ('auto_absent_enabled', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('absent_cutoff_time', "VARCHAR(5) NOT NULL DEFAULT '10:00'"),
            ('absent_mode', "VARCHAR(10) NOT NULL DEFAULT 'approval'"),
            ('absent_min_scan_percent', 'INTEGER NOT NULL DEFAULT 20'),
            ('absent_message_delay_minutes', 'INTEGER NOT NULL DEFAULT 30'),
            ('late_correction_enabled', 'BOOLEAN NOT NULL DEFAULT 1'),
        )
        for name, ddl in additions:
            if name not in columns:
                connection.execute(f'ALTER TABLE qr_config ADD COLUMN {name} {ddl}')
                print(f'Migration: added {name} to qr_config')
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

        if queue_columns and 'send_after' not in queue_columns:
            connection.execute('ALTER TABLE message_queue ADD COLUMN send_after DATETIME')
            print('Migration: added send_after to message_queue')

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
                ('template_test_result', 'TEXT'),
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

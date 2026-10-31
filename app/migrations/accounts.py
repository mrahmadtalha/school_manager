"""Schema migrations for admin accounts and guardian links."""

import os

from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns


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

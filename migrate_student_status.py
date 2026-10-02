"""Standalone migration: student status lifecycle.

Adds the ``status`` / ``leaving_reason`` / ``leaving_date`` columns to the
``students`` table and backfills previously archived students (``is_active = 0``)
with status ``slc_issued``.  Idempotent — safe to run multiple times (the app's
startup migrations perform the same steps automatically).

Usage:  python migrate_student_status.py [path-to-school.db]
"""
import sqlite3
import sys


def migrate(db_path='instance/school.db'):
    print('Connecting to db...')
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE students ADD COLUMN status VARCHAR(20) DEFAULT 'enrolled'")
        print('Added status to students')
        cursor = conn.execute("UPDATE students SET status = 'slc_issued' WHERE is_active = 0")
        if cursor.rowcount:
            print(f'Backfilled slc_issued for {cursor.rowcount} archived student(s)')
    except sqlite3.OperationalError as e:
        print(f'status error: {e}')

    try:
        conn.execute('ALTER TABLE students ADD COLUMN leaving_reason VARCHAR(200)')
        print('Added leaving_reason to students')
    except sqlite3.OperationalError as e:
        print(f'leaving_reason error: {e}')

    try:
        conn.execute('ALTER TABLE students ADD COLUMN leaving_date DATE')
        print('Added leaving_date to students')
    except sqlite3.OperationalError as e:
        print(f'leaving_date error: {e}')

    conn.commit()
    conn.close()
    print('Done')


if __name__ == '__main__':
    migrate(sys.argv[1] if len(sys.argv) > 1 else 'instance/school.db')

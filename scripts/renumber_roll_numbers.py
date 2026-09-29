"""One-time migration: per-class integer roll numbers (UNIQUE(class_id, roll_number)).

The script rebuilds the students table and renumbers every existing student per
class starting from 1001 (ordered by the legacy roll number, then id).  A
pre-migration backup is written first unless ``--no-backup`` is given;
``--dry-run`` only reports what would happen.

Usage
-----
    python scripts/renumber_roll_numbers.py --dry-run
    python scripts/renumber_roll_numbers.py                 # migrate the configured database
    python scripts/renumber_roll_numbers.py --db instance/backups/school-copy.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.db_backup import database_stats, resolve_db_path  # noqa: E402
from app.services.roll_numbers import (  # noqa: E402
    FIRST_ROLL_NUMBER,
    migrate_students_table,
    students_table_needs_migration,
)


def _plan_summary(db_path):
    """Return per-class counts, or 'up-to-date', or None when there is no students table."""
    connection = sqlite3.connect(str(db_path))
    try:
        if not connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='students'"
        ).fetchone():
            return None
        if not students_table_needs_migration(connection):
            return 'up-to-date'
        return connection.execute(
            'SELECT class_id, COUNT(*), MIN(roll_number), MAX(roll_number) '
            'FROM students GROUP BY class_id ORDER BY class_id'
        ).fetchall()
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', help='SQLite file to migrate (default: DATABASE_URL or instance/school.db)')
    parser.add_argument('--dry-run', action='store_true', help='report only; write nothing')
    parser.add_argument('--no-backup', action='store_true', help='skip the pre-migration backup')
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else resolve_db_path()
    if not db_path.exists():
        print(f'ERROR: database file not found: {db_path}')
        return 1

    before = _plan_summary(db_path)
    if before is None:
        print(f'No students table in {db_path} - nothing to migrate.')
        return 0
    if before == 'up-to-date':
        print(f'{db_path} already has per-class integer roll numbers - nothing to do.')
        return 0

    print(f'Database: {db_path}')
    print('Students by class (class_id, count, min, max):')
    for row in before:
        print(f'  class_id={row[0]:>3}  count={row[1]:>4}  min={row[2]}  max={row[3]}')

    if args.dry_run:
        print('Dry run: no changes written.')
        return 0

    stats_before = database_stats(db_path)
    summary = migrate_students_table(db_path, make_backup=not args.no_backup)
    if summary is None:
        print('Nothing to migrate.')
        return 0

    stats_after = database_stats(db_path)
    print(f'Backup: {summary["backup_path"] or "(disabled)"}')
    print(f'Renumbered {summary["students_total"]} students per class from {FIRST_ROLL_NUMBER}:')
    for entry in summary['per_class']:
        print(f'  class_id={entry["class_id"]:>3}  {entry["count"]:>4} students  ->  '
              f'{entry["first"]}..{entry["last"]}')
    print(f'Students before/after : {stats_before["students"]} / {stats_after["students"]}')
    print(f'Row total before/after: {stats_before["__total__"]} / {stats_after["__total__"]}')
    print('Migration complete.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

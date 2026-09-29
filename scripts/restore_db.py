"""Restore the School Manager SQLite database from a backup file.

Usage
-----
    python scripts/restore_db.py instance/backups/school-20260928-120000.db
    python scripts/restore_db.py <backup> --force

Without ``--force`` an existing live database is never overwritten.  With
``--force`` the current database is first preserved as
``<name>.pre-restore-<timestamp>`` so the restore itself can be undone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.db_backup import database_stats, resolve_db_path, restore_database  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description='Restore the School Manager database from a backup.')
    parser.add_argument('backup', help='path to the backup .db file')
    parser.add_argument('--db', help='target SQLite file (default: DATABASE_URL or instance/school.db)')
    parser.add_argument('--force', action='store_true',
                        help='overwrite the existing database (a pre-restore copy is kept)')
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else resolve_db_path()

    before = database_stats(db_path) if db_path.exists() else {}
    target = restore_database(args.backup, db_path, force=args.force)
    after = database_stats(target)

    print(f'Backup used     : {Path(args.backup).resolve()}')
    print(f'Database        : {target}')
    if before:
        print(f'Rows before     : {before["__total__"]}')
    print(f'Rows after      : {after["__total__"]}')
    print('Row counts      : ' + ', '.join(f'{k}={v}' for k, v in after.items() if k != '__total__'))
    return 0


if __name__ == '__main__':
    sys.exit(main())

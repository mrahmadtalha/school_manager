"""Create a timestamped backup of the School Manager SQLite database.

Usage
-----
    python scripts/backup_db.py                        # manual backup (instance/backups)
    python scripts/backup_db.py --out D:\\backups
    python scripts/backup_db.py --auto --if-due --retention 30
        # rotating automatic backup: only when the newest backup is older than
        # AUTO_BACKUP_INTERVAL_HOURS (default 24); keeps BACKUP_RETENTION_COUNT
        # (or --retention) newest automatic copies.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.db_backup import (  # noqa: E402
    auto_backup_dir, backup_database, backup_if_due, database_stats,
    default_backup_dir, prune_auto_backups, resolve_db_path,
)


def _print_details(target):
    stats = database_stats(target)
    print(f'Backup written  : {target}')
    print(f'Size            : {target.stat().st_size} bytes')
    print('Row counts      : ' + ', '.join(f'{k}={v}' for k, v in stats.items()
                                           if k != '__total__'))
    print(f'Total rows      : {stats["__total__"]}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Back up the School Manager database.')
    parser.add_argument('--db', help='path to the SQLite file (default: DATABASE_URL or instance/school.db)')
    parser.add_argument('--out', help='directory for the backup file (default: instance/backups)')
    parser.add_argument('--auto', action='store_true',
                        help='write into the rotating auto folder (instance/backups/auto)')
    parser.add_argument('--if-due', action='store_true',
                        help='skip when a backup newer than AUTO_BACKUP_INTERVAL_HOURS exists')
    parser.add_argument('--retention', type=int, default=None,
                        help='keep only the newest N automatic backups')
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else resolve_db_path()

    if args.if_due:
        summary = backup_if_due(db_path, retention=args.retention)
        if summary['created']:
            _print_details(Path(summary['created']))
        else:
            print('Backup not due : newest backup is fresh; nothing written.')
        for name in summary['pruned']:
            print(f'Pruned old auto backup: {name}')
        return 0

    out_dir = (auto_backup_dir(db_path) if args.auto
               else (Path(args.out) if args.out else default_backup_dir(db_path)))
    target = backup_database(db_path, out_dir)
    _print_details(target)
    if args.retention is not None:
        for name in prune_auto_backups(db_path, keep=args.retention):
            print(f'Pruned old auto backup: {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

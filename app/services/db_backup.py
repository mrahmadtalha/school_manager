"""SQLite backup / restore helpers.

Uses SQLite's online backup API (``sqlite3.Connection.backup``) so a running
application can be backed up safely without copying a half-written file.
"""

import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_BACKUP_DIRNAME = 'backups'
_TABLES = (
    'admin_users', 'students', 'teachers', 'classes', 'sections', 'subjects',
    'attendance', 'tests', 'student_marks', 'test_types',
    'fee_records', 'fee_transactions', 'audit_logs', 'school_settings',
    'message_queue', 'delivery_logs', 'system_settings', 'automation_settings',
)


def project_root():
    return Path(__file__).resolve().parent.parent.parent


def resolve_db_path(database_url=None):
    """Return the filesystem path of the SQLite database in use."""
    url = database_url or os.environ.get('DATABASE_URL') or ''
    if url.startswith('sqlite:///'):
        raw = url[len('sqlite:///'):]
        # Strip an optional query string, e.g. ?check_same_thread=false
        raw = raw.split('?', 1)[0]
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path
    return project_root() / 'instance' / 'school.db'


def default_backup_dir(db_path=None):
    db_path = Path(db_path) if db_path else resolve_db_path()
    return db_path.parent / DEFAULT_BACKUP_DIRNAME


def backup_database(db_path=None, backup_dir=None):
    """Copy the live database into a timestamped backup file."""
    db_path = Path(db_path) if db_path else resolve_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f'Database file not found: {db_path}')

    backup_dir = Path(backup_dir) if backup_dir else default_backup_dir(db_path)
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = backup_dir / f'{db_path.stem}-{stamp}.db'

    source = sqlite3.connect(str(db_path))
    try:
        destination = sqlite3.connect(str(target))
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    return target


def database_stats(db_path):
    """Return ``{table: row_count}`` plus a total, for comparison checks."""
    db_path = Path(db_path)
    stats = {}
    connection = sqlite3.connect(str(db_path))
    try:
        existing = {row[0] for row in
                    connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in _TABLES:
            if table not in existing:
                stats[table] = 0
                continue
            stats[table] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        connection.close()
    stats['__total__'] = sum(v for k, v in stats.items() if k != '__total__')
    return stats


def restore_database(backup_path, db_path=None, force=False):
    """Restore ``backup_path`` over the live database.

    Without ``force`` an existing live database is never overwritten.  When
    forcing, the current database is preserved as ``<name>.pre-restore-<stamp>``
    so a mistaken restore can itself be undone.
    """
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f'Backup file not found: {backup_path}')

    db_path = Path(db_path) if db_path else resolve_db_path()

    # Verify the backup is a readable SQLite database before touching anything.
    probe = sqlite3.connect(str(backup_path))
    try:
        result = probe.execute('PRAGMA integrity_check').fetchone()
        if not result or result[0] != 'ok':
            raise ValueError(f'Backup failed integrity check: {result}')
    finally:
        probe.close()

    if db_path.exists():
        if not force:
            raise FileExistsError(
                f'Refusing to overwrite existing database {db_path}. Re-run with --force.'
            )
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        shutil.copy2(db_path, db_path.with_name(f'{db_path.name}.pre-restore-{stamp}'))

    db_path.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(str(backup_path))
    try:
        destination = sqlite3.connect(str(db_path))
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    return db_path


# -- automatic (rotating) backups ---------------------------------------------

DEFAULT_RETENTION_COUNT = 30
DEFAULT_INTERVAL_HOURS = 24


def auto_backup_dir(db_path=None):
    """Folder for rotating automatic backups (a subfolder of ``backups/``)."""
    return default_backup_dir(db_path) / 'auto'


def auto_backup_settings():
    """Effective automatic-backup configuration, read from the environment."""
    enabled = (os.environ.get('AUTO_BACKUP_ENABLED', '1').strip().lower()
               not in {'0', 'false', 'no', 'off'})
    try:
        interval_hours = float(os.environ.get('AUTO_BACKUP_INTERVAL_HOURS')
                               or DEFAULT_INTERVAL_HOURS)
    except ValueError:
        interval_hours = DEFAULT_INTERVAL_HOURS
    try:
        retention = int(os.environ.get('BACKUP_RETENTION_COUNT')
                        or DEFAULT_RETENTION_COUNT)
    except ValueError:
        retention = DEFAULT_RETENTION_COUNT
    return {'enabled': enabled, 'interval_hours': interval_hours,
            'retention': max(1, retention)}


def list_backups(db_path=None):
    """Every backup (automatic + manual), newest first.

    Each entry: ``name``, ``path``, ``scope`` ('auto' | 'manual'), ``size``
    and ``created`` (local ``datetime``).
    """
    db_path = Path(db_path) if db_path else resolve_db_path()
    root = default_backup_dir(db_path)
    items = []
    for scope, folder in (('auto', root / 'auto'), ('manual', root)):
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() == '.db':
                stat = entry.stat()
                items.append({
                    'name': entry.name,
                    'path': str(entry),
                    'scope': scope,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_mtime),
                })
    items.sort(key=lambda item: item['created'], reverse=True)
    return items


def newest_backup_time(db_path=None):
    """Creation time of the most recent backup, or ``None``."""
    items = list_backups(db_path)
    return items[0]['created'] if items else None


def prune_auto_backups(db_path=None, keep=None):
    """Delete automatic backups beyond the newest ``keep`` ones.

    Only the ``backups/auto`` folder is touched; manual backups (and every
    legacy file in ``backups/``) are never deleted automatically.
    """
    if keep is None:
        keep = auto_backup_settings()['retention']
    keep = max(1, int(keep))
    folder = auto_backup_dir(db_path)
    if not folder.is_dir():
        return []
    entries = sorted((entry for entry in folder.iterdir()
                      if entry.is_file() and entry.suffix.lower() == '.db'),
                     key=lambda entry: entry.stat().st_mtime, reverse=True)
    removed = []
    for entry in entries[keep:]:
        try:
            entry.unlink()
            removed.append(entry.name)
        except OSError:
            pass
    return removed


def backup_if_due(db_path=None, interval_hours=None, retention=None, force=False):
    """Create a rotating automatic backup when the newest one is old enough.

    ``due`` is measured across *all* backups (manual + automatic), so a manual
    backup taken today also satisfies the daily requirement.  Returns a summary
    dict: ``due``, ``created`` (path or ``None``) and ``pruned`` (file names).
    """
    if interval_hours is None:
        interval_hours = auto_backup_settings()['interval_hours']
    newest = newest_backup_time(db_path)
    due = (force or newest is None
           or (datetime.now() - newest) >= timedelta(hours=interval_hours))

    created = None
    if due:
        created = backup_database(db_path, auto_backup_dir(db_path))
    pruned = prune_auto_backups(db_path, keep=retention)
    return {
        'due': due,
        'created': str(created) if created else None,
        'pruned': pruned,
    }

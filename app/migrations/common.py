"""Shared helpers for the schema migrations (SQLite connection, column lookup, safety backup)."""

from contextlib import contextmanager
import os
import sqlite3


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


def _safety_backup(app, db_path, label):
    """Copy the database aside before a schema change; never blocks startup."""
    try:
        from app.services import db_backup
        target = db_backup.backup_database(db_path)
        named = target.with_name('%s-%s%s' % (target.stem, label, target.suffix))
        target.rename(named)
        print('Migration: safety backup written to %s' % named)
        return named
    except Exception as error:  # pragma: no cover - best effort only
        print('Migration: WARNING - could not write a safety backup (%s)' % error)
        return None

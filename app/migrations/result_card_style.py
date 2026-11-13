"""Add result_card_style column to school_settings."""

from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns, _safety_backup


def run(app):
    """Add ``result_card_style`` column to ``school_settings`` if absent."""
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:':
        return

    with _sqlite_connection(db_path) as conn:
        cols = _table_columns(conn, 'school_settings')
        if not cols:
            return  # table not created yet — SQLAlchemy will make it

        if 'result_card_style' not in cols:
            _safety_backup(app, db_path, 'before-result-card-style')
            conn.execute(
                "ALTER TABLE school_settings "
                "ADD COLUMN result_card_style VARCHAR(40) DEFAULT 'classic'"
            )
            print('Migration: added result_card_style to school_settings.')

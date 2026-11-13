"""Create calendar_events table."""

from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns, _safety_backup


def run(app):
    """Create ``calendar_events`` table if it does not exist yet."""
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:':
        return

    with _sqlite_connection(db_path) as conn:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        if 'calendar_events' in tables:
            # Table exists — add any new columns added in later patches
            cols = _table_columns(conn, 'calendar_events')
            if 'end_date' not in cols:
                conn.execute("ALTER TABLE calendar_events ADD COLUMN end_date DATE")
                print('Migration: added end_date to calendar_events.')
            return

        _safety_backup(app, db_path, 'before-calendar-events')
        conn.execute("""
            CREATE TABLE calendar_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       VARCHAR(200) NOT NULL,
                description TEXT DEFAULT '',
                event_date  DATE NOT NULL,
                end_date    DATE,
                category    VARCHAR(40) DEFAULT 'general',
                is_pinned   BOOLEAN NOT NULL DEFAULT 0,
                is_archived BOOLEAN NOT NULL DEFAULT 0,
                created_by  INTEGER REFERENCES admin_users(id),
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX ix_calendar_events_event_date ON calendar_events (event_date)")
        print('Migration: created calendar_events table.')

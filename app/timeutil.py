"""Small time helpers shared across the app."""
from datetime import datetime, timezone


def utcnow():
    """Naive UTC "now" - the same value the deprecated ``datetime.utcnow`` returned.

    Python deprecated ``datetime.utcnow`` (it will be removed). This keeps the
    stored/compared values naive UTC, exactly as before, so no existing database
    row or comparison changes behaviour.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

"""Helpers for the "Absent" mark status.

An absent student is stored as a normal ``StudentMarkModel`` row with
``is_absent=True`` (``marks_obtained`` is kept at 0 only because the column is
NOT NULL).  Everything that totals marks must skip such rows, so that an
absence is neither a zero nor a failure.  Papers with no row at all are still
"not entered yet" and behave exactly as before.
"""

ABSENT_LABEL = 'ABS'      # shown on screens, reports and exports
ABSENT_LETTER = 'A'       # typed / shown in the marks-entry grid

# What a teacher may type in a marks cell to record an absence.
_ABSENT_TOKENS = {'a', 'abs', 'absent'}


def is_absent_token(raw):
    """True when a marks-entry cell value means "absent"."""
    return str(raw or '').strip().lower() in _ABSENT_TOKENS


def mark_is_absent(mark):
    """True when ``mark`` is a stored absence."""
    return bool(mark is not None and getattr(mark, 'is_absent', False))

"""Periods: academic sessions, month ranges and the description of a month, year or session."""

from datetime import date

from app.services.payroll_service import month_bounds, month_label, parse_month

from .common import short_label


def session_bounds(start_year):
    """April-to-March academic session starting in ``start_year``."""
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def current_session_start_year(today=None):
    """Academic sessions run April-March, matching the rest of the app."""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def months_in_range(start, end):
    """Every 'YYYY-MM' key touched by the inclusive date range."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append('%04d-%02d' % (year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def all_months_in_period(period):
    """Every calendar month a period spans (a month period spans exactly one)."""
    return months_in_range(period['start'], period['end'])


def period_descriptor(key):
    """Parse one period key into a descriptor, or None when it is invalid.

    Accepted forms:
      '2026-09'            -> a single month
      'year:2026'          -> the calendar year (Jan-Dec)
      'session:2026-2027'  -> the academic session (Apr 2026 - Mar 2027)
    """
    key = (key or '').strip()
    if not key:
        return None

    if key.startswith('session:'):
        raw = key.split(':', 1)[1].strip()
        try:
            start_year = int(raw.split('-')[0])
        except (ValueError, IndexError):
            return None
        if not 2000 <= start_year <= 2100:
            return None
        start, end = session_bounds(start_year)
        return {'key': key, 'kind': 'session', 'start': start, 'end': end,
                'label': 'Session %d-%d' % (start_year, start_year + 1),
                'short_label': 'Session %d-%02d' % (start_year, (start_year + 1) % 100)}

    if key.startswith('year:'):
        raw = key.split(':', 1)[1].strip()
        try:
            year = int(raw)
        except ValueError:
            return None
        if not 2000 <= year <= 2100:
            return None
        return {'key': key, 'kind': 'year', 'start': date(year, 1, 1),
                'end': date(year, 12, 31), 'label': str(year),
                'short_label': str(year)}

    if parse_month(key):
        start, end = month_bounds(key)
        return {'key': key, 'kind': 'month', 'start': start, 'end': end,
                'label': month_label(key), 'short_label': short_label(key)}

    return None

from datetime import datetime


def _normalize_off_day_name(day_name):
    if not day_name:
        return ''
    return day_name.strip().title()


def get_school_off_days(settings):
    off_days = set()
    if getattr(settings, 'weekend_off', True):
        off_days.update({'Saturday', 'Sunday'})

    custom_days = getattr(settings, 'custom_off_days', '') or ''
    for item in custom_days.split(','):
        day_name = _normalize_off_day_name(item)
        if day_name:
            off_days.add(day_name)
    return off_days


def is_school_day(date_value, settings=None):
    if settings is None:
        from app.models import SchoolSettings
        settings = SchoolSettings.query.first() or type('DefaultSettings', (), {'weekend_off': True, 'custom_off_days': ''})()

    weekday_name = date_value.strftime('%A')
    if weekday_name in get_school_off_days(settings):
        return False
    return True


def get_school_working_days(start_date, end_date, settings=None):
    results = []
    current = start_date
    while current <= end_date:
        if is_school_day(current, settings):
            results.append(current)
        current += __import__('datetime').timedelta(days=1)
    return results


def _to_minutes(value: str):
    if not value:
        return 0
    try:
        hour, minute = value.split(':')
        return int(hour) * 60 + int(minute)
    except Exception:
        return 0


def calculate_late_deduction(arrival_time: str, school_start_time: str, hourly_rate: float):
    if not arrival_time or not school_start_time:
        return 0.0

    arrival_minutes = _to_minutes(arrival_time)
    start_minutes = _to_minutes(school_start_time)
    if arrival_minutes <= start_minutes:
        return 0.0

    late_minutes = arrival_minutes - start_minutes
    hours_late = late_minutes / 60.0
    return round(hours_late * float(hourly_rate or 0), 2)


def calculate_monthly_salary(teacher):
    if getattr(teacher, 'salary_type', 'monthly') == 'hourly':
        return float(getattr(teacher, 'hourly_rate', 0) or 0)
    return float(getattr(teacher, 'monthly_salary', 0) or getattr(teacher, 'salary', 0) or 0)

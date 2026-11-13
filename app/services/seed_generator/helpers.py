"""Small shared helpers: dates, random picks, fabricated names/phone/CNIC/address and status."""

from datetime import date, timedelta

from app.database import db
from app.models.settings import calculate_grade, get_custom_fields
from app.services.custom_fields import serialize_custom_field_values

from .data import (CITIES, CUSTOM_FIELD_VALUES, FIRST_NAMES_FEMALE, FIRST_NAMES_MALE, LAST_NAMES,
                   STREETS)


def _shift_month(day, offset):
    """First day of the month ``offset`` months from ``day``'s month."""
    total = day.year * 12 + (day.month - 1) + offset
    return date(total // 12, total % 12 + 1, 1)


def _month_end(month_start):
    return _shift_month(month_start, 1) - timedelta(days=1)


def _today():
    return date.today()


def _pick(rng, population, weights):
    return rng.choices(population, weights=weights, k=1)[0]


def _weighted_status(rng, weights):
    labels = list(weights)
    return rng.choices(labels, weights=[weights[k] for k in labels], k=1)[0]


def _person_name(rng, female):
    first_pool = FIRST_NAMES_FEMALE if female else FIRST_NAMES_MALE
    return f'{rng.choice(first_pool)} {rng.choice(LAST_NAMES)}'


def _phone(rng):
    return f'+92 3{rng.randint(0, 4)}{rng.randint(0, 9)} {rng.randint(1000000, 9999999)}'


def _cnic(rng):
    return f'{rng.randint(31000, 38000)}-{rng.randint(1000000, 9999999)}-{rng.randint(0, 9)}'


def _address(rng):
    return f'House {rng.randint(1, 250)}, {rng.choice(STREETS)}, {rng.choice(CITIES)}'


def _session_label(day):
    return f'{day.year}-{(day.year + 1) % 100:02d}'


def _custom_field_values(rng, entity_type):
    """Fill every configured custom field so seeded records are complete."""
    values = {}
    for field in get_custom_fields(entity_type):
        if not isinstance(field, dict) or not (field.get('name') or '').strip():
            continue
        kind = (field.get('type') or 'text').lower()
        name = field['name'].strip()
        pool = CUSTOM_FIELD_VALUES.get(name.lower())
        if pool:
            value = rng.choice(pool)
        elif kind == 'number':
            value = str(rng.randint(0, 4))
        elif kind == 'date':
            value = (_today() - timedelta(days=rng.randint(0, 1800))).isoformat()
        elif kind == 'checkbox':
            value = rng.choice(['Yes', 'No'])
        else:
            value = rng.choice(['Siblings in school', 'Scholarship approved', 'Morning shift'])
        values[field['name'].strip()] = value
    return serialize_custom_field_values(values) if values else None


def _status_for(charged, paid):
    """Mirrors ``fee_ledger._status_for`` so seeded cache rows match the ledger."""
    if charged <= 0 and paid <= 0:
        return 'Pending'
    if paid + 0.001 >= charged and charged > 0:
        return 'Paid'
    if paid > 0:
        return 'Partial'
    return 'Pending'


def _ensure_library_subjects(names):
    """Fetch or create a SubjectLibrary entry per demo subject; returns {lower: entry}."""
    from app.models import SubjectLibrary
    by_lower = {lib.name.strip().lower(): lib for lib in SubjectLibrary.query.all()}
    for name in names:
        key = name.strip().lower()
        if key not in by_lower:
            entry = SubjectLibrary(name=name, is_active=True, is_default=False)
            db.session.add(entry)
            db.session.flush()
            by_lower[key] = entry
    return by_lower


def _start_minutes(value):
    try:
        hour, minute = str(value or '08:30').split(':')
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return 8 * 60 + 30


def _minutes_to_time(total_minutes):
    return f'{total_minutes // 60 % 24:02d}:{total_minutes % 60:02d}'


def _enrolled_on(student, day):
    if student.admission_date and day < student.admission_date:
        return False
    if not student.is_active and student.leaving_date and day > student.leaving_date:
        return False
    return True


def _mark_row(test_id, student, total, ability, rng):
    if rng.random() < 0.04:
        return {'test_id': test_id, 'student_id': student.id,
                'marks_obtained': 0.0, 'is_absent': True,
                'percentage': None, 'grade': None}
    obtained = int(max(0, min(total, round(total * ability + rng.uniform(-12, 12)))))
    percentage = round(obtained / total * 100, 1)
    return {'test_id': test_id, 'student_id': student.id,
            'marks_obtained': float(obtained), 'is_absent': False,
            'percentage': percentage, 'grade': calculate_grade(percentage)}


def _month_end_for_pay(m_start):
    return _shift_month(m_start, 1) - timedelta(days=2)

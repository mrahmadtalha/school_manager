"""Automatic admission numbers in a pattern the school chooses.

A school-wide switch plus three options kept in the system settings:

* **prefix** - any text, e.g. ``alberoni-26-`` (``{YY}`` / ``{YYYY}`` stand for the
  current year, so ``alberoni-{YY}-`` becomes ``alberoni-26-`` and rolls over by itself);
* **digits** - how many digits the counter has (4 -> ``0001``);
* **start** - the first counter value for a prefix (default 1).

With the switch ON a new student gets the next number by itself and the Admission No
box on Add Student is read-only; with it OFF the box is typed by hand.  Numbers already
on record (typed or imported) are never changed.

Nobody types an Admission No on Add / Edit Student: the box is always read-only and the
server ignores anything posted for it.  The number only comes from this pattern and only
changes through Settings (prefix, digits, start, or the automatic switch ON / OFF).  With
the switch OFF new students simply get no Admission No.  A student who has no number gets
the next one when the switch is ON and the student is saved, or all at once with
``assign_missing()``.

``assign_missing()`` gives every student who has no Admission No the next numbers in one
go (oldest admission first), so a school that started without numbers can fill the gaps
with a single click.  The counter continues from the highest
number that already uses the same prefix, so ``alberoni-26-0001``, ``-0002`` ... follow
one another and a new prefix (a new year) starts again at *start*.
"""
import re
from datetime import date

from app.database import db
from app.models import StudentModel
from app.models.settings import SystemSettingModel

SETTING_KEY = 'auto_admission_number'
PREFIX_KEY = 'admission_number_prefix'
DIGITS_KEY = 'admission_number_digits'
START_KEY = 'admission_number_start'

DEFAULT_PREFIX = 'ADM-'
DEFAULT_DIGITS = 4
DEFAULT_START = 1
MAX_PREFIX = 30

_PREFIX_ALLOWED = re.compile(r'^[A-Za-z0-9 _./#-]*$')


def _get(key):
    row = SystemSettingModel.query.filter_by(key=key).first()
    return row.value if row is not None else None


def _put(key, value):
    row = SystemSettingModel.query.filter_by(key=key).first()
    if row is None:
        row = SystemSettingModel(key=key, value=str(value))
        db.session.add(row)
    row.value = str(value)


def is_auto():
    return _get(SETTING_KEY) == '1'


def set_auto(enabled):
    """Turn the switch on or off.  Does not commit."""
    _put(SETTING_KEY, '1' if enabled else '0')


def get_config():
    """``{'prefix', 'digits', 'start'}`` (prefix as typed, with any {YY} token)."""
    prefix = _get(PREFIX_KEY)
    try:
        digits = int(_get(DIGITS_KEY) or DEFAULT_DIGITS)
    except ValueError:
        digits = DEFAULT_DIGITS
    try:
        start = int(_get(START_KEY) or DEFAULT_START)
    except ValueError:
        start = DEFAULT_START
    return {'prefix': DEFAULT_PREFIX if prefix is None else prefix,
            'digits': digits, 'start': start}


def save_config(prefix, digits, start):
    """Validate and store the pattern.  Does not commit; raises ``ValueError``."""
    prefix = (prefix or '').strip()
    check = prefix.replace('{YYYY}', '').replace('{YY}', '')
    if '{' in check or '}' in check:
        raise ValueError('Only {YY} and {YYYY} can be used inside braces in the prefix.')
    if not _PREFIX_ALLOWED.match(check):
        raise ValueError('The prefix may only contain letters, numbers, space and - _ . / #')
    if len(resolve_prefix(prefix)) > MAX_PREFIX:
        raise ValueError('The prefix is too long (at most %d characters).' % MAX_PREFIX)
    try:
        digits = int(str(digits).strip() or DEFAULT_DIGITS)
        start = int(str(start).strip() or DEFAULT_START)
    except ValueError:
        raise ValueError('Digits and start number must be whole numbers.')
    if not 1 <= digits <= 8:
        raise ValueError('The counter needs between 1 and 8 digits.')
    if not 1 <= start <= 99999999:
        raise ValueError('The start number must be 1 or more.')
    _put(PREFIX_KEY, prefix)
    _put(DIGITS_KEY, digits)
    _put(START_KEY, start)


def resolve_prefix(prefix, today=None):
    today = today or date.today()
    return (prefix.replace('{YYYY}', '%04d' % today.year)
            .replace('{YY}', '%02d' % (today.year % 100)))


def next_number(today=None):
    """The next free number in the school's pattern (one after the highest used)."""
    config = get_config()
    prefix = resolve_prefix(config['prefix'], today)
    highest = config['start'] - 1
    pattern = re.compile(r'^' + re.escape(prefix) + r'(\d+)$', re.IGNORECASE)
    query = db.session.query(StudentModel.admission_number).filter(
        StudentModel.admission_number.ilike(prefix.replace('%', r'\%').replace('_', r'\_') + '%',
                                            escape='\\'))
    for (value,) in query.all():
        match = pattern.match((value or '').strip())
        if match:
            highest = max(highest, int(match.group(1)))
    return '%s%0*d' % (prefix, config['digits'], highest + 1)


def _missing_query():
    blank = db.or_(StudentModel.admission_number.is_(None),
                   db.func.trim(StudentModel.admission_number) == '')
    return StudentModel.query.filter(blank)


def count_missing():
    """How many students (any status) have no Admission No yet."""
    return _missing_query().count()


def resolve_on_edit(current, typed=None):
    """The Admission No to store when a student is edited (``typed`` is always ignored).

    A number already on record stays.  A student without one gets the next automatic
    number when the switch is ON, otherwise stays without.
    """
    current = (current or '').strip()
    if current:
        return current
    return next_number() if is_auto() else None


def assign_missing(today=None):
    """Give every student without an Admission No the next free number.

    Oldest admission first (admission date, then record order).  Existing numbers are
    never touched.  Does not commit.  Returns ``{'count', 'first', 'last'}``.
    """
    students = _missing_query().all()
    if not students:
        return {'count': 0, 'first': None, 'last': None}
    students.sort(key=lambda row: (row.admission_date or date.max, row.id))
    config = get_config()
    prefix = resolve_prefix(config['prefix'], today)
    pattern = re.compile(r'^' + re.escape(prefix) + r'(\d+)$', re.IGNORECASE)
    highest = config['start'] - 1
    for (value,) in db.session.query(StudentModel.admission_number).all():
        match = pattern.match((value or '').strip())
        if match:
            highest = max(highest, int(match.group(1)))
    first = last = None
    for student in students:
        highest += 1
        last = '%s%0*d' % (prefix, config['digits'], highest)
        first = first or last
        student.admission_number = last
    return {'count': len(students), 'first': first, 'last': last}

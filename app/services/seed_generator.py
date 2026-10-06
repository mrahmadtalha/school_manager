"""Advanced demo/seed data generator.

One engine powers both entry points:

* the first-run setup wizard (``/setup-admin``, which runs it in a background
  thread with live progress), and
* the ``seed_data.py`` CLI script.

The generator produces a realistic *history* for a configurable period
(1 month ... 10 years): students and teachers with consistent ages and a
join/leave lifecycle, daily attendance with per-person behaviour patterns,
monthly fee charges/payments on the append-only ledger, expenses, class tests,
term exams with marks/results, payroll, and optional locally drawn avatar
photos.  All randomness comes from a single seeded ``random.Random`` so a run
is reproducible.

Every generated fact is fabricated.  No real person's data is used.
"""

import io
import json
import os
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from flask import current_app

from app.database import db
from app.models import (
    ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER,
    AdminUser, AttendanceModel, ClassModel, Expense, ExpenseCategory,
    FeeRecordModel, FeeTransaction, GuardianStudentLink, SchoolSettings,
    SectionModel, StaffPayroll, StudentMarkModel, StudentModel, SubjectModel,
    TeacherModel, TermExam, TestModel, TestTypeModel,
    TXN_ADJUSTMENT, TXN_CHARGE, TXN_PAYMENT,
)
from app.models.settings import calculate_grade, get_custom_fields
from app.services.audit import log_action, resume_audit, suspend_audit
from app.services.custom_fields import serialize_custom_field_values
from app.services.enrollments import close_open_enrollment, start_enrollment
from app.services.roll_numbers import FIRST_ROLL_NUMBER

# -- tunables ----------------------------------------------------------------

CLASS_LEVELS = [  # (name, base monthly fee multiplier level, typical age)
    ('Playgroup', 0, 3), ('Nursery', 0, 4),
    ('Class 1', 1, 5), ('Class 2', 1, 6), ('Class 3', 2, 7), ('Class 4', 2, 8),
    ('Class 5', 3, 9), ('Class 6', 3, 10), ('Class 7', 4, 11), ('Class 8', 4, 12),
    ('Class 9', 5, 13), ('Class 10', 5, 14),
]
CLASS_NAMES = [name for name, _, _ in CLASS_LEVELS]
SECTION_NAMES = ('A', 'B')
SUBJECT_NAMES = ['English', 'Urdu', 'Mathematics', 'Science', 'Islamiyat']
TEST_TYPE_NAMES = ['Daily', 'Weekly', 'Monthly', 'Mid-Term', 'Final']

FIRST_NAMES_MALE = ['Ali', 'Ahmed', 'Hassan', 'Hussain', 'Bilal', 'Hamza', 'Zain',
                    'Usman', 'Adeel', 'Umar', 'Imran', 'Talha', 'Salman', 'Danish',
                    'Fahad', 'Junaid', 'Kashif', 'Naveed', 'Saad', 'Waqas']
FIRST_NAMES_FEMALE = ['Ayesha', 'Fatima', 'Maryam', 'Sana', 'Hira', 'Zainab',
                      'Rabia', 'Amna', 'Mahnoor', 'Iqra', 'Laiba', 'Noor',
                      'Hafsa', 'Iqra', 'Sadia', 'Alina', 'Mehak', 'Sidra']
LAST_NAMES = ['Khan', 'Awan', 'Malik', 'Rana', 'Qureshi', 'Abbasi', 'Butt',
              'Sheikh', 'Chaudhry', 'Nawaz', 'Iqbal', 'Farooq']
FATHER_FIRST = ['Muhammad', 'Abdul', 'Ghulam', 'Raja', 'Sheikh', 'Mian', 'Syed']
STREETS = ['Main Bazaar', 'College Road', 'Satellite Town', 'Jinnah Colony',
           'Circular Road', 'Model Town', 'Railway Road', 'Kacheri Bazaar']
CITIES = ['Sargodha', 'Faisalabad', 'Lahore', 'Rawalpindi', 'Multan']

QUALIFICATIONS = ['B.Ed', 'M.Ed', 'M.Sc Mathematics', 'MA English', 'MA Urdu',
                  'B.S Computer Science', 'M.Phil Physics', 'B.A, B.Ed']
DESIGNATIONS = ['Junior Teacher', 'Subject Teacher', 'Senior Teacher',
                'Section Coordinator', 'Head Teacher']
LEAVING_REASONS = ['Migration to another city', 'Transferred to another school',
                   'Family financial reasons', 'Personal family reasons',
                   'Relocated abroad']

TEACHER_GENDER_POOL = (['Female'] * 6) + (['Male'] * 4)

# Per-person behaviour profiles: probabilities for a school day.
STUDENT_PROFILES = [
    ('excellent', {'Present': 0.93, 'Late': 0.04, 'Absent': 0.015, 'Leave': 0.015}),
    ('regular',   {'Present': 0.86, 'Late': 0.05, 'Absent': 0.06,  'Leave': 0.03}),
    ('casual',    {'Present': 0.71, 'Late': 0.09, 'Absent': 0.14,  'Leave': 0.06}),
]
PROFILE_PICK_WEIGHTS = (35, 45, 20)

PAYMENT_PROFILES = ['prompt', 'regular', 'late', 'defaulter']
PAYMENT_PICK_WEIGHTS = (40, 35, 15, 10)

EXPENSE_AMOUNTS = {
    'Utilities': (8000, 15000),
    'Building/Rent': (15000, 25000),
    'Maintenance': (500, 8000),
    'Stationery & Printing': (500, 4000),
    'Refreshment/Events': (1000, 6000),
    'Miscellaneous': (300, 2500),
}
EXPENSE_NOTES = ['Monthly utility bill', 'Campus repair work', 'Exam stationery purchase',
                 'Staff refreshment', 'Generator diesel', 'Classroom cleaning supplies',
                 'Water supply bill', 'Furniture repair']

AVATAR_PALETTE = [(78, 115, 223), (28, 155, 135), (231, 111, 81), (246, 174, 45),
                  (105, 74, 177), (41, 128, 185), (192, 57, 43), (39, 174, 96)]

# Relative size of each stage, used only for the global progress percentage.
_STAGE_WEIGHTS = [
    ('structure', 2), ('teachers', 4), ('students', 12), ('attendance', 40),
    ('fees', 15), ('expenses', 3), ('class_tests', 9), ('term_exams', 8),
    ('payroll', 4), ('photos', 2), ('accounts', 1),
]

_BULK_CHUNK = 4000


@dataclass
class SeedConfig:
    """Options for one demo-data generation run."""
    student_count: int = 60
    teacher_count: int = 8
    monthly_fee: float = 2500.0
    months: int = 12                      # history period, 1 = current month only
    include_attendance: bool = True
    include_fees: bool = True
    include_expenses: bool = True
    include_class_tests: bool = True
    include_term_exams: bool = True
    include_payroll: bool = True
    generate_photos: bool = False
    random_seed: int = 20261004


class _Progress:
    """Maps per-stage fractions onto one global 0-100 percentage."""

    def __init__(self, callback):
        self._cb = callback
        total = float(sum(w for _, w in _STAGE_WEIGHTS))
        offset = 0.0
        self._stages = {}
        for name, weight in _STAGE_WEIGHTS:
            self._stages[name] = (offset / total * 100.0, weight / total * 100.0)
            offset += weight
        self._last = -1

    def report(self, stage, fraction=0.0):
        if self._cb is None or stage not in self._stages:
            return
        base, span = self._stages[stage]
        percent = base + max(0.0, min(1.0, fraction)) * span
        rounded = int(percent)
        if rounded != self._last:
            self._last = rounded
            try:
                self._cb(stage, rounded)
            except Exception:
                pass


# -- small helpers -----------------------------------------------------------

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
        if kind == 'number':
            value = str(rng.randint(1, 999))
        elif kind == 'date':
            value = (_today() - timedelta(days=rng.randint(0, 1800))).isoformat()
        elif kind == 'checkbox':
            value = rng.choice(['Yes', 'No'])
        else:
            value = rng.choice(['Blood group B+', 'Route 3 transport', 'Siblings in school',
                                'Scholarship approved', 'Morning shift'])
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


# -- stages ------------------------------------------------------------------

def _stage_structure(rng, cfg, progress):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
    settings.school_name = settings.school_name or 'Green Valley Public School'
    settings.tagline = settings.tagline or 'Knowledge · Discipline · Character'
    settings.address = settings.address or '12-B Main Road, Sargodha'
    settings.phone = settings.phone or '+92 300 1234567'
    settings.email = settings.email or 'office@greenvalley.example'
    settings.school_start_time = settings.school_start_time or '08:30'
    settings.school_end_time = settings.school_end_time or '15:00'

    classes = []
    for name, fee_level, _age in CLASS_LEVELS:
        class_obj = ClassModel.query.filter_by(name=name).first()
        if class_obj is None:
            class_obj = ClassModel(name=name)
            db.session.add(class_obj)
            db.session.flush()
        if class_obj.monthly_fee is None:
            class_obj.monthly_fee = round(cfg.monthly_fee + fee_level * 150, 2)
        classes.append(class_obj)

        for section_name in SECTION_NAMES:
            if SectionModel.query.filter_by(class_id=class_obj.id,
                                            name=section_name).first() is None:
                db.session.add(SectionModel(name=section_name, class_id=class_obj.id))

        for subject_name in SUBJECT_NAMES:
            if SubjectModel.query.filter_by(class_id=class_obj.id,
                                            name=subject_name).first() is None:
                db.session.add(SubjectModel(name=subject_name, class_id=class_obj.id))

    for test_name in TEST_TYPE_NAMES:
        if TestTypeModel.query.filter_by(name=test_name).first() is None:
            db.session.add(TestTypeModel(name=test_name))

    from app.services.expense_service import seed_default_categories
    seed_default_categories()

    db.session.commit()
    progress.report('structure', 1.0)
    return classes


def _stage_teachers(rng, cfg, progress, classes, period_start):
    total_target = cfg.teacher_count
    existing = TeacherModel.query.count()
    teachers = list(TeacherModel.query.order_by(TeacherModel.id).all())
    next_number = existing + 1

    for _ in range(max(0, total_target - existing)):
        female = rng.random() < 0.45
        name = _person_name(rng, female)
        age = rng.randint(24, 55)
        dob = _today() - timedelta(days=365 * age + rng.randint(0, 330))

        # ~12% join during the demo period; the rest are established staff.
        if rng.random() < 0.12:
            joining = period_start + timedelta(days=rng.randint(0, max(1, (date.today() - period_start).days - 30)))
        else:
            joining = period_start - timedelta(days=rng.randint(365, 3650))
        salary_type = 'hourly' if rng.random() < 0.1 else 'monthly'
        monthly_salary = round(float(cfg.monthly_fee) * rng.uniform(12, 22), 2)
        assigned = rng.sample([c.name for c in classes], k=min(len(classes), rng.randint(1, 3)))

        teacher = TeacherModel(
            teacher_id_str=f'T{next_number:03d}',
            teacher_name=name,
            joining_date=joining,
            qualification=rng.choice(QUALIFICATIONS),
            salary=monthly_salary,
            salary_type=salary_type,
            monthly_salary=monthly_salary,
            hourly_rate=round(rng.uniform(400, 900), 2),
            assigned_class=rng.choice(classes).name,
            cnic=_cnic(rng),
            address=_address(rng),
            contact_number=_phone(rng),
            emergency_contact_number=_phone(rng),
            previous_experience_years=float(min(age - 24, rng.randint(0, 15))),
            previous_salary=round(monthly_salary * rng.uniform(0.7, 0.95), 2),
            assigned_classes=json.dumps(assigned),
            assigned_subjects=json.dumps(rng.sample(SUBJECT_NAMES, k=rng.randint(1, 3))),
            date_of_birth=dob,
            designation=rng.choice(DESIGNATIONS),
            gender='Female' if female else 'Male',
        )
        db.session.add(teacher)
        next_number += 1
    db.session.flush()
    teachers = list(TeacherModel.query.order_by(TeacherModel.id).all())

    # A few established teachers leave mid-period (soft archive only).
    leaving_dates = {}
    if existing == 0 and len(teachers) > 3:
        for teacher in rng.sample(teachers, k=max(1, len(teachers) // 8)):
            leave_day = period_start + timedelta(days=rng.randint(
                60, max(61, (date.today() - period_start).days - 10)))
            if leave_day < date.today():
                teacher.is_active = False
                leaving_dates[teacher.id] = leave_day

    # Assign active teachers to subjects (round-robin).
    active = [t for t in teachers if t.is_active]
    for index, subject in enumerate(SubjectModel.query.order_by(SubjectModel.id).all()):
        subject.teacher_id = active[index % len(active)].id if active else None

    db.session.commit()
    progress.report('teachers', 1.0)
    return teachers, leaving_dates


def _stage_students(rng, cfg, progress, classes, period_start, period_end):
    total_target = cfg.student_count
    existing = StudentModel.query.count()
    if total_target <= existing or not classes:
        progress.report('students', 1.0)
        return

    joiner_frac = 0.15 if cfg.months >= 6 else (0.10 if cfg.months >= 3 else 0.05)
    leaver_frac = 0.10 if cfg.months >= 6 else (0.05 if cfg.months >= 3 else 0.02)

    specs = []
    for index in range(existing, total_target):
        class_obj = classes[index % len(classes)]
        level_age = next(age for name, _, age in CLASS_LEVELS if name == class_obj.name)
        female = rng.random() < 0.48
        is_joiner = rng.random() < joiner_frac
        if is_joiner:
            admission = period_start + timedelta(days=rng.randint(0, max(0, (period_end - period_start).days - 20)))
        else:
            admission = period_start - timedelta(days=rng.randint(30, 2200))
        specs.append((class_obj, level_age, female, is_joiner, admission))

    # Roll numbers follow admission order within each class.
    specs.sort(key=lambda s: (s[0].id, s[4]))
    next_roll = {}
    for class_obj in classes:
        highest = (db.session.query(db.func.max(StudentModel.roll_number))
                   .filter(StudentModel.class_id == class_obj.id).scalar())
        next_roll[class_obj.id] = int(highest) + 1 if highest is not None else FIRST_ROLL_NUMBER

    leaver_candidates = []
    admission_number_seq = 1
    for class_obj, level_age, female, is_joiner, admission in specs:
        sections = SectionModel.query.filter_by(class_id=class_obj.id).order_by(SectionModel.id).all()
        section = sections[admission.day % len(sections)] if sections else None
        first_pool = FIRST_NAMES_FEMALE if female else FIRST_NAMES_MALE
        first = rng.choice(first_pool)
        last = rng.choice(LAST_NAMES)
        roll = next_roll[class_obj.id]
        next_roll[class_obj.id] = roll + 1

        class_fee = round(float(class_obj.monthly_fee or cfg.monthly_fee), 2)
        discount_type = discount_value = None
        if rng.random() < 0.12:
            if rng.random() < 0.6:
                discount_type, discount_value = 'percentage', rng.choice([10.0, 15.0, 25.0])
            else:
                discount_type, discount_value = 'fixed', float(rng.choice([200, 300, 500]))
        monthly_fee = max(0.0, class_fee + rng.choice([-100, 0, 0, 100]))

        student = StudentModel(
            roll_number=roll,
            student_name=f'{first} {last}',
            father_name=f'{rng.choice(FATHER_FIRST)} {rng.choice(FIRST_NAMES_MALE)} {last}',
            sponsor_type=rng.choice(['Father', 'Father', 'Father', 'Mother', 'Guardian']),
            sponsor_cnic=_cnic(rng),
            guardian_phone=_phone(rng),
            address=_address(rng),
            class_id=class_obj.id,
            section_id=section.id if section else None,
            monthly_fee=monthly_fee,
            class_fee=class_fee,
            discount_type=discount_type,
            discount_value=discount_value,
            date_of_birth=_today() - timedelta(days=365 * (level_age + rng.randint(0, 1)) + rng.randint(0, 330)),
            gender='Female' if female else 'Male',
            admission_number=f'ADM-{admission.year}-{admission_number_seq:04d}',
            admission_date=admission,
            custom_fields_data=_custom_field_values(rng, 'student'),
            is_active=True,
            status='enrolled',
        )
        admission_number_seq += 1
        db.session.add(student)
        db.session.flush()
        start_enrollment(student, reason='enrolled', start_date=admission,
                         session_label=_session_label(admission))
        leaver_candidates.append(student)

    db.session.flush()

    # Some students leave part-way through the period.
    period_days = max(1, (period_end - period_start).days)
    leaving = rng.sample(leaver_candidates, k=int(len(leaver_candidates) * leaver_frac))
    for student in leaving:
        admission = student.admission_date or period_start
        earliest = max(admission + timedelta(days=45), period_start + timedelta(days=10))
        if earliest >= period_end:
            continue
        leaving_day = earliest + timedelta(days=rng.randint(0, (period_end - earliest).days))
        if student.class_info and student.class_info.name == 'Class 10' and rng.random() < 0.4:
            status = 'graduated'
        else:
            status = rng.choices(['slc_issued', 'struck_off'], weights=[75, 25], k=1)[0]
        student.status = status
        student.is_active = False
        student.leaving_date = leaving_day
        student.leaving_reason = rng.choice(LEAVING_REASONS)
        close_open_enrollment(student, end_date=leaving_day)

    db.session.commit()
    progress.report('students', 1.0)


def _stage_attendance(rng, cfg, progress, period_start, period_end, teacher_leaving):
    """One row per person per school day, chunked through Core inserts."""
    from app.services.teacher_payroll import get_school_working_days

    settings = SchoolSettings.query.first()
    school_days = get_school_working_days(period_start, period_end, settings)
    start_minutes = _start_minutes(settings.school_start_time)
    profile_weights = dict(STUDENT_PROFILES)

    students = [
        (s.id, s.class_id, s.admission_date or period_start,
         s.leaving_date if not s.is_active else None,
         _pick(rng, list(profile_weights), PROFILE_PICK_WEIGHTS))
        for s in StudentModel.query.all()
    ]
    teachers = [
        (t.id, t.joining_date or period_start, teacher_leaving.get(t.id))
        for t in TeacherModel.query.all()
    ]

    teacher_month_counts = {}
    pending = 0
    total_days = max(1, len(school_days))
    attendance_table = AttendanceModel.__table__
    row_keys = ('date', 'target_type', 'target_id', 'status', 'class_id',
                'is_locked', 'late_time', 'late_minutes')

    for day_index, day in enumerate(school_days):
        rows = []
        for sid, class_id, admission, leaving, profile in students:
            if day < admission or (leaving and day > leaving):
                continue
            status = _weighted_status(rng, profile_weights[profile])
            late_time = late_minutes = None
            if status == 'Late':
                late_minutes = rng.randint(5, 45)
                late_time = _minutes_to_time(start_minutes + late_minutes)
            rows.append({'date': day, 'target_type': 'student', 'target_id': sid,
                         'status': status, 'class_id': class_id, 'is_locked': False,
                         'late_time': late_time, 'late_minutes': late_minutes})

        for tid, joining, leaving in teachers:
            if day < joining or (leaving and day > leaving):
                continue
            status = rng.choices(['Present', 'Absent', 'Leave', 'Late'],
                                 weights=[90, 4, 3, 3], k=1)[0]
            late_time = late_minutes = None
            if status == 'Late':
                late_minutes = rng.randint(5, 30)
                late_time = _minutes_to_time(start_minutes + late_minutes)
            rows.append({'date': day, 'target_type': 'teacher', 'target_id': tid,
                         'status': status, 'class_id': None, 'is_locked': False,
                         'late_time': late_time, 'late_minutes': late_minutes})
            month_key = (tid, f'{day.year:04d}-{day.month:02d}')
            counts = teacher_month_counts.setdefault(
                month_key, {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0})
            counts[status] = counts.get(status, 0) + 1

        if rows:
            # executemany compiles one INSERT from the first row; keep the
            # key set identical across all rows.
            db.session.execute(attendance_table.insert(),
                               [{key: row.get(key) for key in row_keys} for row in rows])
            pending += len(rows)
            if pending >= _BULK_CHUNK:
                db.session.commit()
                pending = 0
        progress.report('attendance', day_index / total_days)

    db.session.commit()
    progress.report('attendance', 1.0)
    return teacher_month_counts


def _start_minutes(value):
    try:
        hour, minute = str(value or '08:30').split(':')
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return 8 * 60 + 30


def _minutes_to_time(total_minutes):
    return f'{total_minutes // 60 % 24:02d}:{total_minutes % 60:02d}'


def _stage_fees(rng, cfg, progress, months, period_start, period_end):
    """Charges + payments on the append-only ledger, cache rebuilt in bulk."""
    students = [s for s in StudentModel.query.all() if s.monthly_fee]
    now = datetime.now()
    txn_table = FeeTransaction.__table__
    record_table = FeeRecordModel.__table__

    totals = {}  # (student_id, month_year) -> [charged, paid, last_payment_dt]
    methods = ['cash', 'bank', 'online']
    pending = 0

    def flush_rows(rows):
        nonlocal pending
        if rows:
            db.session.execute(txn_table.insert(), rows)
            pending += len(rows)
            if pending >= _BULK_CHUNK:
                db.session.commit()
                pending = 0

    for s_index, student in enumerate(students):
        fee = round(float(student.monthly_fee), 2)
        admission = student.admission_date or period_start
        leaving = student.leaving_date if not student.is_active else None
        profile = _pick(rng, PAYMENT_PROFILES, PAYMENT_PICK_WEIGHTS)
        rows = []

        for m_index, (label, m_start, m_end) in enumerate(months):
            if m_end < admission or (leaving and m_start > leaving):
                continue
            is_current = m_end >= _today() and m_start <= _today()
            charge_day = min(m_start + timedelta(days=3), _today())
            charged_at = datetime.combine(charge_day, datetime.min.time())
            rows.append({
                'student_id': student.id, 'month_year': label,
                'txn_type': TXN_CHARGE, 'amount': fee,
                'note': 'Monthly fee charged', 'created_by_name': 'system',
                'created_at': charged_at,
            })
            key = (student.id, label)
            bucket = totals.setdefault(key, [fee, 0.0, None])

            if not is_current:
                pay_chance = {'prompt': 0.98, 'regular': 0.90,
                              'late': 0.75, 'defaulter': 0.45}[profile]
            else:
                pay_chance = {'prompt': 0.85, 'regular': 0.55,
                              'late': 0.30, 'defaulter': 0.10}[profile]
            if rng.random() >= pay_chance:
                continue

            amount = fee
            if profile in ('late', 'defaulter') and rng.random() < 0.45:
                amount = round(fee * rng.uniform(0.3, 0.7), 2)
            offset = {'prompt': rng.randint(4, 9), 'regular': rng.randint(10, 20),
                      'late': rng.randint(25, 40), 'defaulter': rng.randint(20, 35)}[profile]
            pay_day = min(m_start + timedelta(days=offset), _today())
            paid_at = datetime.combine(pay_day, datetime.min.time())
            rows.append({
                'student_id': student.id, 'month_year': label,
                'txn_type': TXN_PAYMENT, 'amount': amount,
                'method': rng.choice(methods),
                'reference': f'SLIP-{student.id:04d}-{m_start:%Y%m}',
                'note': 'Seeded demo payment', 'created_by_name': 'system',
                'created_at': paid_at,
            })
            bucket[1] += amount
            bucket[2] = paid_at

            if rng.random() < 0.03:
                surcharge = round(fee * 0.05, 2)
                rows.append({
                    'student_id': student.id, 'month_year': label,
                    'txn_type': TXN_ADJUSTMENT, 'amount': surcharge,
                    'note': 'Late payment surcharge', 'created_by_name': 'system',
                    'created_at': min(datetime.combine(m_end, datetime.min.time()), now),
                })
                bucket[0] += surcharge

        flush_rows(rows)
        progress.report('fees', s_index / max(1, len(students)))

    db.session.commit()

    records = [{'student_id': key[0], 'month_year': key[1],
                'amount_due': round(bucket[0], 2), 'amount_paid': round(bucket[1], 2),
                'status': _status_for(round(bucket[0], 2), round(bucket[1], 2)),
                'payment_date': bucket[2].date() if bucket[2] else None}
               for key, bucket in totals.items()]
    for chunk_start in range(0, len(records), _BULK_CHUNK):
        db.session.execute(record_table.insert(), records[chunk_start:chunk_start + _BULK_CHUNK])
        db.session.commit()
        progress.report('fees', min(1.0, 0.85 + chunk_start / max(1, len(records)) * 0.15))

    progress.report('fees', 1.0)
    return len(records)


def _stage_expenses(rng, cfg, progress, months):
    categories = {c.name: c.id for c in ExpenseCategory.query.all()}
    category_names = [name for name in EXPENSE_AMOUNTS if name in categories]
    if not category_names:
        progress.report('expenses', 1.0)
        return 0

    count = 0
    for m_index, (_label, m_start, m_end) in enumerate(months):
        rows = []
        for i in range(rng.randint(3, 7)):
            name = rng.choice(category_names)
            low, high = EXPENSE_AMOUNTS[name]
            day = m_start + timedelta(days=rng.randint(0, (m_end - m_start).days))
            rows.append(Expense(
                category_id=categories[name],
                amount=round(rng.uniform(low, high), 2),
                payment_method=rng.choice(['Cash', 'Bank', 'Cheque']),
                date=min(day, _today()),
                receipt_no=f'EXP-{m_start:%Y%m}-{i + 1:02d}',
                description=rng.choice(EXPENSE_NOTES),
                logged_by_name='system',
            ))
        db.session.add_all(rows)
        count += len(rows)
        db.session.commit()
        progress.report('expenses', m_index / max(1, len(months)))
    progress.report('expenses', 1.0)
    return count


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


def _stage_class_tests(rng, cfg, progress, classes, months, period_start, period_end):
    abilities = {s.id: rng.uniform(0.42, 0.94)
                 for s in StudentModel.query.all()}
    students_by_class = {}
    for student in StudentModel.query.all():
        students_by_class.setdefault(student.class_id, []).append(student)

    test_total = mark_total = 0
    mark_table = StudentMarkModel.__table__
    pending_marks = 0

    for c_index, class_obj in enumerate(classes):
        subjects = SubjectModel.query.filter_by(class_id=class_obj.id).all()
        class_students = students_by_class.get(class_obj.id, [])
        for m_index, (_label, m_start, m_end) in enumerate(months):
            for subject in subjects:
                if rng.random() > 0.55:
                    continue
                day = m_start + timedelta(days=rng.randint(0, (m_end - m_start).days))
                day = min(day, period_end)
                test_type = rng.choices(['Weekly', 'Monthly', 'Daily'],
                                        weights=[50, 35, 15], k=1)[0]
                total = {'Weekly': 25.0, 'Monthly': 50.0, 'Daily': 15.0}[test_type]
                test = TestModel(
                    test_title=f'{subject.name} {test_type} Test',
                    test_date=day, test_type=test_type,
                    class_id=class_obj.id, subject_id=subject.id,
                    total_marks=total,
                )
                db.session.add(test)
                db.session.flush()
                test_total += 1

                rows = [_mark_row(test.id, s, total, abilities.get(s.id, 0.6), rng)
                        for s in class_students if _enrolled_on(s, day)]
                if rows:
                    db.session.execute(mark_table.insert(), rows)
                    pending_marks += len(rows)
                    mark_total += len(rows)
                if pending_marks >= _BULK_CHUNK:
                    db.session.commit()
                    pending_marks = 0
            progress.report('class_tests',
                            (c_index + (m_index + 1) / len(months)) / len(classes))
        db.session.commit()

    db.session.commit()
    progress.report('class_tests', 1.0)
    return test_total, mark_total


def _stage_term_exams(rng, cfg, progress, classes, period_start, period_end):
    """Mid-Term + Final per academic session overlapping the period."""
    abilities = {s.id: rng.uniform(0.42, 0.94) for s in StudentModel.query.all()}
    students_by_class = {}
    for student in StudentModel.query.all():
        students_by_class.setdefault(student.class_id, []).append(student)

    sessions = []
    year = period_start.year
    while year <= period_end.year:
        label = f'{year}-{(year + 1) % 100:02d}'
        sessions.append((label, 'Mid-Term', date(year, 10, 6), date(year, 10, 20)))
        sessions.append((label, 'Final', date(year + 1, 3, 5), date(year + 1, 3, 19)))
        year += 1
    sessions = [(label, kind, start, end) for label, kind, start, end in sessions
                if end <= period_end and end >= period_start]

    # Short demo periods (1–6 months) rarely contain a calendar Mid-Term/Final;
    # fall back to one Mid-Term placed inside the period so results workflows
    # still have data to show.
    if not sessions:
        span = (period_end - period_start).days
        if span >= 30:
            start = period_start + timedelta(days=int(span * 0.35))
            end = start + timedelta(days=13)
            if end <= period_end:
                sessions.append((_session_label(start), 'Mid-Term', start, end))

    exam_total = test_total = mark_total = 0
    mark_table = StudentMarkModel.__table__
    pending = 0

    for s_index, (label, kind, start, end) in enumerate(sessions):
        for class_obj in classes:
            exam = TermExam(
                name=f'{kind} Examination {label}',
                class_id=class_obj.id,
                exam_type=kind,
                session_label=label,
                start_date=start,
                end_date=end,
                announce_date=min(end + timedelta(days=7), _today()),
                status='Published',
                created_by='system',
            )
            db.session.add(exam)
            db.session.flush()
            exam_total += 1

            subjects = SubjectModel.query.filter_by(class_id=class_obj.id).all()
            class_students = students_by_class.get(class_obj.id, [])
            for sub_index, subject in enumerate(subjects):
                test = TestModel(
                    test_title=f'{subject.name} {kind} Examination',
                    test_date=start + timedelta(days=sub_index % (max(1, (end - start).days + 1))),
                    test_type=kind,
                    class_id=class_obj.id, subject_id=subject.id,
                    total_marks=100.0, term_exam_id=exam.id,
                    start_time='09:00', room=f'Room {sub_index + 1}',
                )
                db.session.add(test)
                db.session.flush()
                test_total += 1

                rows = [_mark_row(test.id, s, 100.0, abilities.get(s.id, 0.6), rng)
                        for s in class_students if _enrolled_on(s, start)]
                if rows:
                    db.session.execute(mark_table.insert(), rows)
                    pending += len(rows)
                    mark_total += len(rows)
                if pending >= _BULK_CHUNK:
                    db.session.commit()
                    pending = 0
            db.session.commit()
        progress.report('term_exams', s_index / max(1, len(sessions)))

    db.session.commit()
    progress.report('term_exams', 1.0)
    return exam_total, test_total, mark_total


def _stage_payroll(rng, cfg, progress, months, teacher_month_counts, teacher_leaving):
    teachers = [(t, t.joining_date or _today() - timedelta(days=365))
                for t in TeacherModel.query.all()]
    count = 0

    for m_index, (label, m_start, m_end) in enumerate(months):
        ym = f'{m_start.year:04d}-{m_start.month:02d}'
        for teacher, joining in teachers:
            leaving = teacher_leaving.get(teacher.id)
            if m_end < joining or (leaving and m_start > leaving):
                continue
            counts = teacher_month_counts.get((teacher.id, ym),
                                              {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0})
            base = round(float(teacher.monthly_salary or teacher.salary or 0.0), 2)
            working_days = sum(counts.values()) or 26
            absent = counts.get('Absent', 0)
            deductions = round(absent * (base / max(1, working_days)), 2) if base else 0.0
            bonus = round(rng.uniform(2000, 5000), 2) if rng.random() < 0.06 else 0.0
            is_current = m_end >= _today()
            if is_current or rng.random() > 0.93:
                status, payment_date, method = 'Pending', None, None
            else:
                status = 'Paid'
                payment_date = min(_month_end_for_pay(m_start), _today())
                method = rng.choice(['Cash', 'Bank', 'Cheque'])
            db.session.add(StaffPayroll(
                teacher_id=teacher.id, month_year=ym,
                base_salary=base, bonus=bonus, deductions=deductions,
                net_salary=round(base + bonus - deductions, 2),
                payment_status=status, payment_date=payment_date,
                payment_method=method, notes=None, generated_by='system',
                working_days=working_days,
                present_days=counts.get('Present', 0) + counts.get('Late', 0),
                absent_days=absent, late_days=counts.get('Late', 0),
                leave_days=counts.get('Leave', 0),
            ))
            count += 1
        db.session.commit()
        progress.report('payroll', m_index / max(1, len(months)))

    db.session.commit()
    progress.report('payroll', 1.0)
    return count


def _month_end_for_pay(m_start):
    return _shift_month(m_start, 1) - timedelta(days=2)


def _stage_photos(rng, cfg, progress):
    """Optional locally drawn avatar JPEGs — nothing else in the app changes."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # Pillow missing: photos stay optional, skip quietly.
        progress.report('photos', 1.0)
        return 0

    def avatar_bytes(initials, color):
        size = 320
        img = Image.new('RGB', (size, size), color)
        draw = ImageDraw.Draw(img)
        light = tuple(min(255, channel + 60) for channel in color)
        draw.ellipse([36, 36, size - 36, size - 36], fill=light)
        font = None
        for font_name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf'):
            try:
                font = ImageFont.truetype(font_name, 128)
                break
            except OSError:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(128)
            except TypeError:
                font = ImageFont.load_default()
        left, top, right, bottom = draw.textbbox((0, 0), initials, font=font)
        draw.text(((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
                  initials, fill='white', font=font)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()

    def photo_dir(kind):
        root = (current_app.config.get('PHOTO_UPLOAD_DIR')
                or os.path.join(current_app.instance_path, 'uploads'))
        path = os.path.join(root, kind + 's')
        os.makedirs(path, exist_ok=True)
        return path

    created = 0
    targets = ([('student', s) for s in StudentModel.query.all()] +
               [('teacher', t) for t in TeacherModel.query.all()])
    for index, (kind, person) in enumerate(targets):
        if rng.random() > 0.6:
            continue
        parts = (person.student_name if kind == 'student' else person.teacher_name).split()
        initials = ''.join(part[0] for part in parts[:2]).upper() or 'S'
        filename = uuid.uuid4().hex + '.jpg'
        with open(os.path.join(photo_dir(kind), filename), 'wb') as handle:
            handle.write(avatar_bytes(initials, AVATAR_PALETTE[index % len(AVATAR_PALETTE)]))
        person.photo_filename = filename
        created += 1
        if index % 50 == 0:
            db.session.commit()
        progress.report('photos', index / max(1, len(targets)))

    db.session.commit()
    progress.report('photos', 1.0)
    return created


def _stage_accounts(rng, cfg, progress):
    """Documented demo accounts (idempotent; the wizard already has its admin)."""
    import os as _os
    password = _os.environ.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'

    if AdminUser.query.filter_by(username='admin').first() is None:
        admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='School Administrator')
        admin.set_password(password)
        db.session.add(admin)

    if AdminUser.query.filter_by(username='teacher1').first() is None:
        teacher_user = AdminUser(username='teacher1', role=ROLE_TEACHER, full_name='Demo Teacher')
        teacher_user.set_password(password)
        db.session.add(teacher_user)

    first_student = (StudentModel.query.filter_by(is_active=True)
                     .order_by(StudentModel.id).first())
    parent = AdminUser.query.filter_by(username='parent1').first()
    if parent is None and first_student is not None:
        parent = AdminUser(username='parent1', role=ROLE_PARENT,
                           full_name=f'Guardian of {first_student.student_name}',
                           student_id=first_student.id)
        parent.set_password(password)
        db.session.add(parent)
        db.session.flush()
        db.session.add(GuardianStudentLink(user_id=parent.id, student_id=first_student.id))

    db.session.commit()
    progress.report('accounts', 1.0)
    return password


# -- orchestrator ------------------------------------------------------------

def run_seed(config, progress_cb=None):
    """Generate the demo dataset described by ``config``.

    Must run inside an application context.  Returns a summary dict of the
    generated counts.  ``progress_cb(stage, percent)`` receives the global
    0-100 percentage as stages complete.
    """
    if not isinstance(config, SeedConfig):
        raise TypeError('config must be a SeedConfig')
    cfg = config
    rng = random.Random(cfg.random_seed)
    progress = _Progress(progress_cb)

    today = _today()
    period_start = _shift_month(today.replace(day=1), -(max(1, cfg.months) - 1))
    period_end = today
    months = []
    cursor = period_start
    while cursor <= period_end:
        months.append((cursor.strftime('%B %Y'), cursor, _month_end(cursor)))
        cursor = _shift_month(cursor, 1)

    suspend_audit()
    summary = {'period_start': period_start.isoformat(),
               'period_end': period_end.isoformat(),
               'months': cfg.months}
    try:
        classes = _stage_structure(rng, cfg, progress)

        teachers, teacher_leaving = _stage_teachers(rng, cfg, progress, classes, period_start)
        summary['teachers'] = len(teachers)

        _stage_students(rng, cfg, progress, classes, period_start, period_end)
        summary['students'] = StudentModel.query.count()

        teacher_month_counts = {}
        if cfg.include_attendance:
            teacher_month_counts = _stage_attendance(rng, cfg, progress,
                                                     period_start, period_end,
                                                     teacher_leaving)
        summary['attendance_rows'] = AttendanceModel.query.count()

        if cfg.include_fees:
            summary['fee_records'] = _stage_fees(rng, cfg, progress, months,
                                                 period_start, period_end)
        summary['fee_transactions'] = FeeTransaction.query.count()

        if cfg.include_expenses:
            summary['expenses'] = _stage_expenses(rng, cfg, progress, months)

        if cfg.include_class_tests:
            tests, marks = _stage_class_tests(rng, cfg, progress, classes, months,
                                              period_start, period_end)
            summary['class_tests'] = tests
            summary['class_test_marks'] = marks

        if cfg.include_term_exams:
            exams, etests, emarks = _stage_term_exams(rng, cfg, progress, classes,
                                                      period_start, period_end)
            summary['term_exams'] = exams
            summary['term_exam_tests'] = etests
            summary['term_exam_marks'] = emarks

        if cfg.include_payroll:
            summary['payroll_rows'] = _stage_payroll(rng, cfg, progress, months,
                                                     teacher_month_counts, teacher_leaving)

        if cfg.generate_photos:
            summary['photos'] = _stage_photos(rng, cfg, progress)

        summary['demo_password'] = _stage_accounts(rng, cfg, progress)
    except Exception:
        db.session.rollback()
        raise
    finally:
        resume_audit()

    summary['students'] = StudentModel.query.count()
    summary['teachers'] = TeacherModel.query.count()
    db.session.commit()

    log_action(
        'create',
        entity_type='DemoData',
        summary=('Demo data generated: {students} students, {teachers} teachers, '
                 '{months} month(s) of history').format(
                     students=summary.get('students', 0),
                     teachers=summary.get('teachers', 0),
                     months=cfg.months),
        after={key: value for key, value in summary.items()
               if isinstance(value, (int, float, str))},
    )
    db.session.commit()
    return summary


def estimate_records(student_count, teacher_count, months):
    """Rough record-count estimate used by the setup wizard UI."""
    school_days = int(months * 26)
    attendance = (student_count + teacher_count) * school_days
    fee_txns = student_count * months * 2
    marks = student_count * max(1, int(months * 3.5))
    return attendance + fee_txns + marks + student_count * 2 + teacher_count * months

"""Populate the School Manager database with realistic *synthetic* demo data.

The script is idempotent: running it twice does not duplicate anything.  Use
``--reset`` to drop every table first and rebuild from scratch.

Examples
--------
    python seed_data.py                     # top up missing demo data
    python seed_data.py --reset             # wipe and rebuild everything
    python seed_data.py --students 120 --teachers 14

All names, phone numbers and amounts are fabricated.  No real student data is
used at any point.
"""

import argparse
import hashlib
import os
import random
import sys
from datetime import date, datetime, timedelta

from app import create_app
from app.database import db
from app.services.roll_numbers import FIRST_ROLL_NUMBER
from app.models import (
    ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER,
    AdminUser, AttendanceModel, ClassModel, FeeRecordModel, FeeTransaction,
    GuardianStudentLink, SchoolSettings, SectionModel, StudentMarkModel, StudentModel,
    SubjectModel, TeacherModel, TestModel, TestTypeModel,
    TXN_CHARGE, TXN_PAYMENT,
)

DEMO_PASSWORD = os.environ.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'

CLASS_NAMES = ['Playgroup', 'Nursery', 'Class 1', 'Class 2', 'Class 3', 'Class 4',
               'Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10']
SUBJECT_NAMES = ['English', 'Urdu', 'Mathematics', 'Science', 'Islamiyat']
TEST_TYPES = ['Daily', 'Weekly', 'Monthly', 'Mid-Term', 'Final']
FIRST_NAMES = ['Ali', 'Ahmed', 'Hassan', 'Hussain', 'Bilal', 'Ayesha', 'Fatima',
               'Maryam', 'Hamza', 'Zain', 'Sana', 'Usman', 'Hira', 'Adeel']
LAST_NAMES = ['Khan', 'Awan', 'Malik', 'Rana', 'Qureshi', 'Abbasi']
TEACHER_NAMES = ['M. Akram', 'Ayesha Bibi', 'Tariq Mahmood', 'Sana Khan', 'Usman Ali',
                 'Farah Nadeem', 'Ali Raza', 'Hina Malik', 'Bilal Ahmed', 'Maryam Noor',
                 'Zahid Hassan', 'Nadia Shahid', 'Kashif Aslam', 'Saima Qureshi']

ATTENDANCE_DAYS = 10
FEE_MONTHS = 3


def _stable_fraction(*parts):
    """Deterministic 0..1 value for a tuple of identifiers.

    Using a hash instead of the rolling RNG keeps the seeded dataset stable when
    the script is re-run: a decision that was "no payment" on the first run stays
    "no payment" on the next one, so re-seeding never changes a student's balance.
    """
    raw = '|'.join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _month_labels(count=FEE_MONTHS):
    """Return the last ``count`` billing months, oldest first."""
    labels = []
    cursor = date.today().replace(day=1)
    for _ in range(count):
        labels.append(cursor.strftime('%B %Y'))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(labels))


def _recent_school_days(count=ATTENDANCE_DAYS):
    days, cursor = [], date.today()
    while len(days) < count:
        if cursor.weekday() < 5:  # Monday-Friday
            days.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(days)


def reset_database():
    db.drop_all()
    db.create_all()
    print('Database reset: all tables dropped and recreated.')


def ensure_settings(school_name='Green Valley Public School'):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
    settings.school_name = settings.school_name or school_name
    settings.tagline = settings.tagline or 'Knowledge · Discipline · Character'
    settings.address = settings.address or '12-B Main Road, Sargodha'
    settings.phone = settings.phone or '+92 300 1234567'
    settings.email = settings.email or 'office@greenvalley.example'
    settings.school_start_time = settings.school_start_time or '08:30'
    settings.school_end_time = settings.school_end_time or '15:00'
    return settings


def ensure_users():
    """Create the three documented demo accounts (idempotent)."""
    accounts = []

    admin = AdminUser.query.filter_by(username='admin').first()
    if admin is None:
        admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='School Administrator')
        admin.set_password(DEMO_PASSWORD)
        db.session.add(admin)
    accounts.append(('admin', ROLE_ADMIN))

    teacher = AdminUser.query.filter_by(username='teacher1').first()
    if teacher is None:
        teacher = AdminUser(username='teacher1', role=ROLE_TEACHER, full_name='Demo Teacher')
        teacher.set_password(DEMO_PASSWORD)
        db.session.add(teacher)
    accounts.append(('teacher1', ROLE_TEACHER))

    db.session.flush()

    first_student = StudentModel.query.filter_by(is_active=True).order_by(StudentModel.id).first()
    parent = AdminUser.query.filter_by(username='parent1').first()
    if parent is None:
        parent = AdminUser(username='parent1', role=ROLE_PARENT,
                           full_name='Guardian (demo)', student_id=first_student.id if first_student else None)
        parent.set_password(DEMO_PASSWORD)
        db.session.add(parent)
        db.session.flush()
    elif first_student and parent.student_id is None:
        parent.student_id = first_student.id

    if parent.student_id and GuardianStudentLink.query.filter_by(
            user_id=parent.id, student_id=parent.student_id).first() is None:
        db.session.add(GuardianStudentLink(user_id=parent.id, student_id=parent.student_id))

    accounts.append(('parent1', ROLE_PARENT))

    db.session.commit()
    return accounts


def ensure_structure():
    classes = []
    for name in CLASS_NAMES:
        class_obj = ClassModel.query.filter_by(name=name).first()
        if class_obj is None:
            class_obj = ClassModel(name=name)
            db.session.add(class_obj)
            db.session.flush()
        classes.append(class_obj)

        for section_name in ('A', 'B'):
            if SectionModel.query.filter_by(class_id=class_obj.id, name=section_name).first() is None:
                db.session.add(SectionModel(name=section_name, class_id=class_obj.id))

        for subject_name in SUBJECT_NAMES:
            if SubjectModel.query.filter_by(class_id=class_obj.id, name=subject_name).first() is None:
                db.session.add(SubjectModel(name=subject_name, class_id=class_obj.id))

    for test_name in TEST_TYPES:
        if TestTypeModel.query.filter_by(name=test_name).first() is None:
            db.session.add(TestTypeModel(name=test_name))

    db.session.commit()
    return classes


def ensure_teachers(count, classes):
    existing = TeacherModel.query.count()
    for index in range(existing, count):
        name = TEACHER_NAMES[index % len(TEACHER_NAMES)]
        db.session.add(TeacherModel(
            teacher_id_str=f'T{index + 1:03d}',
            teacher_name=name,
            joining_date=date.today() - timedelta(days=400 + index * 7),
            qualification='B.Ed / M.Ed',
            salary=35000 + index * 1500,
            salary_type='monthly',
            monthly_salary=35000 + index * 1500,
            hourly_rate=500 + index * 25,
            assigned_class=classes[index % len(classes)].name,
        ))
    db.session.commit()
    return TeacherModel.query.count()


def ensure_students(count, default_monthly_fee, rng):
    existing = StudentModel.query.count()
    classes = ClassModel.query.order_by(ClassModel.id).all()
    if not classes or existing >= count:
        return StudentModel.query.count()

    next_rolls = {}
    for class_obj in classes:
        highest = (db.session.query(db.func.max(StudentModel.roll_number))
                   .filter(StudentModel.class_id == class_obj.id)
                   .scalar())
        next_rolls[class_obj.id] = int(highest) + 1 if highest is not None else FIRST_ROLL_NUMBER

    for index in range(existing, count):
        class_obj = classes[index % len(classes)]
        sections = SectionModel.query.filter_by(class_id=class_obj.id).order_by(SectionModel.id).all()
        section = sections[index % len(sections)] if sections else None
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
        roll = next_rolls[class_obj.id]
        next_rolls[class_obj.id] = roll + 1
        db.session.add(StudentModel(
            roll_number=roll,
            student_name=f'{first} {last}',
            father_name=f'{last} (father of {first})',
            guardian_phone=f'+92300{1000000 + index:07d}',
            address=f'House {10 + index}, Block {chr(65 + index % 6)}, Sargodha',
            class_id=class_obj.id,
            section_id=section.id if section else None,
            monthly_fee=float(default_monthly_fee) + (index % 4) * 100,
            is_active=True,
        ))
    db.session.commit()
    return StudentModel.query.count()


def ensure_attendance(rng):
    days = _recent_school_days()
    students = StudentModel.query.filter_by(is_active=True).all()
    created = 0
    weights = [('Present', 0.85), ('Absent', 0.07), ('Late', 0.05), ('Leave', 0.03)]

    for student in students:
        for day in days:
            if AttendanceModel.query.filter_by(target_type='student', target_id=student.id,
                                               date=day).first():
                continue
            roll = rng.random()
            cumulative = 0.0
            status = 'Present'
            for label, weight in weights:
                cumulative += weight
                if roll <= cumulative:
                    status = label
                    break
            late_time = None
            if status == 'Late':
                late_time = f'08:{rng.randint(35, 59):02d}'
            db.session.add(AttendanceModel(
                date=day, target_type='student', target_id=student.id,
                status=status, class_id=student.class_id, late_time=late_time,
            ))
            created += 1

    teachers = TeacherModel.query.filter_by(is_active=True).all()
    for teacher in teachers:
        for day in days:
            if AttendanceModel.query.filter_by(target_type='teacher', target_id=teacher.id,
                                               date=day).first():
                continue
            db.session.add(AttendanceModel(
                date=day, target_type='teacher', target_id=teacher.id,
                status='Present' if rng.random() > 0.06 else 'Absent',
            ))
            created += 1

    db.session.commit()
    return created


def ensure_tests_and_marks(rng):
    classes = ClassModel.query.order_by(ClassModel.id).all()
    tests_created = marks_created = 0

    for class_obj in classes:
        subjects = SubjectModel.query.filter_by(class_id=class_obj.id).order_by(SubjectModel.id).limit(2).all()
        for offset, subject in enumerate(subjects):
            title = f'{subject.name} Monthly Test'
            test = TestModel.query.filter_by(test_title=title, class_id=class_obj.id,
                                             subject_id=subject.id).first()
            if test is None:
                test = TestModel(
                    test_title=title,
                    test_date=date.today() - timedelta(days=14 - offset * 7),
                    test_type='Monthly',
                    class_id=class_obj.id,
                    subject_id=subject.id,
                    total_marks=100,
                )
                db.session.add(test)
                db.session.flush()
                tests_created += 1

            students = StudentModel.query.filter_by(is_active=True, class_id=class_obj.id).all()
            for student in students:
                if StudentMarkModel.query.filter_by(test_id=test.id, student_id=student.id).first():
                    continue
                obtained = rng.randint(35, 99)
                percentage = round(obtained / test.total_marks * 100, 1)
                if percentage >= 85:
                    grade = 'A+'
                elif percentage >= 70:
                    grade = 'A'
                elif percentage >= 60:
                    grade = 'B'
                elif percentage >= 50:
                    grade = 'C'
                elif percentage >= 40:
                    grade = 'D'
                else:
                    grade = 'F'
                db.session.add(StudentMarkModel(
                    test_id=test.id, student_id=student.id,
                    marks_obtained=float(obtained), percentage=percentage, grade=grade,
                ))
                marks_created += 1

    db.session.commit()
    return tests_created, marks_created


def ensure_fees(rng):
    months = _month_labels()
    students = StudentModel.query.filter_by(is_active=True).order_by(StudentModel.id).all()
    charges = payments = 0

    for student in students:
        fee = float(student.monthly_fee or 0.0)
        if fee <= 0:
            continue

        for month_index, month in enumerate(months):
            existing_charge = FeeTransaction.query.filter_by(
                student_id=student.id, month_year=month, txn_type=TXN_CHARGE).first()
            if existing_charge is None:
                db.session.add(FeeTransaction(
                    student_id=student.id, month_year=month, txn_type=TXN_CHARGE,
                    amount=fee, note='Monthly fee charged',
                    created_by_name='system',
                    created_at=datetime.combine(_month_start(month), datetime.min.time()) + timedelta(days=3),
                ))
                charges += 1

            if FeeTransaction.query.filter_by(student_id=student.id, month_year=month,
                                              txn_type=TXN_PAYMENT).first():
                continue

            # Older months are mostly settled; the current month has more debtors.
            is_current_month = month_index == len(months) - 1
            roll = _stable_fraction(student.id, month, 'payment')
            if is_current_month:
                amount = 0.0 if roll < 0.35 else (fee / 2 if roll < 0.55 else fee)
            else:
                amount = 0.0 if roll < 0.12 else (fee / 2 if roll < 0.22 else fee)

            if amount > 0:
                methods = ['cash', 'bank', 'online']
                method = methods[int(_stable_fraction(student.id, month, 'method') * 3) % 3]
                db.session.add(FeeTransaction(
                    student_id=student.id, month_year=month, txn_type=TXN_PAYMENT,
                    amount=round(amount, 2),
                    method=method,
                    reference=f'RCPT-{month_index + 1}{student.id:04d}',
                    note='Seeded demo payment',
                    created_by_name='system',
                    created_at=datetime.combine(_month_start(month), datetime.min.time()) + timedelta(days=6),
                ))
                payments += 1

    db.session.commit()
    return charges, payments


def _month_start(month_label):
    return datetime.strptime(month_label, '%B %Y').date().replace(day=1)


def rebuild_fee_summaries():
    """Recompute every cached fee summary row from the ledger."""
    from app.services.fee_ledger import recompute_fee_record

    keys = {(t.student_id, t.month_year)
            for t in FeeTransaction.query.filter_by(is_void=False).all()}
    for student_id, month in keys:
        recompute_fee_record(student_id, month)
    db.session.commit()
    return len(keys)


def run(args):
    app = create_app()
    with app.app_context():
        if args.reset:
            reset_database()

        rng = random.Random(args.seed)
        ensure_settings()
        ensure_structure()
        teacher_count = ensure_teachers(args.teachers, ClassModel.query.order_by(ClassModel.id).all())
        student_count = ensure_students(args.students, args.fee, rng)
        attendance_rows = ensure_attendance(rng)
        tests_created, marks_created = ensure_tests_and_marks(rng)
        charges, payments = ensure_fees(rng)
        accounts = ensure_users()
        summary_rows = rebuild_fee_summaries()

        print('Seed complete.')
        print(f'  classes          : {ClassModel.query.count()}')
        print(f'  sections         : {SectionModel.query.count()}')
        print(f'  subjects         : {SubjectModel.query.count()}')
        print(f'  teachers         : {teacher_count}')
        print(f'  students         : {student_count}')
        print(f'  attendance rows  : +{attendance_rows} (total {AttendanceModel.query.count()})')
        print(f'  tests / marks    : +{tests_created} / +{marks_created}')
        print(f'  fee charges/paid : +{charges} / +{payments}')
        print(f'  fee summaries    : {summary_rows}')
        print('  demo accounts    : ' + ', '.join(f'{u} ({r})' for u, r in accounts))
        print(f'  demo password    : {DEMO_PASSWORD}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reset', action='store_true',
                        help='drop every table and rebuild from scratch')
    parser.add_argument('--students', type=int, default=60, help='target number of students')
    parser.add_argument('--teachers', type=int, default=12, help='target number of teachers')
    parser.add_argument('--fee', type=float, default=2500.0, help='base monthly fee (PKR)')
    parser.add_argument('--seed', type=int, default=20260928, help='random seed for reproducibility')
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

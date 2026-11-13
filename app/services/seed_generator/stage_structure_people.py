"""Stages: the class/section/subject structure, teachers and students."""

import json
from datetime import date, timedelta

from app.database import db
from app.models import (ClassModel, SchoolSettings, SectionModel, StudentModel, SubjectModel, TeacherModel,
                        TestTypeModel)
from app.models.settings import (get_custom_fields, get_holiday_ranges, set_custom_fields,
                                 set_holiday_ranges)
from app.services.enrollments import close_open_enrollment, start_enrollment
from app.services.roll_numbers import FIRST_ROLL_NUMBER

from .data import (CLASS_LEVELS, CUSTOM_FIELDS, DEMO_HOLIDAYS, DESIGNATIONS, FATHER_FIRST, FIRST_NAMES_FEMALE, FIRST_NAMES_MALE,
                   LAST_NAMES, LEAVING_REASONS, QUALIFICATIONS, SECTION_NAMES, SUBJECT_NAMES,
                   TEST_TYPE_NAMES)
from .helpers import (_address, _cnic, _custom_field_values, _ensure_library_subjects, _person_name,
                      _phone, _session_label, _today)


def _stage_structure(rng, cfg, progress, period_start=None, period_end=None):
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
    settings.academic_session = settings.academic_session or _session_label(_today())
    if not settings.attendance_grace_minutes:
        settings.attendance_grace_minutes = 10
    if not settings.result_announcement_date:
        settings.result_announcement_date = _today().isoformat()

    classes = []
    library_by_lower = _ensure_library_subjects(SUBJECT_NAMES)
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
            existing_subject = SubjectModel.query.filter_by(class_id=class_obj.id,
                                                            name=subject_name).first()
            if existing_subject is None:
                db.session.add(SubjectModel(
                    name=subject_name, class_id=class_obj.id,
                    library_id=library_by_lower[subject_name.strip().lower()].id))
            elif existing_subject.library_id is None:
                existing_subject.library_id = library_by_lower[subject_name.strip().lower()].id

    for test_name in TEST_TYPE_NAMES:
        if TestTypeModel.query.filter_by(name=test_name).first() is None:
            db.session.add(TestTypeModel(name=test_name))

    from app.services.expense_service import seed_default_categories
    seed_default_categories()
    from app.services.other_income_service import seed_default_categories as seed_income_categories
    seed_income_categories()

    db.session.commit()

    # Custom fields (so every student / teacher record carries them) and the
    # school calendar's public holidays - only when the school has none yet.
    for entity_type, fields in CUSTOM_FIELDS.items():
        if not get_custom_fields(entity_type):
            set_custom_fields(entity_type, fields)
    if period_start is not None and not get_holiday_ranges():
        ranges = []
        for year in range(period_start.year, (period_end or _today()).year + 1):
            for month, day, label in DEMO_HOLIDAYS:
                when = date(year, month, day)
                if period_start <= when <= (period_end or _today()) + timedelta(days=120):
                    ranges.append({'label': label, 'start': when.isoformat(),
                                   'end': when.isoformat()})
        if ranges:
            set_holiday_ranges(ranges)

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
            custom_fields_data=_custom_field_values(rng, 'teacher'),
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
        # The monthly fee is what the student actually pays: the class fee after the
        # discount (a few students have a hand-agreed fee that differs by Rs 100).
        if discount_type == 'percentage':
            monthly_fee = round(class_fee * (1 - discount_value / 100.0), 2)
        elif discount_type == 'fixed':
            monthly_fee = round(max(0.0, class_fee - discount_value), 2)
        else:
            monthly_fee = max(0.0, class_fee + rng.choice([-100, 0, 0, 0, 0, 100]))

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

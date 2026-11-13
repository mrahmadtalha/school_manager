"""Stages: class tests, term exams and payroll."""

from datetime import date, timedelta

from app.database import db
from app.models import (StaffPayroll, StudentMarkModel, StudentModel, SubjectModel, TeacherModel, TermExam,
                        TestModel)

from .data import _BULK_CHUNK
from .helpers import (_enrolled_on, _mark_row, _month_end_for_pay, _session_label, _today)


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
    """Monthly payroll; paid months get real salary payments (and their expense mirror)."""
    from app.services.payroll_service import record_salary_payment

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
            notes = []
            if bonus:
                notes.append('Festival bonus')
            if deductions:
                notes.append(f'{absent} day(s) absent deducted')
            record = StaffPayroll(
                teacher_id=teacher.id, month_year=ym,
                base_salary=base, bonus=bonus, deductions=deductions,
                net_salary=round(base + bonus - deductions, 2),
                payment_status='Pending', payment_date=None,
                payment_method=None, notes='; '.join(notes) or None, generated_by='admin',
                working_days=working_days,
                present_days=counts.get('Present', 0) + counts.get('Late', 0),
                absent_days=absent, late_days=counts.get('Late', 0),
                leave_days=counts.get('Leave', 0),
            )
            db.session.add(record)
            count += 1

            is_current = m_end >= _today()
            roll = rng.random()
            if is_current:
                outcome = 'pending' if roll < 0.75 else ('partial' if roll < 0.85 else 'paid')
            else:
                outcome = 'paid' if roll < 0.93 else ('partial' if roll < 0.97 else 'pending')
            if outcome == 'pending' or record.net_salary <= 0:
                continue
            db.session.flush()
            pay_day = min(_month_end_for_pay(m_start), _today())
            method = rng.choice(['Cash', 'Bank', 'Cheque'])
            if outcome == 'partial':
                first = round(record.net_salary * rng.uniform(0.4, 0.7), 2)
                record_salary_payment(record, first, pay_day, method, note='Advance part-payment',
                                      actor=None)
            else:
                record_salary_payment(record, record.net_salary, pay_day, method, actor=None)
        db.session.commit()
        progress.report('payroll', m_index / max(1, len(months)))

    db.session.commit()
    progress.report('payroll', 1.0)
    return count

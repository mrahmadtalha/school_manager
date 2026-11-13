"""``run_seed()`` runs every stage in order, and ``estimate_records()`` sizes a run up front."""

import random

from app.database import db
from app.models import (AttendanceModel, CanteenEntry, Expense, FeeTransaction, IssuedDocument, MessageQueue,
                        OtherIncome, Product, StaffPayroll, StudentModel, StudentRemark, TeacherModel,
                        TermExam, TestModel)
from app.services.audit import log_action, resume_audit, suspend_audit

from .config import SeedConfig, _Progress
from .helpers import _month_end, _shift_month, _today
from .stage_attendance_fees import _stage_attendance, _stage_expenses, _stage_fees
from .stage_admission import _stage_admission
from .stage_inventory import _stage_inventory
from .stage_misc import _stage_accounts, _stage_photos
from .stage_money import _stage_canteen, _stage_documents, _stage_other_income
from .stage_school_life import _stage_remarks, _stage_school_life
from .stage_structure_people import _stage_structure, _stage_students, _stage_teachers
from .stage_tests_payroll import _stage_class_tests, _stage_payroll, _stage_term_exams


def _has(query):
    """True when the table (or filtered query) already holds a row."""
    return query.first() is not None


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
        classes = _stage_structure(rng, cfg, progress, period_start, period_end)

        teachers, teacher_leaving = _stage_teachers(rng, cfg, progress, classes, period_start)
        summary['teachers'] = len(teachers)

        _stage_students(rng, cfg, progress, classes, period_start, period_end)
        summary['students'] = StudentModel.query.count()

        book_sets = uniform_sets = None
        if cfg.include_inventory and not _has(Product.query):
            inventory_summary, book_sets, uniform_sets = _stage_inventory(
                rng, cfg, progress, classes, months, period_start, period_end)
            summary.update(inventory_summary)

        if cfg.include_admission:
            summary.update(_stage_admission(rng, cfg, progress, classes, period_start, period_end,
                                            book_sets, uniform_sets))

        teacher_month_counts = {}
        if cfg.include_attendance and not _has(AttendanceModel.query):
            teacher_month_counts = _stage_attendance(rng, cfg, progress,
                                                     period_start, period_end,
                                                     teacher_leaving)
        summary['attendance_rows'] = AttendanceModel.query.count()

        if cfg.include_fees and not _has(FeeTransaction.query):
            summary['fee_records'] = _stage_fees(rng, cfg, progress, months,
                                                 period_start, period_end)
        summary['fee_transactions'] = FeeTransaction.query.count()

        if cfg.include_expenses and not _has(Expense.query):
            summary['expenses'] = _stage_expenses(rng, cfg, progress, months)

        if cfg.include_class_tests and not _has(TestModel.query):
            tests, marks = _stage_class_tests(rng, cfg, progress, classes, months,
                                              period_start, period_end)
            summary['class_tests'] = tests
            summary['class_test_marks'] = marks

        if cfg.include_term_exams and not _has(TermExam.query):
            exams, etests, emarks = _stage_term_exams(rng, cfg, progress, classes,
                                                      period_start, period_end)
            summary['term_exams'] = exams
            summary['term_exam_tests'] = etests
            summary['term_exam_marks'] = emarks

        if cfg.include_term_exams and cfg.include_school_life and not _has(StudentRemark.query):
            summary['remarks'] = _stage_remarks(rng, cfg, progress)

        if cfg.include_payroll and not _has(StaffPayroll.query):
            summary['payroll_rows'] = _stage_payroll(rng, cfg, progress, months,
                                                     teacher_month_counts, teacher_leaving)

        if cfg.include_other_income and not _has(OtherIncome.query.filter(OtherIncome.student_id.is_(None))):
            summary['other_income'] = _stage_other_income(rng, cfg, progress, months)

        if cfg.include_canteen and not _has(CanteenEntry.query):
            summary['canteen_entries'] = _stage_canteen(rng, cfg, progress, months)

        if cfg.include_documents and not _has(IssuedDocument.query):
            summary['issued_documents'] = _stage_documents(rng, cfg, progress, period_start)

        if cfg.include_school_life:
            summary.update(_stage_school_life(rng, cfg, progress, classes))

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

"""Advanced demo-data generator: realism, lifecycle, and integration checks.

Every test runs the generator on a tiny configuration so the suite stays fast
while still exercising each stage end to end.
"""

import pathlib
import shutil
import tempfile
from datetime import date

from app.database import db
from app.models import (
    AttendanceModel, AuditLog, ClassModel, Expense, FeeRecordModel,
    FeeTransaction, SchoolSettings, StaffPayroll, StudentEnrollment,
    StudentMarkModel, StudentModel, SubjectModel, TeacherModel, TermExam,
    TestModel,
)
from app.services.seed_generator import SeedConfig, estimate_records, run_seed


def _small_config(**overrides):
    config = SeedConfig(
        student_count=12, teacher_count=3, monthly_fee=2000.0, months=3,
        random_seed=42,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _test_config():
    return SeedConfig(student_count=12, teacher_count=3, monthly_fee=2000.0,
                      months=3, random_seed=42)


def test_run_seed_populates_every_area(app):
    with app.app_context():
        summary = run_seed(_small_config())

        assert StudentModel.query.count() == 12
        assert TeacherModel.query.count() == 3
        assert ClassModel.query.count() >= 12          # Playgroup .. Class 10
        assert SubjectModel.query.count() >= 12 * 5
        assert AttendanceModel.query.count() > 0
        assert FeeTransaction.query.count() > 0
        assert FeeRecordModel.query.count() > 0
        assert Expense.query.count() > 0
        assert TestModel.query.count() > 0             # class tests
        assert StudentMarkModel.query.count() > 0
        assert TermExam.query.count() > 0
        assert StaffPayroll.query.count() > 0
        assert SchoolSettings.query.first() is not None
        assert summary['students'] == 12


def test_student_ages_match_class_level(app):
    with app.app_context():
        run_seed(_small_config())

        expected_age = {'Playgroup': 3, 'Nursery': 4, 'Class 1': 5, 'Class 2': 6,
                        'Class 3': 7, 'Class 4': 8, 'Class 5': 9, 'Class 6': 10,
                        'Class 7': 11, 'Class 8': 12, 'Class 9': 13, 'Class 10': 14}
        for student in StudentModel.query.filter(
                StudentModel.date_of_birth.isnot(None),
                StudentModel.admission_number.isnot(None)).all():
            if student.status != 'enrolled':
                continue
            age = date.today().year - student.date_of_birth.year
            level = expected_age[student.class_info.name]
            assert level <= age <= level + 2, (
                f'{student.student_name} in {student.class_info.name} is {age}')


def test_teacher_ages_are_adult(app):
    with app.app_context():
        run_seed(_small_config())

        for teacher in TeacherModel.query.filter(
                TeacherModel.date_of_birth.isnot(None),
                TeacherModel.cnic.isnot(None)).all():
            age = date.today().year - teacher.date_of_birth.year
            assert 22 <= age <= 60


def test_students_have_complete_personal_data(app):
    with app.app_context():
        run_seed(_small_config())

        seeded = StudentModel.query.filter(
            StudentModel.admission_number.isnot(None)).all()
        assert seeded
        for student in seeded:
            assert student.student_name
            assert student.father_name
            assert student.guardian_phone
            assert student.address
            assert student.gender in ('Male', 'Female')
            assert student.admission_number
            assert student.admission_date is not None
            assert student.monthly_fee and student.monthly_fee > 0
            assert student.date_of_birth is not None


def test_teachers_have_complete_personal_data(app):
    with app.app_context():
        run_seed(_small_config())

        seeded = TeacherModel.query.filter(
            TeacherModel.cnic.isnot(None)).all()
        assert seeded
        for teacher in seeded:
            assert teacher.teacher_name
            assert teacher.qualification
            assert teacher.cnic
            assert teacher.contact_number
            assert teacher.designation
            assert teacher.date_of_birth is not None


def test_student_lifecycle_join_and_leave(app):
    with app.app_context():
        run_seed(_test_config())

        left = StudentModel.query.filter_by(is_active=False).all()
        active = StudentModel.query.filter_by(is_active=True).all()
        assert active, 'generator should produce active students'
        for student in left:
            assert student.leaving_date is not None
            assert student.leaving_reason
            assert student.status in ('slc_issued', 'graduated', 'struck_off')
            closed = (StudentEnrollment.query
                      .filter_by(student_id=student.id)
                      .filter(StudentEnrollment.end_date.isnot(None)).all())
            assert closed, 'a left student must have a closed enrollment row'

        # Every generator student has exactly one open enrollment unless they left.
        for student in StudentModel.query.filter(
                StudentModel.admission_number.isnot(None)).all():
            open_rows = (StudentEnrollment.query
                         .filter_by(student_id=student.id)
                         .filter(StudentEnrollment.end_date.is_(None)).all())
            assert len(open_rows) == (0 if student in left else 1)


def test_attendance_only_on_weekdays_and_valid_statuses(app):
    with app.app_context():
        run_seed(_small_config())

        valid = {'Present', 'Absent', 'Late', 'Leave'}
        for row in AttendanceModel.query.all():
            assert row.status in valid
            assert row.date.weekday() < 5, 'default school week is Mon-Fri'
            if row.status == 'Late':
                assert row.late_time and (row.late_minutes or 0) > 0
            else:
                assert row.late_time is None


def test_fee_records_match_ledger(app):
    with app.app_context():
        run_seed(_small_config())

        for record in FeeRecordModel.query.all():
            charged = paid = 0.0
            for txn in FeeTransaction.query.filter_by(
                    student_id=record.student_id,
                    month_year=record.month_year, is_void=False).all():
                if txn.txn_type == 'payment':
                    paid += txn.amount or 0.0
                else:
                    charged += txn.amount or 0.0
            assert abs(record.amount_due - round(charged, 2)) < 0.01
            assert abs(record.amount_paid - round(paid, 2)) < 0.01
            assert record.status in ('Paid', 'Pending', 'Partial')


def test_marks_are_graded_and_absents_excluded(app):
    with app.app_context():
        run_seed(_small_config())

        graded = StudentMarkModel.query.filter_by(is_absent=False).limit(50).all()
        assert graded, 'expected graded marks in the generated history'
        for mark in graded:
            assert mark.grade
            assert mark.percentage is not None
            assert 0 <= mark.marks_obtained <= mark.test_info.total_marks

        for absent in StudentMarkModel.query.filter_by(is_absent=True).all():
            assert absent.grade is None
            assert absent.percentage is None


def test_term_exams_are_published_with_subject_papers(app):
    from app.services.seed_generator import _enrolled_on

    with app.app_context():
        run_seed(_small_config())

        exams = TermExam.query.all()
        assert exams
        for exam in exams:
            assert exam.status == 'Published'
            assert exam.session_label
            papers = TestModel.query.filter_by(term_exam_id=exam.id).all()
            subject_count = SubjectModel.query.filter_by(class_id=exam.class_id).count()
            assert len(papers) == subject_count
            assert all(p.total_marks == 100.0 for p in papers)
            for paper in papers:
                eligible = [s for s in StudentModel.query.filter_by(class_id=paper.class_id).all()
                            if _enrolled_on(s, paper.test_date)]
                assert StudentMarkModel.query.filter_by(test_id=paper.id).count() == len(eligible)


def test_payroll_rows_carry_attendance_snapshot(app):
    with app.app_context():
        run_seed(_small_config())

        rows = StaffPayroll.query.all()
        assert rows
        for row in rows:
            assert row.month_year.count('-') == 1
            assert row.net_salary >= 0
            assert row.payment_status in ('Pending', 'Paid')
            assert row.working_days is not None


def test_photos_optional_and_skipped_by_default(app):
    with app.app_context():
        run_seed(_small_config())
        assert StudentModel.query.filter(StudentModel.photo_filename.isnot(None)).count() == 0
        assert TeacherModel.query.filter(TeacherModel.photo_filename.isnot(None)).count() == 0


def test_generated_photos_are_valid_files(app):
    # The project's pytest environment cannot use pytest's tmp_path fixture
    # (temp-dir permissions), so tests make their own directories.
    upload_dir = pathlib.Path(tempfile.mkdtemp(prefix='seed-photos-'))
    app.config['PHOTO_UPLOAD_DIR'] = str(upload_dir)
    with app.app_context():
        run_seed(_small_config(generate_photos=True))

        photo_students = StudentModel.query.filter(
            StudentModel.photo_filename.isnot(None)).all()
        assert photo_students, 'expected some avatar photos when requested'

        from app.services.photos import photo_path
        for student in photo_students:
            path = photo_path('student', student.photo_filename)
            assert path, f'photo file missing for {student.student_name}'
    shutil.rmtree(upload_dir, ignore_errors=True)


def test_seed_run_is_deterministic_with_fixed_seed(fresh_app_factory):
    base = pathlib.Path(tempfile.mkdtemp(prefix='seed-determinism-'))
    app = fresh_app_factory(base, 'determinism.db')
    config = _small_config()
    with app.app_context():
        run_seed(config)
        names_a = sorted(s.student_name for s in StudentModel.query.all())

        db.drop_all()
        db.create_all()
        run_seed(config)
        names_b = sorted(s.student_name for s in StudentModel.query.all())

        assert names_a == names_b
    shutil.rmtree(base, ignore_errors=True)


def test_audit_log_is_not_flooded_by_seed_rows(app):
    with app.app_context():
        run_seed(_small_config())

        audit_rows = AuditLog.query.count()
        student_rows = StudentModel.query.count()
        attendance_rows = AttendanceModel.query.count()
        # One summary entry (plus setup fixtures) — not one per generated row.
        assert audit_rows < 10
        assert attendance_rows > student_rows


def test_estimate_records_grows_with_period():
    small = estimate_records(60, 8, 1)
    large = estimate_records(60, 8, 120)
    assert small > 0
    assert large > small * 50

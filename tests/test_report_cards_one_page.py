"""Reports Hub -> All Report Cards PDF: exactly one page per student."""

import re
from datetime import date

import pytest

from app.database import db
from app.models import StudentMarkModel, StudentModel, SubjectModel, TestModel


def _page_count(pdf_bytes):
    return len(re.findall(rb'/Type\s*/Page(?![s\w])', pdf_bytes))


def _add_marks(class_id, student_ids, tests_per_subject, subject_count):
    """Give every student marks in several tests x subjects (a long report card)."""
    subjects = [db.session.get(SubjectModel, s.id) for s in
                SubjectModel.query.filter_by(class_id=class_id).all()]
    for extra in range(subject_count - len(subjects)):
        sub = SubjectModel(name='Extra %d' % extra, class_id=class_id)
        db.session.add(sub)
        db.session.flush()
        subjects.append(sub)
    for n in range(tests_per_subject):
        for sub in subjects:
            test = TestModel(test_title='Monthly Test %d' % (n + 1),
                             test_date=date(2026, 1 + n % 9, 5), test_type='Monthly',
                             class_id=class_id, subject_id=sub.id, total_marks=50)
            db.session.add(test)
            db.session.flush()
            for sid in student_ids:
                db.session.add(StudentMarkModel(test_id=test.id, student_id=sid,
                                                marks_obtained=40, percentage=80, grade='A'))
    db.session.commit()


@pytest.mark.parametrize('tests_per_subject,subject_count', [(1, 2), (4, 6), (6, 8)])
def test_all_report_cards_pdf_is_one_page_per_student(admin_client, app, seed,
                                                       tests_per_subject, subject_count):
    with app.app_context():
        student_ids = [s.id for s in StudentModel.query.filter_by(
            class_id=seed['class_id'], is_active=True).all()]
        _add_marks(seed['class_id'], student_ids, tests_per_subject, subject_count)
        expected_pages = len(student_ids)

    response = admin_client.get('/reports/class-results/pdf-all?class_id=%d' % seed['class_id'])
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert _page_count(response.data) == expected_pages


def test_single_report_card_is_one_page_even_with_many_marks(admin_client, app, seed):
    with app.app_context():
        _add_marks(seed['class_id'], [seed['student_id']], 6, 8)
    response = admin_client.get('/reports/student/%d/pdf?class_id=%d'
                                % (seed['student_id'], seed['class_id']))
    assert response.status_code == 200
    assert _page_count(response.data) == 1
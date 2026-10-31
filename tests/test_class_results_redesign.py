# -*- coding: utf-8 -*-
"""Class Results page (/reports/class-results), redesigned like the Students and
Class Tests pages: plain header, summary band, student search + Passed / Not passed
filters, a clear marks table and a save bar for remarks."""

from datetime import date

from app.database import db
from app.models import (ClassModel, StudentMarkModel, StudentModel, SubjectModel,
                        TestModel)
from app.services import i18n

DAY = date(2026, 10, 20)


def _class_with_results(name='Results Class', roll_base=8000):
    """Two students: one scores 40/50 (pass), one scores 10/50 (fail)."""
    cls = ClassModel(name=name)
    db.session.add(cls)
    db.session.flush()
    subject = SubjectModel(name='Maths %s' % name, class_id=cls.id)
    db.session.add(subject)
    db.session.flush()
    kids = []
    for i, student_name in enumerate(('Strong Student', 'Weak Student')):
        kid = StudentModel(roll_number=roll_base + i, student_name='%s %s' % (student_name, name),
                           father_name='Father %d' % i, address='X', monthly_fee=0,
                           class_id=cls.id, guardian_phone='03000000000')
        db.session.add(kid)
        kids.append(kid)
    db.session.flush()
    test = TestModel(test_title='Unit Test', test_date=DAY, test_type='Weekly',
                     class_id=cls.id, subject_id=subject.id, total_marks=50)
    db.session.add(test)
    db.session.flush()
    for kid, marks, grade in ((kids[0], 40, 'A'), (kids[1], 10, 'F')):
        db.session.add(StudentMarkModel(test_id=test.id, student_id=kid.id,
                                        marks_obtained=marks, percentage=marks * 2, grade=grade))
    db.session.commit()
    return cls, kids


def _page(admin_client, cls, **params):
    query = '&'.join('%s=%s' % item for item in params.items())
    response = admin_client.get('/reports/class-results?class_id=%d%s' % (cls.id, '&' + query if query else ''))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_header_summary_and_tools(admin_client, app):
    cls, _ = _class_with_results()
    html = _page(admin_client, cls)
    assert '<h1>Class Results</h1>' in html
    assert 'See how every student did' in html
    assert 'cr-tiles' in html and 'Class average' in html and 'Pass Rate' in html and 'Top Scorer' in html
    assert 'All Report Cards PDF' in html and 'More downloads' in html
    assert 'Export Whole Class Result (PDF)' in html
    assert 'id="crSearch"' in html and 'id="crSort"' in html
    assert 'data-mode="fail"' in html


def test_students_marks_and_report_buttons_are_listed(admin_client, app):
    cls, kids = _class_with_results()
    html = _page(admin_client, cls)
    for kid in kids:
        assert kid.student_name in html
        assert 'remark_%d' % kid.id in html
        assert '/reports/student/%d/pdf' % kid.id in html
    assert '>40<' in html and '>10<' in html
    assert 'out of 50' in html


def test_what_to_do_note_counts_students_who_did_not_pass(admin_client, app):
    cls, _ = _class_with_results()
    html = _page(admin_client, cls)
    assert 'What to do now:' in html
    assert '<b>1</b> student(s) did not pass' in html
    assert 'data-status="fail"' in html and 'data-status="pass"' in html


def test_everyone_passed_shows_the_good_news_note(admin_client, app):
    cls, kids = _class_with_results('Passing Class', roll_base=8100)
    mark = StudentMarkModel.query.filter_by(student_id=kids[1].id).first()
    mark.marks_obtained, mark.percentage, mark.grade = 45, 90, 'A+'
    db.session.commit()
    html = _page(admin_client, cls)
    assert 'Everyone who sat the tests has passed' in html
    assert 'did not pass' not in html


def test_grade_legend_follows_the_schools_grading_scale(admin_client, app):
    cls, _ = _class_with_results('Scale Class', roll_base=8200)
    html = _page(admin_client, cls)
    assert 'How grades work' in html
    assert '85% and above' in html and 'Below 40%' in html


def test_session_and_announcement_date_are_kept_in_the_form(admin_client, app):
    cls, _ = _class_with_results('Session Class', roll_base=8300)
    html = _page(admin_client, cls, session='2030-2031', announce_date='2030-05-01')
    assert 'value="2030-2031"' in html
    assert '01 May 2030' in html
    assert 'name="announce_date" value="2030-05-01"' in html


def test_remarks_can_be_saved_and_come_back(admin_client, app):
    cls, kids = _class_with_results('Remark Class', roll_base=8400)
    response = admin_client.post('/reports/class-results/remarks', data={
        'class_id': cls.id, 'test_type': '', 'session': '', 'announce_date': '',
        'remark_%d' % kids[0].id: 'Excellent work'}, follow_redirects=True)
    assert response.status_code == 200
    assert 'Excellent work' in _page(admin_client, cls)


def test_save_bar_and_unsaved_warning_are_on_the_page(admin_client, app):
    cls, _ = _class_with_results('Bar Class', roll_base=8500)
    html = _page(admin_client, cls)
    assert 'id="crSaveBar"' in html and 'remark(s) not saved yet' in html
    assert 'Save Remarks' in html


def test_class_without_tests_shows_a_friendly_empty_page(admin_client, app):
    cls = ClassModel(name='Empty Results Class')
    db.session.add(cls)
    db.session.commit()
    html = _page(admin_client, cls)
    assert 'No tests for this class yet.' in html
    assert 'Go to Class Tests' in html
    assert 'id="crSearch"' not in html


def test_unknown_test_type_offers_to_show_all_types(admin_client, app):
    cls, _ = _class_with_results('Type Class', roll_base=8600)
    html = _page(admin_client, cls, test_type='Nonexistent')
    assert 'No tests of this type for this class.' in html
    assert 'Show all test types' in html


def test_page_is_translated_to_urdu(admin_client, app):
    cls, _ = _class_with_results('Urdu Class', roll_base=8700)
    html = i18n.translate_html(_page(admin_client, cls))
    for english in ('Class Results', 'All Report Cards PDF', 'More downloads', 'Class average',
                    'All students', 'Not passed', 'Sort by', 'How grades work',
                    'Find a student by name', 'Write a remark', 'did not pass',
                    'not saved yet', 'Highest marks first'):
        assert english not in html, english
    assert 'کلاس کے نتائج' in html

"""Term Examinations page (/examinations), redesigned like Class Tests and Students:
plain header, summary band, search + class / status filters, and the exams shown as
cards or as a list (the person picks), with a clear action per exam."""

from datetime import date

from app.database import db
from app.models import (ClassModel, StudentMarkModel, StudentModel, SubjectModel,
                        TermExam, TestModel)

DAY = date(2026, 9, 1)


def _class_with_students(name='Exam Class', students=2, roll_base=7200):
    cls = ClassModel(name=name)
    db.session.add(cls)
    db.session.flush()
    subject = SubjectModel(name='Maths %s' % name, class_id=cls.id)
    db.session.add(subject)
    db.session.flush()
    kids = []
    for i in range(students):
        kid = StudentModel(roll_number=roll_base + i, student_name='Kid %s %d' % (name, i),
                           father_name='F', address='X', monthly_fee=0,
                           class_id=cls.id, guardian_phone='03000000000')
        db.session.add(kid)
        kids.append(kid)
    db.session.flush()
    return cls, subject, kids


def _exam(cls, subject, name, kids_with_marks=(), status='Ongoing'):
    exam = TermExam(name=name, class_id=cls.id, exam_type='Mid-Term', session_label='2026-27',
                    start_date=DAY, end_date=date(2026, 9, 10), status=status)
    db.session.add(exam)
    db.session.flush()
    test = TestModel(test_title=name, test_date=DAY, test_type='Mid-Term', class_id=cls.id,
                     subject_id=subject.id, total_marks=100, term_exam_id=exam.id)
    db.session.add(test)
    db.session.flush()
    for kid in kids_with_marks:
        db.session.add(StudentMarkModel(test_id=test.id, student_id=kid.id,
                                        marks_obtained=70, percentage=70, grade='B'))
    return exam


def _three_exams(app):
    with app.app_context():
        cls, subject, kids = _class_with_students()
        _exam(cls, subject, 'Exam Done', kids, status='Published')   # everybody has marks
        _exam(cls, subject, 'Exam Half', kids[:1])                   # one of two
        _exam(cls, subject, 'Exam Empty', status='Scheduled')        # nobody
        db.session.commit()


def _body(admin_client):
    response = admin_client.get('/examinations')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_page_uses_the_same_look_as_class_tests(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    for marker in ('class="tl-head"', 'class="tl-tiles', 'class="tl-toolbar', 'class="tl-card ',
                   'Class Tests', 'Add Term Exam'):
        assert marker in body, marker
    assert '<h1>Term Examinations</h1>' in body
    assert 'Official term exams with schedules, marks and results.' in body
    assert 'Exam Done' in body and 'Exam Half' in body and 'Exam Empty' in body
    assert 'dashboard-header' not in body and 'Assessment center' not in body


def test_summary_band_counts(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    band = body[body.index('class="tl-tiles'):body.index('</section>')]
    for text in ('Term exams in all', 'Results published', 'Marks complete', 'Marks still to enter'):
        assert text in band, text
    assert 'is-todo' in band
    assert 'What to do now:' in body


def test_each_exam_has_a_clear_action(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    assert body.count('Enter Marks') >= 2          # half-done and empty exams
    assert 'Edit Marks' in body                    # the finished exam
    assert 'Marks complete' in body and 'No marks yet' in body and 'Marks 1/2 (50%)' in body
    assert 'data-todo="1"' in body and 'data-done="1"' in body
    assert '/examinations/' in body and 'Date sheet' in body
    assert '/tests/batch_marks' in body


def test_all_done_says_nothing_is_waiting(admin_client, app):
    with app.app_context():
        cls, subject, kids = _class_with_students('Done Class', roll_base=7300)
        _exam(cls, subject, 'Only Exam', kids, status='Published')
        db.session.commit()
    body = _body(admin_client)
    assert 'Nothing waiting for marks' in body and 'is-clear' in body
    assert 'What to do now:' not in body


def test_search_and_filters_are_offered(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    assert 'id="tlSearch"' in body and 'data-search="exam done' in body
    for text in ('All Classes', 'All Status', 'All term exams', 'Marks to enter', 'Marks complete'):
        assert text in body, text
    assert 'id="classFilter"' in body and 'id="statusFilter"' in body
    assert 'data-status="Published"' in body and 'data-status="Scheduled"' in body


def test_filters_are_remembered_and_can_be_cleared(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    assert 'sm.examsFilters' in body and 'restoreExamFilters' in body
    assert 'id="tlClear"' in body and 'Clear filters' in body


def test_cards_and_list_can_be_switched(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    assert 'Show exams as' in body
    assert 'data-view="cards"' in body and 'data-view="list"' in body
    assert 'id="examGrid"' in body and 'id="examList"' in body
    assert "setExamView('list')" in body and 'sm.testsView' in body


def test_list_has_one_row_per_exam_with_the_same_actions(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    rows = body[body.index('id="examList"'):]
    assert rows.count('class="tl-row ') == 3
    for head in ('>Exam<', '>Class<', '>Marks entered<', '>Actions<'):
        assert head in rows, head
    assert 'Edit Marks' in rows and rows.count('Enter Marks') >= 2
    assert 'Marks 1/2 (50%)' in rows and 'No marks yet' in rows
    assert rows.count('data-todo="1"') == 2 and rows.count('data-done="1"') == 1
    assert 'data-search="exam done' in rows


def test_admin_sees_add_button_and_window(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    assert 'data-bs-target="#addTermExamModal"' in body and 'id="addTermExamModal"' in body
    assert 'name="exam_type"' in body and 'name="class_id"' in body


def test_empty_page_invites_the_first_exam(admin_client, app):
    body = _body(admin_client)
    assert 'No term exams yet.' in body and 'tl-empty' in body
    assert 'class="tl-tiles' not in body and 'Show exams as' not in body


def test_urdu_page_is_translated(admin_client, app):
    _three_exams(app)
    assert admin_client.get('/language/ur').status_code == 302
    body = _body(admin_client)
    for urdu in ('ٹرم امتحانات', 'ٹرم امتحان شامل کریں', 'نمبر لگائیں', 'نمبر لگانے ہیں',
                 'کارڈ', 'فہرست', 'امتحانات اس طرح دکھائیں', 'طے شدہ', 'ڈیٹ شیٹ'):
        assert urdu in body, urdu

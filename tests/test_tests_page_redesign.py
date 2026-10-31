"""Class Tests page (/tests), redesigned like the Students page: plain header,
summary band, search + class / type / marks-status filters, and the tests shown
as cards or as a list (the person picks), with one clear action per test
(Enter Marks / Edit Marks)."""

from datetime import date

from app.database import db
from app.models import (ClassModel, StudentMarkModel, StudentModel, SubjectModel,
                        TestModel, TestTypeModel)

DAY = date(2026, 10, 20)


def _class_with_students(name='Tests Class', students=2, roll_base=7000):
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


def _test(cls, subject, title, kids_with_marks=(), test_type='Weekly', total=50):
    test = TestModel(test_title=title, test_date=DAY, test_type=test_type,
                     class_id=cls.id, subject_id=subject.id, total_marks=total)
    db.session.add(test)
    db.session.flush()
    for kid in kids_with_marks:
        db.session.add(StudentMarkModel(test_id=test.id, student_id=kid.id,
                                        marks_obtained=40, percentage=80, grade='A'))
    return test


def _body(admin_client):
    response = admin_client.get('/tests')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _three_tests(app):
    with app.app_context():
        cls, subject, kids = _class_with_students()
        _test(cls, subject, 'Quiz Done', kids)              # everybody has marks
        _test(cls, subject, 'Quiz Half', kids[:1])          # one of two
        _test(cls, subject, 'Quiz Empty')                   # nobody
        db.session.commit()


def test_page_uses_the_register_book_look(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    for marker in ('class="tl-head"', 'class="tl-tiles', 'class="tl-toolbar', 'class="tl-card ',
                   'Term Examinations'):
        assert marker in body, marker
    assert 'Class Tests' in body and 'Quiz Done' in body
    assert 'Tests &amp; Exams' not in body and 'tl-table' not in body
    assert 'tl-hero' not in body                   # the old coloured banner is gone


def test_summary_band_counts(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    band = body[body.index('class="tl-tiles'):body.index('</section>')]
    assert 'Tests in all' in band and 'Tests this month' in band
    assert 'Marks complete' in band and 'Marks still to enter' in band
    assert 'is-todo' in band
    assert 'What to do now:' in body


def test_each_row_has_one_clear_action(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    assert body.count('Enter Marks') >= 2          # half-done and empty tests (cards)
    assert 'Edit Marks' in body                    # the finished test
    assert 'Marks complete' in body and 'No marks yet' in body and 'Marks 1/2 (50%)' in body
    assert 'data-todo="1"' in body and 'data-done="1"' in body


def test_all_done_says_nothing_is_waiting(admin_client, app):
    with app.app_context():
        cls, subject, kids = _class_with_students('Done Class', roll_base=7100)
        _test(cls, subject, 'Only Quiz', kids)
        db.session.commit()
    body = _body(admin_client)
    assert 'Nothing waiting for marks' in body and 'is-clear' in body
    assert 'What to do now:' not in body


def test_search_and_filters_are_offered(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    assert 'id="tlSearch"' in body and 'data-search="quiz done' in body
    for text in ('All Classes', 'All Types', 'All tests', 'Marks to enter', 'Marks complete'):
        assert text in body, text
    assert 'id="classFilter"' in body and 'id="typeFilter"' in body


def test_buttons_and_modals_still_work(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    assert 'data-bs-target="#addTestModal"' in body and 'Add Test' in body
    assert 'data-bs-target="#addTestTypeModal"' in body and 'Test Categories' in body
    assert 'id="addTestModal"' in body and 'id="deleteBatchModal"' in body
    assert 'aria-label="Delete test Quiz Done"' in body
    assert '/tests/batch_marks' in body


def test_empty_page_invites_the_first_test(admin_client, app):
    body = _body(admin_client)
    assert 'No tests yet.' in body and 'tl-empty' in body and 'class="tl-tiles' not in body


def test_urdu_page_is_translated(admin_client, app):
    _three_tests(app)
    assert admin_client.get('/language/ur').status_code == 302
    body = _body(admin_client)
    for urdu in ('کلاس ٹیسٹ', 'ٹیسٹ شامل کریں', 'نمبر لگائیں', 'نمبر لگانے ہیں', 'تمام ٹیسٹ',
                 'کارڈ', 'فہرست', 'ٹیسٹ اس طرح دکھائیں'):
        assert urdu in body, urdu


def test_header_follows_the_students_page(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    head = body[body.index('class="tl-head"'):body.index('class="tl-toolbar')]
    assert '<h1>Class Tests</h1>' in head
    assert 'Make a test, then enter the marks of every student.' in head
    assert 'Add Test' in head and 'Test Categories' in head and 'Term Examinations' in head


def test_cards_and_list_can_be_switched(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    assert 'Show tests as' in body
    assert 'data-view="cards"' in body and 'data-view="list"' in body
    assert 'id="testsGrid"' in body and 'id="testsList"' in body
    assert "setTestView('list')" in body and 'sm.testsView' in body     # choice is remembered


def test_list_has_one_row_per_test_with_the_same_actions(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    rows = body[body.index('id="testsList"'):]
    assert rows.count('class="tl-row ') == 3
    for head in ('>Test<', '>Class<', '>Marks entered<', '>Actions<'):
        assert head in rows, head
    assert 'Quiz Done' in rows and 'Quiz Half' in rows and 'Quiz Empty' in rows
    assert 'Edit Marks' in rows and rows.count('Enter Marks') >= 2
    assert 'Marks 1/2 (50%)' in rows and 'No marks yet' in rows
    assert '/tests/batch_marks' in rows
    assert rows.count('aria-label="Delete test Quiz Done"') == 1
    # rows are filtered by the same search / class / type / status data as the cards
    assert rows.count('data-todo="1"') == 2 and rows.count('data-done="1"') == 1
    assert 'data-search="quiz done' in rows


def test_empty_page_has_no_view_switch(admin_client, app):
    body = _body(admin_client)
    assert 'Show tests as' not in body and 'id="testsList"' not in body


def test_filters_are_remembered_and_can_be_cleared(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    assert 'sm.testsFilters' in body and 'restoreTestFilters' in body   # kept while editing marks
    assert 'id="tlClear"' in body and 'Clear filters' in body

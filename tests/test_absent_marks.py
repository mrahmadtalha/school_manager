"""An absent student is not a zero: the paper is left out of totals, grade and rank."""
import csv
import io
import sqlite3
import types
from datetime import date

from app.bootstrap import migrate_test_schema
from app.database import db
from app.models import (AdminUser, StudentMarkModel, StudentModel, SubjectModel,
                        TermExam, TestModel, ROLE_PARENT)
from app.routes.reports import _class_results_evaluation
from app.routes.term_exams import build_tabulation


def _exam_setup(seed):
    """Term exam with Maths + English (100 each) for the two seeded students."""
    cid = seed['class_id']
    english = SubjectModel(name='English', class_id=cid)
    db.session.add(english)
    db.session.flush()
    exam = TermExam(name='Mid Term 2026', class_id=cid, exam_type='Mid-Term',
                    session_label='2026', start_date=date(2026, 9, 1),
                    status='Ongoing')
    db.session.add(exam)
    db.session.flush()
    maths = TestModel(test_title='Mid Term 2026', test_date=date(2026, 9, 1),
                      test_type='Mid-Term', class_id=cid,
                      subject_id=seed['subject_id'], total_marks=100,
                      term_exam_id=exam.id)
    eng = TestModel(test_title='Mid Term 2026', test_date=date(2026, 9, 2),
                    test_type='Mid-Term', class_id=cid, subject_id=english.id,
                    total_marks=100, term_exam_id=exam.id)
    db.session.add_all([maths, eng])
    db.session.commit()
    return exam, maths, eng


def _post_marks(client, exam, cells):
    data = {'term_exam_id': str(exam.id)}
    data.update(cells)
    return client.post('/tests/batch_marks', data=data, follow_redirects=False)


def _mark(student_id, test_id):
    return StudentMarkModel.query.filter_by(student_id=student_id, test_id=test_id).one()


# ---------------------------------------------------------------- entry

def test_typing_A_saves_an_absent_record(admin_client, app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali, sara = seed['student_id'], seed['other_student_id']
    response = _post_marks(admin_client, exam, {
        f'marks_{ali}_{maths.id}': '90', f'marks_{ali}_{eng.id}': 'A',
        f'marks_{sara}_{maths.id}': '80', f'marks_{sara}_{eng.id}': 'abs',
    })
    assert response.status_code == 302
    absent = _mark(ali, eng.id)
    assert absent.is_absent is True
    assert absent.marks_obtained == 0.0
    assert absent.percentage is None and absent.grade is None
    assert _mark(sara, eng.id).is_absent is True       # 'abs' is accepted too
    assert _mark(ali, maths.id).is_absent is False
    assert _mark(ali, maths.id).percentage == 90.0


def test_absent_can_be_replaced_by_real_marks_and_back(admin_client, app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali = seed['student_id']
    key = f'marks_{ali}_{eng.id}'
    _post_marks(admin_client, exam, {key: 'A'})
    assert _mark(ali, eng.id).is_absent is True

    _post_marks(admin_client, exam, {key: '70'})        # makes up the paper
    made_up = _mark(ali, eng.id)
    assert made_up.is_absent is False
    assert made_up.marks_obtained == 70 and made_up.percentage == 70.0 and made_up.grade

    _post_marks(admin_client, exam, {key: 'A'})
    assert _mark(ali, eng.id).is_absent is True


def test_entry_page_shows_A_for_saved_absences(admin_client, app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali = seed['student_id']
    _post_marks(admin_client, exam, {f'marks_{ali}_{eng.id}': 'A'})
    page = admin_client.get('/tests/batch_marks', query_string={'term_exam_id': exam.id})
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert f'name="marks_{ali}_{eng.id}"' in html
    assert 'value="A"' in html


# ---------------------------------------------------------------- scoring rules

def test_class_results_leave_absent_paper_out(app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali, sara = seed['student_id'], seed['other_student_id']
    for sid, tid, marks in [(ali, maths.id, 90), (sara, maths.id, 90), (sara, eng.id, 90)]:
        db.session.add(StudentMarkModel(test_id=tid, student_id=sid, marks_obtained=marks,
                                        percentage=marks, grade='A+'))
    db.session.add(StudentMarkModel(test_id=eng.id, student_id=ali, marks_obtained=0.0,
                                    percentage=None, grade=None, is_absent=True))
    db.session.commit()

    _, _, rows, _ = _class_results_evaluation(seed['class_id'])
    by_name = {r['student'].student_name: r for r in rows}
    ali_row = by_name['Ali Khan']
    assert (ali_row['total_obtained'], ali_row['total_max']) == (90.0, 100.0)
    assert ali_row['percentage'] == 90.0
    assert ali_row['status'] == 'Pass' and ali_row['absent'] == {eng.id: True}
    assert ali_row['absent_count'] == 1 and ali_row['all_absent'] is False
    # Same 90% as Sara, so they share first position: not pushed down for the absence.
    assert ali_row['rank'] == by_name['Sara Ali']['rank'] == 1


def test_missing_mark_still_counts_as_before(app, seed):
    """Blank / not-yet-entered is NOT absent: it still counts against the total."""
    exam, maths, eng = _exam_setup(seed)
    ali = seed['student_id']
    db.session.add(StudentMarkModel(test_id=maths.id, student_id=ali, marks_obtained=90,
                                    percentage=90, grade='A+'))
    db.session.commit()
    _, _, rows, _ = _class_results_evaluation(seed['class_id'])
    row = next(r for r in rows if r['student'].id == ali)
    assert (row['total_obtained'], row['total_max'], row['percentage']) == (90.0, 200.0, 45.0)
    assert row['absent_count'] == 0


def test_fully_absent_student_has_no_grade_rank_or_fail(app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali, sara = seed['student_id'], seed['other_student_id']
    for tid in (maths.id, eng.id):
        db.session.add(StudentMarkModel(test_id=tid, student_id=ali, marks_obtained=0.0,
                                        is_absent=True))
        db.session.add(StudentMarkModel(test_id=tid, student_id=sara, marks_obtained=80,
                                        percentage=80, grade='A'))
    db.session.commit()

    _, _, rows, _ = _class_results_evaluation(seed['class_id'])
    ali_row = next(r for r in rows if r['student'].id == ali)
    assert ali_row['status'] == 'Absent' and ali_row['overall_grade'] == 'ABS'
    assert ali_row['rank'] is None and ali_row['rank_label'] == '—'
    assert ali_row['is_pass'] is False
    assert rows[-1] is ali_row                        # listed after ranked students

    tests, tab_rows, summary = build_tabulation(db.session.get(TermExam, exam.id))
    tab_ali = next(r for r in tab_rows if r['student'].id == ali)
    assert tab_ali['all_absent'] and tab_ali['grade'] == 'ABS' and tab_ali['position'] == '—'
    # The class figures are over the one student who sat: not dragged down by a phantom 0%.
    assert summary['sat'] == 1 and summary['average'] == 80.0
    assert summary['pass_count'] == 1 and summary['pass_rate'] == 100.0


def test_tabulation_counts_absence_as_entered(app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali, sara = seed['student_id'], seed['other_student_id']
    for sid, tid, marks, absent in [(ali, maths.id, 90, False), (ali, eng.id, 0, True),
                                    (sara, maths.id, 60, False), (sara, eng.id, 60, False)]:
        db.session.add(StudentMarkModel(test_id=tid, student_id=sid, marks_obtained=marks,
                                        percentage=None if absent else marks,
                                        grade=None if absent else 'B', is_absent=absent))
    db.session.commit()
    tests, rows, summary = build_tabulation(db.session.get(TermExam, exam.id))
    assert summary['complete'] is True and summary['missing'] == 0
    assert summary['absences'] == 1
    assert [r['student'].student_name for r in rows] == ['Ali Khan', 'Sara Ali']
    assert [r['position'] for r in rows] == ['1st', '2nd']      # 90% beats 60%
    ali_row = rows[0]
    assert (ali_row['total_obt'], ali_row['max_marks'], ali_row['pct']) == (90.0, 100.0, 90.0)


# ---------------------------------------------------------------- pages and files

def _seed_mixed(seed):
    exam, maths, eng = _exam_setup(seed)
    ali, sara = seed['student_id'], seed['other_student_id']
    for sid, tid, marks, absent in [(ali, maths.id, 90, False), (ali, eng.id, 0, True),
                                    (sara, maths.id, 60, False), (sara, eng.id, 60, False)]:
        db.session.add(StudentMarkModel(test_id=tid, student_id=sid, marks_obtained=marks,
                                        percentage=None if absent else marks,
                                        grade=None if absent else 'B', is_absent=absent))
    db.session.commit()
    return exam


def test_every_page_and_export_renders_with_an_absence(admin_client, app, seed):
    exam = _seed_mixed(seed)
    ali, cid = seed['student_id'], seed['class_id']
    pages = {
        'tabulation page': f'/examinations/{exam.id}/tabulation',
        'class results page': f'/reports/class-results?class_id={cid}',
        'student report page': f'/students/{ali}/report',
    }
    for label, url in pages.items():
        response = admin_client.get(url)
        assert response.status_code == 200, label
        assert 'ABS' in response.get_data(as_text=True), label

    files = {
        'tabulation csv': (f'/examinations/{exam.id}/tabulation/export.csv', b'ABS'),
        'tabulation xlsx': (f'/examinations/{exam.id}/tabulation/export.xlsx', None),
        'tabulation pdf': (f'/examinations/{exam.id}/tabulation/export.pdf', b'%PDF'),
        'result card pdf': (f'/examinations/{exam.id}/results/{ali}.pdf', b'%PDF'),
        'all result cards pdf': (f'/examinations/{exam.id}/results/pdf-all', b'%PDF'),
        'report card pdf': (f'/reports/student/{ali}/pdf?class_id={cid}', b'%PDF'),
        'all report cards pdf': (f'/reports/class-results/pdf-all?class_id={cid}', b'%PDF'),
        'class sheet pdf': (f'/reports/class-results/pdf-class?class_id={cid}', b'%PDF'),
        'class results csv': (f'/reports/class-results/export/csv?class_id={cid}', b'ABS'),
        'class results xlsx': (f'/reports/class-results/export/excel?class_id={cid}', None),
        'broad sheet': (f'/reports/exports/broad-sheet/csv?class_id={cid}', b'ABS'),
        'broad sheet pdf': (f'/reports/exports/broad-sheet/pdf?class_id={cid}', b'%PDF'),
        'positions': (f'/reports/exports/positions/csv?class_id={cid}', None),
        'positions pdf': (f'/reports/exports/positions/pdf?class_id={cid}', b'%PDF'),
        'student report pdf': (f'/students/{ali}/report/pdf', b'%PDF'),
        'transcript pdf': (f'/students/{ali}/transcript.pdf', b'%PDF'),
    }
    for label, (url, needle) in files.items():
        response = admin_client.get(url)
        assert response.status_code == 200, (label, response.status_code)
        if needle:
            assert needle in response.data, label


def test_tabulation_csv_shows_ABS_and_per_student_max(admin_client, app, seed):
    exam = _seed_mixed(seed)
    response = admin_client.get(f'/examinations/{exam.id}/tabulation/export.csv')
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    header, ali_line = rows[0], next(r for r in rows if 'Ali Khan' in r)
    assert 'ABS' in ali_line
    assert ali_line[header.index('Total Obtained')] == '90.0'
    assert ali_line[header.index('Total Max')] == '100.0'


def test_parent_portal_shows_absent(parent_client, app, seed):
    _seed_mixed(seed)
    response = parent_client.get('/portal')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Absent' in html


def test_publish_skips_whatsapp_for_fully_absent_student(admin_client, app, seed):
    exam, maths, eng = _exam_setup(seed)
    ali, sara = seed['student_id'], seed['other_student_id']
    for tid in (maths.id, eng.id):
        db.session.add(StudentMarkModel(test_id=tid, student_id=ali, marks_obtained=0.0,
                                        is_absent=True))
        db.session.add(StudentMarkModel(test_id=tid, student_id=sara, marks_obtained=80,
                                        percentage=80, grade='A'))
    db.session.commit()
    from app.models import MessageQueue
    admin_client.post(f'/examinations/{exam.id}/publish', data={'queue_whatsapp': '1'})
    queued = {m.student_id for m in MessageQueue.query.filter_by(trigger='result').all()}
    assert ali not in queued and sara in queued


# ---------------------------------------------------------------- migration

def test_migration_adds_is_absent_to_an_existing_database(tmp_path):
    db_file = tmp_path / 'old.db'
    connection = sqlite3.connect(db_file)
    connection.execute('CREATE TABLE student_marks (id INTEGER PRIMARY KEY, test_id INTEGER, '
                       'student_id INTEGER, marks_obtained FLOAT NOT NULL, percentage FLOAT, '
                       'grade VARCHAR(5))')
    connection.execute('INSERT INTO student_marks (test_id, student_id, marks_obtained) '
                       'VALUES (1, 1, 55)')
    connection.commit()
    connection.close()

    fake_app = types.SimpleNamespace(
        config={'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + db_file.as_posix()},
        root_path=str(tmp_path), instance_path=str(tmp_path))
    migrate_test_schema(fake_app)
    migrate_test_schema(fake_app)          # running twice is harmless

    connection = sqlite3.connect(db_file)
    columns = [row[1] for row in connection.execute('PRAGMA table_info(student_marks)')]
    value = connection.execute('SELECT is_absent FROM student_marks').fetchone()[0]
    connection.close()
    assert 'is_absent' in columns
    assert value == 0                       # existing marks are not absent

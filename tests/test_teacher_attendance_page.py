"""Teacher Attendance page (redesigned like the Student Attendance page):
date bar, summary ribbon, "not marked yet" note, search, big status buttons.
The saving / late rules themselves are covered in test_attendance_late.py and
test_attendance_all_at_time.py."""

import re
from datetime import date

from app.database import db
from app.models import AttendanceModel, SchoolSettings, TeacherModel

DAY = date(2026, 9, 21)
URL = '/attendance/teachers?date=%s' % DAY


def _settings(start='08:30', grace=0):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
        db.session.flush()
    settings.school_start_time = start
    settings.attendance_grace_minutes = grace
    db.session.commit()


def _teachers(count=2):
    out = []
    for n in range(count):
        t = TeacherModel(teacher_id_str='TA%d' % n, teacher_name='Teacher Number %d' % n,
                         qualification='MA')
        db.session.add(t)
        out.append(t)
    db.session.commit()
    return [t.id for t in out]


def _body(admin_client, url=URL):
    response = admin_client.get(url)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_page_uses_the_register_book_look(admin_client, app):
    with app.app_context():
        _teachers()
    body = _body(admin_client)
    for marker in ('class="ta-head"', 'class="ta-filters', 'class="ta-ribbon', 'class="ta-toolbar',
                   'class="ta-save"'):
        assert marker in body, marker
    assert 'Teacher Attendance' in body and 'Teacher Number 0' in body
    # old table-style wording is gone
    assert 'Teacher Roster' not in body and 'Faculty tracking' not in body


def test_date_bar_has_previous_next_and_today(admin_client, app):
    with app.app_context():
        _teachers()
    body = _body(admin_client)
    assert 'date=2026-09-20' in body and 'date=2026-09-22' in body
    for text in ('Previous day', 'Next day', 'Today'):
        assert text in body, text


def test_bad_date_does_not_crash(admin_client, app):
    with app.app_context():
        _teachers()
    assert admin_client.get('/attendance/teachers?date=not-a-date').status_code == 200


def test_form_fields_are_unchanged_and_not_duplicated(admin_client, app):
    with app.app_context():
        _settings('08:15')
        ids = _teachers()
    body = _body(admin_client)
    for tid in ids:
        assert body.count('name="status_%d"' % tid) == 4          # Present / Absent / Late / Leave
        assert body.count('name="checkin_time_%d"' % tid) == 1
    assert 'All Teachers at Time' in body
    assert 'id="allTeachersAtTime"' in body and 'value="08:15"' in body


def test_fresh_day_is_not_saved_and_has_no_not_marked_noise(admin_client, app):
    with app.app_context():
        _teachers()
    body = _body(admin_client)
    assert 'Not Yet Saved' in body
    assert 'Saved for this day' not in body
    assert 'attendance not marked yet' not in body
    assert 'Not marked yet' not in body


def test_partly_saved_day_names_the_teachers_still_to_mark(admin_client, app):
    with app.app_context():
        ids = _teachers()
        db.session.add(AttendanceModel(date=DAY, target_type='teacher', target_id=ids[0],
                                       status='Present'))
        db.session.commit()
    body = _body(admin_client)
    assert 'Not Yet Saved' in body
    assert 'attendance not marked yet' in body
    assert 'Teacher Number 1' in body and 'Show only these teachers' in body
    assert body.count('Not marked yet') == 1                        # only the untouched teacher


def test_fully_saved_day_says_saved(admin_client, app):
    with app.app_context():
        ids = _teachers()
        for tid in ids:
            db.session.add(AttendanceModel(date=DAY, target_type='teacher', target_id=tid,
                                           status='Present'))
        db.session.commit()
    body = _body(admin_client)
    assert 'Saved for this day' in body
    assert 'Not Yet Saved' not in body


def test_saved_status_and_late_minutes_are_shown(admin_client, app):
    with app.app_context():
        _settings('08:30', 0)
        ids = _teachers()
        db.session.add(AttendanceModel(date=DAY, target_type='teacher', target_id=ids[0],
                                       status='Late', late_time='08:50', late_minutes=20))
        db.session.add(AttendanceModel(date=DAY, target_type='teacher', target_id=ids[1],
                                       status='Absent'))
        db.session.commit()
        late_id, absent_id = ids
    body = _body(admin_client)
    assert 'Late · 20 min' in body
    assert re.search(r'id="a_%d" value="Absent"\s+checked' % absent_id, body)   # Absent is pre-selected
    assert re.search(r'id="l_%d" value="Late"\s+checked' % late_id, body)
    assert 'value="08:50"' in body


def test_saving_still_works_and_comes_back_to_the_same_day(admin_client, app):
    with app.app_context():
        ids = _teachers()
    response = admin_client.post('/attendance/teachers', data={
        'date': DAY.isoformat(),
        'status_%d' % ids[0]: 'Present', 'checkin_time_%d' % ids[0]: '08:00',
        'status_%d' % ids[1]: 'Absent',
    })
    assert response.status_code == 302 and 'date=2026-09-21' in response.headers['Location']
    with app.app_context():
        rows = {r.target_id: r.status for r in
                AttendanceModel.query.filter_by(target_type='teacher', date=DAY).all()}
        assert rows == {ids[0]: 'Present', ids[1]: 'Absent'}
    assert 'Saved for this day' in _body(admin_client)


def test_no_teachers_shows_a_friendly_empty_state(admin_client, app):
    body = _body(admin_client)
    assert 'No teachers found.' in body and 'Go to Teachers' in body
    assert 'class="ta-save"' not in body


def test_search_box_and_rows_are_offered(admin_client, app):
    with app.app_context():
        _teachers()
    body = _body(admin_client)
    assert 'id="taSearch"' in body
    assert 'data-search="teacher number 0 ta0 ma"' in body


def test_urdu_page_is_translated(admin_client, app):
    with app.app_context():
        _teachers()
    assert admin_client.get('/language/ur').status_code == 302
    body = _body(admin_client)
    for urdu in ('ماہانہ خلاصہ', 'اسکول کے اساتذہ', 'ابھی محفوظ نہیں', 'سب اساتذہ اس وقت پر',
                 'اساتذہ کی حاضری محفوظ کریں', 'جن اساتذہ کو ضرورت ہو'):
        assert urdu in body, urdu

"""Attendance Summary page (redesigned like the Student Attendance page):
class + period bar, summary band, "need attention" filter, register with
the totals first and the day-by-day boxes after them."""

import re
from datetime import date

from app.database import db
from app.models import AttendanceModel, SchoolSettings, StudentModel

MONDAY = date(2026, 10, 19)
TUESDAY = date(2026, 10, 20)


def _school():
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    db.session.commit()


def _mark(student_id, class_id, day, status, minutes=None):
    db.session.add(AttendanceModel(date=day, target_type='student', target_id=student_id,
                                   class_id=class_id, status=status,
                                   late_minutes=minutes))


def _body(admin_client, query):
    response = admin_client.get('/attendance/summary' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _url(seed, start=MONDAY, end=TUESDAY):
    return '?class_id=%d&start_date=%s&end_date=%s' % (seed['class_id'], start, end)


def test_page_uses_the_register_book_look(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client, _url(seed))
    for marker in ('class="as-head"', 'class="as-filters', 'class="as-ribbon', 'class="as-toolbar',
                   'as-table', 'How to read the boxes:'):
        assert marker in body, marker
    assert 'Class Attendance Summary' in body and 'Ali Khan' in body
    assert 'Attendance Ledger' not in body and 'Attendance analysis' not in body


def test_period_bar_has_month_buttons_and_dates(admin_client, app, seed):
    body = _body(admin_client, _url(seed))
    assert 'This Month' in body and 'Last Month' in body
    assert 'name="start_date" value="2026-10-19"' in body
    assert 'name="end_date" value="2026-10-20"' in body


def test_wrong_way_round_and_bad_dates_do_not_crash(admin_client, app, seed):
    flipped = _body(admin_client, _url(seed, TUESDAY, MONDAY))
    assert 'name="start_date" value="2026-10-19"' in flipped          # put the right way round
    bad = '?class_id=%d&start_date=abc&end_date=xyz' % seed['class_id']
    assert admin_client.get('/attendance/summary' + bad).status_code == 200


def test_totals_come_before_the_day_boxes_and_rates_are_toned(admin_client, app, seed):
    with app.app_context():
        _school()
        sid = seed['student_id']
        _mark(sid, seed['class_id'], MONDAY, 'Present')
        _mark(sid, seed['class_id'], TUESDAY, 'Absent')            # 50% -> needs attention
        db.session.commit()
    body = _body(admin_client, _url(seed))
    head = body[body.index('<thead>'):body.index('</thead>')]
    assert head.index('Attendance') < head.index('Present') < head.index('Absent') < head.index('Leave')
    assert head.index('Leave') < head.index('<b>19</b>')            # totals first, days after
    assert re.search(r'as-rate r"[^>]*>.*?50(\.0)?%', body, re.S)
    assert 'Need attention (below 75%)' in body
    assert 'data-risk="1"' in body
    assert 'class="as-day a"' in body and 'class="as-day p"' in body


def test_late_minutes_keep_their_short_form(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Late', 17)
        db.session.commit()
    body = _body(admin_client, _url(seed, MONDAY, MONDAY))
    assert 'L · 17m' in body and '17 min' in body


def test_leave_is_counted(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Leave')
        db.session.commit()
    body = _body(admin_client, _url(seed, MONDAY, MONDAY))
    assert 'class="as-day v"' in body


def test_nothing_saved_shows_a_clear_note(admin_client, app, seed):
    with app.app_context():
        _school()
    body = _body(admin_client, _url(seed))
    assert 'No attendance has been saved' in body
    assert 'What to do now' not in body


def test_clear_class_says_nobody_is_below_75(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client, _url(seed, MONDAY, MONDAY))
    assert 'Nobody is below 75%' in body and 'is-clear' in body


def test_filters_and_search_are_offered(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client, _url(seed, MONDAY, MONDAY))
    assert 'id="asSearch"' in body
    for text in ('All students', 'Need attention', 'Never absent'):
        assert text in body, text
    assert 'data-search="ali khan' in body


def test_whole_school_view_shows_class_names_and_keeps_export(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client, '?class_id=all&start_date=%s&end_date=%s' % (MONDAY, TUESDAY))
    assert 'Whole-School Attendance Summary' in body and 'All School Students' in body
    assert 'Class 1' in body and 'Students in the school' in body
    assert '/attendance/summary/export/pdf?class_id=all' in body


def test_class_view_has_export_and_links(admin_client, app, seed):
    body = _body(admin_client, _url(seed))
    for part in ('export/pdf', 'export/excel', 'export/csv', 'Teacher Attendance Summary',
                 'Take Attendance'):
        assert part in body, part


def test_urdu_page_is_translated(admin_client, app, seed):
    with app.app_context():
        _school()
        _mark(seed['student_id'], seed['class_id'], MONDAY, 'Present')
        db.session.commit()
    assert admin_client.get('/language/ur').status_code == 302
    body = _body(admin_client, _url(seed))
    for urdu in ('کلاس کی حاضری کا خلاصہ', 'پچھلا مہینہ', 'توجہ درکار', 'کبھی غیر حاضر نہیں',
                 'خانوں کو کیسے پڑھیں:', 'حاضری لگائیں'):
        assert urdu in body, urdu

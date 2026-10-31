"""Teacher Attendance Summary page (redesigned like the Attendance Summary
page): period bar, summary band, "need attention" filter, register with the
totals first and the day-by-day boxes after them."""

import re
from datetime import date

from app.database import db
from app.models import AttendanceModel, SchoolSettings, TeacherModel

MONDAY = date(2026, 10, 19)
TUESDAY = date(2026, 10, 20)
URL = '/attendance/teachers/summary?start_date=%s&end_date=%s' % (MONDAY, TUESDAY)


def _school():
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    db.session.commit()


def _teacher(n=0, name=None):
    t = TeacherModel(teacher_id_str='TS%d' % n, teacher_name=name or 'Teacher Number %d' % n,
                     qualification='MA')
    db.session.add(t)
    db.session.commit()
    return t.id


def _mark(teacher_id, day, status, minutes=None):
    db.session.add(AttendanceModel(date=day, target_type='teacher', target_id=teacher_id,
                                   status=status, late_minutes=minutes))


def _body(admin_client, url=URL):
    response = admin_client.get(url)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_page_uses_the_register_book_look(admin_client, app):
    with app.app_context():
        _school()
        _mark(_teacher(), MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client)
    for marker in ('class="ts-head"', 'class="ts-filters', 'class="ts-ribbon', 'class="ts-toolbar',
                   'ts-table', 'How to read the boxes:'):
        assert marker in body, marker
    assert 'Teacher Attendance Summary' in body and 'Teacher Number 0' in body
    assert 'Matrix Summary' not in body and 'Teacher analysis' not in body


def test_period_bar_has_month_buttons_and_dates(admin_client):
    body = _body(admin_client)
    assert 'This Month' in body and 'Last Month' in body
    assert 'name="start_date" value="2026-10-19"' in body
    assert 'name="end_date" value="2026-10-20"' in body


def test_wrong_way_round_and_bad_dates_do_not_crash(admin_client):
    flipped = _body(admin_client, '/attendance/teachers/summary?start_date=%s&end_date=%s' % (TUESDAY, MONDAY))
    assert 'name="start_date" value="2026-10-19"' in flipped
    assert admin_client.get('/attendance/teachers/summary?start_date=abc&end_date=xyz').status_code == 200


def test_totals_come_before_the_day_boxes_and_rates_are_toned(admin_client, app):
    with app.app_context():
        _school()
        tid = _teacher()
        _mark(tid, MONDAY, 'Present')
        _mark(tid, TUESDAY, 'Absent')                    # 50% -> needs attention
        db.session.commit()
    body = _body(admin_client)
    head = body[body.index('<thead>'):body.index('</thead>')]
    assert head.index('Attendance') < head.index('Present') < head.index('Absent') < head.index('Leave')
    assert head.index('Leave') < head.index('<b>19</b>')
    assert re.search(r'ts-rate r"[^>]*>.*?50(\.0)?%', body, re.S)
    assert 'Need attention (below 75%)' in body and 'data-risk="1"' in body
    assert 'class="ts-day a"' in body and 'class="ts-day p"' in body


def test_late_minutes_and_leave_are_shown(admin_client, app):
    with app.app_context():
        _school()
        tid = _teacher()
        _mark(tid, MONDAY, 'Late', 17)
        _mark(tid, TUESDAY, 'Leave')
        db.session.commit()
    body = _body(admin_client)
    assert 'L · 17m' in body and '17 min' in body
    assert 'class="ts-day v"' in body


def test_nothing_saved_shows_a_clear_empty_state(admin_client, app):
    with app.app_context():
        _school()
        _teacher()
    body = _body(admin_client)
    assert 'No attendance logs found for teachers in this date range.' in body
    assert 'Take Teacher Attendance' in body and 'class="ts-ribbon' not in body


def test_no_teachers_at_all(admin_client, app):
    body = _body(admin_client)
    assert 'No teachers found.' in body


def test_clear_school_says_nobody_is_below_75(admin_client, app):
    with app.app_context():
        _school()
        _mark(_teacher(), MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client, '/attendance/teachers/summary?start_date=%s&end_date=%s' % (MONDAY, MONDAY))
    assert 'Nobody is below 75%' in body and 'is-clear' in body


def test_filters_search_exports_and_links_are_offered(admin_client, app):
    with app.app_context():
        _school()
        _mark(_teacher(), MONDAY, 'Present')
        db.session.commit()
    body = _body(admin_client)
    assert 'id="tsSearch"' in body and 'data-search="teacher number 0' in body
    for text in ('All teachers', 'Need attention', 'Never absent', 'Student Attendance Summary',
                 'Take Teacher Attendance',
                 '/attendance/teachers/summary/export/pdf',
                 '/attendance/teachers/summary/export/excel',
                 '/attendance/teachers/summary/export/csv'):
        assert text in body, text


def test_urdu_page_is_translated(admin_client, app):
    with app.app_context():
        _school()
        _mark(_teacher(), MONDAY, 'Present')
        db.session.commit()
    assert admin_client.get('/language/ur').status_code == 302
    body = _body(admin_client)
    for urdu in ('اساتذہ کی حاضری کا خلاصہ', 'پچھلا مہینہ', 'توجہ درکار', 'تمام اساتذہ',
                 'خانوں کو کیسے پڑھیں:', 'اساتذہ کی حاضری لگائیں'):
        assert urdu in body, urdu

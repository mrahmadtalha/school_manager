"""Attendance Summary on phones and tablets.

Same HTML for every screen size: a 30-day register is ~2000px wide, so below
1024px every student becomes one card (name + percentage, the four counts, one
small box per day). These tests check the pieces that layout needs and that no
number, box or button went missing."""

from datetime import date

from app.database import db
from app.models import AttendanceModel, SchoolSettings

FRIDAY = date(2026, 10, 30)
MONDAY = date(2026, 11, 2)      # the next month: the card must say which month the boxes belong to


def _school():
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    db.session.commit()


def _mark(student_id, class_id, day, status, minutes=None):
    db.session.add(AttendanceModel(date=day, target_type='student', target_id=student_id,
                                   class_id=class_id, status=status, late_minutes=minutes))


def _body(client, seed, start=FRIDAY, end=MONDAY):
    reply = client.get('/attendance/summary?class_id=%d&start_date=%s&end_date=%s' % (seed['class_id'], start, end))
    assert reply.status_code == 200
    return reply.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .as-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.as-head' in block][0]


def _marked(app, seed):
    with app.app_context():
        _school()
        sid = seed['student_id']
        _mark(sid, seed['class_id'], FRIDAY, 'Present')
        _mark(sid, seed['class_id'], MONDAY, 'Late', 17)
        db.session.commit()


def test_student_rows_are_cards_below_1024px(admin_client, app, seed):
    _marked(app, seed)
    css = _css(_body(admin_client, seed))
    marker = '@media screen and (max-width: 1023.98px)'
    assert marker in css
    cards = css.split(marker, 1)[1].split('@media', 1)[0]
    for needle in ('.as-scroll { overflow: visible; }', '.as-table thead { display: none; }',
                   'grid-template-columns: repeat(28, minmax(0, 1fr))',
                   '.as-c-rate { grid-column: 19 / 29; justify-self: end; }',
                   '.as-c-n { grid-column: span 7;', '.as-c-day { grid-column: span 4;',
                   'content: attr(data-label)', 'content: attr(data-mon) " " attr(data-day)'):
        assert needle in cards, needle
    assert '@media screen and (min-width: 576px) and (max-width: 1023.98px)' in css      # 14 boxes per line on a tablet
    assert 'position: static; min-width: 0; grid-column: 1 / 19;' in cards                 # no sticky name column in a card
    assert 'html[dir="rtl"] .as-table tbody tr[data-risk="1"]' in cards                    # Urdu: red bar on the other side


def test_phone_header_filters_and_summary_fit_the_screen(admin_client, app, seed):
    _marked(app, seed)
    css = _css(_body(admin_client, seed))
    phone = css.split('@media (max-width: 767.98px) {', 1)[1].split('@media screen', 1)[0]
    for needle in ('.as-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.as-range { flex: 1 1 100%; display: grid;',          # From / To one line each (they pushed the page sideways)
                   '.as-filters .as-range .form-control[type=date] { width: 100%; min-width: 0; }',
                   'font-size: 16px',                                      # no iPhone zoom when a box is tapped
                   '.as-ribbon { grid-template-columns: repeat(3, minmax(0, 1fr));',
                   '.as-ribbon .as-stat:nth-child(2) { grid-column: 1 / -1; order: -1; }'):
        assert needle in phone, needle


def test_every_cell_has_its_phone_label_and_every_day_its_date(admin_client, app, seed):
    _marked(app, seed)
    body = _body(admin_client, seed)
    row = body.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    assert 'as-grp as-c-rate' in row
    for label in ('Present', 'Absent', 'Late', 'Leave'):
        assert 'class="as-c-n" data-label="%s"' % label in row
    assert 'data-day="30" data-dow="Fri" data-mon="Oct"' in row          # first box names its month
    assert 'data-day="2" data-dow="Mon" data-mon="Nov"' in row           # and so does the first box of the next month
    assert row.count('class="text-nowrap as-c-day') == row.count('data-dow=')


def test_numbers_boxes_and_filters_are_unchanged(admin_client, app, seed):
    _marked(app, seed)
    body = _body(admin_client, seed)
    head = body[body.index('<thead>'):body.index('</thead>')]
    assert head.index('Attendance') < head.index('Present') < head.index('Absent') < head.index('Leave') < head.index('<b>30</b>')
    for needle in ('id="asSearch"', "setMode('risk')", "setMode('perfect')", "setMode('all')", 'id="asVisible"',
                   'data-risk=', 'data-perfect=', 'data-search="ali khan', 'How to read the boxes:',
                   'L · 17m', '17 min', 'class="as-day p"', 'name="start_date"', 'name="end_date"', 'name="class_id"',
                   '/attendance/summary/export/pdf', '/attendance/summary/export/excel',
                   '/attendance/summary/export/csv', 'This Month', 'Last Month', 'Take Attendance',
                   'Teacher Attendance Summary'):
        assert needle in body, needle

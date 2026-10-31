"""Teacher Attendance Summary on phones and tablets.

Same HTML for every screen size: a 30-day register is ~2000px wide, so below
1024px every teacher becomes one card (photo, name and percentage, the four
counts, one small box per day). These tests check the pieces that layout needs
and that no number, box or button went missing."""

from datetime import date

from app.database import db
from app.models import AttendanceModel, SchoolSettings, TeacherModel

FRIDAY = date(2026, 10, 30)
MONDAY = date(2026, 11, 2)      # the next month: the card must say which month the boxes belong to


def _school():
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    db.session.commit()


def _teacher():
    teacher = TeacherModel(teacher_id_str='TM1', teacher_name='Ayesha Noor', qualification='MA')
    db.session.add(teacher)
    db.session.commit()
    return teacher.id


def _mark(teacher_id, day, status, minutes=None):
    db.session.add(AttendanceModel(date=day, target_type='teacher', target_id=teacher_id,
                                   status=status, late_minutes=minutes))


def _body(client, start=FRIDAY, end=MONDAY):
    reply = client.get('/attendance/teachers/summary?start_date=%s&end_date=%s' % (start, end))
    assert reply.status_code == 200
    return reply.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .ts-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.ts-head' in block][0]


def _marked(app):
    with app.app_context():
        _school()
        tid = _teacher()
        _mark(tid, FRIDAY, 'Present')
        _mark(tid, MONDAY, 'Late', 17)
        db.session.commit()


def test_teacher_rows_are_cards_below_1024px(admin_client, app):
    _marked(app)
    css = _css(_body(admin_client))
    marker = '@media screen and (max-width: 1023.98px)'
    assert marker in css
    cards = css.split(marker, 1)[1].split('@media', 1)[0]
    for needle in ('.ts-scroll { overflow: visible; }', '.ts-table thead { display: none; }',
                   'grid-template-columns: repeat(28, minmax(0, 1fr))',
                   '.ts-table .ts-c-rate { grid-column: 19 / 29; justify-self: end; }',
                   '.ts-table .ts-c-n { grid-column: span 7;', '.ts-table .ts-c-day { grid-column: span 4;',
                   'content: attr(data-label)', 'content: attr(data-mon) \" \" attr(data-day)'):
        assert needle in cards, needle
    assert '@media screen and (min-width: 576px) and (max-width: 1023.98px)' in css      # 14 boxes per line on a tablet
    assert 'position: static; min-width: 0; grid-column: 1 / 19;' in cards                 # no sticky name column in a card
    assert 'html[dir=\"rtl\"] .ts-table tbody tr[data-risk=\"1\"]' in cards                    # Urdu: red bar on the other side
    assert 'html[dir=\"rtl\"] .ts-table .ts-sticky' in cards                                  # Urdu: no leftover side line in a card


def test_phone_header_filters_and_summary_fit_the_screen(admin_client, app):
    _marked(app)
    css = _css(_body(admin_client))
    phone = css.split('@media (max-width: 767.98px) {', 1)[1].split('@media screen', 1)[0]
    for needle in ('.ts-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.ts-tools > .btn:last-child:nth-child(odd) { grid-column: 1 / -1; }',
                   '.ts-range { flex: 1 1 100%; display: grid;',          # From / To one line each (they pushed the page sideways)
                   '.ts-filters .ts-range .form-control[type=date] { width: 100%; min-width: 0; }',
                   'font-size: 16px',                                      # no iPhone zoom when a box is tapped
                   '.ts-ribbon { grid-template-columns: repeat(3, minmax(0, 1fr));',
                   '.ts-ribbon .ts-stat:nth-child(2) { grid-column: 1 / -1; order: -1; }'):
        assert needle in phone, needle


def test_every_cell_has_its_phone_label_and_every_day_its_date(admin_client, app):
    _marked(app)
    body = _body(admin_client)
    row = body.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    assert 'ts-grp ts-c-rate' in row
    for label in ('Present', 'Absent', 'Late', 'Leave'):
        assert 'class="ts-c-n" data-label="%s"' % label in row
    assert 'data-day="30" data-dow="Fri" data-mon="Oct"' in row          # first box names its month
    assert 'data-day="2" data-dow="Mon" data-mon="Nov"' in row           # and so does the first box of the next month
    assert row.count('class="text-nowrap ts-c-day') == row.count('data-dow=')


def test_numbers_boxes_and_filters_are_unchanged(admin_client, app):
    _marked(app)
    body = _body(admin_client)
    head = body[body.index('<thead>'):body.index('</thead>')]
    assert head.index('Attendance') < head.index('Present') < head.index('Absent') < head.index('Leave') < head.index('<b>30</b>')
    for needle in ('id="tsSearch"', "setMode('risk')", "setMode('perfect')", "setMode('all')", 'id="tsVisible"',
                   'data-risk=', 'data-perfect=', 'data-search="ayesha noor tm1"', 'How to read the boxes:',
                   'L · 17m', '17 min', 'class="ts-day p"', 'name="start_date"', 'name="end_date"',
                   '/attendance/teachers/summary/export/pdf', '/attendance/teachers/summary/export/excel',
                   '/attendance/teachers/summary/export/csv', 'This Month', 'Last Month', 'Take Teacher Attendance',
                   'Student Attendance Summary', 'Teacher Attendance Summary'):
        assert needle in body, needle


def test_empty_page_still_shows_its_message(admin_client):
    body = _body(admin_client)
    assert 'No teachers found.' in body
    assert 'class="ts-table' not in body

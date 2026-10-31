"""Term exam page (/examinations/<id>) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid,
the four summary boxes are two lines of two, and the Date Sheet and the Edit
Date Sheet tables become one small card per subject. These tests check the
pieces that layout needs and that no number, button or field went missing."""

from app.database import db
from app.models import TermExam
from tests.test_examinations_page_redesign import _class_with_students, _exam


def _make(app, status='Ongoing', name='Detail Exam'):
    with app.app_context():
        cls, subject, kids = _class_with_students('Detail Class', roll_base=7400)
        exam = _exam(cls, subject, name, kids[:1], status=status)
        db.session.commit()
        return exam.id


def _body(client, exam_id):
    reply = client.get('/examinations/%d' % exam_id)
    assert reply.status_code == 200
    return reply.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .xd-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.xd-head' in block][0]


def test_phone_rules_only_apply_on_a_phone_screen(admin_client, app):
    css = _css(_body(admin_client, _make(app)))
    assert css.count('@media') == 1
    assert '@media screen and (max-width: 767.98px) {' in css       # "screen": printing the page keeps the table
    assert css.strip().startswith('/*') and css.index('@media') > css.index('*/')   # nothing outside the media query


def test_phone_header_switch_and_summary_fit_the_screen(admin_client, app):
    body = _body(admin_client, _make(app))
    css = _css(body)
    for needle in ('.xd-tools { width: 100%; display: grid !important; grid-template-columns: 1fr 1fr;',
                   '.xd-tools > :first-child, .xd-tools > :last-child:nth-child(even) { grid-column: 1 / -1; }',
                   '.xd-tools > .btn, .xd-tools > form > .btn { width: 100%; min-height: 2.6rem;',   # Unpublish sits in a form
                   '.xd-switch .btn-group { width: 100%; }',
                   '.xd-stats .card-body { padding: 0.7rem 0.8rem; }'):
        assert needle in css, needle
    assert 'xd-head' in body and 'd-flex gap-2 flex-wrap xd-tools' in body
    assert '<div class="xd-switch">' in body
    assert body.count('col-6 col-md-3') == 4 and 'row g-3 mb-3 xd-stats' in body      # two by two on a phone, four in a row on a computer


def test_date_sheet_rows_are_cards_with_a_label_on_every_line(admin_client, app):
    body = _body(admin_client, _make(app))
    css = _css(body)
    for needle in ('.xd-sheet thead, .xd-edit thead { display: none; }',
                   'grid-template-columns: repeat(4, minmax(0, 1fr))',
                   '.xd-sheet td.xd-c-name, .xd-edit td.xd-c-name { grid-column: 2 / -1; }',
                   '.xd-sheet td.xd-c-f, .xd-edit td.xd-c-f { grid-column: span 2; }',
                   '.xd-c-f::before { content: attr(data-label);',
                   '.xd-panel .table-responsive { overflow: visible; }',
                   'html[dir="rtl"] .xd-sheet td, html[dir="rtl"] .xd-edit td { text-align: right !important; }'):
        assert needle in css, needle
    sheet = body.split('xd-sheet">', 1)[1]
    row = sheet.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Exam Date', 'Time', 'Room', 'Max Marks', 'Marks Entered'):
        assert 'data-label="%s"' % label in row, label
    assert 'xd-c-no' in row and 'xd-c-name' in row
    foot = sheet.split('<tfoot>', 1)[1].split('</tfoot>', 1)[0]
    assert 'data-label="Max Marks"' in foot and 'data-label="Marks Entered"' in foot and '>Total<' in foot


def test_edit_date_sheet_rows_are_cards_too(admin_client, app):
    body = _body(admin_client, _make(app))
    css = _css(body)
    assert '.xd-edit .form-control, .xd-shift .form-control, .xd-panel .form-control { font-size: 16px;' in css   # no iPhone zoom
    assert '.xd-shift .btn { width: 100%; min-height: 2.6rem; }' in css
    edit = body.split('xd-edit">', 1)[1]
    row = edit.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Exam Date', 'Time', 'Room'):
        assert 'data-label="%s"' % label in row, label
    for field in ('name="exam_date_', 'name="exam_time_', 'name="exam_room_'):
        assert field in row, field
    assert 'class="row g-2 align-items-end xd-shift"' in body and 'col-12 col-sm-auto' in body


def test_nothing_was_removed_from_the_page(admin_client, app):
    body = _body(admin_client, _make(app))
    for needle in ('Term Examination', 'Detail Exam', 'Enter Marks', 'Tabulation', 'Report Cards', 'Publish Results',
                   'Edit Date Sheet', 'Print Date Sheet', 'fa-file-pdf me-1"></i> PDF', 'fa-arrow-left me-1"></i> All',
                   'Class Tests', 'Term Examinations', 'Subjects', 'Total Marks', 'Students', 'Marks Entered',
                   'id="editSchedule"', 'Save Schedule', 'name="start_date"', 'name="end_date"', 'name="announce_date"',
                   'Postpone / shift all dates by', 'name="shift_days"', 'Shift Dates', 'data-confirm="Shift ALL exam dates',
                   'id="publishModal"', 'name="queue_whatsapp"', '/examinations/', 'Marks entry uses the same fast grid'):
        assert needle in body, needle


def test_published_exam_still_offers_unpublish(admin_client, app):
    body = _body(admin_client, _make(app, status='Published', name='Done Exam'))
    assert 'Unpublish' in body and 'data-confirm="Revert published results back to Scheduled?"' in body
    assert 'Publish Results' not in body.split('id="editSchedule"', 1)[0].split('d-flex gap-2 flex-wrap xd-tools', 1)[1]

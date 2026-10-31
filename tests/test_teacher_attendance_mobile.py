"""Teacher Attendance sheet on phones and tablets.

Same HTML for every screen size: these tests check the pieces the small-screen
layout needs (cards up to 1023px, a Save bar that can stick to the screen, room
for the assistant button, tidy header buttons) and that no feature went missing."""

from datetime import date

from app.database import db
from app.models import AttendanceModel, TeacherModel

DAY = date(2026, 9, 21)
URL = '/attendance/teachers?date=%s' % DAY


def _teachers(count=2):
    out = []
    for n in range(count):
        t = TeacherModel(teacher_id_str='TA%d' % n, teacher_name='Teacher Number %d' % n, qualification='MA')
        db.session.add(t)
        out.append(t)
    db.session.commit()
    return [t.id for t in out]


def _page(client, app, partly_marked=False):
    with app.app_context():
        ids = _teachers()
        if partly_marked:
            db.session.add(AttendanceModel(date=DAY, target_type='teacher', target_id=ids[0], status='Present'))
            db.session.commit()
    reply = client.get(URL)
    assert reply.status_code == 200
    return reply.get_data(as_text=True), ids


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .ta-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.ta-head' in block][0]


def test_teachers_are_cards_on_phones_and_tablets(admin_client, app):
    css = _css(_page(admin_client, app)[0])
    assert '@media (max-width: 1023.98px)' in css
    before_tablet, tablet_and_phone = css.split('@media (max-width: 1023.98px)', 1)
    # the register needs ~820px, so the card rules must live in the 1023px block ...
    for needle in ('.ta-table thead { display: none; }', '.ta-table .ta-row { display: grid;',
                   '.ta-table .ta-c-status, .ta-table .ta-c-time { grid-column: 1 / -1; }'):
        assert needle in tablet_and_phone, needle
    # ... and not be left behind in the phone-only (767px) block
    phone_only = before_tablet.split('@media (max-width: 767.98px)', 1)[1]
    assert '.ta-table thead' not in phone_only


def test_save_bar_can_stick_to_the_screen(admin_client, app):
    css = _css(_page(admin_client, app)[0])
    panel = [line for line in css.splitlines() if line.strip().startswith('.ta-panel {')][0]
    assert 'overflow: clip' in panel          # overflow:hidden would stop position:sticky from working
    assert 'position: sticky; bottom: 0' in css


def test_save_bar_leaves_room_for_the_assistant_button(admin_client, app):
    css = _css(_page(admin_client, app)[0])
    assert 'padding: 0.75rem 5rem 0.75rem 1.1rem' in css          # computer / tablet
    assert 'padding: 0.65rem 4.9rem 0.65rem 0.8rem' in css        # phone
    assert 'html[dir="rtl"] .ta-save' in css                      # Urdu: room on the other side


def test_phone_header_buttons_and_inputs(admin_client, app):
    css = _css(_page(admin_client, app)[0])
    assert '.ta-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;' in css
    assert 'font-size: 16px' in css                                # no iPhone zoom when a box is tapped
    assert '.ta-time .btn { width: 2.75rem; height: 2.75rem; }' in css


def test_not_marked_names_can_be_hidden_on_phones_but_stay_in_the_page(admin_client, app):
    body, _ = _page(admin_client, app, partly_marked=True)
    assert 'class="ta-sub ta-names"' in body
    assert 'Teacher Number 1' in body.split('class="ta-sub ta-names">', 1)[1].split('</span>', 1)[0]
    assert '.ta-warn .ta-names { display: none; }' in _css(body)
    assert 'id="toggleUnmarkedBtn"' in body                        # the button that shows them is still there


def test_teacher_attendance_features_are_still_there(admin_client, app):
    body, ids = _page(admin_client, app)
    for needle in ('id="taSearch"', 'id="attTable"', 'id="allTeachersAtTime"', 'id="allTeachersAtTimeNote"',
                   "markAll('Present')", 'markAllAbsentAsk()', 'resetToInitial()', 'markAllAtTime()',
                   'Monthly Summary', 'Student Attendance', 'Save Teacher Attendance',
                   '/attendance/teachers/export/pdf', '/attendance/teachers/export/excel',
                   '/attendance/teachers/export/csv', 'id="barPresent"', 'id="cntAbsent"', 'id="sumLeave"', 'Today'):
        assert needle in body, needle
    for tid in ids:
        for field in ('status_%d', 'checkin_time_%d'):
            assert 'name="%s"' % (field % tid) in body
        for prefix in ('p_', 'a_', 'l_', 'lv_'):
            assert 'id="%s%d"' % (prefix, tid) in body

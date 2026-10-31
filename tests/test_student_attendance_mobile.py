"""Student Attendance sheet on phones and tablets.

Same HTML for every screen size: these tests check the pieces the small-screen
layout needs (cards up to 1023px, a Save bar that can stick to the screen, room
for the assistant button, tidy header buttons) and that no feature went missing."""

from datetime import date

PAST_DATE = date(2026, 9, 21)


def _page(client, seed, day=PAST_DATE):
    return client.get('/attendance/students?class_id=%d&date=%s' % (seed['class_id'], day)).get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .sa-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.sa-head' in block][0]


def test_students_are_cards_on_phones_and_tablets(admin_client, seed):
    css = _css(_page(admin_client, seed))
    assert '@media (max-width: 1023.98px)' in css
    before_tablet, tablet_and_phone = css.split('@media (max-width: 1023.98px)', 1)
    # the register needs ~820px, so the card rules must live in the 1023px block ...
    for needle in ('.sa-table thead { display: none; }', '.sa-table .sa-row { display: grid;',
                   '.sa-table .sa-c-status, .sa-table .sa-c-time { grid-column: 1 / -1; }'):
        assert needle in tablet_and_phone, needle
    # ... and not be left behind in the phone-only (767px) block
    phone_only = before_tablet.split('@media (max-width: 767.98px)', 1)[1]
    assert '.sa-table thead' not in phone_only


def test_save_bar_can_stick_to_the_screen(admin_client, seed):
    css = _css(_page(admin_client, seed))
    panel = [line for line in css.splitlines() if line.strip().startswith('.sa-panel {')][0]
    assert 'overflow: clip' in panel          # overflow:hidden would stop position:sticky from working
    assert 'position: sticky; bottom: 0' in css


def test_save_bar_leaves_room_for_the_assistant_button(admin_client, seed):
    css = _css(_page(admin_client, seed))
    assert 'padding: 0.75rem 5rem 0.75rem 1.1rem' in css          # computer / tablet
    assert 'padding: 0.65rem 4.9rem 0.65rem 0.8rem' in css        # phone
    assert 'html[dir="rtl"] .sa-save' in css                      # Urdu: room on the other side


def test_phone_header_buttons_and_inputs(admin_client, seed):
    css = _css(_page(admin_client, seed))
    assert '.sa-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;' in css
    assert 'font-size: 16px' in css                                # no iPhone zoom when a box is tapped
    assert '.sa-time .btn { width: 2.75rem; height: 2.75rem; }' in css
    assert '.sa-wa-menu { min-width: min(18rem, calc(100vw - 2rem)); }' in css


def test_not_marked_names_can_be_hidden_on_phones_but_stay_in_the_page(admin_client, seed):
    body = _page(admin_client, seed)
    assert 'class="sa-sub sa-names"' in body
    assert 'Ali Khan' in body.split('class="sa-sub sa-names">', 1)[1].split('</span>', 1)[0]
    assert '.sa-warn .sa-names { display: none; }' in _css(body)
    assert 'id="toggleUnmarkedBtn"' in body                        # the button that shows them is still there


def test_attendance_sheet_features_are_still_there(admin_client, seed):
    body = _page(admin_client, seed)
    for needle in ('id="saSearch"', 'id="attTable"', 'id="allAtTime"', 'id="allAtTimeNote"',
                   "markAll('Present')", 'markAllAbsentAsk()', 'resetToInitial()', 'markAllAtTime()',
                   'id="send-absent-alerts-btn"', 'id="test-whatsapp-btn"', 'Teacher Attendance',
                   'Save Attendance', 'name="class_id"', 'name="date"',
                   '/attendance/export/pdf/', '/attendance/export/excel/', '/attendance/export/csv/',
                   'id="barPresent"', 'id="cntAbsent"', 'id="sumLeave"', 'Today'):
        assert needle in body, needle
    for sid in (seed['student_id'], seed['other_student_id']):
        for field in ('status_%d', 'checkin_time_%d'):
            assert 'name="%s"' % (field % sid) in body
        for prefix in ('p_', 'a_', 'l_', 'lv_'):
            assert 'id="%s%d"' % (prefix, sid) in body


def test_locked_day_still_shows_on_small_screens(admin_client, seed):
    admin_client.post('/attendance/students', data={
        'class_id': str(seed['class_id']), 'date': PAST_DATE.isoformat(),
        'status_%d' % seed['student_id']: 'Absent',
        'status_%d' % seed['other_student_id']: 'Present',
        'checkin_time_%d' % seed['other_student_id']: '08:00',
    })
    body = _page(admin_client, seed)
    assert 'Attendance Locked' in body and 'data-confirm=' in body
    assert 'sa-pill a' in body and 'sa-pill p' in body
    assert 'class="sa-save"' not in body                           # no Save bar while locked
    assert 'sa-savedbar' in body

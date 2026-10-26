"""Student attendance page: the redesigned, plain-language sheet."""

from datetime import date, timedelta

PAST_DATE = date(2026, 9, 21)


def _get(client, class_id, day):
    return client.get('/attendance/students?class_id=%d&date=%s' % (class_id, day)).get_data(as_text=True)


def test_sheet_has_search_save_bar_and_day_buttons(admin_client, seed):
    html = _get(admin_client, seed['class_id'], PAST_DATE)
    assert 'id="saSearch"' in html                       # find a student
    assert 'Save Attendance' in html                     # one clear main button
    assert 'Open — Not Yet Saved' in html
    assert 'date=%s' % (PAST_DATE - timedelta(days=1)) in html     # previous-day button
    assert 'date=%s' % (PAST_DATE + timedelta(days=1)) in html     # next-day button
    # every student still posts a status and a check-in time, exactly as before
    assert 'name="status_%d"' % seed['student_id'] in html
    assert 'name="checkin_time_%d"' % seed['student_id'] in html


def test_today_page_knows_it_is_today(admin_client, seed):
    """The sheet used to be told nothing about 'today', so the Now time was never filled in."""
    today = _get(admin_client, seed['class_id'], date.today())
    assert 'var IS_TODAY = true;' in today
    past = _get(admin_client, seed['class_id'], PAST_DATE)
    assert 'var IS_TODAY = false;' in past


def test_saved_day_shows_locked_state_and_counts(admin_client, seed):
    admin_client.post('/attendance/students', data={
        'class_id': str(seed['class_id']), 'date': PAST_DATE.isoformat(),
        'status_%d' % seed['student_id']: 'Absent',
        'status_%d' % seed['other_student_id']: 'Present',
        'checkin_time_%d' % seed['other_student_id']: '08:00',
    })
    html = _get(admin_client, seed['class_id'], PAST_DATE)
    assert 'Attendance Locked' in html and 'data-confirm=' in html       # Unlock asks first
    assert 'id="cntAbsent">1</b>' in html
    assert 'id="cntPresent">1</b>' in html
    assert 'name="status_%d"' % seed['student_id'] not in html          # no edit buttons while locked

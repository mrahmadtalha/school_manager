"""QR Scans tab (redesigned page): list, chips, set-up steps, role limits, approval card."""

import re
from datetime import date, datetime

import pytest

from app.database import db
from app.models import ROLE_GUARD, AdminUser, SchoolSettings
from app.models.qr_config import QrConfig
from app.services import qr_absent
from app.services import qr_attendance as qr

MONDAY = date(2026, 10, 19)
URL = '/attendance/students?tab=qr&date=2026-10-19'


def _at(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute)


@pytest.fixture(autouse=True)
def _school(app):
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    settings.weekend_off = True
    for name in ('saturday_off', 'sunday_off'):
        if hasattr(settings, name):
            setattr(settings, name, True)
    db.session.commit()


def _scan(student_id, now):
    return qr.process_scan(qr.make_token(qr.get_secret(), student_id), now=now)


def _row(group):
    """The opening of one student row (the CSS also mentions data-group, so match the row itself)."""
    return 'class="qa-row" data-group="%s"' % group


def _page(client, url=URL):
    reply = client.get(url)
    assert reply.status_code == 200
    return reply.get_data(as_text=True)


def _make_guard():
    guard = AdminUser(username='guard', role=ROLE_GUARD, full_name='Gate Guard')
    guard.set_password('guardpass123')
    db.session.add(guard)
    db.session.commit()
    return guard


# -- the list -----------------------------------------------------------------

def test_page_has_the_live_parts_the_script_swaps(app, seed, admin_client):
    html = _page(admin_client)
    for marker in ('id="qaTop"', 'id="qaList"', 'id="qaSearch"', 'id="autoRefresh"',
                   'data-qa-filter="all"', 'data-qa-filter="absent"', 'Update now'):
        assert marker in html


def test_scanned_student_is_arrived_and_the_other_is_not_arrived(app, seed, admin_client):
    _scan(seed['student_id'], _at(MONDAY, 8, 20))
    html = _page(admin_client)
    assert html.count(_row('present')) == 1
    assert html.count(_row('absent')) == 1
    assert 'Arrived' in html and '08:20' in html
    assert 'Not scanned' in html            # an old day: "yet" would be wrong


def test_students_who_have_not_arrived_come_first(app, seed, admin_client):
    _scan(seed['student_id'], _at(MONDAY, 8, 20))
    html = _page(admin_client)
    assert html.index(_row('absent')) < html.index(_row('present'))


def test_late_student_shows_minutes_late(app, seed, admin_client):
    _scan(seed['student_id'], _at(MONDAY, 8, 50))
    html = _page(admin_client)
    assert _row('late') in html and '20 min late' in html


def test_chip_counts_match_the_summary(app, seed, admin_client):
    _scan(seed['student_id'], _at(MONDAY, 8, 20))
    html = _page(admin_client)
    assert re.search(r'data-qa-filter="absent">Not arrived <b>1</b>', html)
    assert re.search(r'data-qa-filter="present">Arrived on time <b>1</b>', html)
    assert re.search(r'data-qa-filter="late">Late <b>0</b>', html)


def test_class_filter_and_day_arrows_keep_the_tab(app, seed, admin_client):
    html = _page(admin_client, URL + '&class_id=%d' % seed['class_id'])
    assert 'tab=qr' in html and 'date=2026-10-18' in html and 'date=2026-10-20' in html
    assert admin_client.get(URL + '&class_id=999999').status_code == 200
    assert 'There are no students in this class yet.' in _page(admin_client, URL + '&class_id=999999')


def test_closed_day_is_explained(app, seed, admin_client):
    html = _page(admin_client, '/attendance/students?tab=qr&date=2026-10-18')   # a Sunday
    assert 'School is closed on this day' in html


# -- set-up steps --------------------------------------------------------------

def _setup_tag(html):
    return re.search(r'<details[^>]*id="qaSetup"[^>]*>', html).group(0)


def test_setup_is_open_while_something_is_missing(app, seed, admin_client):
    html = _page(admin_client)
    assert 'Connect the guard' in html and ' open' in _setup_tag(html)
    assert 'Create guard account' in html


def test_setup_folds_away_when_everything_is_ready(app, seed, admin_client):
    _make_guard()
    QrConfig.get().lan_access = True
    db.session.commit()
    html = _page(admin_client)
    assert 'Guard phone is ready' in html
    assert ' open' not in _setup_tag(html)
    assert 'id="pairBox"' in html


def test_teacher_sees_the_list_but_no_admin_boxes(app, seed, teacher_client):
    html = _page(teacher_client)
    assert 'id="qaList"' in html
    for hidden in ('id="qaSetup"', 'id="qaAuto"', 'id="pairBox"', 'Create guard account'):
        assert hidden not in html


# -- auto-absent ---------------------------------------------------------------

def test_auto_absent_box_states_on_or_off(app, seed, admin_client):
    assert 'id="qaAuto"' in _page(admin_client)
    assert 'Off' in _page(admin_client)
    config = QrConfig.get()
    config.auto_absent_enabled = True
    config.absent_cutoff_time = '09:30'
    db.session.commit()
    assert 'at 09:30' in _page(admin_client)


def test_waiting_approval_card_comes_before_the_setup_box(app, seed, admin_client):
    config = QrConfig.get()
    config.auto_absent_enabled = True
    config.absent_cutoff_time = '09:30'
    config.absent_mode = 'approval'
    config.absent_min_scan_percent = 30
    db.session.commit()
    qr_absent.run_auto_absent(now=_at(MONDAY, 9, 45))
    html = _page(admin_client)
    assert 'waiting for approval' in html and 'Approve' in html
    assert 'No, do not mark anyone' in html
    assert html.index('waiting for approval') < html.index('id="qaSetup"')


def test_teacher_does_not_get_the_approval_buttons(app, seed, teacher_client):
    config = QrConfig.get()
    config.auto_absent_enabled = True
    config.absent_cutoff_time = '09:30'
    config.absent_mode = 'approval'
    config.absent_min_scan_percent = 30
    db.session.commit()
    qr_absent.run_auto_absent(now=_at(MONDAY, 9, 45))
    html = _page(teacher_client)
    assert 'Approve' not in html


# -- the sheet page keeps its own wording ---------------------------------------

def test_sheet_tab_text_is_not_changed_by_the_qr_tab(app, seed, admin_client):
    sheet = _page(admin_client, '/attendance/students?date=2026-10-19')
    assert 'Mark who came to school' in sheet
    assert 'QR Scans' in sheet
    assert 'See who has reached school' in _page(admin_client)

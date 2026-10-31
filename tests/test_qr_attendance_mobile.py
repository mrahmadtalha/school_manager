"""QR Scans tab of Student Attendance on phones and tablets.

Same HTML for every screen size: these tests check the pieces the small-screen
layout needs (the scan list as cards, a pairing picture that can shrink, big
enough boxes and chips) and that no part of the tab went missing."""

from datetime import date, datetime

import pytest

from app.database import db
from app.models import SchoolSettings
from app.services import qr_attendance as qr

MONDAY = date(2026, 10, 19)
URL = '/attendance/students?tab=qr&date=2026-10-19'


@pytest.fixture(autouse=True)
def _school(app):
    settings = SchoolSettings.query.first() or SchoolSettings()
    db.session.add(settings)
    settings.school_start_time = '08:30'
    settings.attendance_grace_minutes = 0
    db.session.commit()


def _page(client, url=URL):
    reply = client.get(url)
    assert reply.status_code == 200
    return reply.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the QR tab's styles are the block that holds .qa-intro
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.qa-intro' in block][0]


def _phone_block(css):
    return css.split('@media (max-width: 767.98px)', 1)[1].split('@media (prefers-reduced-motion', 1)[0]


def test_each_scan_is_a_card_with_status_and_time_on_one_line(admin_client, seed):
    phone = _phone_block(_css(_page(admin_client)))
    assert '.qa-head { display: none; }' in phone
    for needle in ('.qa-row { grid-template-columns: auto minmax(0, 1fr) auto;',
                   '.qa-row .qa-c-who { grid-column: 2 / 4; grid-row: 1; }',
                   '.qa-row .qa-c-class { display: block; grid-column: 2 / 4; grid-row: 2;',
                   '.qa-row .qa-c-status { grid-column: 1 / 3; grid-row: 3; }',
                   '.qa-row .qa-c-when { grid-column: 3; grid-row: 3;'):
        assert needle in phone, needle


def test_phone_boxes_and_chips_are_finger_sized(admin_client, seed):
    css = _css(_page(admin_client))
    phone = _phone_block(css)
    assert '.qa-field .form-control, .qa-field .form-select, #pairGuard { font-size: 16px; }' in phone
    assert '.qa-chip { min-height: 2.5rem; }' in phone
    assert '#qaSearch { text-overflow: ellipsis; }' in css           # long hint is cut with "…", not mid-letter


def test_pairing_picture_can_shrink_on_a_small_phone(admin_client, seed):
    css = _css(_page(admin_client))
    assert '.qa-qr canvas, .qa-qr img { max-width: 100%; height: auto !important; }' in css


def test_scan_rows_keep_their_parts(admin_client, seed):
    qr.process_scan(qr.make_token(qr.get_secret(), seed['student_id']), now=datetime(2026, 10, 19, 8, 50))
    body = _page(admin_client)
    assert body.count('class="qa-row" data-group="late"') == 1
    assert body.count('class="qa-row" data-group="absent"') == 1
    row = body.split('class="qa-row" data-group="late"', 1)[1].split('</div>', 1)[0]
    for part in ('qa-c-roll', 'qa-c-who', 'qa-c-class', 'qa-c-status', 'qa-c-when', '20 min late', '08:50'):
        assert part in row, part


def test_qr_tab_features_are_still_there(admin_client, seed):
    body = _page(admin_client)
    for needle in ('id="qaTop"', 'id="qaList"', 'id="qaSearch"', 'id="autoRefresh"', 'id="qaNow"',
                   'data-qa-filter="all"', 'data-qa-filter="absent"', 'data-qa-filter="late"',
                   'data-qa-filter="present"', 'Print QR ID cards', 'id="qaSetup"', 'id="qaAuto"',
                   'name="absent_cutoff_time"', 'name="absent_mode"', 'name="absent_min_scan_percent"',
                   'name="absent_message_delay_minutes"', 'Save these settings', 'name="class_id"', 'name="date"'):
        assert needle in body, needle

# -*- coding: utf-8 -*-
"""Admission Fees register (/admission-fees) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid (the PDF /
Excel / CSV export buttons on one full-width line), the four summary boxes are two lines of
two, the status buttons and the filter boxes are easy to tap, and every student is one card
with a label on every line (the Total fee card also keeps its small "Admission ... Books +
uniform ... Concession ..." line) and a full-width Open button. These tests check the pieces
that layout needs and that no figure, filter, export or button went missing."""

from app.services import i18n
from tests.test_admission_fee import _register_fixture


def _page(admin_client, seed, query=''):
    _register_fixture(seed)
    response = admin_client.get('/admission-fees' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.adm-tiles' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def test_header_uses_the_shared_phone_helpers(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert 'pb-3 mb-4 m-head' in body
    assert 'd-flex gap-2 flex-wrap align-items-center m-actions' in body
    for needle in ('>PDF<', '>Excel<', '>CSV<', 'Other Income', 'Fee settings'):
        assert needle in body, needle


def test_summary_boxes_are_two_lines_of_two(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert 'su-tiles adm-tiles mb-3' in body
    phone = _phone(_css(body))
    for needle in ('.adm-tiles { grid-template-columns: 1fr 1fr; }',
                   '.adm-tiles .su-num { font-size: 1.25rem; overflow-wrap: anywhere; }'):
        assert needle in phone, needle


def test_status_buttons_and_filter_boxes_are_easy_to_tap(admin_client, app, seed):
    body = _page(admin_client, seed)
    css = _css(body)
    assert 'adm-form' in body
    for needle in ('.adm-page .su-filter a { min-height: 2.4rem;',
                   '.adm-page .adm-form .form-control, .adm-page .adm-form .form-select { min-height: 2.7rem; }',
                   '.adm-page .adm-form .btn-primary { min-height: 2.7rem; }'):
        assert needle in _phone(css), needle
    assert '.adm-page .adm-form .form-control, .adm-page .adm-form .form-select { font-size: 16px; }' in css.split('@media (max-width: 575.98px) {', 1)[1]


def test_students_become_cards_with_a_label_on_every_line(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert 'table table-hover align-middle mb-0 m-cards' in body
    table = body[body.index('align-middle mb-0 m-cards'):].split('</table>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Class', 'Joined', 'Total fee', 'Received', 'Still to collect', 'Status'):
        assert 'data-label="%s"' % label in row, label
    assert 'adm-total' in row and 'adm-open' in row and 'Open' in row
    assert 'Admission ' in row                                                  # the small breakdown line is still there
    phone = _phone(_css(body))
    for needle in ('.adm-page .table-responsive { overflow: visible; }',
                   '.adm-page .m-cards tbody td.adm-total { flex-wrap: wrap; }',
                   '.adm-page .m-cards tbody td.adm-total > div { flex: 1 1 100%; text-align: right; }',
                   '.adm-page .m-cards tbody td.adm-open .btn { width: 100%; min-height: 2.6rem; }'):
        assert needle in phone, needle


def test_filters_still_work_with_the_card_layout(admin_client, app, seed):
    body = _page(admin_client, seed, '?status=pending')
    assert 'Pending Kid' in body and 'Waived Kid' not in body


def test_empty_view_still_shows_its_message(admin_client, app, seed):
    _register_fixture(seed)
    body = admin_client.get('/admission-fees?search=nobody-has-this-name').get_data(as_text=True)
    assert 'No students match this view yet.' in body


def test_phone_rules_are_only_inside_media_queries(admin_client, app, seed):
    css = _css(_page(admin_client, seed))
    outside = css.split('@media (max-width: 767.98px) {', 1)[0]
    assert outside.strip().startswith('/*') and '{' not in outside.split('*/', 1)[1]


def test_new_phone_labels_are_translated_to_urdu(admin_client, app, seed):
    html = i18n.translate_html(_page(admin_client, seed))
    for english in ('data-label="Class"', 'data-label="Joined"', 'data-label="Total fee"',
                    'data-label="Received"', 'data-label="Still to collect"', 'data-label="Status"'):
        assert english not in html, english


def test_nothing_was_removed_from_the_page(admin_client, app, seed):
    body = _page(admin_client, seed)
    for needle in ('Admission Fees', 'Which page do I use?', 'Students listed', 'Agreed total', 'Received',
                   'Still to collect', 'aria-label="Show students by status"', 'name="search"', 'name="class_id"',
                   'name="status"', 'name="date_from"', 'name="date_to"', 'aria-label="Apply filters"',
                   'All classes', 'Student', 'Class', 'Joined', 'Total fee', 'Status',
                   '/admission-fees/export/pdf', '/admission-fees/export/xlsx', '/admission-fees/export/csv',
                   '/admission-fees/student/'):
        assert needle in body, needle

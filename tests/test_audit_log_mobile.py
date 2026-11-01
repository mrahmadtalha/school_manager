# -*- coding: utf-8 -*-
"""Audit Log (/audit-log) on phones.

Same HTML for every screen size. On a phone the Export button is full width, the filter
boxes, the When buttons and the From / To dates fit the screen, the list's own controls
(Show N entries, Quick Filter, paging) are finger-sized, and every log entry is one card
(time and what happened on top, then who, what it was about and the details with the
"See what changed" before / after table) instead of a wide table you swipe sideways. The
sideways-scrolling table setting is switched off only on a phone, so the computer keeps it.
These tests check the pieces that layout needs and that nothing went missing."""

from app.database import db
from app.services import audit as audit_service, i18n


def _entries(app):
    with app.app_context():
        audit_service.log_action('create', entity_type='StudentModel', entity_id=1, summary='Added student Phone Zed')
        audit_service.log_action('update', entity_type='StudentModel', entity_id=1, summary='Fee changed for phone-check',
                                 before={'id': 1, 'monthly_fee': 2500}, after={'id': 1, 'monthly_fee': 3000})
        db.session.commit()


def _page(admin_client, app, seed, query=''):
    _entries(app)
    response = admin_client.get('/audit-log' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.al-ribbon' in block][0]


def _phone(css):
    return css.split('/* phones: Export button', 1)[1].split('@media (max-width: 575.98px) {', 1)[0]


def _small(css):
    return css.split('/* phones: Export button', 1)[1].split('@media (max-width: 575.98px) {', 1)[1]


def test_export_button_and_filters_fit_the_phone(admin_client, app, seed):
    phone = _phone(_css(_page(admin_client, app, seed)))
    for needle in ('.al-tools { width: 100%; }',
                   '.al-tools .btn { flex: 1; min-height: 2.6rem;',
                   '.al-filters .form-select, .al-filters .form-control.al-date { width: 100%; max-width: none; flex: 1 1 100%; }',
                   '.al-seg { width: 100%; }',
                   '.al-seg label { flex: 1; text-align: center; min-height: 2.4rem;',
                   '.al-datebox { flex: 1 1 100%; display: grid; grid-template-columns: auto 1fr;',
                   '.al-filters .btn { flex: 1; justify-content: center; min-height: 2.7rem; }',
                   '.al-filters .btn[aria-label="Clear filters"] { flex: 0 0 auto; min-width: 3rem; }',
                   '.al-count .btn { min-height: 2.4rem;'):
        assert needle in phone, needle


def test_boxes_do_not_zoom_the_page_on_iphones(admin_client, app, seed):
    small = _small(_css(_page(admin_client, app, seed)))
    assert '.al-search input, .al-filters .form-select, .al-filters .form-control.al-date,' in small
    assert 'font-size: 16px' in small


def test_list_controls_are_finger_sized(admin_client, app, seed):
    phone = _phone(_css(_page(admin_client, app, seed)))
    for needle in ('.al-panel .dataTables_wrapper .dataTables_length select, .al-panel .dataTables_wrapper .dataTables_filter input { min-height: 2.6rem; }',
                   '.al-panel .dataTables_wrapper .dataTables_filter input { width: 100%;',
                   '.al-panel .dataTables_wrapper .dataTables_info { text-align: center;',
                   '.al-panel .dataTables_wrapper .pagination { justify-content: center; flex-wrap: wrap;',
                   '.al-panel .dataTables_wrapper .page-link { min-width: 2.4rem; min-height: 2.4rem;',
                   '.al-panel .dataTables_scrollHead { display: none; }'):
        assert needle in phone, needle


def test_log_becomes_cards_with_labels(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    phone = _phone(_css(body))
    table = body[body.index('id="auditTable"'):].split('</table>', 1)[0]
    assert 'datatable al-stack' in table.split('>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for needle in ('al-when', 'al-c-who" data-label="Who"', 'al-c-what', 'al-on" data-label="About"', 'al-c-detail'):
        assert needle in row, needle
    for needle in ('.al-stack > thead { display: none; }',
                   '.al-stack > tbody > tr { display: grid; grid-template-columns: 1fr auto;',
                   '.al-stack > tbody > tr > td[data-label]::before { content: attr(data-label);',
                   '.al-stack > tbody > tr > td.al-when { order: 1;',
                   '.al-stack > tbody > tr > td.al-c-what { order: 2;',
                   '.al-stack > tbody > tr > td.al-c-detail { order: 5; grid-column: 1 / -1;',
                   '.al-stack > tbody > tr > td.dataTables_empty { grid-column: 1 / -1;',
                   'html[dir="rtl"] .al-stack > tbody > tr > td { text-align: right !important; }',
                   '.al-diff td:first-child { white-space: normal; }'):
        assert needle in phone, needle


def test_the_before_and_after_table_is_not_turned_into_cards(admin_client, app, seed):
    body = _page(admin_client, app, seed, '?search=phone-check')
    phone = _phone(_css(body))
    assert 'See what changed' in body and 'class="al-diff"' in body
    assert '.al-diff' in phone and '.al-stack td' not in phone                          # only direct cells of the log are stacked
    assert 'Monthly fee' in body and '2500' in body and '3000' in body


def test_sideways_scroll_is_turned_off_only_on_a_phone(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    table_tag = body[body.rfind('<table', 0, body.index('id="auditTable"')):].split('>', 1)[0]
    assert 'data-scroll-x="true"' in table_tag                                          # the computer keeps it
    assert "window.matchMedia('(max-width: 767.98px)').matches" in body
    assert "table.removeAttribute('data-scroll-x');" in body


def test_phone_rules_are_only_inside_media_queries(admin_client, app, seed):
    css = _css(_page(admin_client, app, seed))
    before = css.split('/* phones: Export button', 1)[0]
    assert '.al-stack' not in before and '.al-tools { width' not in before
    after = css.split('/* phones: Export button', 1)[1]
    assert after.split('*/', 1)[1].lstrip().startswith('@media (max-width: 767.98px) {')


def test_new_phone_labels_are_translated_to_urdu(admin_client, app, seed):
    _entries(app)
    admin_client.get('/language/ur')
    page = admin_client.get('/audit-log').get_data(as_text=True)
    assert 'dir="rtl"' in page
    assert 'data-label="Who"' not in page and 'data-label="About"' not in page
    assert 'What happened' not in page
    admin_client.get('/language/en')


def test_nothing_was_removed_from_the_page(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    for needle in ('Audit Log', 'Export CSV', 'What to do now', 'Entries on this list', 'Failed sign-ins', 'Deleted',
                   'name="search"', 'name="entity_type"', 'name="action"', 'name="username"', 'name="range"',
                   'Any time', 'Today', 'Last 7 days', 'Last 30 days', 'name="date_from"', 'name="date_to"',
                   'Filter', 'entries, newest first', 'id="auditTable"', 'When', 'Who', 'What happened', 'About',
                   'Details', 'Added student Phone Zed', 'Showing up to 500 most recent matching entries',
                   'data-page-length="25"'):
        assert needle in body, needle

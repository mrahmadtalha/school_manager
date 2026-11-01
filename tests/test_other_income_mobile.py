# -*- coding: utf-8 -*-
"""Other Income (/other-income) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid (Financial
Overview on top, Previous / Next side by side, the month box full width), the two summary
boxes share a line, the Add form has bigger boxes, every entry is one card with a label on
every line (empty Note / Receipt lines are hidden), Void is a full-width button, and the
Void window fits the screen. These tests check the pieces that layout needs and that no
figure, box, button or window went missing."""

from app.models import OtherIncome, OtherIncomeCategory
from app.services import i18n

MONTH = '2026-10'


def _add_entries(admin_client, app, description='trip tickets', void_second=False):
    with app.app_context():
        category_id = OtherIncomeCategory.query.filter_by(name='Trips').one().id
    admin_client.post('/other-income/add', data={
        'category_id': str(category_id), 'amount': '2500',
        'income_date': '2026-10-20', 'description': description}, follow_redirects=True)
    if void_second:
        admin_client.post('/other-income/add', data={
            'category_id': str(category_id), 'amount': '700',
            'income_date': '2026-10-21', 'description': ''}, follow_redirects=True)
        with app.app_context():
            row_id = OtherIncome.query.filter_by(amount_paisa=70000).one().id
        admin_client.post('/other-income/%d/void' % row_id, data={'reason': 'test'}, follow_redirects=True)


def _page(admin_client, app, **kwargs):
    # opening the page once makes sure the default categories exist
    admin_client.get('/other-income?month=' + MONTH)
    _add_entries(admin_client, app, **kwargs)
    response = admin_client.get('/other-income?month=' + MONTH)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.oi-tools' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def test_header_uses_the_shared_phone_helpers_and_the_month_arrows_have_names(admin_client, app):
    body = _page(admin_client, app)
    assert 'pb-3 mb-4 m-head' in body
    assert 'btn-toolbar mb-2 mb-md-0 gap-2 m-actions oi-tools' in body
    assert 'aria-label="Previous month"' in body and 'aria-label="Next month"' in body
    phone = _phone(_css(body))
    for needle in ('.oi-tools > a:first-child { grid-column: 1 / -1; order: 0; }',
                   '.oi-tools > a:nth-of-type(2) { order: 1; }',
                   '.oi-tools > a:nth-of-type(3) { order: 2; }',
                   '.oi-tools > form { grid-column: 1 / -1; order: 3; width: 100%; }',
                   '.oi-tools > form .form-control { flex: 1 1 auto; width: auto !important; min-height: 2.7rem; }',
                   '.oi-tools > form .btn { min-height: 2.7rem;'):
        assert needle in phone, needle


def test_summary_boxes_share_a_line(admin_client, app):
    body = _page(admin_client, app)
    assert 'su-tiles oi-tiles mb-3' in body
    phone = _phone(_css(body))
    for needle in ('.oi-tiles { grid-template-columns: 1fr 1fr; }',
                   '.oi-tiles .su-num { font-size: 1.25rem; overflow-wrap: anywhere; }'):
        assert needle in phone, needle


def test_add_form_boxes_are_big_and_do_not_zoom_iphones(admin_client, app):
    body = _page(admin_client, app)
    css = _css(body)
    assert 'oi-add' in body
    for needle in ('.oi-page .form-control, .oi-page .form-select { min-height: 2.7rem; }',
                   '.oi-page .oi-add .btn-success { min-height: 2.8rem; }'):
        assert needle in _phone(css), needle
    assert '.oi-page .form-control, .oi-page .form-select { font-size: 16px; }' in css.split('@media (max-width: 575.98px) {', 1)[1]


def test_entries_become_cards_with_a_label_on_every_line(admin_client, app):
    body = _page(admin_client, app)
    assert 'table table-sm table-striped align-middle mb-0 m-cards' in body
    table = body[body.index('align-middle mb-0 m-cards'):].split('</table>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Category', 'Note', 'Amount (Rs.)', 'Recorded by'):
        assert 'data-label="%s"' % label in row, label
    assert 'oi-act' in row and 'Void' in row
    phone = _phone(_css(body))
    for needle in ('.oi-page .table-responsive { overflow: visible; }',
                   '.oi-page .m-cards tbody td.oi-blank { display: none !important; }',
                   '.oi-page .oi-act .btn { width: 100%; min-height: 2.6rem; }'):
        assert needle in phone, needle


def test_empty_note_and_receipt_lines_are_hidden_on_a_phone(admin_client, app):
    body = _page(admin_client, app, description='')
    table = body[body.index('align-middle mb-0 m-cards'):].split('</table>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    assert 'oi-blank" data-label="Note"' in row                                       # nothing typed -> no empty line


def test_a_voided_entry_is_still_crossed_out_and_shows_its_badge(admin_client, app):
    body = _page(admin_client, app, void_second=True)
    assert 'text-decoration-line-through' in body and 'voided' in body


def test_void_window_fits_the_phone(admin_client, app):
    body = _page(admin_client, app)
    assert 'id="voidIncome' in body
    phone = _phone(_css(body))
    for needle in ('.oi-page .modal .modal-footer .btn { flex: 1 1 0; min-height: 2.7rem; }',
                   '.oi-page .modal .modal-header, .oi-page .modal .modal-body, .oi-page .modal .modal-footer { padding-left: 1rem; padding-right: 1rem; }'):
        assert needle in phone, needle


def test_phone_rules_are_only_inside_media_queries(admin_client, app):
    css = _css(_page(admin_client, app))
    outside = css.split('@media (max-width: 767.98px) {', 1)[0]
    assert outside.strip().startswith('/*') and '{' not in outside.split('*/', 1)[1]


def test_new_phone_labels_are_translated_to_urdu(admin_client, app):
    html = i18n.translate_html(_page(admin_client, app))
    for english in ('data-label="Category"', 'data-label="Note"', 'data-label="Amount (Rs.)"',
                    'data-label="Recorded by"', 'aria-label="Previous month"', 'aria-label="Next month"'):
        assert english not in html, english


def test_nothing_was_removed_from_the_page(admin_client, app):
    body = _page(admin_client, app)
    for needle in ('Other Income', 'Financial Overview', 'name="month"', 'Show', 'Which page do I use?',
                   'Received in', 'Entries this month', 'Add money received', 'What is it for?',
                   'name="category_id"', 'name="amount"', 'id="oiAmount"', 'Charged per student? Work it out',
                   'id="oiPer"', 'id="oiCount"', 'name="income_date"', 'name="description"', 'Save',
                   'Need a new type of income?', 'name="name"', 'Add category',
                   'Date', 'Category', 'Note', 'Receipt', 'Amount (Rs.)', 'Recorded by', 'Action',
                   'data-bs-target="#voidIncome', 'Void this income record?', 'name="reason"', 'Void record'):
        assert needle in body, needle

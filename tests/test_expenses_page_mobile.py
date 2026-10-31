# -*- coding: utf-8 -*-
"""Expenses page (/expenses) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid, the
month bar and filters stack, the summary is two lines of two boxes, Copy / Edit / Void
share one line, and the Table view, the Categories window and the Continue Previous
Month window show one small card per row instead of a wide table. These tests check
the pieces that layout needs and that no button, filter, form or window went missing."""

from app.database import db
from app.services import i18n
from tests.test_expenses_redesign import _category, _expense, _month_first_day


def _page(admin_client, query=''):
    response = admin_client.get('/expenses' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .ex-note
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.ex-note' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1]


def _two_months(app):
    with app.app_context():
        category = _category('Phone Cat')
        _, this_month = _month_first_day(0)
        _, last_month = _month_first_day(-1)
        _expense(category, this_month, 150.0, 'PhoneThisMonth')
        _expense(category, last_month, 90.0, 'PhoneLastMonth')
        db.session.commit()


def test_phone_header_month_bar_and_filters_fit_the_screen(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.ex-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.ex-tools > .btn { grid-column: 1 / -1; width: 100%; min-height: 2.6rem;',
                   '.ex-tools > #categoriesButton { grid-column: auto; }',               # Categories and Export side by side
                   '.ex-nav form { order: -1; flex: 1 1 100%; }',                         # month menu on its own line
                   '.ex-nav > .btn { flex: 1; min-height: 2.6rem;',
                   '.ex-seg { display: flex; width: 100%; }',
                   '.ex-search { flex: 1 1 100%; min-width: 0; }',
                   '.ex-filters .ex-cat { flex: 1 1 100%; width: 100%; max-width: none; }',
                   '.ex-dates .ex-dates-row > div { flex: 1 1 calc(50% - 0.3rem);'):
        assert needle in phone, needle


def test_phone_card_buttons_share_one_line(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.ex-acts { display: flex; width: 100%; }',
                   '.ex-acts .btn, .ex-acts form { flex: 1 1 0; }',
                   '.ex-acts .btn { width: 100%; min-height: 2.5rem;'):
        assert needle in phone, needle


def test_phone_summary_is_two_lines_and_boxes_do_not_zoom(admin_client, app):
    css = _css(_page(admin_client))
    small = _small(css)
    assert '.ex-band { grid-template-columns: 1fr; }' not in css                         # no longer one tall stack
    for needle in ('.ex-num { font-size: 1.2rem; }', 'font-size: 16px', '.ex-grid { grid-template-columns: 1fr; }'):
        assert needle in small, needle


def test_tables_become_cards_on_a_phone(admin_client, app):
    _two_months(app)
    body = _page(admin_client)
    phone = _phone(_css(body))
    for needle in ('.ex-stack thead { display: none; }',
                   '.ex-stack, .ex-stack tbody { display: block; width: 100% !important; }',   # DataTables writes a pixel width
                   '.ex-stack tbody tr { display: grid; grid-template-columns: 1fr 1fr;',
                   '.ex-stack td[data-label]::before { content: attr(data-label);',
                   'html[dir="rtl"] .ex-stack td { text-align: right !important; }',
                   '.ex-tbl-main tbody tr > td:nth-child(3)::before, .ex-tbl-cont tbody tr > td:nth-child(3)::before { content: "Rs. ";',
                   '.ex-tbl-cat tbody tr > td:nth-child(1), .ex-tbl-cat tbody tr > td:nth-child(2) { grid-column: 1 / -1; }',
                   '.ex-tbl-cont .btn { width: 100%; min-height: 2.6rem; }',
                   '.ex-page .modal .modal-footer .btn { flex: 1 1 0; min-height: 2.7rem; }',
                   '.ex-form .ex-pay { flex-wrap: wrap; }'):
        assert needle in phone, needle


def test_every_table_cell_has_its_phone_label(admin_client, app):
    _two_months(app)
    body = _page(admin_client)
    main = body[body.index('id="expenseMainTable"'):].split('</table>', 1)[0]
    assert 'ex-stack ex-tbl-main' in body
    row = main.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Paid by', 'Receipt No', 'Description', 'Entered by'):
        assert 'data-label="%s"' % label in row, label
    categories = body[body.index('ex-stack ex-tbl-cat'):].split('</table>', 1)[0]
    for label in ('Description', 'Entries', 'Total (Rs.)', 'Status', 'Actions'):
        assert 'data-label="%s"' % label in categories, label
    cont = body[body.index('ex-stack ex-tbl-cont'):].split('</table>', 1)[0]
    for label in ('Method', 'Description'):
        assert 'data-label="%s"' % label in cont, label
    assert 'PhoneLastMonth' in cont


def test_new_phone_labels_are_translated_to_urdu(admin_client, app):
    _two_months(app)
    html = i18n.translate_html(_page(admin_client))
    for english in ('data-label="Paid by"', 'data-label="Receipt No"', 'data-label="Entered by"',
                    'data-label="Entries"', 'data-label="Total (Rs.)"'):
        assert english not in html, english


def test_nothing_was_removed_from_the_page(admin_client, app):
    _two_months(app)
    body = _page(admin_client)
    for needle in ('Expense Tracker', 'Add Expense', 'Continue Previous Month', 'Categories', 'Export',
                   'Excel / CSV file', 'Excel workbook (.xlsx)', 'PDF to print', 'id="exSearch"', 'id="exCat"',
                   'Apply', 'Choose exact dates', 'name="date_from"', 'name="date_to"', 'This Month', 'All History',
                   'Previous', 'Next', 'Total spent', 'Average per expense', 'data-ex-view="cards"',
                   'data-ex-view="table"', 'id="expenseMainTable"', 'continue-expense-btn', 'ex-edit-btn',
                   'void-expense-form', 'id="addExpenseModal"', 'id="editExpenseModal"', 'id="categoriesModal"',
                   'id="continueExpenseModal"', 'id="editCategoryModal"', 'id="voidExpenseModal"',
                   'Save Expense', 'Add Category', 'Void expense', 'ex-form'):
        assert needle in body, needle
    for name in ('category_id', 'amount', 'description', 'date', 'payment_method', 'receipt_no', 'continue_from'):
        assert 'name="%s"' % name in body, name

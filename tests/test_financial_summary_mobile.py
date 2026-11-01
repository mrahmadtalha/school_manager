# -*- coding: utf-8 -*-
"""Financial Overview (/financials/summary) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid, the month bar
is stacked (month name on top, Previous / Next side by side, month box full width), the
headline and the three big numbers are tighter, the figure boxes are two per line, alerts
and buttons are full width, the small tables (period comparisons, payroll) are cards with a
label on every line, and the wide side-by-side table keeps the metric name in view while you
swipe. These tests check the pieces that layout needs and that nothing went missing."""

from datetime import date

from app.database import db
from app.models import StaffPayroll
from app.services import i18n, payroll_service
from tests.test_payroll_redesign import _teacher

MONTH = '2026-10'


def _page(admin_client, query=None):
    response = admin_client.get('/financials/summary?' + (query or 'month=' + MONTH))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.fo-monthbar' in block][0]


def _phone(css):
    return css.split('/* phones: month bar', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _with_a_salary(app):
    with app.app_context():
        teacher = _teacher('FM1', 'Overview Phone Teacher', 25000.0)
        payroll_service.generate(MONTH, {'include_%d' % teacher.id: 'on'}, generated_by='tester')
        db.session.commit()


def test_header_uses_the_shared_phone_helpers(admin_client, app):
    body = _page(admin_client)
    header = body[body.index('dashboard-header'):body.index('<style>', body.index('dashboard-header'))]
    assert 'm-head' in header and 'm-actions' in header
    assert 'Export' in header and 'financials/summary/export.csv' in header


def test_month_bar_headline_and_panels_fit_the_phone(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.fo-monthbar .fo-now { display: grid; grid-template-columns: 1fr 1fr;',
                   '.fo-monthbar .fo-month { grid-column: 1 / -1; order: -1;',            # month name on top
                   '.fo-monthbar .fo-now .btn { width: 100%; min-height: 2.6rem;',        # Previous / Next side by side
                   '.fo-monthbar form .form-control { flex: 1 1 100%; width: 100%; height: 2.7rem; }',
                   '.fo-monthbar form .btn { flex: 1; min-height: 2.6rem;',
                   '.fo-verdict { padding: 0.85rem 1rem;',
                   '.fo-tile .fo-num { font-size: 1.5rem; overflow-wrap: anywhere; }',
                   '.fo-mini { display: grid; grid-template-columns: 1fr 1fr;',
                   '.fo-owe .fo-num, .fo-shop .fo-num { overflow-wrap: anywhere; }',
                   '.fo-alert .fo-alert-text { flex: 1 1 100%; }',
                   '.fo-alert .btn { width: 100%; min-height: 2.5rem; }',
                   '.fo-former .btn { width: 100%; min-height: 2.5rem;',
                   '.fo-pills .btn { min-height: 2.4rem;',
                   '.fo-chart { height: 240px; }'):
        assert needle in phone, needle


def test_boxes_do_not_zoom_the_page_on_iphones(admin_client, app):
    css = _css(_page(admin_client))
    small = css.split('@media (max-width: 575.98px) {', 1)[1]
    assert '.fo-monthbar .form-control, .fo-page .fo-panel-body .form-control { font-size: 16px; }' in small


def test_period_comparison_tables_become_cards(admin_client, app):
    body = _page(admin_client)
    assert 'table table-sm align-middle mb-0 m-cards' in body
    table = body[body.index('table table-sm align-middle mb-0 m-cards'):].split('</table>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    assert row.count('data-label=') == 3 and 'data-label="Change"' in row


def test_payroll_table_becomes_cards_with_a_label_on_every_line(admin_client, app):
    _with_a_salary(app)
    body = _page(admin_client)
    assert 'Overview Phone Teacher' in body
    start = body.index('Payroll — ')
    table = body[start:].split('</table>', 1)[0]
    assert 'm-cards' in table
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Net Salary (Rs.)', 'Status', 'Payment Date', 'Payslip'):
        assert 'data-label="%s"' % label in row, label
    assert 'm-tap' in row                                                             # finger-sized payslip button


def test_side_by_side_table_keeps_the_metric_name_in_view(admin_client, app):
    body = _page(admin_client, 'month=%s&preset=last_3' % MONTH)
    assert 'id="comparisonTable"' in body
    phone = _phone(_css(body))
    for needle in ('#comparisonTable th:first-child, #comparisonTable td:first-child { position: sticky; inset-inline-start: 0;',
                   '#comparisonTable tr.table-light > td:first-child { background: #f8f9fa; }',
                   '.fo-mtbl th, .fo-mtbl td { padding: 0.3rem 0.35rem;'):
        assert needle in phone, needle


def test_compare_forms_are_phone_friendly(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.fo-page .fo-panel-body .form-control { min-height: 2.7rem; }',
                   '.fo-page .fo-panel-body .btn-primary.btn-sm, .fo-page .fo-panel-body .btn-dark.btn-sm { min-height: 2.7rem; }',
                   '.fo-page .form-check-input { width: 1.2rem; height: 1.2rem; }'):
        assert needle in phone, needle


def test_phone_rules_are_only_inside_media_queries(admin_client, app):
    """The computer layout must not change: the new rules start after the old small-screen rules."""
    css = _css(_page(admin_client)).replace('\r\n', '\n')
    before, after = css.split('/* phones: month bar', 1)
    assert after.lstrip().split('\n', 1)[1].lstrip().startswith('@media (max-width: 767.98px) {')
    assert '.fo-page' not in before and '#comparisonTable' not in before


def test_new_phone_labels_are_translated_to_urdu(admin_client, app):
    _with_a_salary(app)
    html = i18n.translate_html(_page(admin_client))
    for english in ('data-label="Net Salary (Rs.)"', 'data-label="Payment Date"', 'data-label="Change"'):
        assert english not in html, english


def test_page_keeps_its_everyday_words_and_has_no_native_dialogs(admin_client, app):
    body = _page(admin_client)
    page = body[body.index('dashboard-header'):].lower()
    for jargon in ('salary burden', 'recommendations', 'pending payers', 'percentage points', 'cash basis'):
        assert jargon not in page, jargon
    assert 'confirm(' not in page and 'alert(' not in page


def test_nothing_was_removed_from_the_page(admin_client, app):
    _with_a_salary(app)
    body = _page(admin_client)
    for needle in ('Financial Overview', 'Export', 'Previous month', 'Next month', 'name="month"', 'Show month', 'This month',
                   'What to do now', 'Cash In', 'Cash Out', 'Net Position', 'What do CASH and ACCRUAL mean?',
                   'Where the money came from', 'Where the money went', 'Total received', 'Total paid out',
                   'Fees Remaining', 'Salary Remaining', 'Salaries —', 'What changed', 'class="fo-more"',
                   'Compare periods', 'Compare selected', 'name="periods"', 'Custom range vs preceding period',
                   'name="range_start"', 'name="range_end"', 'id="cashInOutChart"', 'id="collectionChart"',
                   'id="outstandingChart"', 'id="categoryChart"', 'Expense Breakdown', 'Payroll — ', 'Payslip PDF',
                   'summaryChartsPayload'):
        assert needle in body, needle

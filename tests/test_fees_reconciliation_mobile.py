# -*- coding: utf-8 -*-
"""Fee Reconciliation (/fees/reconciliation) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid, the month box
and Apply button fit the screen, the four summary boxes are two lines of two, the repair
button is full width, and every student-month is one card (with a label on every line, a red
edge when it does not match) instead of a wide table. These tests check the pieces that
layout needs and that no button, filter or figure went missing."""

import re
from pathlib import Path

from app.services import i18n
from app.services.fee_ledger import current_month


def _page(admin_client, app, seed, with_rows=True):
    month = current_month()
    if with_rows:
        admin_client.post('/fees/generate-charges',
                          data={'month_year': month, 'class_id': str(seed['class_id'])})
    response = admin_client.get('/fees/reconciliation?month_year=' + month.replace(' ', '+'))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.fr-repair' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def test_shared_phone_helpers_exist_in_the_style_sheet():
    css = (Path(__file__).resolve().parent.parent / 'app' / 'static' / 'style.css').read_text(encoding='utf-8')
    for helper in ('.m-head', '.m-actions', '.m-tap', '.m-cards'):
        assert helper in css, helper


def test_header_uses_the_shared_phone_helpers(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    assert 'pb-3 mb-4 m-head' in body
    assert 'btn-toolbar mb-2 mb-md-0 gap-2 m-actions' in body
    assert 'Fee reminders' in body and 'Back to fees' in body


def test_filter_summary_and_repair_fit_the_phone(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    css = _css(body)
    phone = _phone(css)
    assert 'fr-filter' in body
    assert body.count('<div class="col-6 col-md-3">') == 4                      # two summary boxes per line
    for needle in ('.fr-filter .form-select { min-height: 2.7rem; }',
                   '.fr-filter .btn { min-height: 2.7rem; }',
                   '.fr-page .fr-stat .h4 { font-size: 1.3rem;',
                   '.fr-repair { width: 100%; }',
                   '.fr-repair .btn { width: 100%; min-height: 2.7rem; }',
                   '.fr-page .alert code { overflow-wrap: anywhere;'):
        assert needle in phone, needle
    assert '.fr-filter .form-select { font-size: 16px; }' in css.split('@media (max-width: 575.98px) {', 1)[1]


def test_rows_become_cards_with_a_label_on_every_line(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    assert 'm-cards' in body
    table = body[body.index('m-cards'):].split('</table>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Class', 'Month', 'Charged', 'Paid', 'Balance', 'Stored due', 'Stored paid', 'Check', 'Ledger'):
        assert 'data-label="%s"' % label in row, label
    assert 'fr-student' in row
    assert 'm-tap' in row                                                       # finger-sized ledger button


def test_totals_line_is_a_card_with_labels(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    foot = body[body.index('<tfoot'):].split('</tfoot>', 1)[0]
    for label in ('Charged', 'Paid', 'Balance'):
        assert 'data-label="%s"' % label in foot, label
    assert 'Totals' in foot
    phone = _phone(_css(body))
    assert '.fr-page .m-cards tfoot td[data-label]::before { content: attr(data-label);' in phone


def test_a_mismatch_still_shows_in_red_on_a_phone(admin_client, app, seed):
    phone = _phone(_css(_page(admin_client, app, seed)))
    assert '.fr-page .m-cards tbody tr.table-danger { border-color: #fca5a5; border-left: 5px solid #dc2626; background: #fef2f2 !important; }' in phone


def test_phone_rules_are_only_inside_media_queries(admin_client, app, seed):
    css = _css(_page(admin_client, app, seed))
    outside = css.split('@media (max-width: 767.98px) {', 1)[0]
    assert outside.strip().startswith('/*') and '{' not in outside.split('*/', 1)[1]


def test_new_phone_labels_are_translated_to_urdu(admin_client, app, seed):
    html = i18n.translate_html(_page(admin_client, app, seed))
    for english in ('data-label="Class"', 'data-label="Month"', 'data-label="Charged"', 'data-label="Stored due"',
                    'data-label="Stored paid"', 'data-label="Check"', 'data-label="Ledger"'):
        assert english not in html, english


def test_empty_page_still_shows_its_message(admin_client, app, seed):
    body = admin_client.get('/fees/reconciliation?month_year=January+2031').get_data(as_text=True)
    assert 'No fee transactions recorded yet.' in body
    assert '<tfoot' not in body


def test_nothing_was_removed_from_the_page(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    for needle in ('Fee Reconciliation', 'Fee reminders', 'Back to fees', 'name="month_year"', 'All months',
                   'Apply', 'Total charged (PKR)', 'Total received (PKR)', 'Outstanding (PKR)', 'Student-month rows',
                   'Ledger and summary agree', 'Unapplied payments', 'Repair unapplied payments',
                   'Student', 'Class', 'Month', 'Charged', 'Paid', 'Balance', 'Stored due', 'Stored paid', 'Check',
                   'Ledger', 'Totals', 'badge bg-success'):
        assert needle in body, needle
    assert re.search(r'action="[^"]*fees/repair', body) or 'repair' in body.lower()

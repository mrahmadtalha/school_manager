# -*- coding: utf-8 -*-
"""Student Fee Ledger (/fees/student/<id>) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid, the summary is
two boxes per line, and every ledger entry is one card (type and amount on top, a label on
every line, Refund / Void as big buttons) instead of a wide table. These tests check the
pieces that layout needs and that no figure, button or window went missing."""

from app.models import StudentModel
from app.services import i18n
from app.services.fee_ledger import current_month


def _page(admin_client, app, seed, with_rows=True):
    month = current_month()
    if with_rows:
        admin_client.post('/fees/generate-charges',
                          data={'month_year': month, 'class_id': str(seed['class_id'])})
    with app.app_context():
        student_id = StudentModel.query.filter_by(class_id=seed['class_id']).first().id
    response = admin_client.get('/fees/student/%d' % student_id)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.fl-stack' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def test_header_uses_the_shared_phone_helpers(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    assert 'pb-3 mb-4 m-head' in body
    assert 'btn-toolbar mb-2 mb-md-0 gap-2 m-actions' in body
    assert 'Back to fees' in body and 'Fee Ledger' in body


def test_summary_is_two_boxes_per_line(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    phone = _phone(_css(body))
    assert body.count('fl-stat') >= 4
    assert 'col-6 col-md-3' in body and 'col-6 col-md-2 fl-out' in body
    for needle in ('.fl-page .fl-stat .h4, .fl-page .fl-stat .h5 { font-size: 1.3rem;',
                   '.fl-wo:not(:has(.h5)) { display: none; }',                        # empty written-off box is hidden
                   '.fl-wo:not(:has(.h5)) + .fl-out { flex: 0 0 100%; max-width: 100%; }',
                   '.fl-month-head { flex-direction: column;'):
        assert needle in phone, needle


def test_entries_become_cards_with_a_label_on_every_line(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    phone = _phone(_css(body))
    assert 'table table-sm mb-0 fl-stack' in body
    table = body[body.index('fl-stack'):].split('</table>', 1)[0]
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('When', 'Type', 'Amount', 'Method', 'Reference', 'Recorded by', 'Note'):
        assert 'data-label="%s"' % label in row, label
    for css_class in ('fl-id', 'fl-when', 'fl-type', 'fl-amount', 'fl-method', 'fl-ref', 'fl-by', 'fl-note', 'fl-act'):
        assert css_class in row, css_class
    for needle in ('.fl-stack, .fl-stack tbody { display: block; width: 100% !important; }',
                   '.fl-stack thead { display: none; }',
                   '.fl-stack td[data-label]::before { content: attr(data-label);',
                   '.fl-stack td.fl-id::before { content: "#"; }',
                   '.fl-stack td.fl-act:empty { display: none; }',
                   'html[dir="rtl"] .fl-stack td { text-align: right !important; }'):
        assert needle in phone, needle


def test_refund_and_void_buttons_are_big_enough_to_tap(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    phone = _phone(_css(body))
    assert '.fl-page .fl-act .btn.p-0 { padding: 0.4rem 0.9rem !important; min-height: 2.6rem;' in phone


def test_windows_fit_the_phone(admin_client, app, seed):
    css = _css(_page(admin_client, app, seed))
    phone = _phone(css)
    for needle in ('.fl-page .modal .modal-footer .btn { flex: 1 1 0; min-height: 2.7rem; }',
                   '.fl-page .modal .form-control-sm { min-height: 2.8rem; }'):
        assert needle in phone, needle
    assert '.fl-page .modal .form-control-sm { font-size: 16px; }' in css.split('@media (max-width: 575.98px) {', 1)[1]


def test_phone_rules_are_only_inside_media_queries(admin_client, app, seed):
    css = _css(_page(admin_client, app, seed))
    outside = css.split('@media (max-width: 767.98px) {', 1)[0]
    assert outside.strip().startswith('/*') and '{' not in outside.split('*/', 1)[1]


def test_new_phone_labels_are_translated_to_urdu(admin_client, app, seed):
    html = i18n.translate_html(_page(admin_client, app, seed))
    for english in ('data-label="When"', 'data-label="Type"', 'data-label="Amount"', 'data-label="Method"',
                    'data-label="Reference"', 'data-label="Recorded by"', 'data-label="Note"'):
        assert english not in html, english


def test_nothing_was_removed_from_the_page(admin_client, app, seed):
    body = _page(admin_client, app, seed)
    for needle in ('Fee Ledger', 'Back to fees', 'Total charged (PKR)', 'Total paid (PKR)', 'Outstanding (PKR)',
                   'charged', 'balance', 'void-txn-btn', 'id="voidTxnForm"', 'id="refundForm"',
                   'name="void_reason"', 'name="reason"', 'name="amount"', 'window.prompt',
                   'Append-only history'):
        assert needle in body, needle
    assert 'Refund' in body or 'Void' in body

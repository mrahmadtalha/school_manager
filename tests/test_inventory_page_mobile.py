# -*- coding: utf-8 -*-
"""Inventory & Sales (/inventory) on phones.

Same HTML for every screen size. On a phone the header button is full width, the four
summary numbers are two lines of two, every table (items, sales, purchases, supplier dues,
sets, canteen, student stock, setup) is a list of cards with a label on every line, the
buttons in a card (Undo, Pay, Buy, Sell, Void ...) are full-size tap targets, and the popup
windows fit the screen. These tests check the pieces that layout needs and that no figure,
form, tab, button or window went missing."""

from datetime import date

from app.services import i18n

TABLE_HEADERS = {
    'ivProducts': ('Selling price', 'Cost', 'In stock'),
    'hSales': ('Product', 'Qty', 'Sales', 'Cost', 'Profit'),
    'hPurchases': ('Product / supplier', 'Qty', 'Bill', 'Paid', 'Owed'),
}


def _stock(admin_client):
    """One item, bought on credit (so Supplier dues shows) and sold twice."""
    admin_client.post('/inventory/products/add', data={
        'name': 'Phone Test Shirt', 'category': 'Uniform', 'sale_price': '1200', 'min_stock': '5'},
        follow_redirects=True)
    page = admin_client.get('/inventory').get_data(as_text=True)
    product_id = page.split('name="product_id"', 1)[1].split('value="', 1)[1].split('"', 1)[0]
    admin_client.post('/inventory/purchase', data={
        'product_id': product_id, 'quantity': '20', 'unit_cost': '1000',
        'purchase_date': date.today().strftime('%Y-%m-%d'), 'supplier': 'Ali Traders',
        'paid_now': '12000'}, follow_redirects=True)
    admin_client.post('/inventory/sell', data={
        'product_id': product_id, 'quantity': '2',
        'sale_date': date.today().strftime('%Y-%m-%d')}, follow_redirects=True)


def _page(admin_client, seed):
    _stock(admin_client)
    response = admin_client.get('/inventory')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _table(body, anchor):
    """(opening tag, whole table) of the table that holds, or follows, the anchor text."""
    idx = body.index(anchor)
    start = body.rfind('<table', 0, idx)
    if start == -1 or body.find('</table>', start, idx) != -1:
        start = body.index('<table', idx)
    end = body.index('</table>', start)
    table = body[start:end]
    return table.split('>', 1)[0], table


def _css(body):
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.iv-band' in block][0]


def _phone(css):
    return css.split('/* phones: tables become cards', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1]


def test_existing_page_markers_are_untouched(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert 'class="iv-page"' in body and 'class="iv-head"' in body and 'class="iv-band"' in body


def test_header_and_summary_fit_the_phone(admin_client, app, seed):
    css = _css(_page(admin_client, seed))
    phone, small = _phone(css), _small(css)
    for needle in ('.iv-head > div { flex: 1 1 100%; }',
                   '.iv-head .btn { width: 100%; min-height: 2.6rem;',
                   '.iv-num { font-size: 1.3rem; overflow-wrap: anywhere; }',
                   '.iv-stat { padding: 0.7rem 0.9rem; }'):
        assert needle in phone, needle
    # the four numbers are no longer one tall stack on a phone
    assert '.iv-band { grid-template-columns: 1fr; }' not in css
    assert '.iv-band { grid-template-columns: 1fr 1fr; }' in css
    assert '.iv-stat + .iv-stat { border-left: 0; border-top: 1px solid #eef2f7; }' not in small


def test_tabs_buttons_and_boxes_are_easy_to_tap(admin_client, app, seed):
    css = _css(_page(admin_client, seed))
    phone, small = _phone(css), _small(css)
    for needle in ('.iv-page .su-act { min-height: 2.8rem; }',
                   '.iv-page ul.su-tabs .nav-link { min-height: 2.5rem;',
                   '.iv-page .form-control-sm, .iv-page .form-select-sm { min-height: 2.6rem; }',
                   '.iv-page .btn-sm { min-height: 2.4rem; }',
                   '.iv-search { max-width: none; }'):
        assert needle in phone, needle
    assert '.iv-page .form-control, .iv-page .form-select { font-size: 16px; }' in small


def test_every_table_is_a_list_of_cards(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert body.count('m-cards') >= 12 + 1                                          # 12 tables + the style rules
    phone = _phone(_css(body))
    for needle in ('.iv-page .table-responsive { overflow: visible; }',
                   '.iv-page .m-cards tbody td { white-space: normal !important; }',
                   '.iv-page .m-cards tbody td[data-iv-act] { display: flex; flex-wrap: wrap;',
                   '.iv-page .m-cards tbody td[data-iv-act]:not(:has(.btn, form, span)) { display: none; }',
                   '.iv-page .m-cards tbody td[data-iv-act] .btn { flex: 1 1 auto; min-height: 2.5rem;',
                   '.iv-page .m-cards tbody td[data-iv-act] form .form-control { flex: 1; width: auto !important; max-width: none !important; }'):
        assert needle in phone, needle


def test_each_table_row_has_a_label_on_every_line(admin_client, app, seed):
    body = _page(admin_client, seed)
    for anchor, labels in TABLE_HEADERS.items():
        opening, table = _table(body, 'id="%s"' % anchor)
        assert 'm-cards' in opening, anchor
        row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
        for label in labels:
            assert 'data-label="%s"' % label in row, (anchor, label)
        assert 'data-iv-act' in row, anchor


def test_history_card_keeps_its_ten_row_limit_and_the_search(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert 'iv-collapsed' in body
    assert 'id="ivSearch"' in body and 'data-iv-name=' in body                     # the search still hides rows by name


def test_supplier_dues_card_and_pay_buttons(admin_client, app, seed):
    body = _page(admin_client, seed)
    assert 'Supplier dues' in body and 'Pay supplier' in body and 'pay-supplier-btn' in body
    opening, table = _table(body, 'id="supplierDues"')
    assert 'm-cards' in opening
    row = table.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Unpaid bills', 'Total bought', 'Paid so far', 'Still owed'):
        assert 'data-label="%s"' % label in row, label


def test_windows_fit_the_phone(admin_client, app, seed):
    css = _css(_page(admin_client, seed))
    phone, small = _phone(css), _small(css)
    for needle in ('.iv-page .modal .modal-footer .btn { flex: 1 1 0; min-height: 2.7rem; }',
                   '.iv-page .modal .form-control, .iv-page .modal .form-select { min-height: 2.8rem; }',
                   '#setRows > div { flex-wrap: wrap; }',
                   '#setRows input { flex: 1; max-width: none !important; }'):
        assert needle in phone, needle
    assert '.iv-page .modal .row > .col-4, .iv-page .modal .row > .col-5, .iv-page .modal .row > .col-7 { flex: 0 0 100%; max-width: 100%; }' in small


def test_phone_rules_come_after_the_computer_rules(admin_client, app, seed):
    """The computer layout must not change: every new rule sits inside a max-width query."""
    css = _css(_page(admin_client, seed))
    before, after = css.split('/* phones: tables become cards', 1)
    assert '@media (max-width: 767.98px) {' in after.split('*/', 1)[1][:80]
    assert 'data-iv-act' not in before and '#setRows' not in before


def test_new_phone_labels_are_translated_to_urdu(admin_client, app, seed):
    html = i18n.translate_html(_page(admin_client, seed))
    for english in ('data-label="Selling price"', 'data-label="In stock"', 'data-label="Profit"',
                    'data-label="Still owed"', 'data-label="Paid so far"', 'data-label="Product / supplier"'):
        assert english not in html, english


def test_nothing_was_removed_from_the_page(admin_client, app, seed):
    body = _page(admin_client, seed)
    for needle in ('Inventory &amp; Sales', 'Financial Overview', 'Items you sell', 'Value of stock on the shelf',
                   'data-pane="recordSale"', 'data-pane="recordPurchase"', 'data-pane="addProduct"',
                   'id="secTabs"', 'data-sec-tab="items"', 'data-sec-tab="setup"', 'data-sec-tab="canteen"',
                   'data-sec-tab="sets"', 'data-sec-tab="stock"', 'Setup checklist', 'id="canteen"', 'id="sets"',
                   'id="studentStock"', 'id="supplierDues"', 'id="ivSellForm"', 'id="purchaseForm"',
                   'id="ivSellTotal"', 'name="quantity"', 'name="sale_date"', 'name="in_admission"',
                   'id="ivHistory"', 'id="hSales"', 'id="hPurchases"', 'id="ivProducts"', 'id="ivSearch"',
                   'id="openingModal"', 'id="setModal"', 'id="setBuyModal"', 'id="setSellModal"',
                   'id="paySupplierModal"', 'id="payBillModal"', 'id="undoModal"', 'Undo', 'Stop selling'):
        assert needle in body, needle

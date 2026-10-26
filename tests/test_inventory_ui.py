"""Inventory page redesign: summary band, plain wording, search, no browser confirm()."""


def _body(admin_client):
    resp = admin_client.get('/inventory')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_inventory_uses_the_teacher_page_look(admin_client, app, seed):
    body = _body(admin_client)
    assert 'class="iv-page"' in body
    assert 'class="iv-head"' in body
    assert 'class="iv-band"' in body


def test_summary_band_shows_the_four_numbers(admin_client, app, seed):
    body = _body(admin_client)
    assert 'Items you sell' in body
    assert 'Value of stock on the shelf' in body
    assert ('Nothing running low' in body) or ('Running low' in body)
    assert ('You owe suppliers' in body)


def test_everyday_buttons_and_tabs_still_work(admin_client, app, seed):
    body = _body(admin_client)
    for pane in ('recordSale', 'recordPurchase', 'addProduct'):
        assert f'data-pane="{pane}"' in body
    for key in ('items', 'setup', 'canteen', 'sets', 'stock'):
        assert f'data-sec-tab="{key}"' in body


def test_items_list_has_search_and_plain_words(admin_client, app, seed):
    body = _body(admin_client)
    assert 'id="ivSearch"' in body
    assert 'id="ivProducts"' in body
    assert '>Retire<' not in body and '>Restore<' not in body.split('id="ivProducts"')[1][:6000]


def test_inventory_has_no_native_confirm(admin_client, app, seed):
    body = _body(admin_client)
    assert 'return confirm(' not in body


def test_history_is_one_tabbed_card_not_three_long_tables(admin_client, app, seed):
    body = _body(admin_client)
    assert 'id="ivHistory"' in body
    assert 'id="hSales"' in body and 'id="hPurchases"' in body
    assert 'col-lg-5' not in body                   # no cramped side-by-side columns
    assert 'Recent sales' not in body and 'Recent purchases' not in body


def test_stopped_items_are_hidden_behind_a_switch(admin_client, app, seed):
    body = _body(admin_client)
    # either nothing is stopped (no switch) or the switch is offered
    if 'data-iv-status="retired"' in body:
        assert 'id="ivShowStopped"' in body


def test_sell_form_is_step_by_step_with_a_live_total(admin_client, app, seed):
    body = _body(admin_client)
    for text in ('1. What are you selling?', '2. How many?', 'You will receive',
                 'id="ivSellTotal"', 'name="quantity"', 'name="sale_date"',
                 'name="student"', 'name="in_admission"'):
        assert text in body, text


def test_buy_and_new_item_forms_are_step_by_step(admin_client, app, seed):
    body = _body(admin_client)
    for text in ('1. What did you buy?', 'Price of one (Rs.)', 'Who did you buy from?',
                 'How much did you pay now?', 'id="purchaseSummary"', 'id="sumTotal"',
                 'name="unit_cost"', 'name="paid_now"', 'name="purchase_date"',
                 'Add a new item', 'Item name', 'name="sale_price"', 'name="min_stock"'):
        assert text in body, text


def test_setup_canteen_and_sets_use_plain_words(admin_client, app, seed):
    body = _body(admin_client)
    assert 'Setup checklist' in body
    assert 'class="iv-step' in body
    assert 'Count what is on your shelf today' in body
    assert 'Choose books and uniform for each class' in body
    assert 'Stop using' in body or 'Use again' in body or 'No sets yet' in body
    assert 'Add product' not in body and 'Record purchase' not in body and 'Record sale' not in body


def test_student_stock_and_dues_use_plain_words(admin_client, app, seed):
    body = _body(admin_client)
    assert 'Student stock' in body
    assert 'Given lately' in body
    assert 'Record sale' not in body and 'Recent issues' not in body

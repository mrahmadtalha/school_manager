"""Financial Overview redesign: a plain-language money page for non-technical
owners (headline sentence, three big numbers, where the money came from / went,
shop panel, month buttons).  The figures themselves are covered by the phase 2a,
2b and 3 tests; here we check what the owner reads and taps."""

from datetime import date

from app.database import db
from app.models import Expense, ExpenseCategory, OtherIncomeCategory
from app.services import other_income_service


def _get(client, month):
    return client.get('/financials/summary?month=%s' % month).get_data(as_text=True)


def _income(amount, when):
    other_income_service.seed_default_categories()
    canteen = OtherIncomeCategory.query.filter_by(name='Canteen').one()
    other_income_service.record_income(canteen, amount, when)
    db.session.commit()


def _expense(amount, when):
    category = ExpenseCategory.query.filter_by(name='Redesign Overview').first()
    if category is None:
        category = ExpenseCategory(name='Redesign Overview')
        db.session.add(category)
        db.session.flush()
    db.session.add(Expense(category_id=category.id, amount=amount, payment_method='Cash',
                           date=when, logged_by_name='tester'))
    db.session.commit()


def test_page_starts_with_a_hint_and_the_three_big_numbers(admin_client, app):
    body = _get(admin_client, '2026-10')
    assert 'What to do now:' in body
    assert 'alert alert-info' in body and 'no-print' in body        # same pattern as Students
    for label in ('Cash In', 'Cash Out', 'Net Position'):
        assert label in body, label
    # the plain-language key to the two tags used on every card
    assert 'What do CASH and ACCRUAL mean?' in body


def test_empty_month_says_so_in_plain_words(admin_client, app):
    body = _get(admin_client, '2020-01')
    assert 'Nothing has been recorded for January 2020 yet.' in body
    assert 'kept Rs' not in body and 'more than it received' not in body


def test_profit_month_headline(admin_client, app):
    with app.app_context():
        _income(750.25, date(2026, 10, 22))
    body = _get(admin_client, '2026-10')
    assert 'In October 2026 the school kept Rs 750 after paying its bills.' in body
    assert 'More money came in than went out.' in body
    assert 'Rs. 750.25' in body                                      # the exact figure is still shown


def test_short_month_headline(admin_client, app):
    with app.app_context():
        _expense(400.0, date(2026, 9, 10))
    body = _get(admin_client, '2026-09')
    assert 'In September 2026 the school paid out Rs 400 more than it received.' in body
    assert 'Rs. -400.00' in body                                     # Net Position stays exact


def test_money_in_and_out_lists_match_the_big_numbers(admin_client, app):
    with app.app_context():
        _income(1000.0, date(2026, 10, 3))
        _expense(300.0, date(2026, 10, 4))
    body = _get(admin_client, '2026-10')
    assert 'Where the money came from' in body and 'Where the money went' in body
    assert 'Total received' in body and 'Total paid out' in body
    # 'Total received' repeats Cash In, 'Total paid out' repeats Cash Out
    received = body[body.index('Total received'):][:200]
    paid_out = body[body.index('Total paid out'):][:200]
    assert 'Rs. 1,000.00' in received
    assert 'Rs. 300.00' in paid_out


def test_month_buttons_use_words_and_keep_the_month(admin_client, app):
    body = _get(admin_client, '2026-10')
    assert 'Previous month' in body and 'Next month' in body
    assert 'month=2026-09' in body and 'month=2026-11' in body
    assert 'Show month' in body and 'This month' in body
    assert 'fo-month">October 2026<' in body


def test_alerts_come_before_the_detail_panels(admin_client, app):
    """What needs attention is read before the long detail sections."""
    with app.app_context():
        _income(500.0, date(2026, 10, 3))
    body = _get(admin_client, '2026-10')
    if '<h2><i class="fas fa-bell"></i>Alerts</h2>' in body:       # shown only when there is an alert
        assert body.index('fa-bell') < body.index('Where the money came from')
    assert body.index('What changed') > body.index('Where the money came from')


def test_shop_panel_is_hidden_when_switched_off_or_empty(admin_client, app):
    # nothing sold or bought yet: no empty shop panel
    assert 'Shop and stock' not in _get(admin_client, '2026-10')
    with app.app_context():
        app.config['FEATURE_INVENTORY_SALES'] = False
    try:
        body = _get(admin_client, '2026-10')
        assert 'Estimated Net Operating Position' not in body
        assert 'Shop sales' not in body
    finally:
        with app.app_context():
            app.config['FEATURE_INVENTORY_SALES'] = True


def test_compare_section_is_folded_until_asked(admin_client, app):
    body = _get(admin_client, '2026-10')
    assert 'Compare with other months or years' in body
    assert 'class="fo-more" >' in body or 'class="fo-more" open' not in body
    opened = admin_client.get('/financials/summary?preset=last_3').get_data(as_text=True)
    assert 'class="fo-more" open' in opened


def test_export_stays_in_the_header_and_uses_the_one_verb(admin_client, app):
    body = _get(admin_client, '2026-10')
    start = body.index('dashboard-header')
    header = body[start:body.index('<style>', start)]
    assert 'Export' in header and 'Download' not in header
    assert 'financials/summary/export.csv' in header and 'financials/summary/export.pdf' in header


def test_page_has_no_native_dialogs_or_external_links(app):
    import os
    path = os.path.join(app.root_path, 'templates', 'financial_summary.html')
    with open(path, encoding='utf-8') as handle:
        content = handle.read()
    assert 'confirm(' not in content and 'alert(' not in content
    assert 'http://' not in content and 'https://' not in content

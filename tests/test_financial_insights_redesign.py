# -*- coding: utf-8 -*-
"""Financial Insights redesign: a plain-language page for non-technical owners
(month bar with words, a short answer, four numbers, a "What to do" list with a
button for every step, simple wording, Urdu).  The figures themselves are
hand-calculated in ``tests/test_phase4_reports.py``; here we check what the owner
reads and taps."""
import os

from app.services import i18n, report_insights
from tests.test_phase4_reports import MONTH, world  # noqa: F401  (fixture used by name)

URL = '/financials/insights?month=%s' % MONTH


def _body(client):
    return client.get(URL).get_data(as_text=True)


def test_page_starts_with_a_hint_and_a_month_bar_with_words(admin_client, app):
    body = _body(admin_client)
    assert 'What to do now:' in body
    assert 'alert alert-info' in body and 'no-print' in body          # same pattern as Students
    assert 'Previous month' in body and 'Next month' in body
    assert 'Show month' in body and 'This month' in body
    assert 'month=2026-09' in body and 'month=2026-11' in body
    assert 'fi-month">October 2026<' in body


def test_back_button_goes_to_the_overview_for_the_same_month(admin_client, app):
    body = _body(admin_client)
    assert 'Back to Financial Overview' in body
    assert '/financials/summary?month=2026-10' in body


def test_month_without_history_says_so_in_plain_words(admin_client, app):
    body = _body(admin_client)
    assert 'fi-hero is-empty' in body
    assert 'Not enough history yet.' in body
    assert 'Insights compare this month with last month.' in body
    assert 'than last month (' not in body            # no change chips against nothing


def test_headline_counts_the_things_to_do(admin_client, app, world):
    body = _body(admin_client)
    assert 'fi-hero is-warn' in body
    assert 'thing(s) need your attention in October 2026.' in body
    assert 'The list below says what to do.' in body


def test_every_step_in_what_to_do_has_a_button(admin_client, app, world):
    body = _body(admin_client)
    assert 'Send reminders' in body and 'href="/fees/reminders"' in body
    assert 'Open expenses' in body and 'href="/expenses"' in body
    assert 'Open Financial Overview' in body
    assert 'href="/financials/summary?month=2026-10"' in body


def test_what_to_do_comes_before_what_changed(admin_client, app, world):
    body = _body(admin_client)
    assert body.index('What to do</h2>') < body.index('What changed since last month</h2>')


def test_change_chips_use_words_not_percentage_points(admin_client, app, world):
    body = _body(admin_client)
    assert 'Lower than last month (71.4%)' in body            # fees paid: 51.4% vs 71.4%
    assert 'Rs 10,800.00 lower than last month (Rs 2,000.00)' in body   # Net Position


def test_recommendation_items_carry_a_page_for_each_step(app, world):
    with app.app_context():
        items = report_insights.recommendation_items(MONTH)
        assert items, 'the world fixture has things to do'
        for item in items:
            assert set(item) == {'text', 'endpoint', 'link_text', 'params'}
            assert item['endpoint'].startswith('main.') and item['link_text']
        # the plain-sentence list is exactly the same steps
        assert report_insights.recommendations(MONTH) == [i['text'] for i in items]
        negative = [i for i in items if i['endpoint'] == 'main.financials_summary']
        assert negative and negative[0]['params'] == {'month': MONTH}


def test_metrics_can_be_passed_in_so_the_page_computes_them_once(app, world):
    with app.app_context():
        metrics = report_insights.period_metrics(MONTH)
        assert (report_insights.insight_lines(MONTH, metrics)
                == report_insights.insight_lines(MONTH))
        assert (report_insights.recommendation_items(MONTH, metrics)
                == report_insights.recommendation_items(MONTH))


def test_page_uses_everyday_words(admin_client, app, world):
    body = _body(admin_client)
    page = body[body.index('dashboard-header'):].lower()
    for jargon in ('collection rate', 'arrears', 'salary burden', 'recommendations',
                   'pending payers', 'percentage points', 'cost of goods sold',
                   'cash basis', 'revenue'):
        assert jargon not in page, jargon


def test_page_has_no_native_dialogs_or_external_links(app):
    path = os.path.join(app.root_path, 'templates', 'financial_insights.html')
    with open(path, encoding='utf-8') as handle:
        content = handle.read()
    assert 'confirm(' not in content and 'alert(' not in content
    assert 'http://' not in content and 'https://' not in content


def test_new_sentences_and_labels_are_translated_to_urdu():
    n = i18n.lookup
    assert n('What to do') == 'کیا کرنا ہے'
    assert n('See who owes') and n('Send reminders') and n('Open expenses')
    assert 'فیس' in n("Only 51.4% of this month's fees are paid. Call the parents who have not paid yet.")
    assert 'پرانا بقایا' in n('Collect old dues: Rs 250.00 from earlier months is still unpaid.')
    assert 'اخراجات' in n('Utilities spending went up 300.0% since last month (Rs 1,500.00 more).')
    assert 'خالص پوزیشن' in n('Net Position is Rs 10,800.00 lower than last month.')
    assert 'خالص پوزیشن' in n('More money went out than came in this month (Net Position is below zero).')
    assert 'اکتوبر' in n('2 thing(s) need your attention in October 2026.')
    assert 'اکتوبر' in n('Everything looks fine for October 2026.')
    assert n('Fee collection is weaker than last month: 51.4% paid now, 71.4% last month.')
    assert n('You received 108.0% more money than last month (Rs 5,200.00 now, Rs 2,500.00 last month).')


def test_insights_page_turns_to_urdu(admin_client, app, world):
    assert admin_client.get('/language/ur').status_code == 302
    html = admin_client.get(URL).get_data(as_text=True)
    assert 'dir="rtl"' in html
    assert 'کیا کرنا ہے' in html                     # What to do
    assert 'یاد دہانی بھیجیں' in html                 # Send reminders

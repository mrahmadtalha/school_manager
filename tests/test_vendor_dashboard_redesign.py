"""The redesigned vendor dashboard: plain-language screens for a non-technical person."""
import re

from vendor_dashboard import issuer
from tests.test_vendor_dashboard import (MACHINE, TODAY, _issue, _new_school, browser, env)  # noqa: F401


def _page(browser, url):
    response = browser.get(url)
    assert response.status_code == 200, url
    return response.get_data(as_text=True)


def _school_with_key(browser, name, expires):
    school_id = _new_school(browser, name)
    response = _issue(browser, school_id, period='custom', custom_expires=expires)
    assert response.status_code == 302
    return school_id


# -- plain sentences ---------------------------------------------------------

def test_status_sentences_are_plain_words():
    assert issuer.status_sentence('none', None) == 'No key has been sent yet'
    assert issuer.status_sentence('active', 0) == 'Ends today'
    assert issuer.status_sentence('soon', 1) == 'Ends tomorrow'
    assert issuer.status_sentence('soon', 12) == 'Ends in 12 days'
    assert 'still works for 4 more days' in issuer.status_sentence('grace', -3, 7)
    assert issuer.status_sentence('grace', -6, 7).endswith('still works for 1 more day')
    assert 'now view-only' in issuer.status_sentence('expired', -20, 7)
    assert issuer.status_sentence('expired', -1, 7).startswith('Ended yesterday')


# -- home --------------------------------------------------------------------

def test_empty_home_welcomes_a_new_vendor(browser):
    home = _page(browser, '/')
    assert 'add your first school' in home and 'Send or renew a key' not in home


def test_home_offers_big_tasks_and_a_renew_button(browser):
    soon = _school_with_key(browser, 'Expiring Soon School', '2026-10-30')
    _school_with_key(browser, 'Healthy School', '2027-10-30')
    waiting = _new_school(browser, 'Brand New School')
    home = _page(browser, '/')
    assert 'Send or renew a key' in home and 'Forgotten password' in home and 'Back up my data' in home
    assert f'/schools/{soon}?do=renew#send-key' in home          # one click to the renewal form
    assert 'Ends in 15 days' in home and 'Healthy School' not in home.split('Waiting for their first key')[0]
    assert 'Waiting for their first key' in home and 'Brand New School' in home and str(waiting) in home


def test_home_says_all_good_when_nothing_is_due(browser):
    _school_with_key(browser, 'Healthy School', '2027-10-30')
    assert 'Every school with a key is up to date' in _page(browser, '/')


def test_sidebar_shows_how_many_schools_need_attention(browser):
    _school_with_key(browser, 'Expiring Soon School', '2026-10-30')
    _school_with_key(browser, 'Healthy School', '2027-10-30')
    page = _page(browser, '/schools')
    assert re.search(r'class="vd-badge"[^>]*>1<', page)
    assert 'aria-current="page"' in page


# -- schools list ------------------------------------------------------------

def test_school_list_filters_by_status_with_counts(browser):
    _school_with_key(browser, 'Expiring Soon School', '2026-10-30')
    _school_with_key(browser, 'Healthy School', '2027-10-30')
    _new_school(browser, 'Brand New School')
    everything = _page(browser, '/schools')
    assert all(n in everything for n in ('Expiring Soon School', 'Healthy School', 'Brand New School'))
    soon = _page(browser, '/schools?status=soon')
    assert 'Expiring Soon School' in soon and 'Healthy School' not in soon and 'Brand New School' not in soon
    none_yet = _page(browser, '/schools?status=none')
    assert 'Brand New School' in none_yet and 'Healthy School' not in none_yet
    assert 'Send first key' in none_yet
    assert 'Healthy School' in _page(browser, '/schools?status=nonsense')      # unknown filter = show all


def test_school_list_empty_and_no_match_states(browser):
    assert 'No schools yet' in _page(browser, '/schools')
    _school_with_key(browser, 'Healthy School', '2027-10-30')
    assert 'Nothing matches' in _page(browser, '/schools?q=zzz')


def test_inactive_schools_get_their_own_filter(browser, env):
    school_id = _school_with_key(browser, 'Old Customer', '2027-10-30')
    browser.post(f'/schools/{school_id}/edit', {'name': 'Old Customer', 'billing': 'yearly'})   # active box unticked
    page = _page(browser, '/schools')
    assert 'Not a customer' in page
    assert 'Old Customer' in _page(browser, '/schools?status=inactive')
    assert 'Old Customer' not in _page(browser, '/schools?status=active')


# -- school page: the guided "Send a key" form --------------------------------

def test_first_key_form_only_offers_a_first_key(browser):
    school_id = _new_school(browser, 'Brand New School')
    page = _page(browser, f'/schools/{school_id}')
    assert re.search(r'value="new" checked', page)
    for reason in ('renew', 'update', 'move'):
        assert re.search(rf'value="{reason}"\s+disabled', page)
    assert 'has no key yet' in page and 'Ends in' not in page.split('Send a key')[0]


def test_renewal_form_shows_the_new_end_date_for_each_choice(browser):
    school_id = _school_with_key(browser, 'Al-Noor School', '2026-11-30')
    page = _page(browser, f'/schools/{school_id}')
    assert re.search(r'value="renew" checked', page) and re.search(r'value="new"\s+disabled', page)
    # renewing from 30 Nov 2026: +1 month ends 31 Dec 2026, +1 year ends 30 Nov 2027
    assert '1 month — ends 31 Dec 2026' in page and '1 year — ends 30 Nov 2027' in page
    assert 'Same end date as now — ends 30 Nov 2026' in page


def test_renew_link_and_change_links_preselect_the_reason(browser):
    school_id = _school_with_key(browser, 'Al-Noor School', '2026-11-30')
    update = _page(browser, f'/schools/{school_id}?do=update')
    assert re.search(r'value="update" checked', update)
    assert '<details class="vd-more" id="featBox" open>' in update            # feature switches already open
    assert re.search(r'<option value="keep" selected>', update)               # end date stays the same
    move = _page(browser, f'/schools/{school_id}?do=move')
    assert re.search(r'value="move" checked', move) and re.search(r'<option value="keep" selected>', move)
    renew = _page(browser, f'/schools/{school_id}?do=renew')
    assert re.search(r'value="renew" checked', renew) and '<option value="1y" selected>' in renew
    assert re.search(r'value="renew" checked', _page(browser, f'/schools/{school_id}?do=hack'))   # unknown = default


def test_monthly_school_defaults_to_a_monthly_renewal(browser):
    school_id = _new_school(browser, 'Monthly School', billing='monthly')
    _issue(browser, school_id, period='custom', custom_expires='2026-11-30')
    assert '<option value="1m" selected>' in _page(browser, f'/schools/{school_id}')


def test_ended_key_cannot_be_kept_as_is(browser):
    school_id = _school_with_key(browser, 'Al-Noor School', '2026-10-16')
    # move the clock past the end date by editing the stored expiry
    # (the dashboard only offers "Same end date" while that date is still ahead)
    store = browser.client.application.extensions['vendor'].store
    with store.conn() as c:
        c.execute("UPDATE licenses SET expires='2026-10-01' WHERE school_id=?", (school_id,))
    page = _page(browser, f'/schools/{school_id}')
    assert 'Same end date as now' not in page and 'Ended 14 days ago' in page


def test_school_page_explains_what_to_do_now(browser):
    soon = _school_with_key(browser, 'Expiring Soon School', '2026-10-30')
    assert 'What to do now' in _page(browser, f'/schools/{soon}') and 'Copy reminder' in _page(browser, f'/schools/{soon}')
    fine = _school_with_key(browser, 'Healthy School', '2027-10-30')
    assert 'Nothing to do until the key ends' in _page(browser, f'/schools/{fine}')


def test_payments_page_text_says_it_does_not_send_a_key(browser):
    school_id = _new_school(browser)
    assert 'does not send a key' in _page(browser, f'/schools/{school_id}')


# -- key page ----------------------------------------------------------------

def test_key_page_leads_with_the_ready_to_send_message(browser):
    school_id = _new_school(browser)
    response = _issue(browser, school_id, features=['expenses', 'attendance'])
    page = _page(browser, response.headers['Location'])
    assert 'Copy message' in page and 'Ready-to-send message' in page
    assert page.index('Ready-to-send message') < page.index('Other ways to send')
    features = page.split('<dt>Features</dt><dd>')[1].split('</dd>')[0]
    assert features == 'Expenses, Attendance'                      # readable names, not codes like "expenses"
    assert page.count('SM1.') == 2                                 # the message and the key-only box


# -- plans -------------------------------------------------------------------

def test_new_plan_only_needs_a_name(browser, env):
    response = browser.post('/plans', {'label': 'Gold Plus', 'features': ['attendance'], 'wa_daily': '10'})
    assert response.status_code == 302
    plans = {p['name']: p for p in env[0].extensions['vendor'].store.plans()}
    assert plans['gold_plus']['label'] == 'Gold Plus' and plans['gold_plus']['features'] == ['attendance']
    assert 'Gold Plus' in _page(browser, '/plans')


def test_plan_without_any_name_is_explained(browser):
    response = browser.post('/plans', {'features': ['attendance']})
    assert response.status_code == 302
    assert 'Give the plan a name' in _page(browser, '/plans')


def test_existing_plan_keeps_its_id_when_renamed(browser, env):
    browser.post('/plans', {'name': 'basic', 'label': 'Starter', 'features': ['attendance']})
    plans = {p['name']: p for p in env[0].extensions['vendor'].store.plans()}
    assert plans['basic']['label'] == 'Starter' and 'starter' not in plans


# -- recovery, settings, unlock ----------------------------------------------

def test_password_help_shows_the_phone_to_call_back(browser):
    from tests.test_vendor_dashboard import _request_code
    school_id = _new_school(browser)
    page = browser.post('/recovery', {'request_code': _request_code(), 'action': 'lookup'}).get_data(as_text=True)
    assert 'Call back on' in page and '0300' in page and 'Issue reset token' in page
    assert 'Make sure it is really them' in page


def test_settings_tells_the_vendor_whether_the_key_is_protected(browser):
    page = _page(browser, '/settings')
    assert 'One thing to do' in page and 'Download backup' in page
    browser.post('/settings/remove-plain-key', {'password': 'correct horse battery'})
    assert 'Your signing key is protected' in _page(browser, '/settings')


def test_unlock_screen_is_friendly_and_has_labels(env):
    from tests.test_vendor_dashboard import Browser
    page = Browser(env[0]).client.get('/unlock').get_data(as_text=True)
    assert 'Let’s set up' in page and 'Write this password down' in page
    assert 'for="pw"' in page and 'id="pw"' in page and 'for="pw2"' in page


# -- every screen -------------------------------------------------------------

def test_no_screen_loads_anything_from_the_internet(browser):
    school_id = _school_with_key(browser, 'Al-Noor School', '2026-11-30')
    for url in ('/', '/schools', '/schools/new', f'/schools/{school_id}', '/plans', '/settings', '/recovery'):
        page = _page(browser, url)
        assert not re.search(r'(?:src|href)="https?://', page), url


def test_every_page_has_the_menu_and_a_lock_button(browser):
    school_id = _new_school(browser)
    for url in ('/', '/schools', '/schools/new', f'/schools/{school_id}', '/plans', '/settings', '/recovery'):
        page = _page(browser, url)
        assert 'Password help' in page and 'Lock dashboard' in page and 'name="_csrf"' in page, url

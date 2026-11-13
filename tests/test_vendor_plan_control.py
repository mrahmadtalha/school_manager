"""Vendor control by plan: size limits and prices on plans and keys, the plan-versus-key comparison,
the 'who has what' matrix and its spreadsheet export."""
import csv
import io
import json
import sqlite3
from datetime import date

import pytest

from app.services import licensing
from tests.test_vendor_dashboard import (MACHINE, PASSWORD, TODAY, Browser, browser, env,  # noqa: F401
                                         _issue, _key_text, _new_school)
from vendor_dashboard import issuer
from vendor_dashboard.core import features as feature_catalog
from vendor_dashboard.core import lic as dash_lic
from vendor_dashboard.store import Store


def _decode(browser, env, response):
    return dash_lic.verify_license_text(_key_text(browser, response), env[1])


def _save_plan(browser, **fields):
    data = {'label': 'Gold', 'features': ['attendance', 'exams', 'whatsapp'], 'wa_daily': '50',
            'wa_monthly': '1000', 'max_students': '500', 'max_staff': '12',
            'price_monthly': '3,000', 'price_yearly': '30000'}
    data.update(fields)
    response = browser.post('/plans', data)
    assert response.status_code == 302
    return response


# ---- keys carry the limits -----------------------------------------------------------------

def test_a_key_carries_the_student_and_staff_limits(browser, env):
    school_id = _new_school(browser)
    payload = _decode(browser, env, _issue(browser, school_id, max_students='300', max_staff='5'))
    assert payload['_limits'] == {'wa_daily': 100, 'wa_monthly': 2000, 'max_students': 300, 'max_staff': 5}


def test_blank_limits_leave_the_key_unlimited(browser, env):
    school_id = _new_school(browser)
    payload = _decode(browser, env, _issue(browser, school_id, max_students='', max_staff='  '))
    assert 'max_students' not in payload['_limits'] and 'max_staff' not in payload['_limits']


def test_zero_is_kept_as_a_real_limit(browser, env):
    school_id = _new_school(browser)
    payload = _decode(browser, env, _issue(browser, school_id, max_students='0'))
    assert payload['_limits']['max_students'] == 0


@pytest.mark.parametrize('field, value, words', [
    ('max_students', 'many', 'student limit must be a whole number'),
    ('max_staff', '2.5', 'staff-login limit must be a whole number'),
    ('max_students', '-3', 'student limit cannot be negative'),
])
def test_a_bad_limit_is_refused_and_no_key_is_made(browser, env, field, value, words):
    school_id = _new_school(browser)
    response = _issue(browser, school_id, **{field: value})
    assert response.status_code == 302 and '/keys/' not in response.headers['Location']
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert words in page
    assert env[0].extensions['vendor'].store.latest_license(school_id) is None


def test_the_limits_are_remembered_in_the_key_history(browser, env):
    school_id = _new_school(browser)
    _issue(browser, school_id, max_students='300', max_staff='5')
    row = env[0].extensions['vendor'].store.latest_license(school_id)
    assert (row['max_students'], row['max_staff']) == (300, 5)
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'students 300' in page and 'staff logins 5' in page


def test_renewal_keeps_the_limits_of_the_last_key(browser, env):
    school_id = _new_school(browser)
    _issue(browser, school_id, max_students='300', max_staff='5')
    page = browser.get(f'/schools/{school_id}?do=renew').data.decode()
    assert 'name="max_students" id="maxStudents" type="number" min="0" value="300"' in page
    assert 'name="max_staff" id="maxStaff" type="number" min="0" value="5"' in page


# ---- plans: limits and prices -----------------------------------------------------------------

def test_a_plan_saves_limits_and_prices(browser, env):
    _save_plan(browser)
    plan = {p['name']: p for p in env[0].extensions['vendor'].store.plans()}['gold']
    assert (plan['max_students'], plan['max_staff']) == (500, 12)
    assert (plan['price_monthly'], plan['price_yearly']) == (3000.0, 30000.0)
    page = browser.get('/plans').data.decode()
    assert 'students 500' in page and 'staff logins 12' in page and '30,000/year' in page


def test_blank_plan_limits_and_prices_mean_not_set(browser, env):
    _save_plan(browser, max_students='', max_staff='', price_monthly='', price_yearly='')
    plan = {p['name']: p for p in env[0].extensions['vendor'].store.plans()}['gold']
    assert plan['max_students'] is None and plan['max_staff'] is None
    assert plan['price_monthly'] is None and plan['price_yearly'] is None


@pytest.mark.parametrize('field, value, words', [
    ('max_students', 'lots', 'must be whole numbers'),
    ('max_staff', '-1', 'must be whole numbers'),
    ('price_yearly', 'free', 'Prices must be numbers'),
    ('price_monthly', '-5', 'Prices must be numbers'),
])
def test_a_bad_plan_value_is_refused(browser, env, field, value, words):
    response = browser.post('/plans', {'label': 'Bad', 'features': ['attendance'], field: value},
                            follow_redirects=True)
    assert words in response.data.decode()
    assert 'bad' not in {p['name'] for p in env[0].extensions['vendor'].store.plans()}


def test_a_first_key_starts_from_the_plan_with_its_limits(browser, env):
    _save_plan(browser)
    school_id = _new_school(browser)
    page = browser.get(f'/schools/{school_id}').data.decode()
    # choosing Gold in the plan box fills the number boxes from the page's own list of plans
    start = page.index('var PLANS=') + len('var PLANS=')
    plans = {p['name']: p for p in json.loads(page[start:page.index(', PREVIEW=')])}
    assert (plans['gold']['max_students'], plans['gold']['max_staff']) == (500, 12)
    assert 'getElementById' in page and "$('maxStudents').value=p.max_students" in page


def test_the_payment_form_is_filled_in_from_the_plan_price(browser, env):
    _save_plan(browser)
    school_id = _new_school(browser, billing='yearly')
    _issue(browser, school_id, plan='gold')
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'name="amount" placeholder="0" value="30000.0"' in page
    assert 'Filled in from the Gold plan’s price (30,000 per year)' in page


def test_a_monthly_school_gets_the_monthly_price(browser, env):
    _save_plan(browser)
    school_id = _new_school(browser, name='Monthly School', billing='monthly')
    _issue(browser, school_id, plan='gold', period='1m')
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'value="3000.0"' in page and '3,000 per month' in page


def test_no_price_means_an_empty_payment_amount(browser, env):
    school_id = _new_school(browser)
    _issue(browser, school_id, plan='standard')
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'name="amount" placeholder="0" value="" required' in page and 'Filled in from' not in page


# ---- plan versus key ------------------------------------------------------------------------

PLAN = {'features': ['attendance', 'exams'], 'wa_daily': 100, 'wa_monthly': None,
        'max_students': 500, 'max_staff': None}


def _key(**changes):
    return {**{k: PLAN[k] for k in PLAN}, **changes}


def test_a_key_that_matches_the_plan_is_the_same():
    assert issuer.plan_differences(PLAN, _key())['same'] is True


def test_extra_and_missing_features_are_named():
    diff = issuer.plan_differences(PLAN, _key(features=['attendance', 'payroll', 'qr_attendance']))
    assert diff['extras'] == ['Payroll', 'QR attendance']
    assert diff['missing'] == ['Exams, marks & results']
    assert diff['same'] is False


def test_different_limits_are_listed_in_plain_words():
    diff = issuer.plan_differences(PLAN, _key(max_students=800, max_staff=4, wa_daily=None))
    assert {(d['label'], d['plan'], d['key']) for d in diff['limits']} == {
        ('Students', '500', '800'), ('Staff logins', 'no limit', '4'),
        ('WhatsApp per day', '100', 'no limit')}


def test_the_school_page_warns_when_the_key_differs_from_its_plan(browser, env):
    school_id = _new_school(browser)
    _issue(browser, school_id, plan='standard', features=['attendance'])      # Standard has many more
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'not the same as the Standard plan' in page and 'It is <b>missing</b>' in page
    assert 'match_plan=1' in page


def test_the_school_page_is_quiet_when_the_key_matches_its_plan(browser, env):
    store = env[0].extensions['vendor'].store
    standard = {p['name']: p for p in store.plans()}['standard']
    school_id = _new_school(browser)
    _issue(browser, school_id, plan='standard', features=standard['features'],
           wa_daily=str(standard['wa_daily']), wa_monthly=str(standard['wa_monthly']),
           max_students='', max_staff='')
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'not the same as the' not in page


def test_use_the_plans_settings_fills_the_form_from_the_plan(browser, env):
    store = env[0].extensions['vendor'].store
    _save_plan(browser)
    school_id = _new_school(browser)
    _issue(browser, school_id, plan='gold', features=['attendance'], max_students='10')
    page = browser.get(f'/schools/{school_id}?do=update&match_plan=1').data.decode()
    assert 'plan’s settings are filled in below' in page
    assert 'value="exams" id="f_exams" checked' in page and 'value="whatsapp" id="f_whatsapp" checked' in page
    assert 'value="payroll" id="f_payroll" checked' not in page
    assert 'id="maxStudents" type="number" min="0" value="500"' in page
    assert 'value="update" checked' in page
    # ...and sending it makes the key match the plan again
    gold = {p['name']: p for p in store.plans()}['gold']
    response = _issue(browser, school_id, reason='update', plan='gold', period='keep',
                      features=gold['features'], wa_daily='50', wa_monthly='1000',
                      max_students='500', max_staff='12')
    assert response.status_code == 302
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'not the same as the' not in page


def test_the_plans_page_lists_schools_that_no_longer_match(browser, env):
    _save_plan(browser)
    in_step = _new_school(browser, name='In Step School')
    drifted = _new_school(browser, name='Drifted School')
    gold = {p['name']: p for p in env[0].extensions['vendor'].store.plans()}['gold']
    _issue(browser, in_step, plan='gold', features=gold['features'], wa_daily='50', wa_monthly='1000',
           max_students='500', max_staff='12')
    _issue(browser, drifted, plan='gold', features=['attendance'], wa_daily='50', wa_monthly='1000',
           max_students='500', max_staff='12')
    page = browser.get('/plans').data.decode()
    assert '2 schools on this plan' in page and '1 no longer matches it' in page
    assert 'In Step School' in page and 'Drifted School' in page and 'Matches the plan' in page
    assert f'/schools/{drifted}?do=update&amp;match_plan=1' in page


# ---- who has what -----------------------------------------------------------------------------

def _two_schools(browser):
    a = _new_school(browser, name='Alpha School')
    b = _new_school(browser, name='Beta School')
    _issue(browser, a, plan='standard', features=['attendance', 'whatsapp'], max_students='300')
    _issue(browser, b, plan='basic', features=['attendance', 'exams'], max_staff='4')
    return a, b


def test_the_matrix_lists_every_school_with_a_key(browser):
    _two_schools(browser)
    page = browser.get('/matrix').data.decode()
    assert 'Alpha School' in page and 'Beta School' in page
    assert 'Students' in page and '300' in page


def test_the_matrix_footer_counts_schools_per_feature(browser):
    _two_schools(browser)
    page = browser.get('/matrix').data.decode()
    footer = page[page.index('<tfoot>'):page.index('</tfoot>')]
    assert footer.count('<b>2</b>') == 1          # attendance: both schools
    assert footer.count('<b>1</b>') == 2          # exams (Beta) and whatsapp (Alpha)
    assert footer.count('<b>0</b>') == len(feature_catalog.ALL_FEATURES) - 3


def test_the_matrix_can_show_who_is_missing_a_feature(browser):
    _two_schools(browser)
    page = browser.get('/matrix?feature=exams&has=no').data.decode()
    assert 'Alpha School' in page and 'Beta School' not in page
    page = browser.get('/matrix?feature=exams&has=yes').data.decode()
    assert 'Beta School' in page and 'Alpha School' not in page


def test_the_matrix_can_filter_by_plan_including_custom(browser):
    _two_schools(browser)
    c = _new_school(browser, name='Custom School')
    _issue(browser, c, plan='', features=['attendance'])
    assert 'Beta School' in (page := browser.get('/matrix?plan=basic').data.decode()) \
        and 'Alpha School' not in page and 'Custom School' not in page
    page = browser.get('/matrix?plan=custom').data.decode()
    assert 'Custom School' in page and 'Alpha School' not in page


def test_a_feature_filter_without_has_is_ignored(browser):
    _two_schools(browser)
    page = browser.get('/matrix?feature=exams').data.decode()
    assert 'Alpha School' in page and 'Beta School' in page
    page = browser.get('/matrix?feature=not_a_feature&has=no').data.decode()
    assert 'Alpha School' in page and 'Beta School' in page


def test_schools_without_a_key_or_not_customers_are_left_out(browser, env):
    _two_schools(browser)
    _new_school(browser, name='Waiting School')                          # no key yet
    gone = _new_school(browser, name='Former School')
    _issue(browser, gone, plan='basic', features=['attendance'])
    browser.post(f'/schools/{gone}/edit', {'name': 'Former School', 'billing': 'yearly'})   # not active
    page = browser.get('/matrix').data.decode()
    assert 'Waiting School' not in page and 'Former School' not in page
    assert '1 school has no key yet' in page


def test_an_empty_matrix_says_so(browser):
    page = browser.get('/matrix').data.decode()
    assert 'No school has a key yet' in page


def test_the_matrix_spreadsheet_has_a_row_per_school_and_yes_no_per_feature(browser):
    _two_schools(browser)
    response = browser.get('/matrix.csv')
    assert response.status_code == 200 and response.mimetype == 'text/csv'
    assert 'attachment' in response.headers['Content-Disposition']
    rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
    header, body = rows[0], {row[0]: row for row in rows[1:]}
    assert header[:9] == ['School', 'City', 'Plan', 'Key status', 'Key ends', 'Students limit',
                          'Staff logins limit', 'WhatsApp per day', 'WhatsApp per month']
    assert set(body) == {'Alpha School', 'Beta School'}
    assert body['Alpha School'][5] == '300' and body['Beta School'][6] == '4'
    assert body['Alpha School'][header.index('WhatsApp automation')] == 'Yes'
    assert body['Beta School'][header.index('WhatsApp automation')] == 'No'


def test_the_matrix_spreadsheet_follows_the_filters(browser):
    _two_schools(browser)
    rows = list(csv.reader(io.StringIO(browser.get('/matrix.csv?feature=exams&has=no').data.decode('utf-8-sig'))))
    assert [row[0] for row in rows[1:]] == ['Alpha School']


def test_the_matrix_needs_the_dashboard_to_be_unlocked(env):
    client = env[0].test_client()
    client.get('/unlock')
    assert client.get('/matrix').status_code == 302
    assert client.get('/matrix.csv').status_code == 302


def test_the_menu_links_to_the_matrix(browser):
    assert 'href="/matrix"' in browser.get('/').data.decode()


# ---- older vendor databases -------------------------------------------------------------------

def test_an_old_vendor_database_is_upgraded_in_place(tmp_path):
    path = tmp_path / 'vendor.db'
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE schools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, contact_name TEXT,
            phone TEXT, email TEXT, city TEXT, billing TEXT NOT NULL DEFAULT 'yearly', machine_code TEXT,
            license_id TEXT, notes TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE licenses (id INTEGER PRIMARY KEY AUTOINCREMENT, school_id INTEGER NOT NULL,
            license_id TEXT NOT NULL, rev INTEGER NOT NULL, reason TEXT, plan TEXT, machine_code TEXT NOT NULL,
            issued TEXT NOT NULL, expires TEXT NOT NULL, grace_days INTEGER NOT NULL, features TEXT NOT NULL,
            wa_daily INTEGER, wa_monthly INTEGER, key_text TEXT, note TEXT, created_at TEXT NOT NULL);
        CREATE TABLE plans (name TEXT PRIMARY KEY, label TEXT NOT NULL, features TEXT NOT NULL,
            wa_daily INTEGER, wa_monthly INTEGER);
        INSERT INTO plans VALUES ('basic', 'Basic', '["attendance"]', 0, 0);
        INSERT INTO schools (name, created_at) VALUES ('Old School', '2025-01-01T00:00:00');
        INSERT INTO licenses (school_id, license_id, rev, plan, machine_code, issued, expires, grace_days,
            features, created_at) VALUES (1, 'LIC-1', 1, 'basic', 'AAAA-BBBB-CCCC-DDDD', '2025-01-01',
            '2026-12-31', 7, '["attendance"]', '2025-01-01T00:00:00');
        UPDATE schools SET license_id = 'LIC-1';
    """)
    old.commit()
    old.close()

    store = Store(tmp_path)
    plan = store.plans()[0]
    assert plan['name'] == 'basic' and plan['max_students'] is None and plan['price_yearly'] is None
    store.save_plan('basic', 'Basic', ['attendance'], 0, 0, 200, 3, 1000, 10000)
    assert store.plans()[0]['max_students'] == 200
    row = store.schools_with_license()[0]
    assert row['max_students'] is None and row['max_staff'] is None      # old keys: unlimited
    store.add_license(school_id=1, license_id='LIC-1', rev=2, machine_code='AAAA-BBBB-CCCC-DDDD',
                      issued='2026-01-01', expires='2026-12-31', grace_days=7, features=['attendance'],
                      max_students=200, max_staff=3)
    assert store.latest_license(1)['max_students'] == 200


def test_matrix_rows_helper_skips_inactive_and_keyless_schools(tmp_path):
    store = Store(tmp_path)
    keyless = store.create_school(name='Keyless')
    active = store.create_school(name='Active')
    store.add_license(school_id=active, license_id='LIC-A', rev=1, plan='basic',
                      machine_code='AAAA-BBBB-CCCC-DDDD', issued='2026-01-01', expires='2026-12-31',
                      grace_days=7, features=['attendance'])
    off = store.create_school(name='Off')
    store.add_license(school_id=off, license_id='LIC-O', rev=1, plan='basic',
                      machine_code='AAAA-BBBB-CCCC-DDDD', issued='2026-01-01', expires='2026-12-31',
                      grace_days=7, features=['attendance'])
    store.update_school(off, active=0)
    entries = issuer.matrix_rows(store.schools_with_license(), TODAY)
    assert [e['school']['name'] for e in entries] == ['Active'] and keyless
    assert issuer.feature_totals(entries)['attendance'] == 1


def test_money_and_limit_words():
    assert issuer.money_text(30000.0) == '30,000' and issuer.money_text(1234.5) == '1,234.50'
    assert issuer.money_text(None) == ''
    assert issuer.limit_text(None) == 'no limit' and issuer.limit_text(1500) == '1,500'
    assert issuer.plan_label('') == 'Custom' and issuer.plan_label('gold_plus') == 'Gold Plus'
    assert issuer.plan_price(None, 'yearly') is None
    assert issuer.plan_price({'price_monthly': 5, 'price_yearly': 50}, 'monthly') == 5
    assert issuer.plan_price({'price_monthly': 5, 'price_yearly': 50}, 'yearly') == 50


# ---- the command-line tool ---------------------------------------------------------------------

def test_the_command_line_payload_carries_the_new_limits():
    from tests.licensing_fixtures import tool
    payload = tool.build_payload(license_id='LIC-CLI', licensee='Cli School', machine_code=MACHINE,
                                 issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7,
                                 wa_daily=10, max_students=250, max_staff=6)
    assert payload['limits'] == {'wa_daily': 10, 'max_students': 250, 'max_staff': 6}
    bare = tool.build_payload(license_id='LIC-CLI2', licensee='Cli', machine_code=MACHINE,
                              issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7)
    assert 'limits' not in bare

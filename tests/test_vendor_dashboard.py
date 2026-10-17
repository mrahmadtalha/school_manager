"""The vendor license-manager dashboard (runs on the vendor's laptop only)."""

import csv
import io
import json
import time
import zipfile
from datetime import date

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services import licensing
from vendor_dashboard import issuer
from vendor_dashboard.app import create_app
from vendor_dashboard.core import features as feature_catalog
from vendor_dashboard.core import lic as dash_lic

PASSWORD = 'correct horse battery'
MACHINE = '7F3A-91BC-0D42-E8A5'
TODAY = date(2026, 10, 15)


@pytest.fixture()
def env(tmp_path):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    public = licensing.b64u_encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    keys_dir = tmp_path / 'vendor_keys'
    keys_dir.mkdir()
    (keys_dir / 'license_private.key').write_text(licensing.b64u_encode(raw) + '\n')
    application = create_app({'TESTING': True, 'DATA_DIR': tmp_path / 'vendor_data',
                              'KEYS_DIR': keys_dir, 'PUBLIC_KEY': public, 'KDF_N': 2 ** 10,
                              'TODAY_FN': lambda: TODAY})
    return application, public, keys_dir


class Browser:
    def __init__(self, application):
        self.client = application.test_client()
        self.client.get('/unlock')

    @property
    def csrf(self):
        with self.client.session_transaction() as session:
            return session['csrf']

    def post(self, url, data=None, **kwargs):
        return self.client.post(url, data={**(data or {}), '_csrf': self.csrf}, **kwargs)

    def get(self, url, **kwargs):
        return self.client.get(url, **kwargs)


@pytest.fixture()
def browser(env):
    page = Browser(env[0])
    response = page.post('/unlock', {'password': PASSWORD, 'confirm': PASSWORD})
    assert response.status_code == 302
    return page


def _new_school(browser, name='Al-Noor School', billing='yearly'):
    response = browser.post('/schools/new', {'name': name, 'phone': '0300', 'billing': billing,
                                              'machine_code': MACHINE})
    assert response.status_code == 302
    return int(response.headers['Location'].rstrip('/').split('/')[-1])


def _issue(browser, school_id, **overrides):
    data = {'reason': 'new', 'machine_code': MACHINE, 'plan': 'standard', 'period': '1y',
            'grace_days': '7', 'wa_daily': '100', 'wa_monthly': '2000',
            'features': ['expenses', 'attendance', 'whatsapp']}
    data.update(overrides)
    return browser.post(f'/schools/{school_id}/issue', data)


def _key_text(browser, response):
    assert response.status_code == 302, response.data[:300]
    page = browser.get(response.headers['Location']).data.decode()
    start = page.index('SM1.')
    return page[start:page.index('</textarea>', start)].strip()


# -- access control -----------------------------------------------------------

def test_everything_is_locked_until_the_password_is_entered(env):
    page = Browser(env[0])
    for url in ('/', '/schools', '/recovery', '/settings', '/plans'):
        response = page.get(url)
        assert response.status_code == 302 and '/unlock' in response.headers['Location']


def test_first_run_needs_a_strong_matching_password_and_keeps_the_plain_key(env):
    application, _public, keys_dir = env
    page = Browser(application)
    weak = page.post('/unlock', {'password': 'short', 'confirm': 'short'})
    assert b'at least 10 characters' in weak.data
    mismatch = page.post('/unlock', {'password': PASSWORD, 'confirm': PASSWORD + 'x'})
    assert b'do not match' in mismatch.data
    assert page.post('/unlock', {'password': PASSWORD, 'confirm': PASSWORD}).status_code == 302
    assert (keys_dir / 'license_private.key').exists()
    enc = application.extensions['vendor'].keystore.enc_path
    assert enc.exists() and PASSWORD.encode() not in enc.read_bytes()


def test_wrong_password_is_refused_and_throttled(env, browser):
    page = Browser(env[0])
    for _ in range(5):
        assert b'Wrong password' in page.post('/unlock', {'password': 'nope nope nope'}).data
    assert b'Too many wrong passwords' in page.post('/unlock', {'password': PASSWORD}).data


def test_lock_forgets_the_key(env, browser):
    assert browser.post('/logout').status_code == 302
    assert browser.get('/schools').status_code == 302
    assert env[0].extensions['vendor'].private_key is None
    again = Browser(env[0])
    assert again.post('/unlock', {'password': PASSWORD}).status_code == 302
    assert again.get('/schools').status_code == 200


def test_foreign_hosts_and_missing_csrf_are_rejected(env, browser):
    assert browser.get('/', headers={'Host': 'evil.example.com'}).status_code == 403
    assert browser.client.post('/schools/new', data={'name': 'x'}).status_code == 400


def test_a_key_that_does_not_match_the_app_is_refused(tmp_path):
    other = Ed25519PrivateKey.generate()
    raw = other.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                              serialization.NoEncryption())
    keys_dir = tmp_path / 'k'
    keys_dir.mkdir()
    (keys_dir / 'license_private.key').write_text(licensing.b64u_encode(raw))
    application = create_app({'TESTING': True, 'DATA_DIR': tmp_path / 'd', 'KEYS_DIR': keys_dir,
                              'PUBLIC_KEY': 'A' * 43, 'KDF_N': 2 ** 10})
    page = Browser(application)
    assert b'does not match the public key' in page.post(
        '/unlock', {'password': PASSWORD, 'confirm': PASSWORD}).data


# -- issuing keys ----------------------------------------------------------------

def test_issued_key_is_valid_for_the_app_with_features_and_limits(env, browser):
    school_id = _new_school(browser)
    key = _key_text(browser, _issue(browser, school_id))
    payload = licensing.verify_license_text(key, env[1])
    assert payload['licensee'] == 'Al-Noor School' and payload['machine_id'] == MACHINE
    assert payload['_features'] == ('attendance', 'expenses', 'whatsapp')
    assert payload['_limits'] == {'wa_daily': 100, 'wa_monthly': 2000}
    assert payload['_rev'] == 1 and payload['_plan'] == 'standard'
    assert payload['issued'] == '2026-10-15' and payload['expires'] == '2027-10-14'


def test_renewal_extends_from_the_current_expiry_and_bumps_the_revision(env, browser):
    school_id = _new_school(browser)
    _issue(browser, school_id)
    second = _key_text(browser, _issue(browser, school_id, reason='renew', period='1m',
                                       features=['expenses']))
    payload = licensing.verify_license_text(second, env[1])
    assert payload['_rev'] == 2 and payload['expires'] == '2027-11-14'
    assert payload['license_id'].startswith('LIC-20261015-')
    assert payload['_features'] == ('expenses',)


def test_feature_update_keeps_the_expiry(env, browser):
    school_id = _new_school(browser)
    _issue(browser, school_id)
    updated = _key_text(browser, _issue(browser, school_id, reason='update', period='keep',
                                        features=['expenses', 'payroll'], wa_daily='', wa_monthly=''))
    payload = licensing.verify_license_text(updated, env[1])
    assert payload['expires'] == '2027-10-14' and payload['_limits'] == {}
    assert payload['_features'] == ('expenses', 'payroll')


def test_move_to_a_new_pc_rebinds_the_same_license(env, browser):
    school_id = _new_school(browser)
    first = licensing.verify_license_text(_key_text(browser, _issue(browser, school_id)), env[1])
    moved = licensing.verify_license_text(_key_text(browser, _issue(
        browser, school_id, reason='move', period='keep', machine_code='1111-2222-3333-4444')), env[1])
    assert moved['license_id'] == first['license_id'] and moved['_rev'] == 2
    assert moved['machine_id'] == '1111-2222-3333-4444'


def test_bad_input_is_explained_not_signed(env, browser):
    school_id = _new_school(browser)
    for overrides, text in (({'machine_code': 'abc'}, b'machine code'),
                            ({'wa_daily': 'lots'}, b'whole numbers'),
                            ({'period': 'custom', 'custom_expires': '2020-01-01'}, b'in the past'),
                            ({'period': 'keep'}, b'validity period')):
        response = _issue(browser, school_id, **overrides)
        assert response.status_code == 302
        assert text in browser.get(response.headers['Location']).data
    assert env[0].extensions['vendor'].store.licenses_for(school_id) == []


def test_the_app_accepts_the_new_key_and_refuses_the_older_one(env, browser, tmp_path):
    school_id = _new_school(browser)
    first = _key_text(browser, _issue(browser, school_id))
    second = _key_text(browser, _issue(browser, school_id, reason='update', period='keep'))
    manager = licensing.LicenseManager(tmp_path / 'l.key', tmp_path / 'l.state', env[1],
                                       machine_code=MACHINE, cache_seconds=0,
                                       now_fn=lambda: __import__('datetime').datetime(2026, 10, 16))
    manager.activate(second)
    with pytest.raises(licensing.LicenseError) as err:
        manager.activate(first)
    assert err.value.code == 'older_key'


def test_key_download_and_message(browser):
    school_id = _new_school(browser)
    response = _issue(browser, school_id)
    row_id = int(response.headers['Location'].rstrip('/').split('/')[-1])
    download = browser.get(f'/keys/{row_id}/download')
    assert download.headers['Content-Disposition'].endswith('rev1.key"')
    assert download.data.startswith(b'SM1.')
    assert b'Ready-to-send message' in browser.get(f'/keys/{row_id}').data


# -- dates & status -----------------------------------------------------------------

def test_add_months_clamps_to_the_month_end():
    assert issuer.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert issuer.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


def test_compute_expiry_rules():
    today = date(2026, 10, 15)
    assert issuer.compute_expiry('1y', None, None, today) == date(2027, 10, 14)
    assert issuer.compute_expiry('1m', None, date(2026, 10, 31), today) == date(2026, 11, 30)  # early
    assert issuer.compute_expiry('1m', None, date(2026, 9, 1), today) == date(2026, 11, 14)    # late
    assert issuer.compute_expiry('keep', None, date(2027, 1, 1), today) == date(2027, 1, 1)
    assert issuer.compute_expiry('custom', date(2027, 5, 5), None, today) == date(2027, 5, 5)


def test_license_status_buckets():
    today = date(2026, 10, 15)
    assert issuer.license_status('2027-01-01', 7, today)[0] == 'active'
    assert issuer.license_status('2026-11-01', 7, today)[0] == 'soon'
    assert issuer.license_status('2026-10-12', 7, today)[0] == 'grace'
    assert issuer.license_status('2026-09-01', 7, today)[0] == 'expired'
    assert issuer.license_status(None, 0, today)[0] == 'none'


def test_home_lists_schools_needing_attention(browser):
    soon = _new_school(browser, 'Expiring Soon School')
    _issue(browser, soon, period='custom', custom_expires='2026-10-30')
    fine = _new_school(browser, 'Healthy School')
    _issue(browser, fine)
    home = browser.get('/').data
    assert b'Expiring Soon School' in home and b'Healthy School' not in home


# -- password recovery ----------------------------------------------------------------

def _request_code(license_id='', machine=MACHINE):
    return licensing.make_recovery_request('a1b2c3d4e5f6', machine, license_id, int(time.time()))


def test_recovery_token_is_signed_for_the_request_and_logged(env, browser):
    school_id = _new_school(browser)
    key = _key_text(browser, _issue(browser, school_id))
    license_id = licensing.verify_license_text(key, env[1])['license_id']
    code = _request_code(license_id)

    lookup = browser.post('/recovery', {'request_code': code, 'action': 'lookup'})
    assert b'Al-Noor School' in lookup.data and b'Issue reset token' in lookup.data

    issued = browser.post('/recovery', {'request_code': code, 'action': 'issue', 'hours': '24',
                                        'note': 'called principal'})
    page = issued.data.decode()
    token = page[page.index('SMT1.'):].split('</textarea>')[0].strip()
    data = licensing.verify_recovery_token(token, env[1])
    assert data['nonce'] == 'a1b2c3d4e5f6' and data['machine'] == MACHINE.replace('-', '')
    assert 23 * 3600 < data['expires_ts'] - data['issued_ts'] <= 24 * 3600
    rows = env[0].extensions['vendor'].store.recoveries()
    assert len(rows) == 1 and rows[0]['note'] == 'called principal'


def test_unknown_or_mismatched_requests_need_explicit_confirmation(env, browser):
    school_id = _new_school(browser)
    _issue(browser, school_id)
    stranger = _request_code(machine='9999-8888-7777-6666')
    refused = browser.post('/recovery', {'request_code': stranger, 'action': 'issue', 'hours': '1'})
    assert b'Tick the confirmation box' in refused.data and b'SMT1.' not in refused.data
    allowed = browser.post('/recovery', {'request_code': stranger, 'action': 'issue', 'hours': '1',
                                         'confirm': 'on'})
    assert b'SMT1.' in allowed.data


def test_damaged_request_codes_are_explained(browser):
    code = _request_code()
    broken = browser.post('/recovery', {'request_code': code[:-12], 'action': 'lookup'})
    assert b'damaged' in broken.data or b'not a valid' in broken.data


# -- plans, ledger, backup, key file --------------------------------------------------

def test_plans_can_be_edited(browser, env):
    response = browser.post('/plans', {'name': 'basic', 'label': 'Basic', 'wa_daily': '5',
                                       'wa_monthly': '', 'features': ['attendance', 'bogus']})
    assert response.status_code == 302
    basic = [p for p in env[0].extensions['vendor'].store.plans() if p['name'] == 'basic'][0]
    assert basic['features'] == ['attendance'] and basic['wa_daily'] == 5 and basic['wa_monthly'] is None


def test_import_of_the_old_ledger_is_safe_to_repeat(env, browser):
    keys_dir = env[2]
    with (keys_dir / 'issued_licenses.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['created_at', 'license_id', 'licensee', 'machine_id', 'issued', 'expires',
                         'grace_days'])
        writer.writerow(['2025-10-01T10:00:00', 'LIC-20251001-0001', 'Old School', MACHINE,
                         '2025-10-01', '2026-09-30', '7'])
        writer.writerow(['2026-09-20T10:00:00', 'LIC-20260920-0002', 'Old School', MACHINE,
                         '2026-09-20', '2027-09-19', '7'])
    browser.post('/settings/import-ledger')
    browser.post('/settings/import-ledger')
    store = env[0].extensions['vendor'].store
    schools = store.schools_with_license()
    assert len(schools) == 1 and schools[0]['expires'] == '2027-09-19'
    # Renewing an imported school continues from revision 0 -> 1.
    key = licensing.verify_license_text(
        _key_text(browser, _issue(browser, schools[0]['id'], reason='renew', period='1y')), env[1])
    assert key['_rev'] == 1 and key['license_id'] == 'LIC-20260920-0002'


def test_backup_contains_database_and_encrypted_key(browser):
    archive = zipfile.ZipFile(io.BytesIO(browser.get('/settings/backup').data))
    assert set(archive.namelist()) == {'vendor.db', 'license_private.enc'}


def test_plain_key_is_erased_only_with_the_right_password(env, browser):
    plain = env[2] / 'license_private.key'
    assert b'Wrong password' in browser.post('/settings/remove-plain-key', {'password': 'x' * 12},
                                             follow_redirects=True).data
    assert plain.exists()
    browser.post('/settings/remove-plain-key', {'password': PASSWORD})
    assert not plain.exists()
    # The dashboard still unlocks and signs from the encrypted copy.
    again = Browser(env[0])
    assert again.post('/unlock', {'password': PASSWORD}).status_code == 302


def test_password_change_works(env, browser):
    browser.post('/settings/password', {'old_password': PASSWORD, 'new_password': 'another long pass',
                                        'confirm_password': 'another long pass'})
    fresh = Browser(env[0])
    assert b'Wrong password' in fresh.post('/unlock', {'password': PASSWORD}).data
    assert fresh.post('/unlock', {'password': 'another long pass'}).status_code == 302


def test_catalog_checkboxes_cover_every_feature(browser):
    school_id = _new_school(browser)
    page = browser.get(f'/schools/{school_id}').data.decode()
    for key in feature_catalog.ALL_FEATURES:
        assert f'value="{key}"' in page


def test_remaining_pages_render(browser):
    school_id = _new_school(browser)
    for url in ('/schools/new', '/schools?q=noor', '/plans', '/settings', '/recovery',
                f'/schools/{school_id}'):
        assert browser.get(url).status_code == 200, url

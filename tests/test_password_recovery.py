"""Forgot username / password: vendor-signed, single-use, machine-bound tokens."""

import re
import time

from app.models import AdminUser
from app.services import licensing
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (MACHINE, clock, keypair, licensed_app_factory,  # noqa: F401
                                      make_key)

NEW_PASSWORD = 'BrandNew2026pw'


def _request_code(client):
    page = client.get('/recover')
    assert page.status_code == 200
    return re.search(rb'SMR1\.[\w\-]+\.[\w\-]+', page.data).group(0).decode()


def _token_for(keypair, code, *, machine=MACHINE, lifetime=3600, issued=None):
    request_data = licensing.parse_recovery_request(code)
    now = int(issued if issued is not None else time.time())
    return licensing.sign_recovery_token(keypair[0], request_data['nonce'], machine,
                                         now, now + lifetime)


def _setup(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(make_key(keypair[0]))
    return application


def test_full_recovery_resets_the_password_once(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    code = _request_code(client)
    assert licensing.parse_recovery_request(code)['machine_code'] == MACHINE
    token = _token_for(keypair, code)

    step = client.post('/recover', data={'token': token}, follow_redirects=False)
    assert step.status_code == 302 and step.headers['Location'].endswith('/recover/reset')

    with application.app_context():
        admin_id = AdminUser.query.filter_by(username='admin').first().id
    assert b'admin' in client.get('/recover/reset').data          # shows the username too
    done = client.post('/recover/reset', data={
        'user_id': admin_id, 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD},
        follow_redirects=False)
    assert done.status_code == 302 and done.headers['Location'].endswith('/login')

    fresh = application.test_client()
    assert login(fresh, 'admin', NEW_PASSWORD).status_code == 302
    assert login(application.test_client(), 'admin', ADMIN_PASSWORD).status_code != 302

    # Replaying the same token fails, and the reset page needs a fresh token.
    replay = application.test_client()
    replay.get('/recover')
    assert b'already been used' in replay.post('/recover', data={'token': token}).data
    assert replay.get('/recover/reset', follow_redirects=False).status_code == 302


def test_recovery_works_while_the_license_is_expired(licensed_app_factory, keypair, clock):
    from datetime import datetime
    application = _setup(licensed_app_factory, keypair)
    clock.set(datetime(2027, 3, 1))                       # past expiry + grace: read-only
    assert application.extensions['license_manager'].status().read_only
    client = application.test_client()
    code = _request_code(client)
    token = _token_for(keypair, code)
    assert client.post('/recover', data={'token': token}).status_code == 302
    with application.app_context():
        admin_id = AdminUser.query.filter_by(username='admin').first().id
    done = client.post('/recover/reset', data={
        'user_id': admin_id, 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert done.status_code == 302 and done.headers['Location'].endswith('/login')
    assert login(application.test_client(), 'admin', NEW_PASSWORD).status_code == 302


def test_bad_tokens_are_rejected(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    code = _request_code(client)

    wrong_machine = _token_for(keypair, code, machine='ZZZZ-ZZZZ-ZZZZ-ZZZZ')
    assert b'different computer' in client.post('/recover', data={'token': wrong_machine}).data

    expired = _token_for(keypair, code, issued=time.time() - 7200, lifetime=3600)
    assert b'expired' in client.post('/recover', data={'token': expired}).data

    good = _token_for(keypair, code)
    forged = good[:-6] + ('AAAAAA' if not good.endswith('AAAAAA') else 'BBBBBB')
    assert b'not genuine' in client.post('/recover', data={'token': forged}).data

    assert b'not a valid reset token' in client.post('/recover', data={'token': 'hello'}).data
    from app.auth import RECOVERY_THROTTLE_KEY
    from app.security import clear_failed_logins
    clear_failed_logins(RECOVERY_THROTTLE_KEY)       # the throttle is global; reset it for the rest

    # An attacker's own key cannot sign a working token.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    attacker = licensing.sign_recovery_token(
        Ed25519PrivateKey.generate(), licensing.parse_recovery_request(code)['nonce'],
        MACHINE, int(time.time()), int(time.time()) + 3600)
    assert b'not genuine' in client.post('/recover', data={'token': attacker}).data

    # A license key must not work as a recovery token (separate signing context).
    assert b'not a valid reset token' in client.post(
        '/recover', data={'token': make_key(keypair[0])}).data


def test_new_request_code_invalidates_the_old_token(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    old_code = _request_code(client)
    old_token = _token_for(keypair, old_code)
    client.post('/recover', data={'action': 'new_code'})
    assert _request_code(client) != old_code
    assert b'does not match the request code' in client.post('/recover', data={'token': old_token}).data


def test_request_code_is_stable_until_used(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    assert _request_code(client) == _request_code(client)


def test_wrong_tokens_are_throttled(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    client.get('/recover')
    statuses = [client.post('/recover', data={'token': 'SMT1.x.y'}).status_code for _ in range(8)]
    assert 429 in statuses


def test_reset_page_requires_a_valid_token_first(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    response = client.get('/recover/reset', follow_redirects=False)
    assert response.status_code == 302 and response.headers['Location'].endswith('/recover')
    assert client.post('/recover/reset', data={'user_id': 1, 'password': NEW_PASSWORD,
                                               'confirm_password': NEW_PASSWORD},
                       follow_redirects=False).status_code == 302


def test_weak_or_mismatched_new_password_is_refused(licensed_app_factory, keypair):
    application = _setup(licensed_app_factory, keypair)
    client = application.test_client()
    client.post('/recover', data={'token': _token_for(keypair, _request_code(client))})
    with application.app_context():
        admin_id = AdminUser.query.filter_by(username='admin').first().id
    mismatch = client.post('/recover/reset', data={
        'user_id': admin_id, 'password': NEW_PASSWORD, 'confirm_password': 'other'})
    assert b'do not match' in mismatch.data
    weak = client.post('/recover/reset', data={
        'user_id': admin_id, 'password': 'abc', 'confirm_password': 'abc'})
    assert weak.status_code == 200 and b'alert-danger' in weak.data
    # Token still usable after those mistakes.
    ok = client.post('/recover/reset', data={
        'user_id': admin_id, 'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert ok.status_code == 302

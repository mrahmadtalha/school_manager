"""Easy guard-phone connection: connection QR code, device token, discovery answer."""

import json
import socket

import pytest
from flask import g

from app.database import db
from app.models import ROLE_GUARD, AdminUser
from app.models.qr_config import QrConfig
from app.services import qr_attendance as qr
from app.services import qr_pairing as pairing
from tests.conftest import ADMIN_PASSWORD, TEACHER_PASSWORD, login

GUARD_PASSWORD = 'guardpass123'


@pytest.fixture()
def guard(app):
    user = AdminUser(username='guard', role=ROLE_GUARD, full_name='Gate Guard')
    user.set_password(GUARD_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


class _RoleClient:
    """A test client for one logged-in user.

    conftest's ``admin_client`` and ``teacher_client`` share ONE client, so using
    both in a test leaves everybody signed in as the teacher.  These own clients
    keep each role separate.  Flask-Login caches the first request's user in
    ``g`` (the ``app`` fixture keeps one app context open), so that cache is
    dropped before every call.
    """

    def __init__(self, client):
        self._client = client

    def _call(self, method, *args, **kwargs):
        g.pop('_login_user', None)
        return getattr(self._client, method)(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._call('get', *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._call('post', *args, **kwargs)


def _signed_in(app, username, password):
    client = app.test_client()
    g.pop('_login_user', None)
    login(client, username, password)
    return _RoleClient(client)


@pytest.fixture()
def admin_client(app):
    return _signed_in(app, 'admin', ADMIN_PASSWORD)


@pytest.fixture()
def teacher_client(app):
    return _signed_in(app, 'teacher', TEACHER_PASSWORD)


# -- tokens (no database) ---------------------------------------------------

def test_pair_token_round_trip_expiry_and_tampering():
    token = pairing.make_pair_token('secret-one', 7, now=1000)
    assert pairing.check_pair_token('secret-one', token, now=1100) == ('ok', 7)
    assert pairing.parse_pair_token('secret-one', token, now=1100) == 7
    late = 1000 + pairing.PAIR_LIFETIME_SECONDS + 1
    assert pairing.check_pair_token('secret-one', token, now=late) == ('expired', None)
    assert pairing.check_pair_token('another-school', token, now=1100) == ('invalid', None)
    assert pairing.check_pair_token('secret-one', token.replace('.7.', '.8.'), now=1100) == ('invalid', None)
    assert pairing.check_pair_token('secret-one', 'junk') == ('invalid', None)
    assert pairing.check_pair_token('secret-one', None) == ('invalid', None)


def test_device_token_stops_working_when_the_password_changes():
    token = pairing.make_device_token('secret-one', 7, 'hash-a')
    assert pairing.device_token_user_id(token) == 7
    assert pairing.verify_device_token('secret-one', token, 7, 'hash-a')
    assert not pairing.verify_device_token('secret-one', token, 7, 'hash-b')
    assert not pairing.verify_device_token('secret-one', token, 8, 'hash-a')
    assert not pairing.verify_device_token('another-school', token, 7, 'hash-a')
    assert pairing.device_token_user_id('SMDEV1.x.y') is None


def test_qr_text_round_trip():
    text = pairing.build_pair_payload(['http://10.0.0.5:8000/', 'http://192.168.1.9:8000'], 'tok')
    assert text.startswith('SMGUARD1|')
    assert pairing.parse_pair_payload(text) == (['http://10.0.0.5:8000', 'http://192.168.1.9:8000'], 'tok')
    assert pairing.parse_pair_payload('hello') is None
    assert pairing.parse_pair_payload('SMGUARD1||tok') is None


def test_discovery_answers_only_the_right_question():
    thread = pairing.start_discovery_responder(8123, udp_port=50598)
    assert thread is not None
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.settimeout(2)
    try:
        probe.sendto(b'something else', ('127.0.0.1', 50598))
        probe.sendto(pairing.DISCOVERY_REQUEST, ('127.0.0.1', 50598))
        data, _ = probe.recvfrom(256)
    finally:
        probe.close()
    assert json.loads(data) == {'app': pairing.DISCOVERY_APP, 'port': 8123}


# -- the guard API ------------------------------------------------------------

def test_connection_code_signs_the_phone_in_and_gives_a_device_token(app, client, guard):
    token = pairing.make_pair_token(qr.get_secret(), guard.id)
    reply = client.post('/api/qr/pair', json={'pair_token': token})
    body = reply.get_json()
    assert reply.status_code == 200 and body['ok'] is True
    assert body['user']['username'] == 'guard' and body['device_token'].startswith('SMDEV1.')
    assert client.get('/api/qr/ping').status_code == 200          # signed in

    phone = app.test_client()                                     # later: sign in with the token only
    again = phone.post('/api/qr/login', json={'device_token': body['device_token']})
    assert again.status_code == 200 and again.get_json()['ok'] is True
    assert phone.get('/api/qr/ping').status_code == 200


def test_old_wrong_and_admin_codes_are_refused(app, client, guard):
    secret = qr.get_secret()
    expired = pairing.make_pair_token(secret, guard.id, now=1000)
    reply = client.post('/api/qr/pair', json={'pair_token': expired})
    assert reply.status_code == 401 and reply.get_json()['error'] == 'pair_expired'

    wrong = client.post('/api/qr/pair', json={'pair_token': 'SMPAIR1.1.9999999999.deadbeef'})
    assert wrong.status_code == 401 and wrong.get_json()['error'] == 'pair_invalid'

    admin = AdminUser.query.filter_by(username='admin').first()
    admin_code = pairing.make_pair_token(secret, admin.id)
    refused = client.post('/api/qr/pair', json={'pair_token': admin_code})
    assert refused.status_code == 401                              # only guard accounts can be connected
    assert client.get('/api/qr/ping').status_code in (401, 302, 403)


def test_changing_the_guard_password_disconnects_the_phone(app, client, guard):
    token = pairing.make_device_token(qr.get_secret(), guard.id, guard.password_hash)
    assert client.post('/api/qr/login', json={'device_token': token}).status_code == 200

    guard.set_password('somethingNew123')
    db.session.commit()
    phone = app.test_client()
    reply = phone.post('/api/qr/login', json={'device_token': token})
    assert reply.status_code == 401 and reply.get_json()['error'] == 'bad_device_token'


def test_password_login_also_returns_a_device_token(app, client, guard):
    reply = client.post('/api/qr/login', json={'username': 'guard', 'password': GUARD_PASSWORD})
    assert reply.status_code == 200 and reply.get_json()['device_token'].startswith('SMDEV1.')


def test_other_devices_can_reach_the_pairing_endpoint(app, client):
    remote = {'environ_overrides': {'REMOTE_ADDR': '192.168.1.50'}}
    reply = client.post('/api/qr/pair', json={}, **remote)
    assert reply.status_code == 401 and reply.get_json()['error'] == 'pair_invalid'   # reached the route


# -- admin page -----------------------------------------------------------------

def test_admin_can_make_a_connection_code_teacher_cannot(app, admin_client, teacher_client, guard, monkeypatch):
    monkeypatch.setattr(qr, 'local_ip_addresses', lambda: ['192.168.1.20'])
    reply = admin_client.get(f'/attendance/qr/pair-code?user_id={guard.id}')
    body = reply.get_json()
    assert reply.status_code == 200 and body['ok'] is True
    addresses, token = pairing.parse_pair_payload(body['payload'])
    assert addresses[0].startswith('http://192.168.1.20:')
    assert pairing.parse_pair_token(qr.get_secret(), token) == guard.id

    assert admin_client.get('/attendance/qr/pair-code?user_id=999999').status_code == 404
    assert teacher_client.get(f'/attendance/qr/pair-code?user_id={guard.id}').status_code == 403


def test_admin_can_create_a_guard_account_in_one_click(app, admin_client, teacher_client):
    assert teacher_client.post('/attendance/qr/guard/create').status_code == 403
    admin_client.post('/attendance/qr/guard/create')
    admin_client.post('/attendance/qr/guard/create')
    names = sorted(u.username for u in AdminUser.query.filter_by(role=ROLE_GUARD).all())
    assert names == ['guard', 'guard2']


def test_connection_box_is_shown_to_the_admin_only(app, admin_client, teacher_client, guard, monkeypatch):
    monkeypatch.setattr(qr, 'local_ip_addresses', lambda: ['192.168.1.20'])
    QrConfig.get().lan_access = True
    db.session.commit()
    assert 'id="pairBox"' in admin_client.get('/attendance/students?tab=qr').get_data(as_text=True)
    assert 'id="pairBox"' not in teacher_client.get('/attendance/students?tab=qr').get_data(as_text=True)

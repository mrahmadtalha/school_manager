"""Offline licensing: signature checks, lifecycle, clock protection, lockout."""

import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.database import db
from app.models import AuditLog, ClassModel
from app.services import licensing
from app.services.licensing import LicenseError, LicenseManager
from tests.conftest import ADMIN_PASSWORD, TEACHER_PASSWORD, login, seed_reference_data

MACHINE = 'AAAA-BBBB-CCCC-DDDD'
OTHER_MACHINE = 'EEEE-FFFF-1111-2222'
T0 = datetime(2026, 1, 10, 9, 0, 0)          # "now" at issue time


# -- helpers -------------------------------------------------------------

def _load_tool():
    path = Path(__file__).resolve().parent.parent / 'tools' / 'license_admin.py'
    spec = importlib.util.spec_from_file_location('license_admin_tool', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


@pytest.fixture(scope='module')
def keypair():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, licensing.b64u_encode(raw)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def set(self, value):
        self.now = value


def make_key(private, *, machine=MACHINE, issued=date(2026, 1, 10), expires=date(2026, 12, 31),
             license_id='LIC-TEST-0001', grace_days=7, **overrides):
    payload = {
        'v': licensing.PAYLOAD_VERSION, 'product': licensing.PRODUCT,
        'license_id': license_id, 'licensee': 'Test School', 'machine_id': machine,
        'issued': issued.isoformat(), 'expires': expires.isoformat(), 'grace_days': grace_days,
    }
    payload.update(overrides)
    return tool.sign_license(private, payload)


@pytest.fixture()
def clock():
    return Clock(T0)


@pytest.fixture()
def manager(tmp_path, keypair, clock):
    return LicenseManager(tmp_path / 'license.key', tmp_path / 'license.state', keypair[1],
                          machine_code=MACHINE, now_fn=clock, cache_seconds=0)


# -- signature / parsing -------------------------------------------------

def test_valid_key_verifies(keypair):
    payload = licensing.verify_license_text(make_key(keypair[0]), keypair[1])
    assert payload['licensee'] == 'Test School'
    assert payload['_expires'] == date(2026, 12, 31)


def test_key_survives_pasted_line_breaks(keypair):
    key = make_key(keypair[0])
    wrapped = '\n'.join(key[i:i + 60] for i in range(0, len(key), 60))
    assert licensing.verify_license_text(wrapped, keypair[1])['license_id'] == 'LIC-TEST-0001'


def test_tampered_payload_is_rejected(keypair):
    prefix, payload_b64, signature = make_key(keypair[0]).split('.')
    forged = json.loads(licensing.b64u_decode(payload_b64))
    forged['expires'] = '2099-12-31'
    forged_b64 = licensing.b64u_encode(json.dumps(forged, separators=(',', ':')).encode())
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text(f'{prefix}.{forged_b64}.{signature}', keypair[1])
    assert err.value.code == 'bad_signature'


def test_key_signed_by_someone_else_is_rejected(keypair):
    attacker = Ed25519PrivateKey.generate()
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text(make_key(attacker), keypair[1])
    assert err.value.code == 'bad_signature'


@pytest.mark.parametrize('text', ['', 'hello', 'SM1.abc', 'XX1.abc.def', 'SM1.!!!.???'])
def test_garbage_is_malformed(keypair, text):
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text(text, keypair[1])
    assert err.value.code == 'malformed'


def test_missing_public_key_is_reported():
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text('SM1.a.b', '')
    assert err.value.code == 'no_public_key'


def test_wrong_product_rejected(keypair):
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text(make_key(keypair[0], product='other-app'), keypair[1])
    assert err.value.code == 'wrong_product'


# -- activation / machine binding ----------------------------------------

def test_activation_installs_license(manager, keypair):
    assert manager.status().state == licensing.UNLICENSED
    status = manager.activate(make_key(keypair[0]))
    assert status.state == licensing.ACTIVE and not status.read_only
    assert manager.license_path.exists()
    assert manager.status().licensee == 'Test School'


def test_license_for_another_machine_is_refused(manager, keypair):
    with pytest.raises(LicenseError) as err:
        manager.activate(make_key(keypair[0], machine=OTHER_MACHINE))
    assert err.value.code == 'wrong_machine'
    assert not manager.license_path.exists()


def test_copying_license_file_to_another_machine_locks_it(tmp_path, keypair, clock, manager):
    manager.activate(make_key(keypair[0]))
    copied = LicenseManager(manager.license_path, tmp_path / 'other.state', keypair[1],
                            machine_code=OTHER_MACHINE, now_fn=clock, cache_seconds=0)
    status = copied.status()
    assert status.state == licensing.INVALID and status.read_only
    assert status.reason == 'wrong_machine'


def test_long_expired_license_cannot_be_activated(manager, keypair, clock):
    clock.set(datetime(2027, 6, 1))
    with pytest.raises(LicenseError) as err:
        manager.activate(make_key(keypair[0]))
    assert err.value.code == 'expired'


# -- lifecycle -----------------------------------------------------------

def test_lifecycle_active_expiring_grace_expired(manager, keypair, clock):
    manager.activate(make_key(keypair[0]))                    # expires 2026-12-31, 7 days grace

    clock.set(datetime(2026, 6, 1))
    status = manager.status()
    assert status.state == licensing.ACTIVE and not status.expiring_soon

    clock.set(datetime(2026, 12, 15))
    status = manager.status()
    assert status.state == licensing.ACTIVE and status.expiring_soon and status.days_left == 16

    clock.set(datetime(2026, 12, 31, 23, 0))                  # last valid day
    assert manager.status().state == licensing.ACTIVE

    clock.set(datetime(2027, 1, 3))
    status = manager.status()
    assert status.state == licensing.GRACE and not status.read_only

    clock.set(datetime(2027, 1, 8))                           # grace ends 2027-01-07
    status = manager.status()
    assert status.state == licensing.EXPIRED and status.read_only


def test_renewal_reactivates(manager, keypair, clock):
    manager.activate(make_key(keypair[0]))
    clock.set(datetime(2027, 3, 1))
    assert manager.status().read_only
    renewed = make_key(keypair[0], license_id='LIC-TEST-0002', issued=date(2027, 3, 1),
                       expires=date(2028, 2, 28))
    status = manager.activate(renewed)
    assert status.state == licensing.ACTIVE and not status.read_only


# -- clock protection ----------------------------------------------------

def test_rolling_clock_back_does_not_revive_expired_license(manager, keypair, clock):
    manager.activate(make_key(keypair[0]))
    clock.set(datetime(2027, 3, 1))
    assert manager.status().state == licensing.EXPIRED

    clock.set(datetime(2026, 6, 1))                           # user winds the clock back
    status = manager.status()
    assert status.state == licensing.EXPIRED and status.read_only
    assert status.clock_rollback is True


def test_clock_before_issue_date_gives_no_extra_time(manager, keypair, clock):
    clock.set(datetime(2015, 1, 1))                           # dead CMOS battery
    manager.activate(make_key(keypair[0]))
    status = manager.status()
    assert status.state == licensing.ACTIVE
    assert status.days_left == (date(2026, 12, 31) - date(2026, 1, 10)).days


def test_wrong_future_clock_is_recovered_by_replacement_key(manager, keypair, clock):
    manager.activate(make_key(keypair[0]))
    clock.set(datetime(2030, 1, 1))                           # someone typed the wrong year once
    assert manager.status().state == licensing.EXPIRED
    clock.set(datetime(2026, 2, 1))                           # clock corrected...
    status = manager.status()
    assert status.state == licensing.EXPIRED and status.clock_rollback   # ...but the mark stays

    # The vendor re-issues the same license under a new id; activating it resets the mark.
    replacement = make_key(keypair[0], license_id='LIC-TEST-0001-R1')
    status = manager.activate(replacement)
    assert status.state == licensing.ACTIVE and not status.clock_rollback


def test_tampered_state_file_is_ignored_not_fatal(manager, keypair, clock):
    manager.activate(make_key(keypair[0]))
    manager.state_path.write_text('{"license_id": "LIC-TEST-0001", "hwm": "2020-01-01T00:00:00", "sig": "bad"}')
    assert manager.status().state == licensing.ACTIVE
    manager.state_path.write_text('not json at all')
    assert manager.status().state == licensing.ACTIVE


def test_enforcement_off_never_locks(tmp_path, keypair):
    disabled = LicenseManager(tmp_path / 'l.key', tmp_path / 'l.state', keypair[1],
                              enforced=False, machine_code=MACHINE, cache_seconds=0)
    status = disabled.status()
    assert status.state == licensing.DISABLED and not status.read_only


# -- the vendor tool -----------------------------------------------------

def test_tool_and_app_agree_on_format(keypair):
    key = tool.sign_license(keypair[0], {
        'v': 1, 'product': licensing.PRODUCT, 'license_id': 'LIC-X', 'licensee': 'X',
        'machine_id': MACHINE, 'issued': '2026-01-01', 'expires': '2026-12-31', 'grace_days': 3})
    assert licensing.verify_license_text(key, keypair[1])['_grace_days'] == 3


# -- HTTP behaviour: activation flow and read-only lockout ---------------

@pytest.fixture()
def licensed_app_factory(tmp_path, keypair, clock, fresh_app_factory):
    """An app with enforcement ON, its own database and its own license folder."""
    def _make(seed=True):
        application = fresh_app_factory(tmp_path, 'licensed.db', {
            'LICENSE_ENFORCEMENT': True,
            'LICENSE_PUBLIC_KEY': keypair[1],
            'LICENSE_DIR': str(tmp_path / 'lic'),
            'LICENSE_MACHINE_CODE': MACHINE,
            'LICENSE_NOW_FN': clock,
            'LICENSE_CACHE_SECONDS': 0,
        })
        with application.app_context():
            db.drop_all()
            db.create_all()
            if seed:
                application.config['SEED_DATA'] = seed_reference_data()
        return application
    return _make


def test_fresh_install_requires_activation_before_setup(licensed_app_factory, keypair):
    application = licensed_app_factory(seed=False)
    client = application.test_client()

    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302 and response.headers['Location'].endswith('/license')
    assert client.get('/setup-admin', follow_redirects=False).headers['Location'].endswith('/license')

    page = client.get('/license')
    assert page.status_code == 200 and MACHINE.encode() in page.data

    bad = client.post('/license', data={'license_key': 'nonsense'})
    assert bad.status_code == 400

    good = client.post('/license', data={'license_key': make_key(keypair[0])}, follow_redirects=False)
    assert good.status_code == 302 and good.headers['Location'].endswith('/setup-admin')
    assert client.get('/setup-admin').status_code == 200


def test_license_page_is_admin_only_after_setup(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(make_key(keypair[0]))

    anonymous = application.test_client()
    response = anonymous.get('/license', follow_redirects=False)
    assert response.status_code == 302 and '/login' in response.headers['Location']
    assert anonymous.post('/license', data={'license_key': make_key(keypair[0])},
                          follow_redirects=False).status_code == 302

    teacher = application.test_client()
    login(teacher, 'teacher', TEACHER_PASSWORD)
    assert teacher.get('/license').status_code == 403

    admin = application.test_client()
    login(admin, 'admin', ADMIN_PASSWORD)
    assert admin.get('/license').status_code == 200


def _expire(application, keypair, clock):
    """Activate, then let time run past expiry and the grace period."""
    manager = application.extensions['license_manager']
    if manager.status().state != licensing.ACTIVE:
        manager.activate(make_key(keypair[0]))
    clock.set(datetime(2027, 3, 1))
    assert manager.status().read_only


def test_read_only_lockout_blocks_writes_but_not_reads(licensed_app_factory, keypair, clock):
    application = licensed_app_factory()
    seed = application.config['SEED_DATA']
    application.extensions['license_manager'].activate(make_key(keypair[0]))
    # A school that has been using the system has already opened this month's fees.
    warm = application.test_client()
    login(warm, 'admin', ADMIN_PASSWORD)
    assert warm.get('/fees?class_id=%d&month_year=January 2026' % seed['class_id']).status_code == 200
    _expire(application, keypair, clock)
    client = application.test_client()

    # Login must keep working, otherwise the school could not even reach the renewal page.
    assert login(client, 'admin', ADMIN_PASSWORD).status_code == 302

    # Reading and exporting stay available.
    for path in ('/', '/students', '/classes', '/fees?class_id=%d&month_year=January 2026' % seed['class_id'],
                 '/students/export/csv', '/audit-log'):
        assert client.get(path).status_code == 200, path

    # Writes are refused and nothing is saved.
    with application.app_context():
        before = ClassModel.query.count()
    blocked = client.post('/classes/add', data={'name': 'Class 9'})
    assert blocked.status_code == 403 and b'Read-only mode' in blocked.data
    with application.app_context():
        assert ClassModel.query.count() == before

    api = client.post('/api/whatsapp/test', json={'phone': '03001234567'})
    assert api.status_code == 403 and api.get_json()['error'] == 'license_read_only'

    # Protecting data and renewing are still allowed.
    assert client.get('/license').status_code == 200
    backup = client.post('/settings/backups/run', follow_redirects=False)
    assert backup.status_code == 302


def test_backstop_blocks_get_pages_that_write(licensed_app_factory, keypair, clock):
    """/fees creates charge rows on GET for a month not yet opened."""
    application = licensed_app_factory()
    seed = application.config['SEED_DATA']
    _expire(application, keypair, clock)
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)

    from app.models import FeeRecordModel
    response = client.get('/fees?class_id=%d&month_year=August 2027' % seed['class_id'])
    assert response.status_code == 403
    with application.app_context():
        assert FeeRecordModel.query.filter_by(month_year='August 2027').count() == 0


def test_teacher_sees_read_only_banner_without_license_details(licensed_app_factory, keypair, clock):
    application = licensed_app_factory()
    _expire(application, keypair, clock)
    client = application.test_client()
    login(client, 'teacher', TEACHER_PASSWORD)
    page = client.get('/students')
    assert b'Read-only mode' in page.data and b'Manage license' not in page.data


def test_grace_period_still_allows_writes_with_warning(licensed_app_factory, keypair, clock):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(make_key(keypair[0]))
    clock.set(datetime(2027, 1, 3))                            # inside the 7-day grace
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    assert client.post('/classes/add', data={'name': 'Class 9'}, follow_redirects=False).status_code == 302
    assert b'grace period' in client.get('/').data


def test_whatsapp_bridge_gets_empty_queue_when_locked(licensed_app_factory, keypair, clock):
    application = licensed_app_factory()
    _expire(application, keypair, clock)
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    assert client.get('/api/whatsapp/pending').get_json() == {'items': []}


def test_activation_is_written_to_audit_log(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    client.post('/license', data={'license_key': make_key(keypair[0])})
    with application.app_context():
        assert AuditLog.query.filter(AuditLog.summary.like('License LIC-TEST-0001 activated%')).count() == 1

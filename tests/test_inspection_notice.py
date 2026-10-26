"""Inspection keys (short, view-only), the vendor's notice and the expiry reminders."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import features as feature_catalog
from app.services import licensing
from app.services.licensing import LicenseError, LicenseManager, reminder_stage
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (MACHINE, T0, clock, keypair, licensed_app_factory,  # noqa: F401
                                      make_key, tool)
from tests.test_vendor_dashboard import browser, env, _new_school  # noqa: F401

ALL = list(feature_catalog.ALL_FEATURES)


def _ts(moment):
    return int(moment.replace(tzinfo=timezone.utc).timestamp())


def _inspection(private, now, *, hours=24, license_id='LIC-TEST-0001', machine=MACHINE, iid='INS-1'):
    return licensing.sign_inspection(private, inspection_id=iid, license_id=license_id,
                                     licensee='Test School', machine_code=machine,
                                     issued_ts=_ts(now), hours=hours)


@pytest.fixture()
def manager(tmp_path, keypair, clock):  # noqa: F811
    return LicenseManager(tmp_path / 'license.key', tmp_path / 'license.state', keypair[1],
                          machine_code=MACHINE, now_fn=clock, cache_seconds=0)


# ---- reminders and notice --------------------------------------------------------------

@pytest.mark.parametrize('days, stage', [(45, None), (31, None), (30, 30), (20, 30), (14, 14), (10, 14),
                                         (7, 7), (5, 7), (3, 3), (2, 3), (1, 1), (0, 1), (-1, None)])
def test_reminder_stage(days, stage):
    assert reminder_stage(days) == stage


def test_notice_travels_in_the_signed_key_and_is_trimmed(manager, keypair):
    key = make_key(keypair[0], features=ALL, notice='  Renewal   due on 25 Oct  ')
    status = manager.activate(key)
    assert status.notice == 'Renewal due on 25 Oct'


def test_a_key_without_a_notice_has_none(manager, keypair):
    assert manager.activate(make_key(keypair[0], features=ALL)).notice == ''


def test_a_long_notice_is_cut(keypair):
    key = make_key(keypair[0], features=ALL, notice='x' * 1000)
    payload = licensing.verify_license_text(key, keypair[1])
    assert len(payload['_notice']) == licensing.NOTICE_MAX_LENGTH


def test_status_reports_the_reminder_stage(manager, keypair, clock):  # noqa: F811
    manager.activate(make_key(keypair[0], features=ALL, expires=date(2026, 1, 15)))   # 5 days from T0
    status = manager.status(force=True)
    assert status.days_left == 5 and status.reminder_stage == 7
    clock.set(T0 + timedelta(days=4))
    assert manager.status(force=True).reminder_stage == 1


# ---- inspection key --------------------------------------------------------------------

def test_inspection_key_makes_everything_visible_but_read_only(manager, keypair, clock):  # noqa: F811
    manager.activate(make_key(keypair[0], features=['expenses']))
    assert not manager.status(force=True).feature_enabled('payroll')
    status = manager.activate_inspection(_inspection(keypair[0], clock.now))
    assert status.inspection and status.read_only
    assert status.feature_enabled('payroll') and status.feature_enabled('audit_log_view')
    assert status.role_enabled('accountant')
    # the real license is untouched
    real = manager.status(force=True, inspection=False)
    assert not real.inspection and not real.read_only and not real.feature_enabled('payroll')


def test_inspection_key_ends_by_itself(manager, keypair, clock):  # noqa: F811
    manager.activate(make_key(keypair[0], features=['expenses']))
    manager.activate_inspection(_inspection(keypair[0], clock.now, hours=24))
    clock.set(T0 + timedelta(hours=23))
    assert manager.status(force=True).inspection
    clock.set(T0 + timedelta(hours=25))
    status = manager.status(force=True)
    assert not status.inspection and not status.read_only


def test_rolling_the_clock_back_does_not_revive_an_inspection_key(manager, keypair, clock):  # noqa: F811
    manager.activate(make_key(keypair[0], features=['expenses']))
    manager.activate_inspection(_inspection(keypair[0], clock.now, hours=2))
    clock.set(T0 + timedelta(hours=3))
    assert not manager.status(force=True).inspection
    clock.set(T0 + timedelta(minutes=30))             # clock turned back
    assert not manager.status(force=True).inspection


def test_inspection_key_is_not_a_license_and_a_license_is_not_an_inspection_key(manager, keypair, clock):  # noqa: F811
    inspection = _inspection(keypair[0], clock.now)
    with pytest.raises(LicenseError):
        manager.activate(inspection)
    with pytest.raises(LicenseError):
        manager.activate_inspection(make_key(keypair[0], features=ALL))
    assert manager.status(force=True).state == licensing.UNLICENSED


def test_inspection_key_checks_machine_license_and_signature(manager, keypair, clock):  # noqa: F811
    manager.activate(make_key(keypair[0], features=ALL))
    with pytest.raises(LicenseError) as err:
        manager.activate_inspection(_inspection(keypair[0], clock.now, machine='AAAA-AAAA-AAAA-AAAA'))
    assert err.value.code == 'wrong_machine'
    with pytest.raises(LicenseError) as err:
        manager.activate_inspection(_inspection(keypair[0], clock.now, license_id='LIC-OTHER'))
    assert err.value.code == 'wrong_license'
    good = _inspection(keypair[0], clock.now)
    with pytest.raises(LicenseError) as err:
        manager.activate_inspection(good[:-4] + 'AAAA')
    assert err.value.code == 'bad_signature'
    with pytest.raises(LicenseError) as err:
        manager.activate_inspection(_inspection(keypair[0], clock.now - timedelta(hours=30), hours=24))
    assert err.value.code == 'expired'


def test_inspection_length_is_capped(keypair):
    key = licensing.sign_inspection(keypair[0], inspection_id='INS-X', license_id='', licensee='x',
                                    machine_code=MACHINE, issued_ts=1_800_000_000, hours=10_000)
    data = licensing.verify_inspection_text(key, keypair[1])
    assert data['expires_ts'] - data['issued_ts'] == licensing.INSPECTION_MAX_HOURS * 3600


def test_ending_an_inspection_returns_to_the_license(manager, keypair, clock):  # noqa: F811
    manager.activate(make_key(keypair[0], features=['expenses']))
    manager.activate_inspection(_inspection(keypair[0], clock.now))
    status = manager.end_inspection()
    assert not status.inspection and not status.feature_enabled('payroll')


# ---- in the running application ---------------------------------------------------------

def test_inspection_mode_blocks_changes_and_shows_a_banner(licensed_app_factory, keypair, clock):  # noqa: F811
    application = licensed_app_factory()
    manager = application.extensions['license_manager']
    manager.activate(make_key(keypair[0], features=['expenses']))
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    manager.activate_inspection(_inspection(keypair[0], clock.now))

    page = client.get('/license').get_data(as_text=True)
    assert 'Inspection mode' in page
    assert client.get('/audit-log').status_code == 200            # visible: not in the license's features
    blocked = client.post('/students/add', data={'roll_number': '9', 'student_name': 'X'})
    assert blocked.status_code == 403                              # nothing can be changed

    client.post('/license', data={'action': 'end_inspection'})
    # The "Inspection mode ended." flash message also contains the words "Inspection mode",
    # so check the banner text itself rather than the bare phrase.
    after = client.get('/license').get_data(as_text=True)
    assert 'Inspection mode is on' not in after
    assert '<strong>Inspection mode.</strong>' not in after       # the banner is gone too


# ---- vendor dashboard ----------------------------------------------------------------------

def test_dashboard_issues_inspection_keys(browser, env):  # noqa: F811
    school_id = _new_school(browser)
    response = browser.post(f'/schools/{school_id}/inspection', data={'hours': '24'})
    assert response.status_code == 302 and '/inspections/' in response.headers['Location']
    page = browser.get(response.headers['Location']).get_data(as_text=True)
    assert 'SMI1.' in page
    refused = browser.post(f'/schools/{school_id}/inspection', data={'hours': '5'})
    assert refused.status_code == 302 and '/schools/' in refused.headers['Location']

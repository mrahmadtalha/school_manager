"""Feature switches carried by the signed license key."""

import json
from datetime import date

import pytest
from flask import url_for

from app.services import licensing
from app.services.licensing import LicenseError
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (MACHINE, clock, keypair, licensed_app_factory,  # noqa: F401
                                      make_key, tool)


def test_legacy_key_has_everything_on(keypair):
    legacy = tool.build_payload(license_id='LIC-OLD', licensee='Old School', machine_code=MACHINE,
                                issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7)
    legacy.pop('rev')                       # keys issued before this release have no rev
    payload = licensing.verify_license_text(tool.sign_license(keypair[0], legacy), keypair[1])
    assert payload['_features'] is None and payload['_limits'] == {} and payload['_rev'] == 0


def test_features_limits_rev_and_plan_are_parsed(keypair):
    key = make_key(keypair[0], rev=3, plan='standard', features=['expenses', 'payroll'],
                   wa_daily=100, wa_monthly=2000)
    payload = licensing.verify_license_text(key, keypair[1])
    assert payload['_features'] == ('expenses', 'payroll')
    assert payload['_limits'] == {'wa_daily': 100, 'wa_monthly': 2000}
    assert payload['_rev'] == 3 and payload['_plan'] == 'standard'


def test_features_cannot_be_edited_without_breaking_the_signature(keypair):
    prefix, body, signature = make_key(keypair[0], features=['expenses']).split('.')
    forged = json.loads(licensing.b64u_decode(body))
    forged['features'] = ['expenses', 'payroll', 'whatsapp']
    forged_b64 = licensing.b64u_encode(json.dumps(forged, separators=(',', ':')).encode())
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text(f'{prefix}.{forged_b64}.{signature}', keypair[1])
    assert err.value.code == 'bad_signature'


@pytest.mark.parametrize('extra', [{'features': 'expenses'}, {'limits': {'wa_daily': 'many'}}])
def test_malformed_feature_fields_are_rejected(keypair, extra):
    key = tool.sign_license(keypair[0], {**tool.build_payload(
        license_id='LIC-X', licensee='X', machine_code=MACHINE, issued=date(2026, 1, 10),
        expires=date(2026, 12, 31), grace_days=7), **extra})
    with pytest.raises(LicenseError) as err:
        licensing.verify_license_text(key, keypair[1])
    assert err.value.code == 'malformed'


def test_older_revision_is_refused_but_newer_is_accepted(tmp_path, keypair, clock):
    manager = licensing.LicenseManager(tmp_path / 'license.key', tmp_path / 'license.state',
                                       keypair[1], machine_code=MACHINE, now_fn=clock,
                                       cache_seconds=0)
    manager.activate(make_key(keypair[0], rev=2, features=['expenses']))
    with pytest.raises(LicenseError) as err:
        manager.activate(make_key(keypair[0], rev=1, features=['expenses', 'payroll']))
    assert err.value.code == 'older_key'
    assert manager.status().rev == 2
    manager.activate(make_key(keypair[0], rev=3, features=['expenses', 'payroll']))
    status = manager.status()
    assert status.rev == 3 and status.feature_enabled('payroll')


def test_a_different_license_id_is_not_blocked_by_revision(tmp_path, keypair, clock):
    manager = licensing.LicenseManager(tmp_path / 'license.key', tmp_path / 'license.state',
                                       keypair[1], machine_code=MACHINE, now_fn=clock,
                                       cache_seconds=0)
    manager.activate(make_key(keypair[0], rev=5))
    manager.activate(make_key(keypair[0], rev=1, license_id='LIC-OTHER-0002'))
    assert manager.status().license_id == 'LIC-OTHER-0002'


def test_disabled_feature_is_blocked_and_hidden(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(
        make_key(keypair[0], rev=1, features=['attendance', 'exams']))
    admin = application.test_client()
    login(admin, 'admin', ADMIN_PASSWORD)

    blocked = admin.get('/expenses')
    assert blocked.status_code == 403 and b'Not included in your plan' in blocked.data
    assert admin.get('/payroll').status_code == 403
    assert admin.get('/automation').status_code == 403
    assert admin.get('/students').status_code == 200

    with application.test_request_context():
        expenses_url = url_for('main.expenses_list')
        attendance_url = url_for('main.student_attendance')
    page = admin.get('/students')
    assert f'href="{expenses_url}"'.encode() not in page.data
    assert f'href="{attendance_url}"'.encode() in page.data


def test_legacy_key_keeps_every_feature(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(make_key(keypair[0]))
    admin = application.test_client()
    login(admin, 'admin', ADMIN_PASSWORD)
    assert admin.get('/expenses').status_code == 200
    assert admin.get('/payroll').status_code == 200


def test_license_page_lists_features_and_plan(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(
        make_key(keypair[0], rev=2, plan='standard', features=['attendance'], wa_daily=10))
    admin = application.test_client()
    login(admin, 'admin', ADMIN_PASSWORD)
    page = admin.get('/license')
    assert b'Included features' in page.data and b'Standard' in page.data


def test_whatsapp_feature_off_stops_the_bridge_quietly(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(
        make_key(keypair[0], rev=1, features=['attendance']))
    admin = application.test_client()
    login(admin, 'admin', ADMIN_PASSWORD)
    response = admin.get('/api/whatsapp/pending')
    assert response.status_code == 200 and response.get_json() == {'items': []}

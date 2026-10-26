"""User-role switches and the newer feature switches (data export, Urdu switch, audit log viewer)."""
from datetime import date

import pytest

from app.database import db
from app.models import AdminUser
from app.services import features as feature_catalog
from app.services import licensing
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (MACHINE, clock, keypair, licensed_app_factory,  # noqa: F401
                                      make_key, tool)
from tests.test_vendor_dashboard import (browser, env, _issue, _key_text,  # noqa: F401
                                         _new_school)

ALL = list(feature_catalog.ALL_FEATURES)


def _without(*names):
    return [key for key in ALL if key not in names]


def _admin(application, key_text):
    application.extensions['license_manager'].activate(key_text)
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    return client


# ---- licensing -----------------------------------------------------------------------

def test_legacy_key_allows_every_role(keypair):
    payload = tool.build_payload(license_id='LIC-OLD', licensee='Old', machine_code=MACHINE,
                                 issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7)
    parsed = licensing.verify_license_text(tool.sign_license(keypair[0], payload), keypair[1])
    assert parsed['_roles'] is None


def test_roles_are_parsed_and_admin_is_always_on(keypair):
    parsed = licensing.verify_license_text(
        make_key(keypair[0], features=ALL, roles=['teacher']), keypair[1])
    assert parsed['_roles'] == ('admin', 'teacher')
    base = dict(state='active', read_only=False, level='ok', title='', message='', machine_code=MACHINE)
    status = licensing.LicenseStatus(roles=parsed['_roles'], **base)
    assert status.role_enabled('admin') and status.role_enabled('teacher')
    assert not status.role_enabled('accountant') and not status.role_enabled('parent')
    assert licensing.LicenseStatus(roles=None, **base).role_enabled('parent')


def test_a_key_with_a_bad_roles_field_is_refused(keypair):
    key = tool.sign_license(keypair[0], {**tool.build_payload(
        license_id='LIC-X', licensee='X', machine_code=MACHINE, issued=date(2026, 1, 10),
        expires=date(2026, 12, 31), grace_days=7), 'roles': 'teacher'})
    with pytest.raises(licensing.LicenseError):
        licensing.verify_license_text(key, keypair[1])


def test_keys_issued_before_the_new_features_keep_them_on(keypair):
    old = tool.build_payload(license_id='LIC-OLD2', licensee='Old', machine_code=MACHINE,
                             issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7,
                             features=['expenses'])
    old.pop('fv')                                    # a key made before the catalog grew
    parsed = licensing.verify_license_text(tool.sign_license(keypair[0], old), keypair[1])
    assert {'expenses', 'data_export', 'language_switch', 'audit_log_view'} <= set(parsed['_features'])
    new = licensing.verify_license_text(
        make_key(keypair[0], features=['expenses']), keypair[1])
    assert new['_features'] == ('expenses',)         # a new key lists exactly what is on


# ---- app: new feature switches ---------------------------------------------------------

def test_data_export_switch_closes_every_export(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=_without('data_export')))
    exports = [r.rule for r in application.url_map.iter_rules()
               if 'GET' in r.methods and '<' not in r.rule and feature_catalog.is_export_endpoint(r.endpoint)]
    assert exports, 'the app has export pages'
    for path in exports:
        resp = client.get(path)
        assert resp.status_code == 403, path
    on = _admin(licensed_app_factory(), make_key(keypair[0], rev=1, features=ALL))
    assert all(on.get(p).status_code != 403 for p in exports)


def test_audit_log_viewer_switch(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=_without('audit_log_view')))
    assert client.get('/audit-log').status_code == 403
    assert b'/audit-log' not in client.get('/students').data
    on = _admin(licensed_app_factory(), make_key(keypair[0], rev=1, features=ALL))
    assert on.get('/audit-log').status_code == 200 and b'/audit-log' in on.get('/students').data


def test_audit_trail_is_still_recorded_when_the_viewer_is_off(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=_without('audit_log_view')))
    with application.app_context():
        before = db.session.execute(db.text('SELECT COUNT(*) FROM audit_logs')).scalar()
    client.post('/settings', data={'action': 'save_general_info', 'school_name': 'Recorded School'})
    with application.app_context():
        after = db.session.execute(db.text('SELECT COUNT(*) FROM audit_logs')).scalar()
    assert after > before


def test_language_switch_follows_the_license(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=_without('language_switch')))
    assert b'/language/ur' not in client.get('/students').data
    client.get('/language/ur')
    assert b'dir="rtl"' not in client.get('/students').data          # stays English
    on = _admin(licensed_app_factory(), make_key(keypair[0], rev=1, features=ALL))
    assert b'/language/ur' in on.get('/students').data
    on.get('/language/ur')
    assert b'dir="rtl"' in on.get('/students').data


# ---- app: role switches ----------------------------------------------------------------

def _add_user(application, username, role):
    with application.app_context():
        user = AdminUser(username=username, role=role, full_name=username.title())
        user.set_password('Passw0rd!xx')
        db.session.add(user)
        db.session.commit()


def test_a_switched_off_role_is_signed_out_with_a_message(licensed_app_factory, keypair):
    application = licensed_app_factory()
    application.extensions['license_manager'].activate(
        make_key(keypair[0], rev=1, features=ALL, roles=['teacher']))
    _add_user(application, 'acct1', 'accountant')
    _add_user(application, 'teach1', 'teacher')

    acct = application.test_client()
    login(acct, 'acct1', 'Passw0rd!xx')
    resp = acct.get('/students', follow_redirects=True)
    assert b'not included in this school' in resp.data and b'Accountant' in resp.data
    assert acct.get('/students').status_code == 302               # still signed out

    teacher = application.test_client()
    login(teacher, 'teach1', 'Passw0rd!xx')
    assert teacher.get('/students').status_code in (200, 302) and b'not included' not in teacher.get(
        '/students', follow_redirects=True).data


def test_a_switched_off_role_cannot_be_created_or_chosen(licensed_app_factory, keypair):
    application = licensed_app_factory()
    admin = _admin(application, make_key(keypair[0], rev=1, features=ALL, roles=['teacher']))
    page = admin.get('/users').data.decode()
    assert '<option value="teacher">' in page and '<option value="accountant">' not in page
    resp = admin.post('/users/create', data={'username': 'newacct', 'password': 'Passw0rd!xx',
                                             'role': 'accountant', 'full_name': 'New'},
                      follow_redirects=True)
    assert b'not included in this school' in resp.data
    with application.app_context():
        assert AdminUser.query.filter_by(username='newacct').first() is None


def test_legacy_key_allows_all_roles_in_the_app(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _admin(application, make_key(keypair[0]))
    _add_user(application, 'acct2', 'accountant')
    client = application.test_client()
    login(client, 'acct2', 'Passw0rd!xx')
    assert b'not included in this school' not in client.get('/', follow_redirects=True).data


# ---- vendor dashboard ------------------------------------------------------------------

def test_vendor_dashboard_issues_roles_and_new_features(env, browser):
    school_id = _new_school(browser)
    key = _key_text(browser, _issue(
        browser, school_id, roles_present='1', roles=['teacher', 'accountant'],
        features=['attendance', 'data_export']))
    payload = licensing.verify_license_text(key, env[1])
    assert payload['_roles'] == ('accountant', 'admin', 'teacher')
    assert payload['_features'] == ('attendance', 'data_export')
    page = browser.get(f'/schools/{school_id}').data.decode()
    assert 'name="roles"' in page and 'Audit Log is always' in page and 'Urdu / English switch' in page


def test_vendor_dashboard_without_roles_section_keeps_all_roles(env, browser):
    school_id = _new_school(browser)
    payload = licensing.verify_license_text(_key_text(browser, _issue(browser, school_id)), env[1])
    assert payload['_roles'] is None


def test_vendor_default_plans_know_the_new_features(env):
    plans = feature_catalog.DEFAULT_PLANS
    assert 'data_export' in plans['standard']['features'] and 'language_switch' in plans['premium']['features']

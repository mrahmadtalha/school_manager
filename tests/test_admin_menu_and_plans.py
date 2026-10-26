"""The administrator's menu must not depend on license features; dashboard keys must be what was typed."""
from datetime import date

from app.services import features as feature_catalog
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (MACHINE, T0, clock, keypair, licensed_app_factory,  # noqa: F401
                                      make_key, tool)
from vendor_dashboard import issuer
from vendor_dashboard.store import Store


def test_admin_always_sees_users_settings_and_license_links(licensed_app_factory, keypair, clock):  # noqa: F811
    """Before: Users & Roles, School Settings and License hid together with the Audit Log link."""
    application = licensed_app_factory()
    manager = application.extensions['license_manager']
    features = [name for name in feature_catalog.ALL_FEATURES if name != 'audit_log_view']
    manager.activate(make_key(keypair[0], features=features))
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)

    page = client.get('/license').get_data(as_text=True)
    assert 'Users &amp; Roles' in page
    assert 'School Settings' in page
    assert '<span class="nav-label">License</span>' in page
    assert '<span class="nav-label">Audit Log</span>' not in page      # still follows its feature

    assert client.get('/users').status_code == 200


def test_audit_log_link_shows_when_the_license_includes_it(licensed_app_factory, keypair, clock):  # noqa: F811
    application = licensed_app_factory()
    manager = application.extensions['license_manager']
    manager.activate(make_key(keypair[0], features=list(feature_catalog.ALL_FEATURES)))
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    page = client.get('/license').get_data(as_text=True)
    assert '<span class="nav-label">Audit Log</span>' in page
    assert 'Users &amp; Roles' in page


def test_typed_custom_expiry_wins_over_the_validity_dropdown():
    today = date(2026, 10, 14)
    typed = date(2026, 10, 22)
    assert issuer.compute_expiry('1y', typed, date(2030, 10, 18), today) == typed
    assert issuer.compute_expiry('keep', typed, date(2030, 10, 18), today) == typed
    assert issuer.compute_expiry('custom', typed, None, today) == typed
    # no typed date: the dropdown works as before
    assert issuer.compute_expiry('keep', None, date(2027, 1, 1), today) == date(2027, 1, 1)


def test_premium_plan_picks_up_features_added_later(tmp_path):
    store = Store(tmp_path)
    store.seed_plans({'premium': {'label': 'Premium', 'features': ['attendance'],
                                  'wa_daily': 0, 'wa_monthly': 0}})
    store.sync_premium_plan(feature_catalog.ALL_FEATURES)
    plan = [p for p in store.plans() if p['name'] == 'premium'][0]
    assert plan['features'] == list(feature_catalog.ALL_FEATURES)

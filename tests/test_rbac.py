"""Role-based access control checks."""

import pytest

from app.models import ROLE_ACCOUNTANT, ROLE_ADMIN, ROLE_TEACHER
from app.security import PUBLIC_ENDPOINTS, ROUTE_ROLES, role_allowed
from tests.conftest import ADMIN_PASSWORD, PARENT_PASSWORD, TEACHER_PASSWORD, login


def test_anonymous_is_redirected_from_protected_pages(client):
    for path in ('/', '/students', '/attendance/students', '/fees', '/audit-log', '/users'):
        response = client.get(path)
        assert response.status_code == 302, path
        assert '/login' in response.location, path


def test_admin_can_reach_every_core_module(admin_client):
    for path in ('/', '/students', '/teachers', '/classes', '/attendance/students',
                 '/tests', '/fees', '/fees/reconciliation', '/reports/hub',
                 '/documents', '/settings', '/users', '/audit-log'):
        response = admin_client.get(path)
        assert response.status_code == 200, f'{path} -> {response.status_code}'


def test_teacher_can_reach_academic_modules(teacher_client):
    for path in ('/', '/students', '/teachers', '/classes', '/attendance/students',
                 '/tests', '/reports/hub', '/documents'):
        response = teacher_client.get(path)
        assert response.status_code == 200, f'{path} -> {response.status_code}'


@pytest.mark.parametrize('path', [
    '/fees',
    '/fees/reconciliation',
    '/settings',
    '/automation',
    '/users',
    '/audit-log',
])
def test_teacher_is_blocked_from_administrative_pages(teacher_client, path):
    response = teacher_client.get(path)
    assert response.status_code == 403, f'{path} -> {response.status_code}'


@pytest.mark.parametrize('path', [
    '/students/restore-all',
    '/teachers/restore-all',
])
def test_teacher_is_blocked_from_destructive_bulk_actions(teacher_client, path):
    response = teacher_client.post(path)
    assert response.status_code == 403, f'{path} -> {response.status_code}'


def test_parent_is_sent_to_the_portal_and_cannot_open_admin_pages(parent_client):
    dashboard = parent_client.get('/')
    assert dashboard.status_code == 302
    assert '/portal' in dashboard.location

    assert parent_client.get('/portal').status_code == 200

    for path in ('/students', '/fees', '/users', '/audit-log', '/teachers'):
        response = parent_client.get(path)
        assert response.status_code == 403, f'{path} -> {response.status_code}'


def test_parent_portal_only_exposes_their_own_child(parent_client, app, seed):
    body = parent_client.get('/portal').get_data(as_text=True)
    assert 'Ali Khan' in body          # linked child
    assert 'Sara Ali' not in body      # another family's child


def test_api_requires_authentication_or_bridge_token(client, app):
    anonymous = client.get('/api/whatsapp/pending')
    assert anonymous.status_code == 403

    with app.test_client() as bridge:
        response = bridge.get('/api/whatsapp/status',
                              headers={'X-Bridge-Token': app.config['WHATSAPP_BRIDGE_TOKEN']})
        # No bridge token configured in this test config -> still forbidden.
        assert response.status_code == 403


def test_api_works_for_authenticated_admin(admin_client):
    response = admin_client.get('/api/whatsapp/pending')
    assert response.status_code == 200
    assert 'items' in response.get_json()


def test_healthz_is_public(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True


def test_deny_by_default_for_unknown_endpoints():
    """Anything not explicitly listed is administrator-only."""
    assert role_allowed('main.some_future_page', ROLE_TEACHER) is False
    assert role_allowed('main.some_future_page', ROLE_ADMIN) is True
    assert role_allowed('auth.login', None) is True


def test_public_endpoints_do_not_include_privileged_views():
    # Accountants deliberately get the money modules (ACCOUNTANT_ENDPOINTS in
    # app/security.py); every other privileged view stays administrator-only.
    expected_roles = {
        'main.fees_list': {ROLE_ADMIN, ROLE_ACCOUNTANT},
        'main.users_list': {ROLE_ADMIN},
        'main.audit_log': {ROLE_ADMIN},
        'main.school_settings': {ROLE_ADMIN},
        'main.automation_panel': {ROLE_ADMIN},
    }
    for endpoint, expected in expected_roles.items():
        assert endpoint not in PUBLIC_ENDPOINTS
        assert ROUTE_ROLES.get(endpoint, {ROLE_ADMIN}) == expected


def test_login_as_each_role_works(client):
    for username, password in (('admin', ADMIN_PASSWORD),
                               ('teacher', TEACHER_PASSWORD),
                               ('parent', PARENT_PASSWORD)):
        fresh = client.application.test_client()
        response = login(fresh, username, password)
        assert response.status_code == 302, username

# --------------------------------------------------------------------------- #
# New roles: owner (read-only executive) and accountant (finance modules only)
# --------------------------------------------------------------------------- #

def _make_role_user(app, username, role, password='RolePass123'):
    from app.database import db
    from app.models import AdminUser

    with app.app_context():
        user = AdminUser(username=username, role=role, full_name=username.title())
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def test_accountant_lands_on_fees_and_reaches_finance_modules(app, client):
    _make_role_user(app, 'test_accountant', 'accountant')
    response = login(client, 'test_accountant', 'RolePass123')
    assert response.status_code == 302
    assert response.location.endswith('/fees')

    for path in ('/fees', '/fees/reconciliation', '/expenses', '/payroll',
                 '/financials/summary', '/reports/hub'):
        assert client.get(path).status_code == 200, path

    # `/` bounces to the finance landing
    root = client.get('/')
    assert root.status_code == 302 and root.location.endswith('/fees')


def test_accountant_is_blocked_from_admin_and_academic_pages(app, client):
    _make_role_user(app, 'test_accountant2', 'accountant')
    login(client, 'test_accountant2', 'RolePass123')

    for path in ('/classes', '/settings', '/users', '/audit-log', '/tests',
                 '/teachers', '/documents', '/students'):
        assert client.get(path).status_code == 403, path

    # Admin-only actions inside the money modules stay locked.
    assert client.get('/fees/reminders').status_code == 403
    assert client.post('/fees/class-bulk-update', data={}).status_code == 403
    assert client.post('/expenses/categories/add', data={}).status_code == 403


def test_accountant_hub_is_finance_only(app, client):
    _make_role_user(app, 'test_accountant3', 'accountant')
    login(client, 'test_accountant3', 'RolePass123')

    response = client.get('/reports/hub?tab=academic')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Universal Financial &amp; Fee Exports' in body
    assert 'Academic &amp; Examinations' not in body
    assert 'Students, Staff &amp; Operations' not in body


def test_owner_is_read_only_executive(app, client):
    _make_role_user(app, 'test_owner', 'owner')
    response = login(client, 'test_owner', 'RolePass123')
    assert response.status_code == 302
    assert response.location.endswith('/executive')

    assert client.get('/executive').status_code == 200
    assert client.get('/executive/summary.pdf').status_code == 200

    for path in ('/fees', '/expenses', '/payroll', '/users', '/audit-log',
                 '/classes', '/settings', '/tests', '/reports/hub',
                 '/financials/summary'):
        assert client.get(path).status_code == 403, path

    # Strictly read-only: write endpoints are blocked.
    assert client.post('/students/add', data={}).status_code == 403
    assert client.post('/users/create', data={}).status_code == 403


def test_owner_root_redirects_to_executive(app, client):
    _make_role_user(app, 'test_owner2', 'owner')
    login(client, 'test_owner2', 'RolePass123')
    root = client.get('/')
    assert root.status_code == 302 and root.location.endswith('/executive')


def test_new_roles_can_logout_and_change_password(app):
    _make_role_user(app, 'test_owner3', 'owner')
    owner_client = app.test_client()
    login(owner_client, 'test_owner3', 'RolePass123')
    logout_response = owner_client.get('/logout')
    assert logout_response.status_code == 302

    _make_role_user(app, 'test_accountant4', 'accountant')
    accountant_client = app.test_client()
    login(accountant_client, 'test_accountant4', 'RolePass123')
    response = accountant_client.post('/change-password', data={
        'current_password': 'RolePass123',
        'new_password': 'NewRolePass123',
        'confirm_password': 'NewRolePass123',
    })
    assert response.status_code == 302  # redirect after success - not 403

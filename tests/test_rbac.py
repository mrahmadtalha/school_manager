"""Role-based access control checks."""

import pytest

from app.models import ROLE_ADMIN, ROLE_TEACHER
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
    '/students/delete-all-permanent',
    '/teachers/delete-all-permanent',
    '/students/restore-all',
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
    for endpoint in ('main.fees_list', 'main.users_list', 'main.audit_log',
                     'main.school_settings', 'main.automation_panel'):
        assert endpoint not in PUBLIC_ENDPOINTS
        assert ROUTE_ROLES.get(endpoint, {ROLE_ADMIN}) == {ROLE_ADMIN}


def test_login_as_each_role_works(client):
    for username, password in (('admin', ADMIN_PASSWORD),
                               ('teacher', TEACHER_PASSWORD),
                               ('parent', PARENT_PASSWORD)):
        fresh = client.application.test_client()
        response = login(fresh, username, password)
        assert response.status_code == 302, username

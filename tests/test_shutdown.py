"""Exit Software: sidebar button, confirmation modal and the /shutdown route.

Only administrators may close the shared local server.  The action must stay
available even while the license is read-only (an expired school must always
be able to close the app), and under pytest the process exit is only recorded,
never performed.
"""

from app.database import db
from tests.conftest import TEACHER_PASSWORD, login


def test_shutdown_requires_post(admin_client):
    # Guards run before routing, so an authenticated admin is needed to see 405.
    assert admin_client.get('/shutdown').status_code == 405


def test_shutdown_requires_login(client):
    response = client.post('/shutdown')
    assert response.status_code == 302
    assert '/login' in response.location


def test_shutdown_is_admin_only(client, app):
    login(client, 'teacher', TEACHER_PASSWORD)
    response = client.post('/shutdown')
    assert response.status_code == 403           # role guard denies non-admins
    with app.app_context():
        assert not app.extensions.get('shutdown_requested')


def test_admin_shutdown_renders_goodbye_and_schedules_exit(admin_client, app):
    response = admin_client.post('/shutdown')

    assert response.status_code == 200
    assert 'School Manager is closing' in response.get_data(as_text=True)
    with app.app_context():
        assert app.extensions.get('shutdown_requested') is True
        # Nothing actually exits under pytest: the DB is still usable.
        assert db.session.execute(db.text('SELECT 1')).scalar() == 1


def test_sidebar_shows_exit_button_and_modal_for_admins(admin_client):
    body = admin_client.get('/').get_data(as_text=True)
    assert 'Exit Software' in body
    assert 'exitSoftwareModal' in body
    assert 'Are you sure you want to close School Manager?' in body
    assert 'action="/shutdown"' in body


def test_exit_button_hidden_from_non_admins(client):
    login(client, 'teacher', TEACHER_PASSWORD)
    body = client.get('/').get_data(as_text=True)
    assert 'Exit Software' not in body
    assert 'exitSoftwareModal' not in body

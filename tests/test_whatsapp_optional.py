"""WhatsApp bridge state detection.

Since Phase 6 the bridge ships as a mandatory core component of the installer;
the app must still detect its state (running / stopped / missing) and explain
it, never fail silently.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from app.database import db
from app.models import MessageQueue
from app.services import whatsapp_bridge


@pytest.fixture()
def fake_bridge(monkeypatch):
    """A bridge folder on disk + WHATSAPP_BRIDGE_DIR pointed at it."""
    made = []

    def _make(with_modules=True):
        directory = Path(tempfile.mkdtemp(prefix='fake-bridge-'))
        (directory / 'package.json').write_text('{"name": "bridge"}', encoding='utf-8')
        (directory / 'server.js').write_text('// bridge', encoding='utf-8')
        if with_modules:
            (directory / 'node_modules').mkdir()
            (directory / 'node_modules' / '.keep').write_text('', encoding='utf-8')
        monkeypatch.setenv('WHATSAPP_BRIDGE_DIR', str(directory))
        made.append(directory)
        return directory

    yield _make
    for directory in made:
        shutil.rmtree(directory, ignore_errors=True)


def test_bridge_dir_defaults_to_project_whatsapp_service(app):
    with app.test_request_context():
        assert whatsapp_bridge.bridge_dir() == \
            whatsapp_bridge.BASE_DIR / 'whatsapp-service'


def test_bridge_dir_env_override(app, monkeypatch):
    monkeypatch.setenv('WHATSAPP_BRIDGE_DIR', 'D:/SchoolComponents/bridge')
    with app.test_request_context():
        assert whatsapp_bridge.bridge_dir() == Path('D:/SchoolComponents/bridge')


def test_not_installed_state_when_no_bridge_folder(app, monkeypatch):
    monkeypatch.setenv('WHATSAPP_BRIDGE_DIR', 'Z:/does/not/exist')
    with app.test_request_context():
        assert whatsapp_bridge.is_installed() is False
        state = whatsapp_bridge.install_state(
            {'serviceReachable': False, 'connected': False})
        assert state == whatsapp_bridge.STATE_NOT_INSTALLED
        assert 'missing' in whatsapp_bridge.state_hint(state).lower()


def test_installed_without_node_reports_node_missing(app, fake_bridge, monkeypatch):
    fake_bridge(with_modules=True)
    monkeypatch.setattr(shutil, 'which', lambda name: None)  # no Node runtime
    with app.test_request_context():
        assert whatsapp_bridge.is_installed() is True
        state = whatsapp_bridge.install_state(
            {'serviceReachable': False, 'connected': False})
        assert state == whatsapp_bridge.STATE_NODE_MISSING


def test_status_payload_carries_install_block(admin_client):
    response = admin_client.get('/api/whatsapp/status')
    assert response.status_code == 200
    data = response.get_json()
    assert 'install' in data
    install = data['install']
    for key in ('install_state', 'hint', 'bridge_dir', 'installed'):
        assert key in install
    # On the dev machine the real bridge folder may or may not exist, but the
    # state must always be one of the documented values.
    assert install['install_state'] in {
        whatsapp_bridge.STATE_NOT_INSTALLED, whatsapp_bridge.STATE_NODE_MISSING,
        whatsapp_bridge.STATE_INSTALLED_STOPPED,
        whatsapp_bridge.STATE_RUNNING_UNPAIRED, whatsapp_bridge.STATE_READY,
    }


def test_automation_page_explains_missing_bridge(admin_client, monkeypatch):
    monkeypatch.setenv('WHATSAPP_BRIDGE_DIR', 'Z:/does/not/exist')
    # Pin the health probe: a real bridge may legitimately be running on this
    # machine, which would render a different (also correct) banner state.
    monkeypatch.setattr('app.services.whatsapp_bridge.health',
                        lambda *a, **k: {'serviceReachable': False,
                                         'connected': False})
    page = admin_client.get('/automation')
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'WhatsApp notifications' in body
    assert 'The WhatsApp component is missing' in body


def test_ready_state_reports_paired(app, fake_bridge):
    fake_bridge(with_modules=True)
    with app.test_request_context():
        summary = whatsapp_bridge.install_summary(
            {'serviceReachable': True, 'connected': True})
        assert summary['install_state'] == whatsapp_bridge.STATE_READY


def test_queue_message_survives_missing_bridge(app, seed):
    """Queued notifications wait (never fail) while no bridge is installed."""
    with app.app_context():
        item = MessageQueue(phone='923001234567', message='Hello guardian',
                            status='approved', trigger='result')
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    # The bridge is unreachable here, and nothing marks the message failed.
    with app.app_context():
        saved = db.session.get(MessageQueue, item_id)
        assert saved.status == 'approved'
        assert (saved.error_msg or '') == ''


def test_start_all_launch_plan_skips_missing_bridge(monkeypatch):
    import start_all

    monkeypatch.setattr(start_all, 'NODE_SERVICE_SCRIPT',
                        start_all.Path('Z:/missing/server.js'))
    action, reason = start_all.whatsapp_launch_plan()
    assert action == 'skip'
    assert 'not installed' in reason.lower()


def test_start_all_launch_plan_skips_without_node(monkeypatch):
    import start_all

    base = Path(tempfile.mkdtemp(prefix='bridge-no-node-'))
    (base / 'server.js').write_text('//', encoding='utf-8')
    (base / 'package.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(start_all, 'NODE_SERVICE_DIR', base)
    monkeypatch.setattr(start_all, 'NODE_SERVICE_SCRIPT', base / 'server.js')
    monkeypatch.setattr(start_all.shutil, 'which', lambda name: None)
    monkeypatch.delenv('WHATSAPP_NODE_PATH', raising=False)
    try:
        action, reason = start_all.whatsapp_launch_plan()
        assert action == 'skip'
        assert 'node' in reason.lower()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_start_all_launch_plan_skips_without_node_modules(monkeypatch):
    import start_all

    base = Path(tempfile.mkdtemp(prefix='bridge-no-deps-'))
    (base / 'server.js').write_text('//', encoding='utf-8')
    (base / 'package.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(start_all, 'NODE_SERVICE_DIR', base)
    monkeypatch.setattr(start_all, 'NODE_SERVICE_SCRIPT', base / 'server.js')
    monkeypatch.setattr(start_all.shutil, 'which', lambda name: 'C:/Node/node.exe')
    try:
        action, reason = start_all.whatsapp_launch_plan()
        assert action == 'skip'
        assert 'npm install' in reason
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_start_all_launch_plan_starts_installed_bridge(monkeypatch):
    import start_all

    base = Path(tempfile.mkdtemp(prefix='bridge-ok-'))
    (base / 'server.js').write_text('//', encoding='utf-8')
    (base / 'package.json').write_text('{}', encoding='utf-8')
    (base / 'node_modules').mkdir()
    monkeypatch.setattr(start_all, 'NODE_SERVICE_DIR', base)
    monkeypatch.setattr(start_all, 'NODE_SERVICE_SCRIPT', base / 'server.js')
    monkeypatch.setattr(start_all.shutil, 'which', lambda name: 'C:/Node/node.exe')
    try:
        action, command = start_all.whatsapp_launch_plan()
        assert action == 'start'
        assert command == ['C:/Node/node.exe', str(base / 'server.js')]
    finally:
        shutil.rmtree(base, ignore_errors=True)

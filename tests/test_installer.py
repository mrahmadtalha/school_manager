"""Phase 6: installer branding, WhatsApp-as-core bundling, data preservation.

* the Baileys socket must carry the connection-timeout fix,
* the installer must bundle the app AND the WhatsApp bridge (with a private
  Node runtime) under the "Ahmi software firm" branding,
* school data in %LOCALAPPDATA%\\SchoolManager must survive updates and
  uninstalls, and the WhatsApp session must never be shipped or deleted.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from app.database import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ISS_FILE = PROJECT_ROOT / 'installer' / 'SchoolManager.iss'
SERVER_JS = PROJECT_ROOT / 'whatsapp-service' / 'server.js'


def _iss_text():
    return ISS_FILE.read_text(encoding='utf-8')


def test_baileys_socket_has_timeout_fix():
    source = SERVER_JS.read_text(encoding='utf-8')
    for option in ('syncFullHistory: false',
                   'connectTimeoutMs: 60000',
                   'defaultQueryTimeoutMs: 60000',
                   'keepAliveIntervalMs: 30000'):
        assert option in source, f'missing socket option: {option}'


def test_bridge_session_path_is_configurable():
    """The WhatsApp session must be movable to the per-school data folder."""
    source = SERVER_JS.read_text(encoding='utf-8')
    assert "process.env.SESSION_PATH" in source


def test_installer_carries_ahmi_branding():
    text = _iss_text()
    assert '#define MyAppPublisher "Ahmi software firm"' in text
    assert 'AppPublisher={#MyAppPublisher}' in text
    assert 'Copyright (c) 2020-2026 Ahmi software firm' in text
    assert 'UninstallDisplayName={#MyAppName} - {#MyAppPublisher}' in text
    assert 'VersionInfoCompany={#MyAppPublisher}' in text


def test_installer_uses_the_stable_appid():
    text = _iss_text()
    assert 'AppId={{A8F2D19E-6C31-4F20-B84A-91D0E49E01F8}' in text


def test_installer_output_name_and_version():
    text = _iss_text()
    assert '#define MyAppVersion "1.0.0"' in text
    assert 'OutputBaseFilename=SchoolManager_Setup_v{#MyAppVersion}' in text


def test_installer_bundles_app_and_whatsapp_bridge():
    text = _iss_text()
    assert '..\\build\\exe\\SchoolManager\\*' in text
    assert '..\\build\\installer-staging\\whatsapp-service\\*' in text
    # The bridge is a *required* component: no Tasks/Components gating.
    assert 'Tasks: ' not in text.split('[Files]')[1].split('[Dirs]')[0]


def test_installer_creates_shortcuts_with_publisher_name():
    text = _iss_text()
    assert 'School Manager - {#MyAppPublisher}' in text
    assert '{autodesktop}' in text and '{group}' in text


def test_installer_preserves_the_data_folder():
    text = _iss_text()
    assert '{localappdata}\\SchoolManager' in text
    assert 'Permissions: users-modify' in text
    uninstall_delete = text.split('[UninstallDelete]')[1]
    # The section must not delete school data on uninstall: no deletion
    # directives at all, and the data folder is pre-created with user rights.
    assert 'Type:' not in uninstall_delete


def test_installer_closes_running_app_on_install_and_uninstall():
    text = _iss_text()
    assert 'PrepareToInstall' in text and 'taskkill /IM SchoolManager.exe' in text
    assert 'CurUninstallStepChanged' in text


def test_whatsapp_session_is_never_shipped():
    from build_installer import BRIDGE_FILES
    assert 'session' not in BRIDGE_FILES
    assert 'test' not in BRIDGE_FILES
    staging_code = (PROJECT_ROOT / 'tools' / 'build_installer.py').read_text(
        encoding='utf-8')
    assert "'session', 'test'" in staging_code  # ignored patterns in copytree


def test_bundled_node_runtime_is_preferred(app, monkeypatch):
    """The installer ships node.exe inside the bridge folder - prefer it."""
    from app.services import whatsapp_bridge

    fake = Path(tempfile.mkdtemp(prefix='bridge-node-')) / 'whatsapp-service'
    fake.mkdir(parents=True)
    (fake / 'package.json').write_text('{}', encoding='utf-8')
    (fake / 'server.js').write_text('//', encoding='utf-8')
    (fake / 'node.exe').write_text('MZA fake binary', encoding='utf-8')
    monkeypatch.setattr(whatsapp_bridge, 'bridge_dir', lambda: fake)
    monkeypatch.setenv('WHATSAPP_NODE_PATH', '')
    try:
        with app.test_request_context():
            assert whatsapp_bridge.node_runtime_path() == fake / 'node.exe'
    finally:
        shutil.rmtree(fake.parent, ignore_errors=True)



def test_uploaded_logo_lives_in_data_folder_not_install_dir(app):
    """Installed products write the logo to %LOCALAPPDATA%, never Program Files."""
    import os

    from app.models import SchoolSettings
    from app.services.attendance_export import school_branding
    from app.services.id_documents import school_branding as id_branding

    with app.app_context():
        data_uploads = Path(app.config['DATA_DIR']) / 'uploads'
        data_uploads.mkdir(parents=True, exist_ok=True)
        logo = data_uploads / 'logo.png'
        logo.write_bytes(b'fake-png')

        settings = SchoolSettings.query.first() or SchoolSettings()
        db.session.add(settings)
        settings.logo_filename = 'logo.png'
        db.session.commit()

        branding = school_branding(app.root_path)
        assert branding['logo_path'] == str(logo)
        assert id_branding(app.root_path)['logo_path'] == str(logo)
        assert 'static' not in branding['logo_path']
        os.remove(logo)

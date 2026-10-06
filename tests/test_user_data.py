"""User-data folder: one location for DB, secret, license files and uploads.

The product keeps every mutable file in a single folder (see
``app/user_data.py``).  These tests cover the resolution rules and the
one-time migration from a legacy layout.  Directories come from
``tempfile.mkdtemp`` because this machine's pytest ``tmp_path`` fixture cannot
create its numbered temp root (environment permission quirk).
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from app import user_data


@pytest.fixture()
def workspace():
    """A disposable temp root: ``<root>/project`` (fake checkout) + ``<root>/data``."""
    base = Path(tempfile.mkdtemp(prefix='user-data-tests-'))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture()
def data_dir(workspace, monkeypatch):
    """Isolated SCHOOL_DATA_DIR *and* a fake project dir, so the real
    ``<project>/instance`` is never considered a migration source."""
    project = workspace / 'project'
    project.mkdir()
    monkeypatch.setattr(user_data, 'BASE_DIR', project)
    target = workspace / 'data'
    monkeypatch.setenv('SCHOOL_DATA_DIR', str(target))
    yield target
    monkeypatch.delenv('SCHOOL_DATA_DIR', raising=False)


def test_data_root_honours_env_override(data_dir):
    assert user_data.data_root() == data_dir


def test_default_source_layout_is_project_instance(monkeypatch):
    monkeypatch.delenv('SCHOOL_DATA_DIR', raising=False)
    monkeypatch.delattr(user_data.sys, 'frozen', raising=False)
    assert user_data.data_root() == user_data.BASE_DIR / 'instance'


def test_frozen_layout_uses_localappdata(monkeypatch):
    monkeypatch.delenv('SCHOOL_DATA_DIR', raising=False)
    monkeypatch.setattr(user_data.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(user_data.sys, '_MEIPASS', 'dummy', raising=False)
    monkeypatch.setattr(user_data, '_frozen_exe_dir',
                        lambda: Path('C:/Program Files/SchoolManager'))
    monkeypatch.setattr(user_data, '_localappdata',
                        lambda: Path('C:/Users/school/AppData/Local'))
    assert user_data.data_root() == Path('C:/Users/school/AppData/Local/SchoolManager')


def test_migration_copies_legacy_files_and_folders(data_dir):
    legacy = data_dir.parent / 'project' / 'instance'
    (legacy / 'uploads' / 'students').mkdir(parents=True)
    (legacy / 'backups').mkdir()
    (legacy / 'school.db').write_text('db-bytes', encoding='utf-8')
    (legacy / '.secret_key').write_text('secret', encoding='utf-8')
    (legacy / 'license.key').write_text('key', encoding='utf-8')
    (legacy / 'license.state').write_text('state', encoding='utf-8')
    (legacy / 'uploads' / 'students' / 'a.jpg').write_bytes(b'jpg')

    report = user_data.migrate_into_data_root()

    assert (data_dir / 'school.db').read_text(encoding='utf-8') == 'db-bytes'
    assert (data_dir / '.secret_key').read_text(encoding='utf-8') == 'secret'
    assert (data_dir / 'license.key').exists()
    assert (data_dir / 'license.state').exists()
    assert (data_dir / 'uploads' / 'students' / 'a.jpg').read_bytes() == b'jpg'
    assert (data_dir / 'backups').is_dir()
    assert report


def test_migration_never_overwrites_existing_data(data_dir):
    legacy = data_dir.parent / 'project' / 'instance'
    legacy.mkdir()
    (legacy / 'school.db').write_text('legacy-db', encoding='utf-8')

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / 'school.db').write_text('current-db', encoding='utf-8')
    user_data.migrate_into_data_root()

    assert (data_dir / 'school.db').read_text(encoding='utf-8') == 'current-db'


def test_migration_is_idempotent(data_dir):
    legacy = data_dir.parent / 'project' / 'instance'
    legacy.mkdir()
    (legacy / 'school.db').write_text('db', encoding='utf-8')

    first = user_data.migrate_into_data_root()
    second = user_data.migrate_into_data_root()

    assert any(line.startswith('migrated') for line in first)
    assert not any(line.startswith('migrated') for line in second)


def test_create_app_uses_data_dir_for_instance_path(data_dir, app):
    assert Path(app.instance_path) == data_dir
    assert app.config['DATA_DIR'] == str(data_dir)


def test_legacy_app_instance_license_files_are_pulled_into_data_dir(
        workspace, monkeypatch):
    """Pre-Phase-2 installs kept license.key/license.state in <project>/app/instance.

    create_app() itself must run the migration during startup.
    """
    from app import create_app

    project = workspace / 'project'
    project.mkdir()
    legacy = project / 'app' / 'instance'
    legacy.mkdir(parents=True)
    (legacy / 'license.key').write_text('old-key', encoding='utf-8')
    (legacy / 'license.state').write_text('old-state', encoding='utf-8')

    monkeypatch.setattr(user_data, 'BASE_DIR', project)
    monkeypatch.setenv('SCHOOL_DATA_DIR', str(workspace / 'data'))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (workspace / 'data' / 'school.db').as_posix())
    monkeypatch.setenv('SECRET_KEY', 'migration-test-secret')
    try:
        application = create_app()
        data_dir = Path(application.instance_path)
        assert (data_dir / 'license.key').read_text(encoding='utf-8') == 'old-key'
        assert (data_dir / 'license.state').read_text(encoding='utf-8') == 'old-state'
    finally:
        monkeypatch.delenv('SCHOOL_DATA_DIR', raising=False)
        monkeypatch.delenv('DATABASE_URL', raising=False)
        monkeypatch.delenv('SECRET_KEY', raising=False)

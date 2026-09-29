"""Automatic backups: due-check, retention, Settings section, downloads."""

import os
import sqlite3
import time
from pathlib import Path

from app.services import db_backup


def _make_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.execute('CREATE TABLE t (x INTEGER)')
    connection.commit()
    connection.close()


def _make_backup_file(path, age_hours=0.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'fake backup')
    stamp = time.time() - age_hours * 3600
    os.utime(path, (stamp, stamp))


def test_backup_if_due_creates_then_skips(tmp_path):
    db_path = tmp_path / 'school.db'
    _make_db(db_path)

    first = db_backup.backup_if_due(db_path, retention=5)
    assert first['due'] is True
    assert first['created'] and Path(first['created']).exists()
    assert Path(first['created']).parent == db_backup.auto_backup_dir(db_path)

    second = db_backup.backup_if_due(db_path, retention=5)
    assert second['due'] is False
    assert second['created'] is None

    forced = db_backup.backup_if_due(db_path, retention=5, force=True)
    assert forced['created'] is not None


def test_manual_backup_counts_as_fresh(tmp_path):
    db_path = tmp_path / 'school.db'
    _make_db(db_path)
    _make_backup_file(db_backup.default_backup_dir(db_path) / 'school-manual.db',
                      age_hours=1)

    summary = db_backup.backup_if_due(db_path, interval_hours=24)
    assert summary['due'] is False
    assert summary['created'] is None


def test_prune_keeps_newest_and_never_touches_manual(tmp_path):
    db_path = tmp_path / 'school.db'
    _make_db(db_path)
    auto = db_backup.auto_backup_dir(db_path)
    _make_backup_file(auto / 'school-1.db', age_hours=50)
    _make_backup_file(auto / 'school-2.db', age_hours=40)
    _make_backup_file(auto / 'school-3.db', age_hours=30)
    manual_keep = db_backup.default_backup_dir(db_path) / 'school-keep.db'
    _make_backup_file(manual_keep, age_hours=100)

    removed = db_backup.prune_auto_backups(db_path, keep=2)

    assert removed == ['school-1.db']
    assert (auto / 'school-3.db').exists()
    assert manual_keep.exists()


def test_list_backups_flags_scopes(tmp_path):
    db_path = tmp_path / 'school.db'
    _make_db(db_path)
    _make_backup_file(db_backup.auto_backup_dir(db_path) / 'auto-1.db', age_hours=1)
    _make_backup_file(db_backup.default_backup_dir(db_path) / 'manual-1.db', age_hours=2)

    items = db_backup.list_backups(db_path)
    assert [item['scope'] for item in items] == ['auto', 'manual']
    assert items[0]['name'] == 'auto-1.db'


def test_settings_page_shows_backups_section(admin_client):
    body = admin_client.get('/settings').get_data(as_text=True)
    assert 'Backups' in body
    assert 'Back up now' in body


def test_run_backup_now_creates_downloadable_file(admin_client, app):
    with app.app_context():
        before = len(db_backup.list_backups())

    response = admin_client.post('/settings/backups/run', follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        items = db_backup.list_backups()
    assert len(items) == before + 1
    newest = items[0]
    assert newest['scope'] == 'manual'

    download = admin_client.get(f"/settings/backups/download/{newest['name']}")
    assert download.status_code == 200
    assert download.data.startswith(b'SQLite format 3')


def test_download_rejects_unknown_names(admin_client):
    for bad in ('nope.txt', 'missing.db', '..%2Fschool.db'):
        assert admin_client.get(f'/settings/backups/download/{bad}').status_code == 404


def test_backup_routes_require_admin(teacher_client):
    assert teacher_client.post('/settings/backups/run').status_code == 403
    assert teacher_client.get('/settings/backups/download/x.db').status_code == 403

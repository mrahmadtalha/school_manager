"""Backup and restore must actually round-trip the data."""

import pytest

from app.database import db
from app.models import FeeRecordModel, StudentModel
from app.services.db_backup import (
    backup_database, database_stats, default_backup_dir, resolve_db_path,
    restore_database,
)
from tests.conftest import ADMIN_PASSWORD, login, seed_reference_data

DB_NAME = 'backup_target.db'


@pytest.fixture()
def live_app(fresh_app_factory, tmp_path):
    application = fresh_app_factory(tmp_path, DB_NAME)
    with application.app_context():
        db.drop_all()
        db.create_all()
        seed_reference_data()
        db.session.commit()
    return application


def _db_path(application):
    return resolve_db_path(application.config['SQLALCHEMY_DATABASE_URI'])


def test_backup_creates_a_timestamped_file(live_app, tmp_path):
    db_path = _db_path(live_app)
    backup_file = backup_database(db_path, tmp_path / 'backups')

    assert backup_file.exists()
    assert backup_file.parent == tmp_path / 'backups'
    assert backup_file.suffix == '.db'
    assert database_stats(backup_file)['students'] == database_stats(db_path)['students']


def test_restore_refuses_to_clobber_without_force(live_app, tmp_path):
    db_path = _db_path(live_app)
    backup_file = backup_database(db_path, tmp_path / 'backups')

    with pytest.raises(FileExistsError):
        restore_database(backup_file, db_path, force=False)


def test_full_backup_and_restore_round_trip(live_app, tmp_path):
    db_path = _db_path(live_app)
    backup_dir = tmp_path / 'backups'
    assert default_backup_dir(db_path) == db_path.parent / 'backups'

    with live_app.app_context():
        db.session.remove()
        db.engine.dispose()

    before = database_stats(db_path)
    backup_file = backup_database(db_path, backup_dir)

    # Mutate the live data after the backup: add a student and set a fee payment.
    with live_app.app_context():
        student = StudentModel(roll_number=1999, student_name='After Backup',
                               father_name='Test', guardian_phone='03000000000',
                               address='Nowhere', class_id=1, monthly_fee=1000.0)
        db.session.add(student)
        db.session.commit()
        student_id = student.id
        db.session.add(FeeRecordModel(student_id=student_id, month_year='November 2026',
                                      amount_due=1000.0, amount_paid=400.0, status='Partial'))
        db.session.commit()
        db.session.remove()
        db.engine.dispose()

    mutated = database_stats(db_path)
    assert mutated['students'] == before['students'] + 1
    assert mutated['fee_records'] == before['fee_records'] + 1

    restored_path = restore_database(backup_file, db_path, force=True)
    assert restored_path == db_path

    after = database_stats(db_path)
    assert after['students'] == before['students']
    assert after['fee_records'] == before['fee_records']
    assert after['__total__'] == before['__total__']

    # The application must serve the restored data.
    with live_app.app_context():
        db.session.remove()
        db.engine.dispose()
        assert StudentModel.query.filter_by(roll_number=1999).first() is None
        assert StudentModel.query.filter_by(roll_number=1001).first() is not None

    client = live_app.test_client()
    assert login(client, 'admin', ADMIN_PASSWORD).status_code == 302
    assert client.get('/students').status_code == 200
    assert client.get('/fees').status_code == 200


def test_restore_rejects_a_non_sqlite_file(live_app, tmp_path):
    db_path = _db_path(live_app)
    bogus = tmp_path / 'bogus.db'
    bogus.write_text('this is not a sqlite database', encoding='utf-8')

    with pytest.raises(Exception):
        restore_database(bogus, db_path, force=True)

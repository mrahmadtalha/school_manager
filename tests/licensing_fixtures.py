"""Shared fixtures for the feature / quota / recovery tests (enforced license)."""

import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.database import db
from app.services import licensing
from tests.conftest import seed_reference_data

MACHINE = 'AAAA-BBBB-CCCC-DDDD'
T0 = datetime(2026, 1, 10, 9, 0, 0)


def _load_tool():
    path = Path(__file__).resolve().parent.parent / 'tools' / 'license_admin.py'
    spec = importlib.util.spec_from_file_location('license_admin_tool_fx', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def set(self, value):
        self.now = value


def make_key(private, *, machine=MACHINE, issued=date(2026, 1, 10), expires=date(2026, 12, 31),
             license_id='LIC-TEST-0001', grace_days=7, **extra):
    payload = tool.build_payload(
        license_id=license_id, licensee='Test School', machine_code=machine,
        issued=issued, expires=expires, grace_days=grace_days, **extra)
    return tool.sign_license(private, payload)


@pytest.fixture(scope='module')
def keypair():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, licensing.b64u_encode(raw)


@pytest.fixture()
def clock():
    return Clock(T0)


@pytest.fixture()
def licensed_app_factory(tmp_path, keypair, clock, fresh_app_factory):
    def _make(seed=True):
        application = fresh_app_factory(tmp_path, 'licensed.db', {
            'LICENSE_ENFORCEMENT': True,
            'LICENSE_PUBLIC_KEY': keypair[1],
            'LICENSE_DIR': str(tmp_path / 'lic'),
            'LICENSE_MACHINE_CODE': MACHINE,
            'LICENSE_NOW_FN': clock,
            'LICENSE_CACHE_SECONDS': 0,
        })
        with application.app_context():
            db.drop_all()
            db.create_all()
            if seed:
                application.config['SEED_DATA'] = seed_reference_data()
        return application
    return _make

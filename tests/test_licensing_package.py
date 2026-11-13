"""``app/services/licensing`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
license code ships obfuscated.  These tests pin the three things that must not
break because of the split: every file stays small, every name the application
and the vendor tools used before is still importable from
``app.services.licensing``, and the package still loads *by file path* (the way
the vendor dashboard and ``tools/license_admin.py`` load it, without starting
Flask) and produces keys the application accepts.
"""

import importlib.util
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services import licensing

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'licensing'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

PUBLIC_NAMES = (
    # constants
    'PRODUCT', 'KEY_PREFIX', 'SIGN_CONTEXT', 'PAYLOAD_VERSION', 'DEFAULT_GRACE_DAYS',
    'MAX_GRACE_DAYS', 'EXPIRING_SOON_DAYS', 'ROLLBACK_TOLERANCE', 'STATE_WRITE_INTERVAL',
    'ACTIVE', 'GRACE', 'EXPIRED', 'UNLICENSED', 'INVALID', 'DISABLED', 'READ_ONLY_STATES',
    'LIMIT_WA_DAILY', 'LIMIT_WA_MONTHLY', 'LIMIT_NAMES', 'FEATURES_ADDED_LATER',
    'REMINDER_MILESTONES', 'NOTICE_MAX_LENGTH', 'INSPECTION_PREFIX', 'INSPECTION_SIGN_CONTEXT',
    'INSPECTION_MAX_HOURS', 'INSPECTION_START_TOLERANCE',
    'RECOVERY_REQUEST_PREFIX', 'RECOVERY_TOKEN_PREFIX', 'RECOVERY_SIGN_CONTEXT',
    # errors, status, manager
    'LicenseError', 'LicenseStatus', 'LicenseManager',
    # helpers and functions
    'b64u_encode', 'b64u_decode', 'default_public_key', 'get_machine_code',
    'normalize_machine_code', 'format_machine_code', 'verify_license_text', 'reminder_stage',
    'verify_inspection_text', 'sign_inspection', 'make_recovery_request',
    'parse_recovery_request', 'sign_recovery_token', 'verify_recovery_token',
)


def _load_like_the_vendor_tools(name):
    """The loading used by vendor_dashboard/core.py and tools/license_admin.py."""
    spec = importlib.util.spec_from_file_location(
        name, PACKAGE_DIR / '__init__.py', submodule_search_locations=[str(PACKAGE_DIR)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _private_and_public():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw,
                                            serialization.PublicFormat.Raw)
    return private, licensing.b64u_encode(raw)


def test_licensing_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'licensing.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 8
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_public_name_is_still_importable():
    missing = [name for name in PUBLIC_NAMES if not hasattr(licensing, name)]
    assert missing == []


def test_the_original_import_lines_still_work():
    from app.services.licensing import (INSPECTION_PREFIX, LIMIT_WA_DAILY,  # noqa: F401
                                        LIMIT_WA_MONTHLY, LicenseError, LicenseManager,
                                        default_public_key, normalize_machine_code)
    assert LicenseManager.__module__.endswith('licensing.manager')


def test_package_loads_by_file_path_without_flask():
    module = _load_like_the_vendor_tools('sm_test_licensing_by_path')
    assert module.LicenseManager is not licensing.LicenseManager     # a separate copy
    assert module.PRODUCT == licensing.PRODUCT
    assert module.get_machine_code() == licensing.get_machine_code()


def test_keys_signed_by_the_path_loaded_copy_are_accepted_by_the_app():
    vendor = _load_like_the_vendor_tools('sm_test_licensing_vendor_copy')
    private, public_b64 = _private_and_public()
    machine = '7F3A-91BC-0D42-E8A5'
    now = int(time.time())

    inspection = vendor.sign_inspection(
        private, inspection_id='INSP-1', license_id='LIC-1', licensee='Test School',
        machine_code=machine, issued_ts=now, hours=2)
    data = licensing.verify_inspection_text(inspection, public_b64)
    assert data['inspection_id'] == 'INSP-1'
    assert licensing.normalize_machine_code(data['machine_id']) == \
        licensing.normalize_machine_code(machine)

    request = licensing.make_recovery_request('a1b2c3d4e5f60718', machine, 'LIC-1', now)
    parsed = vendor.parse_recovery_request(request)
    assert parsed['nonce'] == 'a1b2c3d4e5f60718'
    token = vendor.sign_recovery_token(private, parsed['nonce'], parsed['machine_code'],
                                       now, now + 3600)
    checked = licensing.verify_recovery_token(token, public_b64)
    assert checked['nonce'] == 'a1b2c3d4e5f60718'
    assert checked['expires_ts'] == now + 3600

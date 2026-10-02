"""Offline license verification.

How it works
------------
* The vendor signs a small JSON payload (licensee, machine code, issue and
  expiry dates) with an Ed25519 **private** key that never leaves the vendor's
  machine.  The application ships only the matching **public** key
  (``license_public_key.py``), so it can verify licenses but cannot create them.
* A license key is a single line of text: ``SM1.<payload>.<signature>`` (both
  parts base64url).  It is bound to one machine through the machine code.
* Nothing here needs the internet.

Lifecycle of a valid license::

    active  ->  grace  ->  expired (read-only)

``unlicensed`` (no key installed) and ``invalid`` (bad signature, wrong
machine, ...) are also read-only.  "Read-only" means the *enforcement layer*
(``app/license_guard.py``) rejects writes; this module only decides the state.

Clock protection
----------------
Rolling the Windows clock back must not revive an expired license, so the
manager keeps a signed "high-water mark" (the latest date it has seen) in a
small state file and never lets effective time go backwards.  If a wrong
far-future date was ever seen, the vendor recovers the school by issuing a
replacement key (new license id), which restarts the mark from its issue date.

Honest limits: this is a deterrent against casual copying and clock tricks, not
DRM.  Someone who edits the running code, or deletes the state file *and* keeps
the clock frozen, can still get around it.  Code obfuscation (Phase 3) raises
that bar; it cannot remove it.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time as _time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PRODUCT = 'school-manager'
KEY_PREFIX = 'SM1'
SIGN_CONTEXT = b'school-manager-license-v1\n'
PAYLOAD_VERSION = 1

DEFAULT_GRACE_DAYS = 7
MAX_GRACE_DAYS = 60
EXPIRING_SOON_DAYS = 30
ROLLBACK_TOLERANCE = timedelta(hours=24)
STATE_WRITE_INTERVAL = timedelta(minutes=10)

# License states
ACTIVE = 'active'
GRACE = 'grace'
EXPIRED = 'expired'
UNLICENSED = 'unlicensed'
INVALID = 'invalid'
DISABLED = 'disabled'           # enforcement switched off (development only)

READ_ONLY_STATES = {EXPIRED, UNLICENSED, INVALID}


class LicenseError(Exception):
    """A license key could not be accepted.  ``code`` is machine-readable."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# -- encoding helpers ----------------------------------------------------

def b64u_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


_B64U_CHARS = re.compile(r'^[A-Za-z0-9_-]+$')


def b64u_decode(text):
    """Strict base64url decode (the stdlib silently skips invalid characters)."""
    text = text.strip()
    if not _B64U_CHARS.match(text):
        raise ValueError('not valid base64url')
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _load_public_key(public_key_b64):
    if not public_key_b64 or not public_key_b64.strip():
        raise LicenseError(
            'no_public_key',
            'This build has no license public key configured. '
            'Run "python tools/license_admin.py init" before building.')
    try:
        return Ed25519PublicKey.from_public_bytes(b64u_decode(public_key_b64))
    except Exception as exc:
        raise LicenseError('no_public_key',
                           f'The configured license public key is not valid ({exc}).')


def default_public_key():
    from app.services.license_public_key import PUBLIC_KEY_B64
    return PUBLIC_KEY_B64


# -- machine identity ----------------------------------------------------

def _raw_machine_id():
    """A stable per-installation identifier for this computer."""
    if sys.platform.startswith('win'):
        try:
            import winreg
            flags = winreg.KEY_READ | getattr(winreg, 'KEY_WOW64_64KEY', 0)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'SOFTWARE\Microsoft\Cryptography', 0, flags) as key:
                value, _ = winreg.QueryValueEx(key, 'MachineGuid')
                if value:
                    return str(value).strip().lower()
        except OSError:
            pass
    for candidate in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            text = Path(candidate).read_text(encoding='utf-8').strip()
            if text:
                return text.lower()
        except OSError:
            continue
    return f'mac-{uuid.getnode():012x}'


def get_machine_code():
    """Short, human-readable machine code, e.g. ``7F3A-91BC-0D42-E8A5``."""
    digest = hashlib.sha256(f'{PRODUCT}|{_raw_machine_id()}'.encode('utf-8')).hexdigest().upper()
    return '-'.join(digest[i:i + 4] for i in range(0, 16, 4))


def normalize_machine_code(code):
    return ''.join(ch for ch in (code or '').upper() if ch.isalnum())


# -- parsing / verification ---------------------------------------------

def _parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise LicenseError('malformed', f'License field "{field}" is not a valid date.')


def verify_license_text(text, public_key_b64):
    """Verify the signature and structure of a license key; return its payload.

    Does NOT check the machine or the dates - see ``LicenseManager``.
    """
    cleaned = ''.join((text or '').split())      # tolerate pasted line breaks
    if not cleaned:
        raise LicenseError('malformed', 'The license key is empty.')
    parts = cleaned.split('.')
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        raise LicenseError('malformed', 'This does not look like a School Manager license key.')

    public_key = _load_public_key(public_key_b64)
    try:
        payload_bytes = b64u_decode(parts[1])
        signature = b64u_decode(parts[2])
    except Exception:
        raise LicenseError('malformed',
                           'The license key is damaged (it may have been cut short when copied).')

    try:
        public_key.verify(signature, SIGN_CONTEXT + payload_bytes)
    except InvalidSignature:
        raise LicenseError('bad_signature', 'The license key is not genuine or has been altered.')

    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        raise LicenseError('malformed', 'The license contents could not be read.')
    if not isinstance(payload, dict):
        raise LicenseError('malformed', 'The license contents could not be read.')

    if payload.get('product') != PRODUCT:
        raise LicenseError('wrong_product', 'This license is for a different product.')
    if payload.get('v') != PAYLOAD_VERSION:
        raise LicenseError('unsupported_version',
                           'This license was issued for a different version of the software.')
    for field in ('license_id', 'licensee', 'machine_id', 'issued', 'expires'):
        if not payload.get(field):
            raise LicenseError('malformed', f'License field "{field}" is missing.')

    payload['_issued'] = _parse_date(payload['issued'], 'issued')
    payload['_expires'] = _parse_date(payload['expires'], 'expires')
    if payload['_expires'] < payload['_issued']:
        raise LicenseError('malformed', 'License expiry is earlier than its issue date.')
    try:
        grace = int(payload.get('grace_days', DEFAULT_GRACE_DAYS))
    except (TypeError, ValueError):
        grace = DEFAULT_GRACE_DAYS
    payload['_grace_days'] = max(0, min(MAX_GRACE_DAYS, grace))
    return payload


# -- status object -------------------------------------------------------

@dataclass(frozen=True)
class LicenseStatus:
    state: str
    read_only: bool
    level: str                    # bootstrap colour: success / warning / danger / secondary
    title: str
    message: str
    machine_code: str
    enforced: bool = True
    reason: str = ''              # machine-readable detail for invalid licenses
    licensee: str = ''
    license_id: str = ''
    issued: date = None
    expires: date = None
    grace_ends: date = None
    days_left: int = None         # negative once expired
    expiring_soon: bool = False
    clock_rollback: bool = False

    @property
    def needs_attention(self):
        return (self.state in (GRACE, EXPIRED, UNLICENSED, INVALID)
                or self.expiring_soon or self.clock_rollback)


# -- manager -------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LicenseManager:
    """Loads, verifies and activates the license for one application."""

    def __init__(self, license_path, state_path, public_key_b64, *, enforced=True,
                 machine_code=None, now_fn=None, cache_seconds=30):
        self.license_path = Path(license_path)
        self.state_path = Path(state_path)
        self.public_key_b64 = public_key_b64 or ''
        self.enforced = bool(enforced)
        self._machine_code = machine_code
        self._now = now_fn or _utcnow
        self._cache_seconds = cache_seconds
        self._cache = None
        self._cache_at = 0.0
        self._lock = threading.RLock()

    # -- public API ------------------------------------------------------
    def machine_code(self):
        if callable(self._machine_code):
            return self._machine_code()
        return self._machine_code or get_machine_code()

    def status(self, force=False):
        with self._lock:
            fresh = (self._cache is not None and not force
                     and (_time.monotonic() - self._cache_at) < self._cache_seconds)
            if fresh:
                return self._cache
            self._cache = self._evaluate()
            self._cache_at = _time.monotonic()
            return self._cache

    def activate(self, text):
        """Verify ``text`` and, if it is valid for this machine, install it."""
        with self._lock:
            payload = self._check_machine(verify_license_text(text, self.public_key_b64))
            today = self._now().date()
            grace_end = payload['_expires'] + timedelta(days=payload['_grace_days'])
            if today > grace_end:
                raise LicenseError(
                    'expired',
                    f'This license expired on {payload["_expires"]:%d %b %Y} '
                    'and can no longer be activated. Please request a renewal.')

            previous_id = self._read_state().get('license_id')
            self._atomic_write(self.license_path, ''.join(text.split()) + '\n')
            if previous_id != payload['license_id']:
                # A different license was issued: restart the time mark from its issue date.
                self._write_state(payload['license_id'], self._floor(payload))
            self._cache = None
            return self.status(force=True)

    def read_license_text(self):
        try:
            return self.license_path.read_text(encoding='utf-8-sig').strip() or None
        except OSError:
            return None

    # -- evaluation ------------------------------------------------------
    def _check_machine(self, payload):
        expected = normalize_machine_code(payload['machine_id'])
        actual = normalize_machine_code(self.machine_code())
        if not hmac.compare_digest(expected.encode(), actual.encode()):
            raise LicenseError(
                'wrong_machine',
                "This license was issued for a different computer. "
                "Send this computer's machine code to your vendor to get a new key.")
        return payload

    def _base_status(self, **kwargs):
        return LicenseStatus(machine_code=self.machine_code(), enforced=self.enforced, **kwargs)

    def _evaluate(self):
        if not self.enforced:
            return self._base_status(
                state=DISABLED, read_only=False, level='secondary',
                title='License enforcement is off',
                message='Development mode: license checks are not being enforced.')

        text = self.read_license_text()
        if text is None:
            return self._base_status(
                state=UNLICENSED, read_only=True, level='danger', reason='missing',
                title='Not activated',
                message='No license is installed. The system is read-only until a valid '
                        'license is activated.')

        try:
            payload = self._check_machine(verify_license_text(text, self.public_key_b64))
        except LicenseError as err:
            return self._base_status(
                state=INVALID, read_only=True, level='danger', reason=err.code,
                title='License problem', message=err.message + ' The system is read-only.')

        effective, rollback = self._effective_now(payload)
        today = effective.date()
        expires = payload['_expires']
        grace_end = expires + timedelta(days=payload['_grace_days'])
        days_left = (expires - today).days
        common = dict(licensee=payload['licensee'], license_id=payload['license_id'],
                      issued=payload['_issued'], expires=expires, grace_ends=grace_end,
                      days_left=days_left, clock_rollback=rollback)

        if today <= expires:
            soon = days_left <= EXPIRING_SOON_DAYS
            when = 'today' if days_left == 0 else f'in {days_left} day{"s" if days_left != 1 else ""}'
            return self._base_status(
                state=ACTIVE, read_only=False, expiring_soon=soon,
                level='warning' if soon else 'success',
                title='License expiring soon' if soon else 'License active',
                message=(f'Your license expires {when} ({expires:%d %b %Y}). Please arrange a renewal.'
                         if soon else f'Licensed to {payload["licensee"]} until {expires:%d %b %Y}.'),
                **common)
        if today <= grace_end:
            return self._base_status(
                state=GRACE, read_only=False, level='warning',
                title='License expired - grace period',
                message=(f'Your license expired on {expires:%d %b %Y}. You can keep working until '
                         f'{grace_end:%d %b %Y}; after that the system becomes read-only unless '
                         'it is renewed.'),
                **common)
        return self._base_status(
            state=EXPIRED, read_only=True, level='danger',
            title='License expired - read-only mode',
            message=(f'Your license expired on {expires:%d %b %Y}. You can still view records and '
                     'export data, but changes are disabled until the license is renewed.'),
            **common)

    # -- time high-water mark -------------------------------------------
    @staticmethod
    def _floor(payload):
        """A license cannot have been issued in the future, so real time >= issue date."""
        return datetime.combine(payload['_issued'], dtime.min)

    def _effective_now(self, payload):
        """Return (effective_now, clock_rolled_back); persists the time mark."""
        system_now = self._now()
        floor = self._floor(payload)
        stored = self._read_state()
        same_license = stored.get('license_id') == payload['license_id']
        mark = floor
        if same_license and stored.get('hwm'):
            try:
                mark = max(floor, datetime.fromisoformat(stored['hwm']))
            except ValueError:
                pass

        if system_now >= mark:
            effective, rollback = system_now, False
            if system_now - mark >= STATE_WRITE_INTERVAL or not same_license:
                self._write_state(payload['license_id'], system_now)
        else:
            effective = mark
            rollback = (mark - system_now) > ROLLBACK_TOLERANCE
        return effective, rollback

    # -- state file (tamper-evident, not tamper-proof) --------------------
    def _state_key(self):
        return hashlib.sha256(f'sm-state-v1|{self.machine_code()}'.encode()).digest()

    def _sign_state(self, license_id, hwm_iso):
        return hmac.new(self._state_key(), f'{license_id}|{hwm_iso}'.encode(),
                        hashlib.sha256).hexdigest()

    def _read_state(self):
        try:
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            expected = self._sign_state(data['license_id'], data['hwm'])
            if hmac.compare_digest(expected, data.get('sig', '')):
                return data
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return {}

    def _write_state(self, license_id, hwm):
        hwm_iso = hwm.replace(microsecond=0).isoformat()
        body = {'v': 1, 'license_id': license_id, 'hwm': hwm_iso,
                'sig': self._sign_state(license_id, hwm_iso)}
        try:
            self._atomic_write(self.state_path, json.dumps(body))
        except OSError:
            pass    # an unwritable folder must not take the application down

    @staticmethod
    def _atomic_write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)

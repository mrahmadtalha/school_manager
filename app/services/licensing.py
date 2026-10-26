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

Features and limits
-------------------
A key may also carry ``features`` (the modules the school has paid for),
``limits`` (daily/monthly WhatsApp message caps), ``plan`` (a label) and
``rev`` (revision number).  All are OPTIONAL and the payload version stays 1,
so keys without them (legacy) keep everything switched on and older builds of
the application simply ignore the extra fields.  A newer revision of the same
license id replaces an older one; an older revision is refused.

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
from dataclasses import dataclass, replace
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

#: Limits a key may carry (a missing limit means "unlimited").
LIMIT_WA_DAILY = 'wa_daily'

# Features added after the first release; keys that pre-date them keep them switched on.
FEATURES_ADDED_LATER = ('data_export', 'language_switch', 'audit_log_view')
LIMIT_WA_MONTHLY = 'wa_monthly'
LIMIT_NAMES = (LIMIT_WA_DAILY, LIMIT_WA_MONTHLY)

#: Days-before-expiry at which the administrator gets a reminder pop-up.
REMINDER_MILESTONES = (30, 14, 7, 3, 1)
NOTICE_MAX_LENGTH = 300

# Inspection keys: short, view-only keys the vendor sends for support / audits.
INSPECTION_PREFIX = 'SMI1'            # different prefix: an older build refuses it as "not a license key"
INSPECTION_SIGN_CONTEXT = b'school-manager-inspection-v1\n'   # never reused for licenses or recovery
INSPECTION_MAX_HOURS = 168            # a week at most, whatever the vendor types
INSPECTION_START_TOLERANCE = timedelta(days=1)    # school clock slightly behind the vendor's


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

    features = payload.get('features')
    if features is None:
        payload['_features'] = None            # legacy key: everything on
    elif isinstance(features, list):
        payload['_features'] = tuple(sorted({str(item) for item in features}))
    else:
        raise LicenseError('malformed', 'License field "features" is not valid.')

    if payload['_features'] is not None and int(payload.get('fv', 1) or 1) < 2:
        # key issued before these features existed: they stay on
        payload['_features'] = tuple(sorted(set(payload['_features']) | set(FEATURES_ADDED_LATER)))

    roles = payload.get('roles')
    if roles is None:
        payload['_roles'] = None               # legacy key: every role on
    elif isinstance(roles, list):
        payload['_roles'] = tuple(sorted({str(item) for item in roles} | {'admin'}))
    else:
        raise LicenseError('malformed', 'License field "roles" is not valid.')

    limits = payload.get('limits')
    clean_limits = {}
    if limits is not None:
        if not isinstance(limits, dict):
            raise LicenseError('malformed', 'License field "limits" is not valid.')
        for name in LIMIT_NAMES:
            value = limits.get(name)
            if value is None:
                continue                       # missing = unlimited
            try:
                clean_limits[name] = max(0, int(value))
            except (TypeError, ValueError):
                raise LicenseError('malformed', f'License limit "{name}" is not a number.')
    payload['_limits'] = clean_limits
    try:
        payload['_rev'] = max(0, int(payload.get('rev', 0)))
    except (TypeError, ValueError):
        payload['_rev'] = 0
    payload['_plan'] = str(payload.get('plan') or '')[:40]
    payload['_notice'] = ' '.join(str(payload.get('notice') or '').split())[:NOTICE_MAX_LENGTH]
    return payload


def reminder_stage(days_left):
    """The reminder milestone (30, 14, 7, 3 or 1) a license is in, or None.

    A license with 20 days left is in stage 30 (past the 30-day mark, not yet at 14);
    with 5 days left it is in stage 7; on the last day it is in stage 1.
    """
    if days_left is None or days_left < 0 or days_left > REMINDER_MILESTONES[0]:
        return None
    for stage in sorted(REMINDER_MILESTONES):
        if days_left <= stage:
            return stage
    return None


# -- inspection keys -------------------------------------------------------
#
# A short, VIEW-ONLY key on top of the real license: while it is valid every
# module and the audit log are visible, but nothing can be changed, and a banner
# says so.  It never replaces license.key.  Keys carry their own prefix and
# signature context, so an inspection key can never be installed as a license.

def verify_inspection_text(text, public_key_b64):
    """Verify an inspection key's signature and structure; return its fields."""
    cleaned = ''.join((text or '').split())
    parts = cleaned.split('.')
    if len(parts) != 3 or parts[0] != INSPECTION_PREFIX:
        raise LicenseError('malformed', 'This does not look like an inspection key.')
    public_key = _load_public_key(public_key_b64)
    try:
        body = b64u_decode(parts[1])
        signature = b64u_decode(parts[2])
    except Exception:
        raise LicenseError('malformed',
                           'The inspection key is damaged (it may have been cut short when copied).')
    try:
        public_key.verify(signature, INSPECTION_SIGN_CONTEXT + body)
    except InvalidSignature:
        raise LicenseError('bad_signature', 'The inspection key is not genuine or has been altered.')
    try:
        data = json.loads(body.decode('utf-8'))
        if data.get('product') != PRODUCT or data.get('kind') != 'inspection':
            raise ValueError('wrong kind')
        issued_ts, expires_ts = int(data['issued_ts']), int(data['expires_ts'])
        result = {'inspection_id': str(data['inspection_id']),
                  'license_id': str(data.get('license_id') or ''),
                  'licensee': str(data.get('licensee') or ''),
                  'machine_id': str(data['machine_id']),
                  'issued_ts': issued_ts, 'expires_ts': expires_ts}
    except Exception:
        raise LicenseError('malformed', 'The inspection key contents could not be read.')
    if not 0 < expires_ts - issued_ts <= INSPECTION_MAX_HOURS * 3600:
        raise LicenseError('malformed', 'The inspection key has an invalid duration.')
    return result


def sign_inspection(private_key, *, inspection_id, license_id, licensee, machine_code,
                    issued_ts, hours):
    """Vendor side: sign a view-only inspection key valid for ``hours`` hours."""
    hours = max(1, min(INSPECTION_MAX_HOURS, int(hours)))
    body = _compact_json({'v': PAYLOAD_VERSION, 'product': PRODUCT, 'kind': 'inspection',
                          'inspection_id': inspection_id, 'license_id': license_id or '',
                          'licensee': (licensee or '').strip(),
                          'machine_id': format_machine_code(machine_code),
                          'issued_ts': int(issued_ts), 'expires_ts': int(issued_ts) + hours * 3600})
    signature = private_key.sign(INSPECTION_SIGN_CONTEXT + body)
    return f'{INSPECTION_PREFIX}.{b64u_encode(body)}.{b64u_encode(signature)}'


# -- recovery codes (forgotten username / password) -----------------------
#
# The application is offline, so a lost administrator login is recovered with
# a challenge/response through the vendor: the app shows a REQUEST code, the
# vendor dashboard answers with a signed one-time TOKEN bound to that request
# and to the school's computer.  Nothing here reveals a password.

RECOVERY_REQUEST_PREFIX = 'SMR1'
RECOVERY_TOKEN_PREFIX = 'SMT1'
RECOVERY_SIGN_CONTEXT = b'school-manager-recovery-v1\n'     # never reused for licenses


def format_machine_code(code):
    clean = normalize_machine_code(code)
    return '-'.join(clean[i:i + 4] for i in range(0, len(clean), 4))


def _compact_json(data):
    return json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf-8')


def _request_check(body):
    return b64u_encode(hashlib.sha256(body).digest()[:4])


def make_recovery_request(nonce, machine_code, license_id, now_ts):
    """Build the request code the school reads out / sends to the vendor."""
    body = _compact_json({'n': nonce, 'm': normalize_machine_code(machine_code),
                          'l': license_id or '', 't': int(now_ts)})
    return f'{RECOVERY_REQUEST_PREFIX}.{b64u_encode(body)}.{_request_check(body)}'


def parse_recovery_request(text):
    """Decode a request code; raises ``LicenseError`` when it is damaged."""
    cleaned = ''.join((text or '').split())
    parts = cleaned.split('.')
    if len(parts) != 3 or parts[0] != RECOVERY_REQUEST_PREFIX:
        raise LicenseError('malformed', 'This is not a valid recovery request code.')
    try:
        body = b64u_decode(parts[1])
        data = json.loads(body.decode('utf-8'))
    except Exception:
        raise LicenseError('malformed', 'The request code is damaged (it may have been cut short).')
    if not hmac.compare_digest(_request_check(body), parts[2]):
        raise LicenseError('malformed', 'The request code is damaged (check digits do not match).')
    try:
        nonce, machine, license_id = str(data['n']), str(data['m']), str(data.get('l') or '')
        requested = int(data['t'])
    except (KeyError, TypeError, ValueError):
        raise LicenseError('malformed', 'The request code is incomplete.')
    if not re.fullmatch(r'[0-9a-f]{8,64}', nonce) or len(machine) != 16:
        raise LicenseError('malformed', 'The request code is incomplete.')
    return {'nonce': nonce, 'machine_code': format_machine_code(machine),
            'license_id': license_id,
            'requested_at': datetime.fromtimestamp(requested, timezone.utc).replace(tzinfo=None)}


def sign_recovery_token(private_key, nonce, machine_code, issued_ts, expires_ts):
    """Vendor side: sign a one-time reset token for one request on one machine."""
    body = _compact_json({'n': nonce, 'm': normalize_machine_code(machine_code),
                          'i': int(issued_ts), 'e': int(expires_ts)})
    signature = private_key.sign(RECOVERY_SIGN_CONTEXT + body)
    return f'{RECOVERY_TOKEN_PREFIX}.{b64u_encode(body)}.{b64u_encode(signature)}'


def verify_recovery_token(text, public_key_b64):
    """Check a token's signature and structure; return its fields.

    Matching the nonce, machine and expiry is the caller's job
    (``app/services/password_recovery.py``).
    """
    cleaned = ''.join((text or '').split())
    parts = cleaned.split('.')
    if len(parts) != 3 or parts[0] != RECOVERY_TOKEN_PREFIX:
        raise LicenseError('malformed', 'This is not a valid reset token.')
    public_key = _load_public_key(public_key_b64)
    try:
        body = b64u_decode(parts[1])
        signature = b64u_decode(parts[2])
    except Exception:
        raise LicenseError('malformed', 'The reset token is damaged (it may have been cut short).')
    try:
        public_key.verify(signature, RECOVERY_SIGN_CONTEXT + body)
    except InvalidSignature:
        raise LicenseError('bad_signature', 'The reset token is not genuine.')
    try:
        data = json.loads(body.decode('utf-8'))
        return {'nonce': str(data['n']), 'machine': str(data['m']),
                'issued_ts': int(data['i']), 'expires_ts': int(data['e'])}
    except Exception:
        raise LicenseError('malformed', 'The reset token could not be read.')


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
    features: tuple = None        # None = legacy key / not applicable: everything on
    roles: tuple = None           # None = legacy key: every role on; 'admin' is always on
    limits: dict = None           # {'wa_daily': n, 'wa_monthly': n}; missing = unlimited
    rev: int = 0
    plan: str = ''
    notice: str = ''              # vendor's message carried by the key (e.g. "renewal due")
    reminder_stage: int = None    # 30 / 14 / 7 / 3 / 1 while an active license is near its end
    inspection: bool = False      # a view-only inspection key is in effect
    inspection_until: datetime = None    # UTC, naive
    inspection_id: str = ''

    def feature_enabled(self, key):
        """True when this license includes ``key`` (legacy keys include all)."""
        if not self.enforced or self.features is None:
            return True
        return key in self.features

    def role_enabled(self, role):
        """True when users of ``role`` may sign in (admin always may)."""
        if not self.enforced or self.roles is None or role == 'admin':
            return True
        return role in self.roles

    def limit(self, name):
        """The numeric limit called ``name``, or None when unlimited."""
        return (self.limits or {}).get(name)

    @property
    def needs_attention(self):
        return (self.state in (GRACE, EXPIRED, UNLICENSED, INVALID)
                or self.expiring_soon or self.clock_rollback or self.inspection)


# -- manager -------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LicenseManager:
    """Loads, verifies and activates the license for one application."""

    def __init__(self, license_path, state_path, public_key_b64, *, enforced=True,
                 machine_code=None, now_fn=None, cache_seconds=30):
        self.license_path = Path(license_path)
        self.state_path = Path(state_path)
        self.inspection_path = self.license_path.with_name('inspection.key')
        self.inspection_state_path = self.license_path.with_name('inspection.state')
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

    def status(self, force=False, inspection=True):
        """Current status.  ``inspection=False`` gives the underlying license, ignoring
        any inspection key (the License page shows both)."""
        if not inspection:
            with self._lock:
                return self._evaluate_license()
        with self._lock:
            fresh = (self._cache is not None and not force
                     and (_time.monotonic() - self._cache_at) < self._cache_seconds)
            if fresh:
                return self._cache
            self._cache = self._evaluate()
            self._cache_at = _time.monotonic()
            return self._cache

    # -- inspection keys -----------------------------------------------
    def _now_ts(self):
        return int(self._now().replace(tzinfo=timezone.utc).timestamp())

    def activate_inspection(self, text):
        """Install a view-only inspection key for this computer."""
        with self._lock:
            data = verify_inspection_text(text, self.public_key_b64)
            expected = normalize_machine_code(data['machine_id'])
            if not hmac.compare_digest(expected.encode(),
                                       normalize_machine_code(self.machine_code()).encode()):
                raise LicenseError(
                    'wrong_machine', 'This inspection key was issued for a different computer.')
            base = self._evaluate_license()
            if data['license_id'] and base.license_id and data['license_id'] != base.license_id:
                raise LicenseError(
                    'wrong_license', 'This inspection key belongs to a different license.')
            now_ts = self._now_ts()
            if now_ts > data['expires_ts']:
                raise LicenseError('expired', 'This inspection key has already expired.')
            if now_ts < data['issued_ts'] - int(INSPECTION_START_TOLERANCE.total_seconds()):
                raise LicenseError(
                    'not_yet_valid',
                    "This computer's date and time look wrong (earlier than the key's issue time). "
                    'Please correct the Windows date and time and try again.')
            self._atomic_write(self.inspection_path, ''.join(text.split()) + '\n')
            self._write_inspection_state(data['inspection_id'], max(now_ts, data['issued_ts']))
            self._cache = None
            return self.status(force=True)

    def end_inspection(self):
        """Remove the inspection key (the school or the vendor is done)."""
        with self._lock:
            for path in (self.inspection_path, self.inspection_state_path):
                try:
                    path.unlink()
                except OSError:
                    pass
            self._cache = None
            return self.status(force=True)

    def _inspection_payload(self):
        """The installed inspection key's fields while it is valid right now, else None."""
        try:
            text = self.inspection_path.read_text(encoding='utf-8-sig').strip()
        except OSError:
            return None
        if not text:
            return None
        try:
            data = verify_inspection_text(text, self.public_key_b64)
        except LicenseError:
            return None
        expected = normalize_machine_code(data['machine_id'])
        if not hmac.compare_digest(expected.encode(),
                                   normalize_machine_code(self.machine_code()).encode()):
            return None
        stored = self._read_inspection_state(data['inspection_id'])
        system_ts = self._now_ts()
        effective = max(system_ts, stored)            # the clock cannot be rolled back
        if effective - stored >= 60 or not stored:
            self._write_inspection_state(data['inspection_id'], effective)
        if effective > data['expires_ts']:
            return None
        if effective < data['issued_ts'] - int(INSPECTION_START_TOLERANCE.total_seconds()):
            return None
        return data

    def _overlay_inspection(self, base):
        data = self._inspection_payload()
        if data is None:
            return base
        if data['license_id'] and base.license_id and data['license_id'] != base.license_id:
            return base                                # a key for some other license: ignored
        until = datetime.fromtimestamp(data['expires_ts'], timezone.utc).replace(tzinfo=None)
        return replace(
            base, read_only=True, level='info', features=None, roles=None,
            inspection=True, inspection_until=until, inspection_id=data['inspection_id'],
            title='Inspection mode',
            message=('A view-only inspection key is active until '
                     f'{until:%d %b %Y %H:%M} UTC. Everything can be viewed; nothing can be changed.'))

    def _inspection_signature(self, inspection_id, hwm):
        return hmac.new(self._state_key(), f'insp|{inspection_id}|{hwm}'.encode(),
                        hashlib.sha256).hexdigest()

    def _read_inspection_state(self, inspection_id):
        try:
            data = json.loads(self.inspection_state_path.read_text(encoding='utf-8'))
            if (data['id'] == inspection_id and hmac.compare_digest(
                    self._inspection_signature(inspection_id, int(data['hwm'])), data.get('sig', ''))):
                return int(data['hwm'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return 0

    def _write_inspection_state(self, inspection_id, hwm):
        body = {'id': inspection_id, 'hwm': int(hwm),
                'sig': self._inspection_signature(inspection_id, int(hwm))}
        try:
            self._atomic_write(self.inspection_state_path, json.dumps(body))
        except OSError:
            pass

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

            installed = self._installed_payload()
            if (installed and installed['license_id'] == payload['license_id']
                    and payload['_rev'] < installed['_rev']):
                raise LicenseError(
                    'older_key',
                    'A newer key for this license is already installed. '
                    'This older key was not applied.')

            previous_id = self._read_state().get('license_id')
            self._atomic_write(self.license_path, ''.join(text.split()) + '\n')
            if previous_id != payload['license_id']:
                # A different license was issued: restart the time mark from its issue date.
                self._write_state(payload['license_id'], self._floor(payload))
            self._cache = None
            return self.status(force=True)

    def _installed_payload(self):
        """Payload of the key currently on disk, or None (unreadable/invalid)."""
        text = self.read_license_text()
        if not text:
            return None
        try:
            return verify_license_text(text, self.public_key_b64)
        except LicenseError:
            return None

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
        base = self._evaluate_license()
        if base.state == DISABLED:
            return base
        return self._overlay_inspection(base)

    def _evaluate_license(self):
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
                      days_left=days_left, clock_rollback=rollback,
                      features=payload['_features'], roles=payload['_roles'], limits=dict(payload['_limits']),
                      rev=payload['_rev'], plan=payload['_plan'],
                      notice=payload['_notice'])

        if today <= expires:
            soon = days_left <= EXPIRING_SOON_DAYS
            when = 'today' if days_left == 0 else f'in {days_left} day{"s" if days_left != 1 else ""}'
            return self._base_status(
                state=ACTIVE, read_only=False, expiring_soon=soon,
                reminder_stage=reminder_stage(days_left),
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

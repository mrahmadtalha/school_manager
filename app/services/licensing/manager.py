"""LicenseManager: loads, verifies and activates the license for one application,
keeps the clock high-water mark and handles inspection keys."""

import hashlib
import hmac
import json
import os
import threading
import time as _time
from dataclasses import replace
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

from .constants import (ACTIVE, DISABLED, EXPIRED, EXPIRING_SOON_DAYS, GRACE, INSPECTION_START_TOLERANCE,
                        INVALID, ROLLBACK_TOLERANCE, STATE_WRITE_INTERVAL, UNLICENSED)
from .errors import LicenseError
from .inspection import verify_inspection_text
from .keys import reminder_stage, verify_license_text
from .machine import get_machine_code, normalize_machine_code
from .status import LicenseStatus


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

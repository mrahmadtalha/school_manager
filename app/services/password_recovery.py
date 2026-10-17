"""Offline recovery of a forgotten administrator username / password.

School Manager runs on the school's own computer with no internet, and
passwords are stored only as hashes - nobody (including the vendor) can read
one back.  Recovery is therefore a challenge/response through the vendor:

1. The login page's "Forgot username / password?" screen shows a **request
   code** (a random one-time nonce + this computer's machine code).
2. The school sends that code to the vendor.  The vendor dashboard checks who
   is asking and answers with a signed **reset token** bound to that exact
   nonce and machine, valid for a limited time.
3. The school enters the token.  The app verifies the signature with the
   public key already built in, checks the machine, the expiry and that the
   nonce is the current, unused one - then lets them pick an administrator
   account and set a new password.

There is no master password and no back door: without a token signed by the
vendor's private key nothing can be reset.  A token works once; replaying it,
or using it on another computer or after expiry, fails.

State (current nonce + list of used nonces) lives in ``recovery.state`` in the
school's data folder, signed with a machine-derived key (tamper-evident, the
same approach as ``license.state``).
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from app.services import licensing

STATE_FILE = 'recovery.state'
REQUEST_VALID_HOURS = 72       # an unused request code is kept this long
MAX_REMEMBERED_USED = 50
CLOCK_SKEW_SECONDS = 24 * 3600


class RecoveryError(Exception):
    """A reset token could not be accepted; ``message`` is safe to show."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _manager():
    from app.license_guard import get_manager
    return get_manager()


def _state_path():
    # Next to license.key/license.state, so it follows the school's data folder.
    return Path(_manager().state_path).parent / STATE_FILE


def _key(machine_code):
    return hashlib.sha256(
        f'sm-recovery-state-v1|{licensing.normalize_machine_code(machine_code)}'.encode()).digest()


def _sign(machine_code, nonce, created, used):
    body = json.dumps({'n': nonce, 'c': created, 'u': used}, sort_keys=True,
                      separators=(',', ':')).encode()
    return hmac.new(_key(machine_code), body, hashlib.sha256).hexdigest()


def _load(machine_code):
    """Return ``{'nonce', 'created', 'used'}``; a missing/tampered file = empty."""
    empty = {'nonce': None, 'created': 0, 'used': []}
    try:
        data = json.loads(_state_path().read_text(encoding='utf-8'))
        nonce, created, used = data.get('n'), int(data.get('c') or 0), list(data.get('u') or [])
        if hmac.compare_digest(_sign(machine_code, nonce, created, used), data.get('s', '')):
            return {'nonce': nonce, 'created': created, 'used': used}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return empty


def _save(machine_code, state):
    used = state['used'][-MAX_REMEMBERED_USED:]
    body = {'n': state['nonce'], 'c': state['created'], 'u': used,
            's': _sign(machine_code, state['nonce'], state['created'], used)}
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(body), encoding='utf-8')
    os.replace(tmp, path)


def get_request_code(force_new=False, now=None):
    """Return the current request code, creating one when needed.

    The same code is shown on every visit until it is used, expires or the
    school asks for a new one - so a token the vendor already issued for it
    stays valid while the school waits.
    """
    manager = _manager()
    machine = manager.machine_code()
    now = int(now if now is not None else time.time())
    state = _load(machine)
    stale = now - state['created'] > REQUEST_VALID_HOURS * 3600
    if force_new or not state['nonce'] or stale:
        state['nonce'] = secrets.token_hex(6)
        state['created'] = now
        _save(machine, state)
    license_id = manager.status().license_id or ''
    return licensing.make_recovery_request(state['nonce'], machine, license_id, state['created'])


def redeem(token_text, now=None):
    """Validate a vendor reset token and return its nonce (not yet consumed)."""
    manager = _manager()
    machine = manager.machine_code()
    now = int(now if now is not None else time.time())
    try:
        data = licensing.verify_recovery_token(token_text, manager.public_key_b64)
    except licensing.LicenseError as err:
        raise RecoveryError(err.message)

    if licensing.normalize_machine_code(data['machine']) != licensing.normalize_machine_code(machine):
        raise RecoveryError('This reset token was issued for a different computer.')
    if now > data['expires_ts']:
        raise RecoveryError('This reset token has expired. Ask your vendor for a new one.')
    if data['issued_ts'] - now > CLOCK_SKEW_SECONDS:
        raise RecoveryError("This computer's clock looks wrong. Correct the date and time, then try again.")

    state = _load(machine)
    if data['nonce'] in state['used']:
        raise RecoveryError('This reset token has already been used.')
    if not state['nonce'] or data['nonce'] != state['nonce']:
        raise RecoveryError('This token does not match the request code currently shown. '
                            'Send your vendor the latest request code and use the token for that one.')
    return data['nonce']


def mark_used(nonce):
    """Consume ``nonce`` so its token can never be used again."""
    machine = _manager().machine_code()
    state = _load(machine)
    if nonce not in state['used']:
        state['used'].append(nonce)
    if state['nonce'] == nonce:
        state['nonce'] = None
    _save(machine, state)

"""Recovery codes (forgotten username / password).

The application is offline, so a lost administrator login is recovered with
a challenge/response through the vendor: the app shows a REQUEST code, the
vendor dashboard answers with a signed one-time TOKEN bound to that request
and to the school's computer.  Nothing here reveals a password.
"""

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature

from .encoding import _compact_json, _load_public_key, b64u_decode, b64u_encode
from .errors import LicenseError
from .machine import format_machine_code, normalize_machine_code


RECOVERY_REQUEST_PREFIX = 'SMR1'
RECOVERY_TOKEN_PREFIX = 'SMT1'
RECOVERY_SIGN_CONTEXT = b'school-manager-recovery-v1\n'     # never reused for licenses


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

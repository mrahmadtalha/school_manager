"""Inspection keys: short, VIEW-ONLY keys the vendor sends for support / audits.

A short, VIEW-ONLY key on top of the real license: while it is valid every
module and the audit log are visible, but nothing can be changed, and a banner
says so.  It never replaces license.key.  Keys carry their own prefix and
signature context, so an inspection key can never be installed as a license.
"""

import json

from cryptography.exceptions import InvalidSignature

from .constants import (INSPECTION_MAX_HOURS, INSPECTION_PREFIX, INSPECTION_SIGN_CONTEXT,
                        PAYLOAD_VERSION, PRODUCT)
from .encoding import _compact_json, _load_public_key, b64u_decode, b64u_encode
from .errors import LicenseError
from .machine import format_machine_code


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

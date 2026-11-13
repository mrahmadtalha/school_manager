"""License keys: verify the signature and structure of a key and read its payload."""

import json
from datetime import date

from cryptography.exceptions import InvalidSignature

from .constants import (DEFAULT_GRACE_DAYS, FEATURES_ADDED_LATER, KEY_PREFIX, LIMIT_NAMES,
                        MAX_GRACE_DAYS, NOTICE_MAX_LENGTH, PAYLOAD_VERSION, PRODUCT,
                        REMINDER_MILESTONES, SIGN_CONTEXT)
from .encoding import _load_public_key, b64u_decode
from .errors import LicenseError


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

"""base64url helpers, compact JSON and public-key loading shared by every key type."""

import base64
import json
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .errors import LicenseError


def b64u_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


_B64U_CHARS = re.compile(r'^[A-Za-z0-9_-]+$')


def b64u_decode(text):
    """Strict base64url decode (the stdlib silently skips invalid characters)."""
    text = text.strip()
    if not _B64U_CHARS.match(text):
        raise ValueError('not valid base64url')
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _compact_json(data):
    return json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf-8')


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

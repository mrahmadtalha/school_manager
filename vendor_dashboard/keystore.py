"""The license signing key, encrypted at rest.

``tools/license_admin.py`` keeps the private key as a plain file in
``vendor_keys/``.  The dashboard imports it ONCE into an encrypted file
(``vendor_data/license_private.enc``: scrypt + AES-GCM, protected by the
dashboard password).  While the dashboard runs, the decrypted key lives in
memory only.  After checking your backup you can have the plain file removed.

Whoever steals the private key can issue licenses for every school, so this
file and the password are the crown jewels of the business.
"""

import base64
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

ENC_NAME = 'license_private.enc'
MIN_PASSWORD_LENGTH = 10


class KeyStoreError(Exception):
    """A key problem with a message that is safe to show on screen."""


def _b64(raw):
    return base64.b64encode(raw).decode('ascii')


def _unb64(text):
    return base64.b64decode(text.encode('ascii'))


def _derive(password, salt, n, r, p):
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode('utf-8'))


def public_b64(private_key, lic):
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return lic.b64u_encode(raw)


class KeyStore:
    def __init__(self, data_dir, plain_key_path, expected_public_b64, lic, *, kdf_n=2 ** 15):
        self.enc_path = Path(data_dir) / ENC_NAME
        self.plain_path = Path(plain_key_path)
        self.expected_public = expected_public_b64
        self.lic = lic
        self.kdf_n = kdf_n

    # -- state --------------------------------------------------------------
    def is_set_up(self):
        return self.enc_path.is_file()

    def plain_exists(self):
        return self.plain_path.is_file()

    # -- helpers --------------------------------------------------------------
    def _check_matches_app(self, private_key):
        if public_b64(private_key, self.lic) != self.expected_public:
            raise KeyStoreError(
                'This private key does not match the public key built into the application. '
                'Keys it signs would be rejected by every school.')

    def _encrypt(self, raw, password):
        salt, nonce = os.urandom(16), os.urandom(12)
        key = _derive(password, salt, self.kdf_n, 8, 1)
        blob = AESGCM(key).encrypt(nonce, raw, b'school-manager-vendor-key-v1')
        return json.dumps({'v': 1, 'kdf': 'scrypt', 'n': self.kdf_n, 'r': 8, 'p': 1,
                           'salt': _b64(salt), 'nonce': _b64(nonce), 'ct': _b64(blob)})

    def _decrypt(self, text, password):
        try:
            data = json.loads(text)
            key = _derive(password, _unb64(data['salt']), int(data['n']), int(data['r']), int(data['p']))
            return AESGCM(key).decrypt(_unb64(data['nonce']), _unb64(data['ct']),
                                       b'school-manager-vendor-key-v1')
        except InvalidTag:
            raise KeyStoreError('Wrong password.')
        except (ValueError, KeyError, TypeError):
            raise KeyStoreError('The encrypted key file is damaged.')

    def _write_enc(self, raw, password):
        self.enc_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.enc_path.with_name(self.enc_path.name + '.tmp')
        tmp.write_text(self._encrypt(raw, password), encoding='utf-8')
        os.replace(tmp, self.enc_path)

    @staticmethod
    def _check_password_strength(password):
        if len(password or '') < MIN_PASSWORD_LENGTH:
            raise KeyStoreError(f'Use a password of at least {MIN_PASSWORD_LENGTH} characters.')

    # -- operations -----------------------------------------------------------
    def setup(self, password):
        """First run: import the plain private key and encrypt it."""
        self._check_password_strength(password)
        if not self.plain_exists():
            raise KeyStoreError(
                f'No private key found at {self.plain_path}. Run this dashboard on the laptop '
                'that holds your vendor_keys folder (or run "python tools/license_admin.py init" '
                'if you have never created a key).')
        try:
            raw = self.lic.b64u_decode(self.plain_path.read_text(encoding='utf-8').strip())
            private_key = Ed25519PrivateKey.from_private_bytes(raw)
        except Exception:
            raise KeyStoreError('The private key file could not be read.')
        self._check_matches_app(private_key)
        self._write_enc(raw, password)
        return private_key

    def unlock(self, password):
        raw = self._decrypt(self.enc_path.read_text(encoding='utf-8'), password)
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
        self._check_matches_app(private_key)
        return private_key

    def change_password(self, old, new):
        self._check_password_strength(new)
        raw = self._decrypt(self.enc_path.read_text(encoding='utf-8'), old)
        self._write_enc(raw, new)

    def remove_plain(self, password):
        """Overwrite and delete the plain key file (only after proving the
        encrypted copy decrypts to the same key)."""
        if not self.plain_exists():
            return False
        encrypted_raw = self._decrypt(self.enc_path.read_text(encoding='utf-8'), password)
        plain_raw = self.lic.b64u_decode(self.plain_path.read_text(encoding='utf-8').strip())
        if encrypted_raw != plain_raw:
            raise KeyStoreError('The plain key file differs from the encrypted copy; not removing it.')
        size = self.plain_path.stat().st_size
        with self.plain_path.open('r+b') as handle:
            handle.write(os.urandom(size))
            handle.flush()
            os.fsync(handle.fileno())
        self.plain_path.unlink()
        return True

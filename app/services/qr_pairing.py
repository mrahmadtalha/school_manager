"""Easy guard-phone connection: pairing QR code, device token, LAN discovery.

Why this exists
---------------
Typing ``http://192.168.1.5:8000`` + username + password on a phone is hard for
a gate guard, and the address changes whenever the router hands the computer a
new IP.  So:

* The admin page shows a **connection QR code**.  The guard opens the app, taps
  *Scan QR to connect*, points at it - done.  No typing at all.
* The app then keeps a **device token** (not the password).  Changing the guard
  account's password, or deactivating it, disconnects every phone using it.
* If the computer's IP changes later, the app **finds the computer again by
  itself**: it shouts on the Wi-Fi (UDP broadcast) and the computer answers.

Everything here is plain Python (no database, no Flask) so it can be tested
alone.  The caller supplies the school secret (``QrConfig.secret``).

Formats
-------
pairing token   ``SMPAIR1.<user_id>.<expires_unix>.<signature>``   (short lived)
device token    ``SMDEV1.<user_id>.<signature>``                  (kept by the phone)
QR text         ``SMGUARD1|<address>[,<address>...]|<pairing token>``
"""

import hashlib
import hmac
import json
import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)

PAIR_PREFIX = 'SMPAIR1'
DEVICE_PREFIX = 'SMDEV1'
PAYLOAD_PREFIX = 'SMGUARD1'

#: How long a connection QR code stays valid.
PAIR_LIFETIME_SECONDS = 15 * 60

#: UDP port the computer listens on so phones can find it (Wi-Fi broadcast).
DISCOVERY_PORT = 50555
DISCOVERY_REQUEST = b'SMGUARD_WHERE_ARE_YOU'
DISCOVERY_APP = 'school_manager_guard'


# -- signatures --------------------------------------------------------------

def _signature(secret, message):
    digest = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return digest.hexdigest()[:32]


def _is_number(text, max_len):
    return bool(text) and text.isascii() and text.isdigit() and len(text) <= max_len


# -- pairing token (shown as a QR code on the computer) ------------------------------

def make_pair_token(secret, user_id, now=None, lifetime=PAIR_LIFETIME_SECONDS):
    expires = int(now if now is not None else time.time()) + int(lifetime)
    body = f'{int(user_id)}.{expires}'
    return f'{PAIR_PREFIX}.{body}.{_signature(secret, "pair:" + body)}'


def check_pair_token(secret, raw, now=None):
    """Return ``('ok', user_id)``, ``('expired', None)`` or ``('invalid', None)``."""
    if not isinstance(raw, str):
        return 'invalid', None
    parts = raw.strip().split('.')
    if len(parts) != 4 or parts[0] != PAIR_PREFIX:
        return 'invalid', None
    if not (_is_number(parts[1], 9) and _is_number(parts[2], 12)):
        return 'invalid', None
    expected = _signature(secret, f'pair:{parts[1]}.{parts[2]}')
    if not hmac.compare_digest(parts[3].strip().lower(), expected):
        return 'invalid', None
    current = int(now if now is not None else time.time())
    if current > int(parts[2]):
        return 'expired', None
    return 'ok', int(parts[1])


def parse_pair_token(secret, raw, now=None):
    """The guard's user id inside a valid, unexpired pairing token, else ``None``."""
    state, user_id = check_pair_token(secret, raw, now)
    return user_id if state == 'ok' else None


# -- device token (stored by the phone instead of the password) ----------------------

def make_device_token(secret, user_id, password_hash):
    """Token for one guard account.  It stops working when the password changes."""
    return f'{DEVICE_PREFIX}.{int(user_id)}.{_signature(secret, f"device:{int(user_id)}:{password_hash}")}'


def device_token_user_id(raw):
    """The user id written in a device token (NOT yet verified), else ``None``."""
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split('.')
    if len(parts) != 3 or parts[0] != DEVICE_PREFIX or not _is_number(parts[1], 9):
        return None
    return int(parts[1])


def verify_device_token(secret, raw, user_id, password_hash):
    if device_token_user_id(raw) != user_id:
        return False
    expected = make_device_token(secret, user_id, password_hash)
    return hmac.compare_digest(raw.strip().lower(), expected.lower())


# -- the text inside the QR code -----------------------------------------------------

def build_pair_payload(addresses, pair_token):
    cleaned = [a.strip().rstrip('/') for a in addresses if a and a.strip()]
    return f'{PAYLOAD_PREFIX}|{",".join(cleaned)}|{pair_token}'


def parse_pair_payload(text):
    """``(addresses, token)`` from a connection QR text, or ``None``."""
    if not isinstance(text, str):
        return None
    parts = text.strip().split('|')
    if len(parts) != 3 or parts[0] != PAYLOAD_PREFIX:
        return None
    addresses = [a.strip() for a in parts[1].split(',') if a.strip()]
    if not addresses or not parts[2].strip():
        return None
    return addresses, parts[2].strip()


# -- "where is the school computer?" (UDP broadcast answer) ----------------------------

def discovery_reply(http_port):
    return json.dumps({'app': DISCOVERY_APP, 'port': int(http_port)}).encode('utf-8')


def is_discovery_request(data):
    return isinstance(data, (bytes, bytearray)) and bytes(data).strip() == DISCOVERY_REQUEST


_responder_lock = threading.Lock()
_responder = None


def start_discovery_responder(http_port, udp_port=DISCOVERY_PORT):
    """Answer phones that ask where School Manager is.  Safe to call twice.

    Returns the running thread, or ``None`` when the port could not be used
    (the app still works - phones just cannot find the computer by themselves).
    """
    global _responder
    with _responder_lock:
        if _responder is not None and _responder.is_alive():
            return _responder
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(('0.0.0.0', int(udp_port)))
            sock.settimeout(1.0)
        except OSError:
            logger.warning('Guard phone discovery is not available (UDP port %s busy).', udp_port)
            return None

        reply = discovery_reply(http_port)

        def _serve():
            while True:
                try:
                    data, sender = sock.recvfrom(256)
                except socket.timeout:
                    continue
                except OSError:
                    return
                if is_discovery_request(data):
                    try:
                        sock.sendto(reply, sender)
                    except OSError:
                        pass

        _responder = threading.Thread(target=_serve, name='guard-discovery', daemon=True)
        _responder.start()
        return _responder

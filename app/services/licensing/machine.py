"""Machine identity: the short code a license is bound to."""

import hashlib
import sys
import uuid
from pathlib import Path

from .constants import PRODUCT


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


def format_machine_code(code):
    clean = normalize_machine_code(code)
    return '-'.join(clean[i:i + 4] for i in range(0, len(clean), 4))

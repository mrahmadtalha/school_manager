"""Shared loading for the vendor dashboard.

The dashboard reuses the application's own licensing and feature modules (so a
key it signs is, by construction, one the application can read).  They are
loaded by file path, exactly like ``tools/license_admin.py`` does, so this does
not start the Flask application.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lic = _load('sm_dash_licensing', 'app/services/licensing.py')
features = _load('sm_dash_features', 'app/services/features.py')
admin_tool = _load('sm_dash_license_admin', 'tools/license_admin.py')


def project_public_key():
    """The public key currently built into the application source."""
    text = (ROOT / 'app' / 'services' / 'license_public_key.py').read_text(encoding='utf-8')
    match = re.search(r"PUBLIC_KEY_B64 = '(.*)'", text)
    return match.group(1) if match else ''

"""Application configuration.

Configuration is resolved at ``create_app()`` time (not import time) so that a
missing secret key cannot break an unrelated import, and so tests can point the
app at an isolated database.

Secret key resolution order:

1. ``SECRET_KEY`` / ``APP_SECRET_KEY`` environment variable.
2. A randomly generated key persisted to ``<data dir>/.secret_key``
   (development and test only) so a clean checkout still starts.
3. ``RuntimeError`` in production - a production deployment must supply its own
   secret and must never silently generate one.
"""

import os
import secrets
import sys
from datetime import timedelta

from app.user_data import BASE_DIR, data_root

DEV_SECRET_NAME = '.secret_key'

DEFAULT_DEV_PORT = 5000
DEFAULT_PROD_PORT = 8000


def _is_frozen():
    """True inside a PyInstaller build (the product customers receive)."""
    return bool(getattr(sys, 'frozen', False))


def _flag(name, default=False):
    """Read a boolean environment flag."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _int(name, default):
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _database_uri():
    """Resolve the database URI, defaulting to <data dir>/school.db."""
    explicit = (os.environ.get('DATABASE_URL') or '').strip()
    if explicit:
        return explicit
    return 'sqlite:///' + (data_root() / 'school.db').as_posix()


def _resolve_secret_key(app_env, allow_generated_dev_key=True):
    key = (os.environ.get('SECRET_KEY') or os.environ.get('APP_SECRET_KEY') or '').strip()
    if key:
        return key

    if app_env == 'production':
        raise RuntimeError(
            'SECRET_KEY is required in production. Set SECRET_KEY (or APP_SECRET_KEY) '
            'in the environment before starting the app.'
        )

    if not allow_generated_dev_key:
        raise RuntimeError('SECRET_KEY is required for this configuration.')

    secret_file = data_root() / DEV_SECRET_NAME
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.exists():
        stored = secret_file.read_text(encoding='utf-8').strip()
        if stored:
            return stored

    generated = secrets.token_urlsafe(48)
    secret_file.write_text(generated, encoding='utf-8')
    print(
        'WARNING: SECRET_KEY was not set. Generated a local development key at '
        f'{secret_file} (git-ignored). Set SECRET_KEY for any shared or '
        'production deployment.'
    )
    return generated


def get_config():
    """Build the Flask configuration mapping for the active environment."""
    app_env = (os.environ.get('APP_ENV') or 'development').strip().lower()
    production = app_env == 'production'

    return {
        'APP_ENV': app_env,
        'DEBUG': _flag('FLASK_DEBUG', False),
        'TESTING': _flag('TESTING', False),
        'DATA_DIR': str(data_root()),
        'SECRET_KEY': _resolve_secret_key(app_env),
        'SQLALCHEMY_DATABASE_URI': _database_uri(),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {'pool_pre_ping': True},
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_COOKIE_SECURE': production and _flag('SESSION_COOKIE_SECURE', False),
        'PERMANENT_SESSION_LIFETIME': timedelta(hours=8),
        'LOGIN_MESSAGE': 'Please log in to access this page.',
        'LOGIN_MESSAGE_CATEGORY': 'warning',
        'HOST': os.environ.get('HOST', '127.0.0.1'),
        'PORT': _int('PORT', DEFAULT_PROD_PORT if production else DEFAULT_DEV_PORT),
        # WhatsApp bridge (optional Node service - see app/services/whatsapp_bridge.py)
        'WHATSAPP_NODE_URL': (os.environ.get('WHATSAPP_NODE_URL') or 'http://127.0.0.1:3001').rstrip('/'),
        'WHATSAPP_BRIDGE_TOKEN': (os.environ.get('WHATSAPP_BRIDGE_TOKEN') or '').strip(),
        # Where the optional bridge component is installed, and which Node
        # runtime to use (the installer ships a private Node with the bridge).
        'WHATSAPP_BRIDGE_DIR': (os.environ.get('WHATSAPP_BRIDGE_DIR') or None),
        'WHATSAPP_NODE_PATH': (os.environ.get('WHATSAPP_NODE_PATH') or None),
        # Login throttling (in-process; see README known limitations)
        'LOGIN_MAX_ATTEMPTS': _int('LOGIN_MAX_ATTEMPTS', 5),
        'LOGIN_LOCKOUT_SECONDS': _int('LOGIN_LOCKOUT_SECONDS', 300),
        # Offline licensing (see app/services/licensing.py).
        # Environment overrides are honoured ONLY when running from source, so a
        # customer running the packaged .exe cannot switch enforcement off or
        # redirect the license/state files with an environment variable.
        'LICENSE_ENFORCEMENT': True if _is_frozen() else _flag('LICENSE_ENFORCEMENT', True),
        'LICENSE_DIR': None if _is_frozen() else (os.environ.get('LICENSE_DIR') or None),
        # Demo/seed convenience
        'DEFAULT_DEMO_PASSWORD': os.environ.get('DEFAULT_DEMO_PASSWORD') or 'School@2026',
    }


class Config:
    """Backwards-compatible accessor for code that only needs defaults."""

    LOGIN_MESSAGE = 'Please log in to access this page.'
    LOGIN_MESSAGE_CATEGORY = 'warning'

    @staticmethod
    def as_dict():
        return get_config()


class DevelopmentConfig(Config):
    pass


class ProductionConfig(Config):
    pass


CONFIG_MAP = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}

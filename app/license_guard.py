"""Flask enforcement of the license: the read-only lockout.

Two independent layers, so one gap does not defeat the lockout:

1. **HTTP guard** (``before_request``) - while the license is expired, missing
   or invalid, every request that is not a plain read (GET/HEAD/OPTIONS) is
   refused, except a short allow-list (login, logout, license activation,
   change-password, manual backup).  Reading, printing and exporting data stays
   available so a school is never locked out of its own records.

2. **Database backstop** (``before_flush``) - some GET pages write behind the
   scenes (for example ``/fees`` creates the monthly charge rows the first time
   a month is opened).  While locked, any flush that would create, change or
   delete business data inside a request is refused, whatever the HTTP method.
   Audit-log rows and user accounts are exempt so logging in still works.

Both layers only act inside a web request; scripts, tests and background
threads are unaffected.
"""

from pathlib import Path

from flask import g, has_request_context, jsonify, redirect, render_template, request, url_for
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database import db
from app.services.licensing import LicenseManager, default_public_key

SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}

# Reachable in every license state, with any method.
ALWAYS_OPEN_ENDPOINTS = {
    'static',
    'main.healthz',
    'main.license_page',
    'auth.login',
    'auth.logout',
    'auth.shutdown',        # closing the software must always stay possible
}

# Non-read requests that are still allowed while the system is read-only.
WRITE_ALLOWED_ENDPOINTS = {
    'auth.change_password',
    'main.run_backup_now',       # protecting data must never be blocked
}

# Models that may still be written while locked (login bookkeeping + audit).
BACKSTOP_EXEMPT_MODELS = {'AuditLog', 'AdminUser'}

READ_ONLY_MESSAGE = ('The system is in read-only mode because the license is not active. '
                     'Records can be viewed and exported, but changes are disabled.')


class LicenseReadOnlyError(Exception):
    """Raised by the database backstop when locked code tries to write."""


def build_manager(app):
    """Create the LicenseManager for ``app`` from its configuration."""
    config = app.config
    directory = Path(config.get('LICENSE_DIR') or app.instance_path)
    return LicenseManager(
        license_path=directory / 'license.key',
        state_path=directory / 'license.state',
        public_key_b64=config.get('LICENSE_PUBLIC_KEY') or default_public_key(),
        enforced=config.get('LICENSE_ENFORCEMENT', True),
        machine_code=config.get('LICENSE_MACHINE_CODE'),
        now_fn=config.get('LICENSE_NOW_FN'),
        cache_seconds=config.get('LICENSE_CACHE_SECONDS', 30),
    )


def get_manager():
    from flask import current_app
    return current_app.extensions['license_manager']


def _blocked_response(status=None):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'license_read_only',
                        'message': READ_ONLY_MESSAGE}), 403
    return render_template('license_locked.html', license_status=status), 403


def _has_admin():
    from app.models import AdminUser
    return AdminUser.query.first() is not None


def _readonly_before_flush(session, flush_context, instances):
    if not has_request_context() or not g.get('license_read_only'):
        return
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if type(obj).__name__ in BACKSTOP_EXEMPT_MODELS:
            continue
        if obj in session.dirty and obj not in session.new and not session.is_modified(obj):
            continue
        raise LicenseReadOnlyError(
            f'Blocked write to {type(obj).__name__} while the license is read-only.')


_backstop_installed = False


def _install_backstop():
    global _backstop_installed
    if not _backstop_installed:
        event.listen(Session, 'before_flush', _readonly_before_flush)
        _backstop_installed = True


def install_license_guard(app):
    """Attach the manager, the request guard, the backstop and the template hooks.

    Must be called BEFORE the app's other ``before_request`` handlers are
    registered, so the license is checked first.
    """
    manager = build_manager(app)
    app.extensions['license_manager'] = manager
    _install_backstop()

    @app.before_request
    def _license_gate():
        status = manager.status()
        g.license_status = status
        g.license_read_only = status.read_only
        if not status.read_only:
            return None

        endpoint = request.endpoint
        if endpoint is None or endpoint in ALWAYS_OPEN_ENDPOINTS:
            return None

        # Fresh install: there is no data to protect yet, so send the user to
        # activation first (the school name on the license can guide setup).
        if not _has_admin():
            return redirect(url_for('main.license_page'))

        # The WhatsApp bridge polls this to fetch messages to send; while
        # read-only it gets an empty queue so nothing new goes out.
        if endpoint == 'main.whatsapp_pending_messages':
            return jsonify({'items': []})

        if request.method in SAFE_METHODS or endpoint in WRITE_ALLOWED_ENDPOINTS:
            return None
        return _blocked_response(status)

    @app.errorhandler(LicenseReadOnlyError)
    def _read_only_backstop(_error):
        db.session.rollback()
        return _blocked_response(g.get('license_status'))

    @app.context_processor
    def _inject_license_status():
        status = g.get('license_status') if has_request_context() else None
        return {'license_status': status or manager.status()}

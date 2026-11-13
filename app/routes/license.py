"""License status and activation page.

Reachable in every license state (see ``app.license_guard``).  Access rules:

* fresh install (no user exists yet): open, so the first license can be
  activated before the setup wizard;
* afterwards: administrators only.
"""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.license_guard import get_manager
from app.models import ROLE_ADMIN, AdminUser
from app.routes import main
from app.services.audit import log_action
from app.services.features import FEATURE_CATALOG
from app.services.licensing import INSPECTION_PREFIX, LicenseError
from app.services.provider_info import PROVIDER, whatsapp_link

MAX_LICENSE_FILE_BYTES = 16 * 1024

#: Pre-filled text for the referral WhatsApp button, kept short and friendly.
REFERRAL_WHATSAPP_MESSAGE = "Hi! I'd like to know more about the School Manager referral rewards."


def _license_extras():
    """Feature list, WhatsApp usage and provider/referral info shown next to
    the license status. The provider card is independent of license state
    (it shows on a fresh install too), so it is always included here."""
    from app.services import usage_limits, whatsapp_quota
    try:
        usage = whatsapp_quota.summary()
    except Exception:       # a counter problem must never break the license page
        usage = None
    try:
        size = usage_limits.summary()
    except Exception:       # same for the student / staff-login counts
        size = None
    return {'feature_catalog': FEATURE_CATALOG, 'wa_usage': usage, 'size_usage': size,
            'provider': PROVIDER,
            'provider_whatsapp_link': whatsapp_link(),
            'referral_whatsapp_link': whatsapp_link(REFERRAL_WHATSAPP_MESSAGE)}


def _render(manager, fresh_install, code=200):
    """The License page.  It always describes the REAL license (``real_status``); an
    inspection key in effect is shown separately (``license_status`` is the effective one)."""
    return render_template('license.html', real_status=manager.status(force=True, inspection=False),
                           license_status=manager.status(force=True),
                           fresh_install=fresh_install, **_license_extras()), code


@main.route('/license', methods=['GET', 'POST'])
def license_page():
    fresh_install = AdminUser.query.first() is None
    if not fresh_install:
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.path))
        if getattr(current_user, 'role', None) != ROLE_ADMIN:
            abort(403)

    manager = get_manager()

    if request.method == 'POST' and request.form.get('action') == 'end_inspection':
        manager.end_inspection()
        log_action('settings_change', entity_type='License',
                   summary='Inspection mode ended', after={'inspection': False})
        db.session.commit()
        flash('Inspection mode ended.', 'success')
        return redirect(url_for('main.license_page'))

    if request.method == 'POST':
        text = (request.form.get('license_key') or '').strip()
        upload = request.files.get('license_file')
        if upload and upload.filename:
            text = upload.read(MAX_LICENSE_FILE_BYTES).decode('utf-8-sig', errors='ignore').strip()

        if ''.join(text.split()).startswith(INSPECTION_PREFIX + '.'):
            # A view-only inspection key: it sits on top of the license and never replaces it.
            try:
                status = manager.activate_inspection(text)
            except LicenseError as err:
                flash(err.message, 'danger')
                return _render(manager, fresh_install, 400)
            log_action('settings_change', entity_type='License',
                       summary=f'Inspection mode started ({status.inspection_id}, view-only, '
                               f'until {status.inspection_until:%Y-%m-%d %H:%M} UTC)',
                       after={'inspection_id': status.inspection_id,
                              'until': status.inspection_until.isoformat()})
            db.session.commit()
            flash('Inspection mode is on: everything can be viewed, nothing can be changed.', 'info')
            return redirect(url_for('main.license_page'))

        try:
            status = manager.activate(text)
        except LicenseError as err:
            flash(err.message, 'danger')
            return _render(manager, fresh_install, 400)

        log_action('settings_change', entity_type='License',
                   summary=f'License {status.license_id} activated for {status.licensee} '
                           f'(valid until {status.expires:%Y-%m-%d})',
                   after={'license_id': status.license_id, 'licensee': status.licensee,
                          'expires': status.expires.isoformat()})
        db.session.commit()
        flash('License activated successfully.', 'success')
        if fresh_install:
            return redirect(url_for('auth.setup_admin'))
        return redirect(url_for('main.license_page'))

    return _render(manager, fresh_install)

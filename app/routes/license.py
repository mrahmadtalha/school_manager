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
from app.services.licensing import LicenseError

MAX_LICENSE_FILE_BYTES = 16 * 1024


@main.route('/license', methods=['GET', 'POST'])
def license_page():
    fresh_install = AdminUser.query.first() is None
    if not fresh_install:
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.path))
        if getattr(current_user, 'role', None) != ROLE_ADMIN:
            abort(403)

    manager = get_manager()

    if request.method == 'POST':
        text = (request.form.get('license_key') or '').strip()
        upload = request.files.get('license_file')
        if upload and upload.filename:
            text = upload.read(MAX_LICENSE_FILE_BYTES).decode('utf-8-sig', errors='ignore').strip()

        try:
            status = manager.activate(text)
        except LicenseError as err:
            flash(err.message, 'danger')
            return render_template('license.html', license_status=manager.status(force=True),
                                   fresh_install=fresh_install), 400

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

    return render_template('license.html', license_status=manager.status(force=True),
                           fresh_install=fresh_install)

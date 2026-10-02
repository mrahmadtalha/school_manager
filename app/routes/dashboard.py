"""Dashboard: executive analytics control center."""
from datetime import date

from flask import jsonify, redirect, render_template, url_for
from flask_login import current_user

from app.models import ROLE_ACCOUNTANT, ROLE_OWNER, ROLE_PARENT, StudentModel
from app.routes import main
from app.routes.settings import get_whatsapp_service_status
from app.services import dashboard_service


@main.route('/healthz')
def healthz():
    """Unauthenticated liveness probe used by the smoke test and monitoring."""
    from app.models import AdminUser
    return jsonify({
        'ok': True,
        'database': 'up',
        'users': AdminUser.query.count(),
        'students': StudentModel.query.count(),
    })


@main.route('/')
def dashboard():
    role = getattr(current_user, 'role', None)
    if role == ROLE_PARENT:
        return redirect(url_for('main.portal'))
    if role == ROLE_OWNER:
        return redirect(url_for('main.executive_dashboard'))
    if role == ROLE_ACCOUNTANT:
        return redirect(url_for('main.fees_list'))

    is_admin = bool(getattr(current_user, 'is_admin', False))
    context = dashboard_service.build_context(is_admin=is_admin)
    return render_template('dashboard.html',
                           dash=context,
                           today=date.today(),
                           whatsapp_status=get_whatsapp_service_status())

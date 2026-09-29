import logging

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user

from app.bootstrap import (
    create_default_admin,
    ensure_school_settings,
    inject_school_settings,
    install_auto_backup,
    migrate_admin_schema,
    migrate_attendance_schema,
    migrate_automation_schema,
    migrate_guardian_links,
    migrate_school_settings_schema,
    migrate_student_roll_schema,
    migrate_teacher_schema,
    register_blueprints,
)
from app.config import get_config
from app.database import db
from app.security import PUBLIC_ENDPOINTS, install_role_guard
from app.services.audit import format_local, install_audit_hooks

login_manager = LoginManager()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
)


def create_app(config_override=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(get_config())
    if config_override:
        app.config.update(config_override)

    db.init_app(app)
    install_audit_hooks()

    login_manager.login_view = 'auth.login'
    login_manager.login_message = app.config['LOGIN_MESSAGE']
    login_manager.login_message_category = app.config['LOGIN_MESSAGE_CATEGORY']
    login_manager.init_app(app)

    with app.app_context():
        from app.models import AdminUser  # noqa: F401  (ensures models are imported)

        db.create_all()
        migrate_admin_schema(app)
        migrate_attendance_schema(app)
        migrate_student_roll_schema(app)
        migrate_guardian_links(app)
        migrate_automation_schema(app)
        migrate_teacher_schema(app)
        migrate_school_settings_schema(app)
        register_blueprints(app)
        create_default_admin()
        ensure_school_settings()
        inject_school_settings(app)
        app.jinja_env.filters['localtime'] = format_local
        install_auto_backup(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import AdminUser
        try:
            return db.session.get(AdminUser, int(user_id))
        except (TypeError, ValueError):
            return None

    @app.before_request
    def enforce_setup():
        """Force the first-run setup wizard while no account exists."""
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        from app.models import AdminUser
        if not AdminUser.query.first():
            return redirect(url_for('auth.setup_admin'))
        return None

    @app.before_request
    def require_login():
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if request.path.startswith('/api/whatsapp/'):
            # Protected inside the route by the bridge token / admin session.
            return None
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'authentication_required'}), 401
            return redirect(url_for('auth.login', next=request.path))
        return None

    install_role_guard(app)

    @app.errorhandler(403)
    def forbidden(_error):
        if request.path.startswith('/api/'):
            return jsonify({'ok': False, 'error': 'forbidden'}), 403
        return render_template('forbidden.html'), 403

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith('/api/'):
            return jsonify({'ok': False, 'error': 'not_found'}), 404
        return render_template('not_found.html'), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        if request.path.startswith('/api/'):
            return jsonify({'ok': False, 'error': 'server_error'}), 500
        return render_template('server_error.html'), 500

    return app

from flask import Flask, redirect, request, url_for
from flask_login import LoginManager, current_user

from app.bootstrap import (
    create_default_admin,
    ensure_school_settings,
    inject_school_settings,
    migrate_attendance_schema,
    migrate_automation_schema,
    migrate_school_settings_schema,
    migrate_teacher_schema,
    register_blueprints,
)
from app.config import get_config
from app.database import db

login_manager = LoginManager()


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config())

    db.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = app.config['LOGIN_MESSAGE']
    login_manager.login_message_category = app.config['LOGIN_MESSAGE_CATEGORY']
    login_manager.init_app(app)

    with app.app_context():
        from app.models import AdminUser

        db.create_all()
        register_blueprints(app)
        create_default_admin()
        migrate_attendance_schema(app)
        migrate_automation_schema(app)
        migrate_teacher_schema(app)
        migrate_school_settings_schema(app)
        ensure_school_settings()
        inject_school_settings(app)

    @login_manager.user_loader
    def load_user(user_id):
        return AdminUser.query.get(int(user_id))

    @app.before_request
    def enforce_setup():
        if not AdminUser.query.first() and request.endpoint not in {'auth.setup_admin', 'auth.login', 'static', None}:
            return redirect(url_for('auth.setup_admin'))

    @app.before_request
    def require_login():
        public_endpoints = {'auth.login', 'auth.setup_admin', 'static', None}
        if request.endpoint in public_endpoints:
            return None

        if request.endpoint and request.endpoint.startswith('auth.'):
            return None

        if request.path.startswith('/api/whatsapp/'):
            return None

        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.path))

        return None

    return app
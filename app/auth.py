from datetime import datetime

from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from app.database import db
from app.models import (ROLE_ACCOUNTANT, ROLE_ADMIN, ROLE_OWNER, AdminUser,
                        SchoolSettings)
from app.seed_progress import (get_seed_job, seed_config_from_form,
                               start_seed_job)
from app.security import (
    clear_failed_logins,
    is_login_locked,
    lockout_seconds_remaining,
    password_problem,
    register_failed_login,
)
from app.services.audit import log_action

auth = Blueprint('auth', __name__)


def _safe_next(target):
    """Only allow same-site relative redirects."""
    if not target or not target.startswith('/') or target.startswith('//'):
        return None
    return target


@auth.route('/setup-admin', methods=['GET', 'POST'])
def setup_admin():
    if AdminUser.query.first():
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''
        school_name = (request.form.get('school_name') or '').strip() or 'School Manager'
        tagline = (request.form.get('tagline') or '').strip()
        address = (request.form.get('address') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        email = (request.form.get('email') or '').strip()
        include_dummy_data = request.form.get('dummy_data') == 'on'

        if not username or not password:
            flash('Username and password are required.', 'danger')
        elif len(username) > 80:
            flash('Username is too long (max 80 characters).', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        else:
            admin = AdminUser(username=username, role=ROLE_ADMIN, full_name='School Administrator')
            admin.set_password(password)
            db.session.add(admin)

            settings = SchoolSettings.query.first()
            if settings is None:
                settings = SchoolSettings()
                db.session.add(settings)

            settings.school_name = school_name
            settings.tagline = tagline
            settings.address = address
            settings.phone = phone
            settings.email = email

            db.session.flush()
            log_action('create', entity_type='AdminUser', entity_id=admin.id,
                       summary=f'Initial administrator "{username}" created via first-run setup',
                       after={'username': username, 'role': ROLE_ADMIN})

            if include_dummy_data:
                # Commit the admin account before the worker thread starts
                # writing, so both never fight over the SQLite write lock.
                db.session.commit()
                config = seed_config_from_form(request.form)
                token = start_seed_job(current_app._get_current_object(), config)
                session['seed_job_token'] = token
                return redirect(url_for('auth.setup_progress'))

            db.session.commit()
            flash('School setup completed successfully. Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('setup_admin.html')


@auth.route('/setup-progress')
def setup_progress():
    token = session.get('seed_job_token')
    if not token or get_seed_job(token) is None:
        return redirect(url_for('auth.login'))
    return render_template('setup_progress.html')


@auth.route('/setup-progress/status')
def setup_progress_status():
    token = session.get('seed_job_token')
    job = get_seed_job(token)
    if job is None:
        return jsonify({'state': 'unknown'}), 404
    return jsonify(job)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if username and is_login_locked(username):
            remaining = lockout_seconds_remaining(username)
            log_action('login_failed', entity_type='AdminUser',
                       summary=f'Locked-out login attempt for "{username}"')
            db.session.commit()
            flash(f'Too many failed attempts. Try again in about {remaining} seconds.', 'danger')
            return render_template('login.html'), 429

        user = AdminUser.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            clear_failed_logins(username)
            login_user(user)
            session.permanent = True
            user.last_login_at = datetime.utcnow()
            log_action('login', entity_type='AdminUser', entity_id=user.id,
                       summary=f'User "{user.username}" logged in ({user.role})')
            db.session.commit()

            landing = url_for('main.dashboard')
            if user.role == ROLE_OWNER:
                landing = url_for('main.executive_dashboard')
            elif user.role == ROLE_ACCOUNTANT:
                landing = url_for('main.fees_list')
            return redirect(_safe_next(request.args.get('next')) or landing)

        register_failed_login(username)
        log_action('login_failed', entity_type='AdminUser',
                   summary=f'Failed login for "{username}"')
        db.session.commit()
        flash('Incorrect username or password.', 'danger')

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    log_action('logout', entity_type='AdminUser', entity_id=current_user.id,
               summary=f'User "{current_user.username}" logged out')
    db.session.commit()
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/shutdown', methods=['POST'])
@login_required
def shutdown():
    """Exit School Manager (admin only) — stops the local server process."""
    if getattr(current_user, 'role', '') != ROLE_ADMIN:
        flash('Only an administrator can close School Manager.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.graceful_exit import request_shutdown
    request_shutdown(current_app._get_current_object())
    return render_template('shutdown.html')


@auth.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password') or ''
    new_pw = request.form.get('new_password') or ''
    confirm_pw = request.form.get('confirm_password') or ''

    problem = password_problem(new_pw)
    if not current_user.check_password(current_pw):
        flash('Current password is incorrect.', 'danger')
    elif new_pw != confirm_pw:
        flash('New passwords do not match.', 'danger')
    elif problem:
        flash(problem.replace('Password', 'New password', 1), 'danger')
    else:
        current_user.set_password(new_pw)
        log_action('user_admin', entity_type='AdminUser', entity_id=current_user.id,
                   summary=f'User "{current_user.username}" changed their own password',
                   after={'password': 'changed'})
        db.session.commit()
        flash('Password changed successfully!', 'success')

    return redirect(url_for('main.dashboard'))

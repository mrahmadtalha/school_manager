"""QR attendance: guard-phone API and the admin report page.

The guard Android app talks to the ``/api/qr/*`` endpoints (JSON).  When
phones are allowed onto the school network, every OTHER address of this
computer is refused for them - only the guard API is reachable from outside.
"""

import secrets
from datetime import date, datetime

from flask import (flash, g, jsonify, redirect, render_template, request,
                   send_file, session, url_for, abort)
from flask_login import current_user, login_user, logout_user

from app.database import db
from app.models import (ROLE_ADMIN, ROLE_GUARD, AdminUser, ClassModel,
                        SchoolSettings, StudentModel)
from app.models.qr_config import QrAbsentRun, QrConfig
from app.routes import main
from app.security import (clear_failed_logins, is_login_locked,
                          register_failed_login, role_required)
from app.services import qr_absent
from app.services import qr_attendance as qr
from app.services import qr_pairing
from app.services.audit import log_action
from app.services.photos import photo_path


def _is_local(address):
    address = address or ''
    return address.startswith('127.') or address in ('::1', '::ffff:127.0.0.1')


@main.before_app_request
def _only_guard_api_from_other_devices():
    """Other devices on the Wi-Fi may use the guard API and nothing else."""
    if _is_local(request.remote_addr):
        return None
    if request.path.startswith('/api/qr/'):
        return None
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'local_only'}), 403
    return ('This address is only for the School Manager guard app. '
            'Open School Manager on the school computer.'), 403


def _school_name():
    settings = SchoolSettings.query.first()
    return (getattr(settings, 'school_name', None) or 'School Manager')


def _user_payload(user):
    return {'username': user.username, 'full_name': user.full_name or user.username,
            'role': user.role}


def _today_counts():
    report = qr.build_daily_report(date.today())
    return {**report['counts'], 'percentage': report['percentage'],
            'is_school_day': report['is_school_day']}


# -- guard API -------------------------------------------------------------

def _guard_account_problem(user):
    """A JSON error (response, status) when this account may not use the guard app."""
    if user.role not in (ROLE_GUARD, ROLE_ADMIN):
        return jsonify({'ok': False, 'error': 'role_not_allowed',
                        'message': 'This account is not a guard account.'}), 403
    status = g.get('license_status')
    if status is not None and not status.role_enabled(user.role):
        return jsonify({'ok': False, 'error': 'role_not_in_license',
                        'message': 'The guard role is not included in this license.'}), 403
    return None


def _start_guard_session(user, how):
    """Sign the guard in and answer the app (shared by password, QR and device sign-in)."""
    login_user(user)
    session.permanent = True
    user.last_login_at = datetime.utcnow()
    log_action('login', entity_type='AdminUser', entity_id=user.id,
               summary=f'User "{user.username}" logged in from the guard app ({how})')
    db.session.commit()
    payload = {'ok': True, 'user': _user_payload(user), 'school_name': _school_name(),
               'today': _today_counts()}
    if user.role == ROLE_GUARD:
        # The phone keeps this instead of the password (see qr_pairing).
        payload['device_token'] = qr_pairing.make_device_token(
            qr.get_secret(), user.id, user.password_hash)
    return jsonify(payload)


def _throttle_key(kind):
    return f'{kind}@{request.remote_addr or "?"}'


@main.route('/api/qr/login', methods=['POST'])
def qr_api_login():
    data = request.get_json(silent=True) or {}
    device_token = str(data.get('device_token') or '').strip()
    if device_token:
        return _device_login(device_token)

    username = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')
    if not username or not password:
        return jsonify({'ok': False, 'error': 'missing_credentials',
                        'message': 'Enter the username and password.'}), 400
    if is_login_locked(username):
        return jsonify({'ok': False, 'error': 'locked',
                        'message': 'Too many wrong attempts. Try again in a few minutes.'}), 429

    user = AdminUser.query.filter_by(username=username).first()
    if not (user and user.is_active and user.check_password(password)):
        register_failed_login(username)
        log_action('login_failed', entity_type='AdminUser',
                   summary=f'Failed guard-app login for "{username}"')
        db.session.commit()
        return jsonify({'ok': False, 'error': 'bad_credentials',
                        'message': 'Wrong username or password.'}), 401
    problem = _guard_account_problem(user)
    if problem is not None:
        return problem

    clear_failed_logins(username)
    return _start_guard_session(user, user.role)


def _device_login(device_token):
    """Sign in with the token a phone received when it was connected by QR code."""
    key = _throttle_key('device')
    if is_login_locked(key):
        return jsonify({'ok': False, 'error': 'locked',
                        'message': 'Too many wrong attempts. Try again in a few minutes.'}), 429
    user_id = qr_pairing.device_token_user_id(device_token)
    user = db.session.get(AdminUser, user_id) if user_id else None
    valid = (user is not None and user.is_active and user.role == ROLE_GUARD
             and qr_pairing.verify_device_token(qr.get_secret(), device_token,
                                                user.id, user.password_hash))
    if not valid:
        register_failed_login(key)
        return jsonify({'ok': False, 'error': 'bad_device_token',
                        'message': 'This phone was disconnected. '
                                   'Scan the connection QR code on the computer again.'}), 401
    problem = _guard_account_problem(user)
    if problem is not None:
        return problem
    clear_failed_logins(key)
    return _start_guard_session(user, 'connected phone')


@main.route('/api/qr/pair', methods=['POST'])
def qr_api_pair():
    """The app scanned the connection QR code shown on the computer."""
    data = request.get_json(silent=True) or {}
    key = _throttle_key('pair')
    if is_login_locked(key):
        return jsonify({'ok': False, 'error': 'locked',
                        'message': 'Too many wrong attempts. Try again in a few minutes.'}), 429
    state, user_id = qr_pairing.check_pair_token(qr.get_secret(), data.get('pair_token'))
    if state == 'expired':
        return jsonify({'ok': False, 'error': 'pair_expired',
                        'message': 'This connection code has expired. '
                                   'Press "New code" on the computer and scan again.'}), 401
    user = db.session.get(AdminUser, user_id) if user_id else None
    if state != 'ok' or user is None or not user.is_active or user.role != ROLE_GUARD:
        register_failed_login(key)
        log_action('login_failed', entity_type='AdminUser',
                   summary='Guard-app connection with a wrong or old QR code')
        db.session.commit()
        return jsonify({'ok': False, 'error': 'pair_invalid',
                        'message': 'This is not a School Manager connection code. '
                                   'Scan the code shown on the computer.'}), 401
    problem = _guard_account_problem(user)
    if problem is not None:
        return problem
    clear_failed_logins(key)
    return _start_guard_session(user, 'connection QR code')


@main.route('/api/qr/logout', methods=['POST'])
def qr_api_logout():
    logout_user()
    session.clear()
    return jsonify({'ok': True})


@main.route('/api/qr/ping')
def qr_api_ping():
    """Lets the app check the connection and show today's numbers."""
    return jsonify({'ok': True, 'user': _user_payload(current_user),
                    'school_name': _school_name(),
                    'server_time': datetime.now().isoformat(timespec='seconds'),
                    'today': _today_counts()})


@main.route('/api/qr/scan', methods=['POST'])
def qr_api_scan():
    data = request.get_json(silent=True) or {}
    token = data.get('token')
    if not isinstance(token, str) or not token.strip():
        return jsonify({'ok': False, 'code': 'invalid_qr', 'student': None,
                        'message': qr.MESSAGES['invalid_qr'][0],
                        'message_ur': qr.MESSAGES['invalid_qr'][1]}), 400
    result = qr.process_scan(token)
    result['today'] = _today_counts()
    return jsonify(result)


@main.route('/api/qr/photo/<int:student_id>')
def qr_student_photo(student_id):
    student = db.session.get(StudentModel, student_id)
    if student is None or not student.photo_filename:
        abort(404)
    path = photo_path('student', student.photo_filename)
    if not path:
        abort(404)
    return send_file(path, mimetype='image/jpeg')


@main.route('/guard')
def qr_guard_home():
    """Landing page when a guard account signs in on the computer's browser."""
    return render_template('qr_guard_home.html')


# -- admin pages -----------------------------------------------------------

@main.route('/attendance/qr')
def qr_attendance_report():
    """Old address. QR attendance is now a tab of the attendance page."""
    params = {'tab': 'qr'}
    date_text = request.args.get('date') or ''
    if date_text:
        params['date'] = date_text
    class_id = request.args.get('class_id', type=int)
    if class_id:
        params['class_id'] = class_id
    return redirect(url_for('main.student_attendance', **params))


@main.route('/attendance/qr/settings', methods=['POST'])
def qr_attendance_settings():
    config = QrConfig.get()
    config.lan_access = request.form.get('lan_access') == 'on'
    log_action('settings_change', entity_type='QrConfig', entity_id=config.id,
               summary='Guard phone access ' + ('allowed' if config.lan_access else 'turned off')
                       + ' (applies after School Manager restarts)')
    db.session.commit()
    flash('Saved. Close and reopen School Manager for this to take effect.', 'success')
    return redirect(url_for('main.student_attendance', tab='qr'))


@main.route('/attendance/qr/pair-code')
@role_required(ROLE_ADMIN)
def qr_pair_code():
    """A fresh connection QR text for one guard account (the page draws the QR)."""
    user_id = request.args.get('user_id', type=int)
    guard = db.session.get(AdminUser, user_id) if user_id else None
    if guard is None or guard.role != ROLE_GUARD or not guard.is_active:
        return jsonify({'ok': False, 'message': 'Choose a guard account first.'}), 404
    info = qr.pairing_info(guard, request.environ.get('SERVER_PORT') or '8000')
    if info is None:
        return jsonify({'ok': False,
                        'message': 'This computer has no Wi-Fi / network address right now. '
                                   'Connect it to the school Wi-Fi or turn on a hotspot.'}), 409
    return jsonify({'ok': True, **info})


@main.route('/attendance/qr/guard/create', methods=['POST'])
@role_required(ROLE_ADMIN)
def qr_create_guard():
    """One-click guard account, so connecting a phone never needs the Users page."""
    status = g.get('license_status')
    if status is not None and not status.role_enabled(ROLE_GUARD):
        flash('The guard role is not included in this school\'s license.', 'danger')
        return redirect(url_for('main.student_attendance', tab='qr'))
    wanted = (request.form.get('username') or '').strip() or 'guard'
    username, number = wanted, 2
    while AdminUser.query.filter_by(username=username).first():
        username = f'{wanted}{number}'
        number += 1
    password = secrets.token_hex(4) + 'Gd7'          # letters + numbers, 11 characters
    user = AdminUser(username=username, role=ROLE_GUARD, full_name='Gate Guard')
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    log_action('user_admin', entity_type='AdminUser', entity_id=user.id,
               summary=f'Created user "{username}" with role {ROLE_GUARD} (from the QR attendance page)',
               after={'username': username, 'role': ROLE_GUARD})
    db.session.commit()
    flash(f'Guard account "{username}" created. You do not need its password when you connect '
          f'the phone by QR code (if you ever want to type it: {password}).', 'success')
    return redirect(url_for('main.student_attendance', tab='qr'))


@main.route('/attendance/qr/auto-absent/settings', methods=['POST'])
def qr_auto_absent_settings():
    if current_user.role != ROLE_ADMIN:
        abort(403)
    values, error = qr_absent.clean_settings(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('main.student_attendance', tab='qr'))
    config = QrConfig.get()
    for name, value in values.items():
        setattr(config, name, value)
    state = 'on' if config.auto_absent_enabled else 'off'
    log_action('settings_change', entity_type='QrConfig', entity_id=config.id,
               summary=(f'Auto-absent turned {state}: cutoff {config.absent_cutoff_time}, '
                        f'mode {config.absent_mode}, safety {config.absent_min_scan_percent}%, '
                        f'message delay {config.absent_message_delay_minutes} min'))
    db.session.commit()
    flash('Auto-absent settings saved.', 'success')
    return redirect(url_for('main.student_attendance', tab='qr'))


@main.route('/attendance/qr/auto-absent/<int:run_id>/<action>', methods=['POST'])
def qr_auto_absent_decide(run_id, action):
    if current_user.role != ROLE_ADMIN:
        abort(403)
    if action not in ('approve', 'reject'):
        abort(404)
    name = current_user.username
    run = db.session.get(QrAbsentRun, run_id)
    if run is None:
        abort(404)
    day = run.run_date
    if action == 'approve':
        outcome = qr_absent.approve_run(run_id, user_name=name)
        if outcome is None:
            flash('This list was already decided.', 'warning')
        else:
            log_action('attendance_auto_absent', entity_type='QrAbsentRun', entity_id=run_id,
                       summary=f'{name} approved auto-absent for {day}: {outcome["marked"]} marked absent')
            db.session.commit()
            flash(f'{outcome["marked"]} student(s) marked absent.', 'success')
    else:
        if qr_absent.reject_run(run_id, user_name=name):
            log_action('attendance_auto_absent', entity_type='QrAbsentRun', entity_id=run_id,
                       summary=f'{name} rejected auto-absent for {day}: nobody marked absent')
            db.session.commit()
            flash('Nobody was marked absent.', 'success')
        else:
            flash('This list was already decided.', 'warning')
    return redirect(url_for('main.student_attendance', tab='qr', date=day.strftime('%Y-%m-%d')))

"""School Manager - license manager dashboard (vendor only).

Runs ONLY on your own laptop: it binds to 127.0.0.1, refuses other host names,
and needs the dashboard password, which also unlocks your license signing key
(kept encrypted on disk, decrypted in memory while the dashboard is open).

From here you: register schools, switch features on/off, set WhatsApp limits,
issue / renew / update keys, move a school to a new PC, track payments, and
answer "forgot username/password" requests.  NEVER ship this folder to schools
(the product build excludes it).
"""

import csv
import io
import json
import os
import re
import secrets
import tempfile
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from flask import (Flask, Response, abort, flash, redirect, render_template, request,
                   send_file, session, url_for)

from vendor_dashboard import issuer
from vendor_dashboard.core import ROOT, features as features_mod, lic, project_public_key
from vendor_dashboard.keystore import KeyStore, KeyStoreError
from vendor_dashboard.store import Store

# How each license status is shown: plain words, a colour tone and an icon (never colour alone).
STATUS_UI = {
    'active': {'label': 'Active', 'tone': 'ok', 'icon': 'fa-circle-check'},
    'soon': {'label': 'Ending soon', 'tone': 'soon', 'icon': 'fa-hourglass-half'},
    'grace': {'label': 'Extra time', 'tone': 'grace', 'icon': 'fa-clock'},
    'expired': {'label': 'Ended', 'tone': 'bad', 'icon': 'fa-circle-xmark'},
    'none': {'label': 'No key yet', 'tone': 'none', 'icon': 'fa-circle-minus'},
}
SCHOOL_FILTERS = ('all', 'active', 'soon', 'grace', 'expired', 'none', 'inactive')
OPEN_ENDPOINTS = {'unlock', 'static', 'healthz'}
ALLOWED_HOSTS = {'127.0.0.1', 'localhost'}
MAX_UNLOCK_FAILURES = 5
LOCKOUT_SECONDS = 60


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-') or 'school'


def _int_or_none(value):
    value = (value or '').strip()
    if not value:
        return None
    number = int(value)
    if number < 0:
        raise ValueError('negative')
    return number


def _money_or_none(value):
    """A price typed in a form: blank = not set, otherwise a number that is not negative."""
    value = (value or '').strip().replace(',', '')
    if not value:
        return None
    number = float(value)
    if number < 0:
        raise ValueError('negative')
    return number


def create_app(config=None):
    config = config or {}
    app = Flask(__name__, static_folder=str(ROOT / 'app' / 'static' / 'vendor'),
                static_url_path='/vendor')
    data_dir = Path(config.get('DATA_DIR') or os.environ.get('VENDOR_DATA_DIR') or ROOT / 'vendor_data')
    keys_dir = Path(config.get('KEYS_DIR') or os.environ.get('VENDOR_KEYS_DIR') or ROOT / 'vendor_keys')
    app.config.update(SECRET_KEY=secrets.token_hex(32), TESTING=bool(config.get('TESTING')))

    store = Store(data_dir)
    store.seed_plans(features_mod.DEFAULT_PLANS)
    store.sync_premium_plan(features_mod.ALL_FEATURES)
    keystore = KeyStore(data_dir, keys_dir / 'license_private.key',
                        config.get('PUBLIC_KEY') or project_public_key(), lic,
                        kdf_n=config.get('KDF_N', 2 ** 15))
    vendor = SimpleNamespace(store=store, keystore=keystore, private_key=None, failures=[],
                             today=config.get('TODAY_FN') or date.today,
                             data_dir=data_dir, keys_dir=keys_dir)
    app.extensions['vendor'] = vendor

    # -- guards ---------------------------------------------------------------
    @app.before_request
    def _guard():
        host = (request.host or '').rsplit(':', 1)[0].strip('[]').lower()
        if host not in ALLOWED_HOSTS:
            abort(403)
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(16)
        if request.method == 'POST':
            sent = request.form.get('_csrf', '')
            if not sent or not secrets.compare_digest(sent, session['csrf']):
                abort(400, 'Invalid form token - reload the page and try again.')
        if request.endpoint in OPEN_ENDPOINTS:
            return None
        if not session.get('unlocked') or vendor.private_key is None:
            return redirect(url_for('unlock'))
        return None

    @app.after_request
    def _headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.context_processor
    def _inject():
        attention = 0
        if session.get('unlocked'):
            attention = sum(1 for row in store.schools_with_license() if row['active'] and issuer.license_status(
                row['expires'], row['grace_days'], vendor.today())[0] in ('soon', 'grace', 'expired'))
        return {'csrf_token': session.get('csrf', ''), 'catalog': features_mod.FEATURE_CATALOG, 'role_catalog': features_mod.ROLE_CATALOG,
                'today': vendor.today(), 'reasons': issuer.REASONS, 'status_ui': STATUS_UI,
                'feature_labels': {row[0]: row[1] for row in features_mod.FEATURE_CATALOG},
                'role_labels': {row[0]: row[1] for row in features_mod.ROLE_CATALOG},
                'nav_attention': attention}

    app.jinja_env.filters['fromjson'] = lambda text: json.loads(text) if text else []
    app.jinja_env.filters['nicedate'] = lambda iso: (date.fromisoformat(iso[:10]).strftime('%d %b %Y')
                                                     if iso else '-')
    app.jinja_env.filters['niceplan'] = lambda name: (name or '-').replace('_', ' ').title()
    app.jinja_env.filters['money'] = issuer.money_text
    app.jinja_env.filters['limit'] = issuer.limit_text

    def decorated(school_row):
        """Attach status/reminder info to a school row (from schools_with_license)."""
        status = issuer.license_status(school_row['expires'], school_row['grace_days'], vendor.today())
        item = {'school': school_row, 'code': status[0], 'label': status[1], 'days_left': status[2],
                'when': issuer.status_sentence(status[0], status[2], school_row['grace_days']),
                'reminder': ''}
        if school_row['expires']:
            item['reminder'] = issuer.reminder_text(school_row['name'], school_row['expires'], status[2])
        return item

    # -- unlock / logout -------------------------------------------------------
    @app.route('/healthz')
    def healthz():
        return 'ok'

    @app.route('/unlock', methods=['GET', 'POST'])
    def unlock():
        setup_mode = not keystore.is_set_up()
        now = time.time()
        vendor.failures[:] = [t for t in vendor.failures if now - t < LOCKOUT_SECONDS]
        if request.method == 'POST':
            password = request.form.get('password') or ''
            if not setup_mode and len(vendor.failures) >= MAX_UNLOCK_FAILURES:
                flash(f'Too many wrong passwords. Wait about {LOCKOUT_SECONDS} seconds.', 'danger')
            else:
                try:
                    if setup_mode:
                        if password != (request.form.get('confirm') or ''):
                            raise KeyStoreError('The two passwords do not match.')
                        vendor.private_key = keystore.setup(password)
                    else:
                        vendor.private_key = keystore.unlock(password)
                except KeyStoreError as err:
                    if not setup_mode:
                        vendor.failures.append(now)
                        if not app.config['TESTING']:
                            time.sleep(1)
                    flash(err.args[0], 'danger')
                else:
                    session['unlocked'] = True
                    vendor.failures.clear()
                    return redirect(url_for('index'))
        return render_template('unlock.html', setup_mode=setup_mode,
                               plain_path=keystore.plain_path, plain_exists=keystore.plain_exists())

    @app.route('/logout', methods=['POST'])
    def logout():
        vendor.private_key = None
        session.clear()
        return redirect(url_for('unlock'))

    # -- home -------------------------------------------------------------------
    @app.route('/')
    def index():
        items = [decorated(row) for row in store.schools_with_license()]
        active_items = [i for i in items if i['school']['active']]
        counts = {code: sum(1 for i in active_items if i['code'] == code)
                  for code in ('active', 'soon', 'grace', 'expired', 'none')}
        attention = sorted((i for i in active_items if i['code'] in ('soon', 'grace', 'expired')),
                           key=lambda i: i['days_left'])
        waiting = [i for i in active_items if i['code'] == 'none']
        return render_template('index.html', counts=counts, attention=attention, waiting=waiting,
                               total=len(active_items))

    # -- schools ------------------------------------------------------------------
    @app.route('/schools')
    def schools():
        search = (request.args.get('q') or '').strip()
        status = request.args.get('status') or 'all'
        if status not in SCHOOL_FILTERS:
            status = 'all'
        everything = [decorated(row) for row in store.schools_with_license(search or None)]
        counts = {code: sum(1 for i in everything if i['school']['active'] and i['code'] == code)
                  for code in ('active', 'soon', 'grace', 'expired', 'none')}
        counts['inactive'] = sum(1 for i in everything if not i['school']['active'])
        counts['all'] = len(everything)
        if status == 'all':
            items = everything
        elif status == 'inactive':
            items = [i for i in everything if not i['school']['active']]
        else:
            items = [i for i in everything if i['school']['active'] and i['code'] == status]
        return render_template('schools.html', items=items, search=search, status=status, counts=counts)

    @app.route('/schools/new', methods=['GET', 'POST'])
    def school_new():
        if request.method == 'POST':
            name = (request.form.get('name') or '').strip()
            if not name:
                flash('Enter the school name.', 'danger')
            else:
                machine = request.form.get('machine_code') or ''
                if machine.strip() and len(lic.normalize_machine_code(machine)) != 16:
                    flash('That machine code is not valid (it should have 16 letters/digits).', 'danger')
                    return render_template('school_form.html', school=request.form)
                school_id = store.create_school(
                    name=name, contact_name=request.form.get('contact_name'),
                    phone=request.form.get('phone'), email=request.form.get('email'),
                    city=request.form.get('city'),
                    billing='monthly' if request.form.get('billing') == 'monthly' else 'yearly',
                    machine_code=lic.format_machine_code(machine) if machine.strip() else None,
                    notes=request.form.get('notes'))
                flash('School added. Now send it its first key below.', 'success')
                return redirect(url_for('school_detail', school_id=school_id))
        return render_template('school_form.html', school={})

    def _get_school_or_404(school_id):
        school = store.school(school_id)
        if school is None:
            abort(404)
        return school

    @app.route('/schools/<int:school_id>')
    def school_detail(school_id):
        school = _get_school_or_404(school_id)
        latest = store.latest_license(school_id)
        plans = store.plans()
        plan_map = {p['name']: p for p in plans}
        base_plan = plan_map.get((latest['plan'] if latest else '') or 'standard') or (plans[0] if plans else None)
        if latest:
            form = {
                'reason': 'renew', 'machine_code': latest['machine_code'],
                'plan': latest['plan'] or '', 'features': json.loads(latest['features']),
                'wa_daily': latest['wa_daily'], 'wa_monthly': latest['wa_monthly'],
                'grace_days': latest['grace_days'],
                'max_students': latest['max_students'], 'max_staff': latest['max_staff'],
                'roles': (json.loads(latest['roles']) if latest['roles'] else list(features_mod.ALL_ROLES)),
            }
        else:
            form = {
                'reason': 'new', 'machine_code': school['machine_code'] or '',
                'plan': base_plan['name'] if base_plan else '',
                'features': base_plan['features'] if base_plan else [],
                'wa_daily': base_plan['wa_daily'] if base_plan else None,
                'wa_monthly': base_plan['wa_monthly'] if base_plan else None,
                'max_students': base_plan['max_students'] if base_plan else None,
                'max_staff': base_plan['max_staff'] if base_plan else None,
                'grace_days': lic.DEFAULT_GRACE_DAYS,
                'roles': list(features_mod.ALL_ROLES),
            }
        form['period'] = '1m' if school['billing'] == 'monthly' else '1y'
        today = vendor.today()
        current_expires = date.fromisoformat(latest['expires']) if latest else None
        # What each validity choice would give, worked out with the same rule the key uses.
        period_preview = {}
        for period_key in issuer.PERIODS:
            try:
                ends = issuer.compute_expiry(period_key, None, current_expires, today)
            except issuer.IssueError:
                ends = None
            period_preview[period_key] = ends.isoformat() if ends and ends >= today else ''
        wanted = request.args.get('do')
        if latest and wanted in ('renew', 'update', 'move'):      # e.g. the Renew button on Home
            form['reason'] = wanted
            if wanted != 'renew' and period_preview['keep']:
                form['period'] = 'keep'
        # What the school pays for, compared with what its key gives (the plan as it is now).
        current_plan = plan_map.get(latest['plan']) if latest and latest['plan'] else None
        drift = issuer.plan_differences(current_plan, issuer.key_as_dict(latest)) if current_plan else None
        matched = False
        if current_plan and request.args.get('match_plan'):     # "Use the plan's settings" button
            form.update(plan=current_plan['name'], features=list(current_plan['features']),
                        wa_daily=current_plan['wa_daily'], wa_monthly=current_plan['wa_monthly'],
                        max_students=current_plan['max_students'], max_staff=current_plan['max_staff'],
                        reason='update')
            if period_preview['keep']:
                form['period'] = 'keep'
            matched = True
        price_plan = current_plan or (base_plan if not latest else None)
        price = issuer.plan_price(price_plan, school['billing'])
        status = issuer.license_status(latest['expires'] if latest else None,
                                       latest['grace_days'] if latest else 0, today)
        return render_template(
            'school.html', school=school, latest=latest, status=status, form=form, plans=plans,
            current_plan=current_plan, drift=drift, matched=matched, price=price, price_plan=price_plan,
            when=issuer.status_sentence(status[0], status[2], latest['grace_days'] if latest else 0),
            period_preview=period_preview,
            periods=issuer.PERIOD_LABELS, licenses=store.licenses_for(school_id),
            payments=store.payments_for(school_id), recoveries=store.recoveries(school_id),
            inspections=store.inspections_for(school_id), inspection_hours=issuer.INSPECTION_HOURS,
            reminder=(issuer.reminder_text(school['name'], latest['expires'], status[2]) if latest else ''))

    @app.route('/schools/<int:school_id>/edit', methods=['POST'])
    def school_edit(school_id):
        _get_school_or_404(school_id)
        name = (request.form.get('name') or '').strip()
        if not name:
            flash('The school name cannot be empty.', 'danger')
            return redirect(url_for('school_detail', school_id=school_id))
        store.update_school(
            school_id, name=name, contact_name=request.form.get('contact_name'),
            phone=request.form.get('phone'), email=request.form.get('email'),
            city=request.form.get('city'),
            billing='monthly' if request.form.get('billing') == 'monthly' else 'yearly',
            notes=request.form.get('notes'), active=1 if request.form.get('active') else 0)
        flash('School details saved.', 'success')
        return redirect(url_for('school_detail', school_id=school_id))

    @app.route('/schools/<int:school_id>/issue', methods=['POST'])
    def school_issue(school_id):
        _get_school_or_404(school_id)
        form = request.form
        try:
            row_id = issuer.issue_key(
                store, vendor.private_key, school_id,
                reason=form.get('reason') or 'renew', machine_code=form.get('machine_code') or '',
                plan=form.get('plan') or '', features=form.getlist('features'),
                wa_daily=form.get('wa_daily'), wa_monthly=form.get('wa_monthly'),
                period=form.get('period') or 'keep', custom_expires=form.get('custom_expires'),
                grace_days=form.get('grace_days'), note=form.get('note'), today=vendor.today(),
                roles=form.getlist('roles') if form.get('roles_present') else None,
                notice=form.get('notice'),
                max_students=form.get('max_students'), max_staff=form.get('max_staff'))
        except issuer.IssueError as err:
            flash(err.args[0], 'danger')
            return redirect(url_for('school_detail', school_id=school_id))
        flash('Key issued. Send it to the school below.', 'success')
        return redirect(url_for('key_view', row_id=row_id))

    @app.route('/schools/<int:school_id>/inspection', methods=['POST'])
    def school_inspection(school_id):
        _get_school_or_404(school_id)
        try:
            row_id, _expires = issuer.issue_inspection(
                store, vendor.private_key, school_id, hours=request.form.get('hours'),
                machine_code=request.form.get('machine_code'), note=request.form.get('note'))
        except issuer.IssueError as err:
            flash(err.args[0], 'danger')
            return redirect(url_for('school_detail', school_id=school_id))
        flash('Inspection key issued. Send it to the school below.', 'success')
        return redirect(url_for('inspection_view', row_id=row_id))

    @app.route('/inspections/<int:row_id>')
    def inspection_view(row_id):
        row = store.inspection(row_id)
        if row is None:
            abort(404)
        school = store.school(row['school_id'])
        message = (f"Assalam o Alaikum! Here is a short, view-only inspection key for {school['name']} "
                   f"(valid until {datetime.fromisoformat(row['expires_at']):%d %b %Y %H:%M}).\n\n"
                   "How to apply it: open School Manager > License > paste the key below > Activate. "
                   "The software shows 'Inspection mode' and everything can be viewed but not changed; "
                   "it ends by itself.\n\n" + row['key_text'])
        return render_template('inspection.html', row=row, school=school, message=message)

    @app.route('/schools/<int:school_id>/payment', methods=['POST'])
    def school_payment(school_id):
        _get_school_or_404(school_id)
        try:
            paid_on = date.fromisoformat(request.form.get('paid_on') or '').isoformat()
            amount = float(request.form.get('amount') or 0)
        except ValueError:
            flash('Enter a valid payment date and amount.', 'danger')
            return redirect(url_for('school_detail', school_id=school_id))
        store.add_payment(school_id, paid_on, amount, request.form.get('period_note'))
        flash('Payment recorded.', 'success')
        return redirect(url_for('school_detail', school_id=school_id))

    # -- keys ---------------------------------------------------------------------
    @app.route('/keys/<int:row_id>')
    def key_view(row_id):
        row = store.license(row_id)
        if row is None:
            abort(404)
        school = store.school(row['school_id'])
        message = ''
        if row['key_text']:
            message = (f"Assalam o Alaikum! Here is the School Manager license key for {school['name']} "
                       f"(valid until {date.fromisoformat(row['expires']).strftime('%d %b %Y')}).\n\n"
                       "How to apply it: open School Manager > License > paste the key below "
                       "(or upload the attached .key file) > Activate.\n\n" + row['key_text'])
        return render_template('key.html', row=row, school=school, message=message)

    @app.route('/keys/<int:row_id>/download')
    def key_download(row_id):
        row = store.license(row_id)
        if row is None or not row['key_text']:
            abort(404)
        school = store.school(row['school_id'])
        filename = f"{_slug(school['name'])}-{row['license_id']}-rev{row['rev']}.key"
        return Response(row['key_text'] + '\n', mimetype='text/plain',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    # -- password recovery ----------------------------------------------------------
    @app.route('/recovery', methods=['GET', 'POST'])
    def recovery():
        context = {'request_text': '', 'decoded': None, 'school': None, 'warnings': [],
                   'token': None, 'token_expires': None, 'hours': issuer.RECOVERY_HOURS}
        if request.method == 'POST':
            context['request_text'] = (request.form.get('request_code') or '').strip()
            try:
                decoded, school, warnings = issuer.decode_request(store, context['request_text'])
            except issuer.IssueError as err:
                flash(err.args[0], 'danger')
            else:
                context.update(decoded=decoded, school=school, warnings=warnings)
                if request.form.get('action') == 'issue':
                    if (school is None or warnings) and not request.form.get('confirm'):
                        flash('Tick the confirmation box to issue a token despite the warnings.', 'danger')
                    else:
                        try:
                            hours = int(request.form.get('hours') or 0)
                            token, expires = issuer.issue_recovery_token(
                                store, vendor.private_key, decoded, school, hours,
                                request.form.get('note'))
                        except (issuer.IssueError, ValueError) as err:
                            flash(err.args[0] if err.args else 'Choose the token validity.', 'danger')
                        else:
                            context.update(token=token, token_expires=expires)
        context['history'] = store.recoveries()
        return render_template('recovery.html', **context)

    # -- plans ----------------------------------------------------------------------
    @app.route('/plans', methods=['GET', 'POST'])
    def plans():
        if request.method == 'POST':
            typed_label = (request.form.get('label') or '').strip()
            if not (request.form.get('name') or '').strip() and not typed_label:
                flash('Give the plan a name.', 'danger')
                return redirect(url_for('plans'))
            # A new plan only needs a name: its short id is made from it.
            name = _slug(request.form.get('name') or typed_label).replace('-', '_')
            label = typed_label or name.replace('_', ' ').title()
            try:
                wa_daily = _int_or_none(request.form.get('wa_daily'))
                wa_monthly = _int_or_none(request.form.get('wa_monthly'))
            except ValueError:
                flash('WhatsApp limits must be whole numbers (blank = unlimited).', 'danger')
                return redirect(url_for('plans'))
            try:
                max_students = _int_or_none(request.form.get('max_students'))
                max_staff = _int_or_none(request.form.get('max_staff'))
            except ValueError:
                flash('The student and staff-login limits must be whole numbers (blank = unlimited).', 'danger')
                return redirect(url_for('plans'))
            try:
                price_monthly = _money_or_none(request.form.get('price_monthly'))
                price_yearly = _money_or_none(request.form.get('price_yearly'))
            except ValueError:
                flash('Prices must be numbers that are not negative (blank = not set).', 'danger')
                return redirect(url_for('plans'))
            store.save_plan(name, label, features_mod.normalize_features(request.form.getlist('features')) or [],
                            wa_daily, wa_monthly, max_students, max_staff, price_monthly, price_yearly)
            flash(f'Plan "{label}" saved. It applies to keys you issue from now on.', 'success')
            return redirect(url_for('plans'))
        plan_list = store.plans()
        rows = [row for row in store.schools_with_license() if row['active'] and row['expires']]
        on_plan = {}
        for plan in plan_list:
            members = []
            for row in rows:
                if (row['plan'] or '') == plan['name']:
                    diff = issuer.plan_differences(plan, issuer.key_as_dict(row))
                    members.append({'school': row, 'diff': diff})
            on_plan[plan['name']] = members
        return render_template('plans.html', plans=plan_list, on_plan=on_plan)

    # -- who has what ---------------------------------------------------------------
    def _matrix_context():
        plan = (request.args.get('plan') or '').strip()
        feature = (request.args.get('feature') or '').strip()
        has = request.args.get('has') or ''
        if has not in ('yes', 'no') or feature not in features_mod.ALL_FEATURES:
            feature, has = '', ''
        rows = store.schools_with_license()
        entries = issuer.matrix_rows(rows, vendor.today(), plan=plan, feature=feature, has=has)
        return {'entries': entries, 'plan': plan, 'feature': feature, 'has': has,
                'everyone': len(issuer.matrix_rows(rows, vendor.today())),
                'waiting': sum(1 for row in rows if row['active'] and not row['expires'])}

    @app.route('/matrix')
    def matrix():
        context = _matrix_context()
        return render_template('matrix.html', totals=issuer.feature_totals(context['entries']),
                               plans=store.plans(), **context)

    @app.route('/matrix.csv')
    def matrix_csv():
        entries = _matrix_context()['entries']
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['School', 'City', 'Plan', 'Key status', 'Key ends', 'Students limit',
                         'Staff logins limit', 'WhatsApp per day', 'WhatsApp per month']
                        + [label for _key, label, _desc, _group in features_mod.FEATURE_CATALOG])
        for entry in entries:
            school = entry['school']
            writer.writerow([school['name'], school['city'] or '', issuer.plan_label(entry['plan']),
                             entry['status'], school['expires'], issuer.limit_text(entry['max_students']),
                             issuer.limit_text(entry['max_staff']), issuer.limit_text(entry['wa_daily']),
                             issuer.limit_text(entry['wa_monthly'])]
                            + ['Yes' if key in entry['features'] else 'No'
                               for key, *_rest in features_mod.FEATURE_CATALOG])
        return Response('\ufeff' + buffer.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition':
                                 f'attachment; filename="feature-matrix-{vendor.today():%Y%m%d}.csv"'})

    # -- settings ---------------------------------------------------------------------
    @app.route('/settings')
    def settings():
        return render_template('settings.html', plain_exists=keystore.plain_exists(),
                               plain_path=keystore.plain_path, data_dir=vendor.data_dir,
                               ledger_exists=(vendor.keys_dir / 'issued_licenses.csv').is_file(),
                               ledger_path=vendor.keys_dir / 'issued_licenses.csv')

    @app.route('/settings/import-ledger', methods=['POST'])
    def import_ledger():
        path = vendor.keys_dir / 'issued_licenses.csv'
        if not path.is_file():
            flash('No issued_licenses.csv found in vendor_keys.', 'danger')
        else:
            created, added = store.import_ledger(path, features_mod.ALL_FEATURES)
            flash(f'Imported {added} license(s) and created {created} school(s). '
                  'Already-imported licenses were skipped.', 'success')
        return redirect(url_for('settings'))

    @app.route('/settings/backup')
    def backup():
        buffer = io.BytesIO()
        with tempfile.TemporaryDirectory() as tmp:
            db_copy = store.backup_to(tmp)
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(db_copy, 'vendor.db')
                if keystore.enc_path.is_file():
                    archive.write(keystore.enc_path, keystore.enc_path.name)
        buffer.seek(0)
        return send_file(buffer, mimetype='application/zip', as_attachment=True,
                         download_name=f'vendor-backup-{datetime.now():%Y%m%d-%H%M}.zip')

    @app.route('/settings/password', methods=['POST'])
    def change_password():
        new = request.form.get('new_password') or ''
        try:
            if new != (request.form.get('confirm_password') or ''):
                raise KeyStoreError('The new passwords do not match.')
            keystore.change_password(request.form.get('old_password') or '', new)
        except KeyStoreError as err:
            flash(err.args[0], 'danger')
        else:
            flash('Dashboard password changed.', 'success')
        return redirect(url_for('settings'))

    @app.route('/settings/remove-plain-key', methods=['POST'])
    def remove_plain_key():
        try:
            removed = keystore.remove_plain(request.form.get('password') or '')
        except KeyStoreError as err:
            flash(err.args[0], 'danger')
        else:
            flash('The plain private key file was erased.' if removed else 'No plain key file to remove.',
                  'success' if removed else 'info')
        return redirect(url_for('settings'))

    return app

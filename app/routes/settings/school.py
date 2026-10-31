"""School settings, language switch, grading and shared settings helpers."""

import os
from pathlib import Path
import re
from functools import wraps
from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
    abort,
    send_file,
)
from flask_login import current_user
from app.database import db
from app.services import admission_numbers, i18n
from app.models.settings import get_timetable_structure, set_timetable_structure
from app.models import SchoolSettings, ROLE_ADMIN, get_holiday_ranges, set_holiday_ranges
from app.routes import main
from app.security import role_required
from app.services import db_backup as db_backup_service
from app.services.audit import log_action


def _node_service_url():
    return current_app.config.get('WHATSAPP_NODE_URL') or 'http://127.0.0.1:3001'


def bridge_access_required(view):
    """Allow either an authenticated administrator or the Node bridge token.

    The bridge authenticates with the ``X-Bridge-Token`` header; the token comes
    from the WHATSAPP_BRIDGE_TOKEN environment variable and is never hardcoded.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        token = (current_app.config.get('WHATSAPP_BRIDGE_TOKEN') or '').strip()
        supplied = (request.headers.get('X-Bridge-Token') or '').strip()
        is_admin = (current_user.is_authenticated
                    and getattr(current_user, 'role', '') == 'admin')
        if is_admin:
            return view(*args, **kwargs)
        if token and supplied and supplied == token:
            return view(*args, **kwargs)
        return jsonify({'ok': False, 'error': 'forbidden',
                        'message': 'Administrator session or valid bridge token required.'}), 403

    return wrapper


def get_whatsapp_service_status():
    """Bridge status for the automation page and dashboard.

    Always includes the optional-component ``install`` block (see
    ``app/services/whatsapp_bridge.py``) so the UI can tell "not installed"
    (a normal state - WhatsApp is optional) apart from "installed but down".
    """
    from app.services import whatsapp_bridge

    status = whatsapp_bridge.health()
    install = whatsapp_bridge.install_summary(status)
    install['service_url'] = _node_service_url()
    status['install'] = install
    return status


@main.route('/language/<code>')
def set_language(code):
    """Switch the interface between English ('en') and Urdu ('ur')."""
    if i18n.switch_allowed():
        i18n.set_lang(code)
    target = request.referrer or ''
    if not target.startswith(request.host_url):      # only ever go back to this app
        target = url_for('main.dashboard')
    return redirect(target)


@main.route('/settings', methods=['GET', 'POST'])
def school_settings():
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
        db.session.commit()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_general_info':
            settings.school_name = request.form.get('school_name', 'School Manager').strip()
            settings.tagline = request.form.get('tagline', '').strip()
            settings.address = request.form.get('address', '').strip()
            settings.phone = request.form.get('phone', '').strip()
            settings.email = request.form.get('email', '').strip()
            settings.primary_color = request.form.get('primary_color', '#0d6efd').strip()
            settings.secondary_color = request.form.get('secondary_color', '#6c757d').strip()
            admission_numbers.set_auto(request.form.get('auto_admission_number') == 'on')
            if 'admission_number_prefix' in request.form:
                try:
                    admission_numbers.save_config(
                        request.form.get('admission_number_prefix'),
                        request.form.get('admission_number_digits'),
                        request.form.get('admission_number_start'))
                except ValueError as exc:
                    flash('Admission No pattern not changed: %s' % exc, 'warning')
            settings_tab = 'general'

            logo = request.files.get('logo')
            if logo and logo.filename:
                ext = logo.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                    # Stored in the per-school data folder (writable at
                    # runtime) — the install directory is read-only for
                    # standard users when the app lives in Program Files.
                    uploads_dir = Path(current_app.config['DATA_DIR']) / 'uploads'
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    logo_path = uploads_dir / f'logo.{ext}'
                    logo.save(str(logo_path))
                    settings.logo_filename = f'logo.{ext}'
                else:
                    flash('Logo must be PNG, JPG, GIF or WEBP.', 'warning')
        elif action == 'save_academic_settings':
            try:
                grace_minutes = int(request.form.get('attendance_grace_minutes') or 0)
                if not 0 <= grace_minutes <= 180:
                    raise ValueError
            except ValueError:
                flash('Attendance grace period must be between 0 and 180 minutes.', 'danger')
                return redirect(url_for('main.school_settings', tab='academic'))
            settings.academic_session = request.form.get('academic_session', '').strip()
            settings.result_announcement_date = request.form.get('result_announcement_date', '').strip()
            settings.school_start_time = request.form.get('school_start_time', '08:30').strip() or '08:30'
            settings.school_end_time = request.form.get('school_end_time', '15:00').strip() or '15:00'
            settings.attendance_grace_minutes = grace_minutes
            if 'late_display' in request.form:
                # 'late' (default) = after the cutoff shows Late | 'present' = stays Present
                settings.late_after_cutoff = request.form.get('late_display') != 'present'
            if 'percent_basis' in request.form:
                # 'present_late' (default) = Present + Late count | 'present_only'
                settings.late_counts_as_present = request.form.get('percent_basis') != 'present_only'
            if 'saturday_off' in request.form or 'sunday_off' in request.form:
                settings.saturday_off = request.form.get('saturday_off') == 'on'
                settings.sunday_off = request.form.get('sunday_off') == 'on'
            else:
                # Older clients posting only the combined weekend_off flag.
                legacy_weekend = request.form.get('weekend_off') == 'on'
                settings.saturday_off = legacy_weekend
                settings.sunday_off = legacy_weekend
            # Legacy flag stays true when both weekend days are off.
            settings.weekend_off = (settings.saturday_off and settings.sunday_off)
            settings.custom_off_days = request.form.get('custom_off_days', '').strip()

            # Timetable period structure (stored for the upcoming timetable feature).
            set_timetable_structure(
                request.form.get('timetable_periods_per_day'),
                request.form.get('timetable_period_minutes'),
                request.form.get('timetable_break_after'),
                request.form.get('timetable_break_minutes'),
                request.form.get('timetable_break_label'),
                assembly_minutes=request.form.get('timetable_assembly_minutes'),
                assembly_label=request.form.get('timetable_assembly_label'))

            # Holiday / vacation date ranges (label + start + end rows)
            labels = request.form.getlist('holiday_label[]')
            starts = request.form.getlist('holiday_start[]')
            ends = request.form.getlist('holiday_end[]')
            ranges = []
            for i in range(max(len(starts), len(ends), len(labels))):
                label = labels[i].strip() if i < len(labels) else ''
                start = starts[i].strip() if i < len(starts) else ''
                end = ends[i].strip() if i < len(ends) else ''
                if start and end and start <= end:
                    ranges.append({'label': label, 'start': start, 'end': end})
            set_holiday_ranges(ranges)
            settings_tab = 'academic'
        else:
            flash('Choose a settings section to save.', 'danger')
            return redirect(url_for('main.school_settings'))

        log_action('settings_change', entity_type='SchoolSettings',
                   entity_id=settings.id,
                   summary=f'School settings updated by {current_user.username}',
                   after={'school_name': settings.school_name,
                          'tagline': settings.tagline,
                          'address': settings.address,
                          'phone': settings.phone,
                          'email': settings.email,
                          'primary_color': settings.primary_color,
                          'secondary_color': settings.secondary_color})

        db.session.commit()
        flash('School settings saved successfully!', 'success')
        return redirect(url_for('main.school_settings', tab=settings_tab))

    backups = db_backup_service.list_backups()
    config = db_backup_service.auto_backup_settings()
    backup_state = {
        'recent': backups[:20],
        'auto_count': sum(1 for item in backups if item['scope'] == 'auto'),
        'manual_count': sum(1 for item in backups if item['scope'] == 'manual'),
        'latest': backups[0] if backups else None,
        'enabled': config['enabled'],
        'interval_hours': config['interval_hours'],
        'retention': config['retention'],
    }
    from app.models.settings import get_custom_fields, get_grading_scale
    grading_scale = get_grading_scale()
    student_custom_fields = get_custom_fields('student')
    teacher_custom_fields = get_custom_fields('teacher')
    active_tab = request.args.get('tab', 'general')
    if active_tab not in {'general', 'academic', 'custom-fields', 'integrations'}:
        active_tab = 'general'
    return render_template('settings.html', settings=settings, backup_state=backup_state, grading_scale=grading_scale, student_custom_fields=student_custom_fields, teacher_custom_fields=teacher_custom_fields, active_tab=active_tab, holiday_ranges=get_holiday_ranges(),
                           auto_admission_number=admission_numbers.is_auto(),
                           missing_admission_count=admission_numbers.count_missing(),
                           admission_number_config=admission_numbers.get_config(),
                           admission_number_next=admission_numbers.next_number(),
                           timetable_structure=get_timetable_structure())


@main.route('/settings/admission-numbers/assign', methods=['POST'])
@role_required(ROLE_ADMIN)
def assign_missing_admission_numbers():
    """One click: give every student without an Admission No the next numbers."""
    result = admission_numbers.assign_missing()
    if result['count']:
        log_action('admission_numbers_assigned', entity_type='StudentModel',
                   summary='Admission numbers given to %d students (%s to %s)'
                           % (result['count'], result['first'], result['last']),
                   after=result)
        db.session.commit()
        flash('Admission No given to %d students (%s to %s).'
              % (result['count'], result['first'], result['last']), 'success')
    else:
        flash('Every student already has an Admission No.', 'info')
    if request.form.get('return_to') == 'students':
        return redirect(url_for('main.students_list'))
    return redirect(url_for('main.school_settings'))


@main.route('/settings/grading', methods=['POST'])
@role_required(ROLE_ADMIN)
def school_settings_grading():
    grades = request.form.getlist('grade[]')
    min_pcts = request.form.getlist('min_pct[]')
    
    scale_list = []
    for g, m in zip(grades, min_pcts):
        if g.strip() and m.strip():
            scale_list.append({
                'grade': g.strip(),
                'min': float(m.strip())
            })
            
    if not scale_list:
        flash('Grading scale cannot be empty.', 'danger')
        return redirect(url_for('main.school_settings', tab='academic'))
        
    from app.models.settings import set_grading_scale
    set_grading_scale(scale_list)
    flash('Grading scale updated successfully!', 'success')
    return redirect(url_for('main.school_settings', tab='academic'))


@main.route('/settings/custom_fields/<entity_type>', methods=['POST'])
@role_required(ROLE_ADMIN)
def school_settings_custom_fields(entity_type):
    if entity_type not in ['student', 'teacher']:
        abort(400)
    
    names = request.form.getlist('field_name[]')
    labels = request.form.getlist('field_label[]')
    types = request.form.getlist('field_type[]')
    required_names = {
        re.sub(r'[^a-z0-9_]+', '_', value.strip().lower()).strip('_')
        for value in request.form.getlist('field_required[]') if value.strip()
    }
    
    fields_list = []
    for n, l, t in zip(names, labels, types):
        name = re.sub(r'[^a-z0-9_]+', '_', n.strip().lower()).strip('_')
        label = l.strip()
        if not name or not label:
            continue
        field_type = t.strip().lower()
        if field_type not in ('text', 'number', 'date'):
            field_type = 'text'
        # Keep the last definition when the same field name is repeated.
        fields_list = [f for f in fields_list if f['name'] != name]
        fields_list.append({
            'name': name,
            'label': label,
            'type': field_type,
            'is_mandatory': name in required_names,
        })
            
    from app.models.settings import set_custom_fields
    set_custom_fields(entity_type, fields_list)
    log_action('settings_change', entity_type='CustomFields',
               summary=f'{entity_type.capitalize()} custom fields updated by {current_user.username}',
               after={'fields': fields_list})
    db.session.commit()
    flash(f'{entity_type.capitalize()} custom fields updated successfully!', 'success')
    return redirect(url_for('main.school_settings', tab='custom-fields'))


@main.route('/settings/backups/run', methods=['POST'])
@role_required(ROLE_ADMIN)
def run_backup_now():
    try:
        target = db_backup_service.backup_database()
    except Exception as error:
        flash(f'Backup failed: {error}', 'danger')
        return redirect(url_for('main.school_settings', tab='integrations'))

    size_kb = max(1, target.stat().st_size // 1024)
    log_action('export', entity_type='Backup',
               summary=f'Manual backup created: {target.name} ({size_kb} KB)')
    db.session.commit()
    flash(f'Backup created: {target.name} ({size_kb} KB).', 'success')
    return redirect(url_for('main.school_settings', tab='integrations'))


@main.route('/settings/backups/download/<filename>')
@role_required(ROLE_ADMIN)
def download_backup(filename):
    safe = os.path.basename(filename or '')
    if not safe or safe != filename or not safe.lower().endswith('.db'):
        abort(404)
    for folder in (db_backup_service.auto_backup_dir(),
                   db_backup_service.default_backup_dir()):
        candidate = folder / safe
        try:
            if candidate.is_file():
                return send_file(candidate, as_attachment=True, download_name=safe)
        except OSError:
            continue
    abort(404)


QUEUE_VIEW_LIMIT = 2000


def _queue_redirect():
    """Back to the queue tab with the same status / trigger / search filters."""
    return redirect(url_for(
        'main.automation_panel', tab='queue',
        status=request.args.get('status') or None,
        trigger=request.args.get('trigger') or None,
        search=request.args.get('search') or None))

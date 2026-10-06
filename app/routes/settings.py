import os
from pathlib import Path
import re
from datetime import date, datetime
from functools import wraps
from urllib.parse import quote

import requests
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
from app.models import (
    AutomationSettings, ClassModel, DeliveryLog, MessageQueue, SchoolSettings,
    StudentModel, TeacherModel, ROLE_ADMIN, get_holiday_ranges, set_holiday_ranges,
)
from app.routes import main
from app.security import role_required
from app.services import db_backup as db_backup_service
from app.services.audit import log_action
from app.services.whatsapp_automation import (
    INTEGRATION_CLOUD_API, INTEGRATION_QR_SCAN, build_whatsapp_message,
    integration_configuration, normalize_whatsapp_number,
)


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
    from app.models.settings import get_grading_scale, get_custom_fields
    grading_scale = get_grading_scale()
    student_custom_fields = get_custom_fields('student')
    teacher_custom_fields = get_custom_fields('teacher')
    active_tab = request.args.get('tab', 'general')
    if active_tab not in {'general', 'academic', 'custom-fields', 'integrations'}:
        active_tab = 'general'
    return render_template('settings.html', settings=settings, backup_state=backup_state, grading_scale=grading_scale, student_custom_fields=student_custom_fields, teacher_custom_fields=teacher_custom_fields, active_tab=active_tab, holiday_ranges=get_holiday_ranges())


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


@main.route('/automation', methods=['GET', 'POST'])
def automation_panel():
    settings = AutomationSettings.get()
    students = StudentModel.query.filter_by(is_active=True).all()

    status_filter = request.args.get('status')
    trigger_filter = request.args.get('trigger')
    search_term = (request.args.get('search') or '').strip()
    active_tab = request.args.get('tab', 'connection')
    if active_tab not in {'connection', 'broadcast', 'queue'}:
        active_tab = 'connection'

    query = MessageQueue.query
    if status_filter:
        query = query.filter(MessageQueue.status == status_filter)
    if trigger_filter:
        query = query.filter(MessageQueue.trigger == trigger_filter)
    if search_term:
        like_term = f'%{search_term}%'
        query = query.filter(
            (MessageQueue.phone.like(like_term))
            | (MessageQueue.trigger.like(like_term))
            | (MessageQueue.message.like(like_term))
        )

    page = max(request.args.get('page', 1, type=int) or 1, 1)
    ordered_queue = query.order_by(MessageQueue.created_at.desc())
    queue_pagination = ordered_queue.paginate(
        page=page, per_page=10, error_out=False)
    if queue_pagination.pages and page > queue_pagination.pages:
        page = queue_pagination.pages
        queue_pagination = ordered_queue.paginate(
            page=page, per_page=10, error_out=False)
    queue_items = queue_pagination.items

    queue_summary = {
        'total': MessageQueue.query.count(),
        'pending': MessageQueue.query.filter_by(status='pending').count(),
        'approved': MessageQueue.query.filter_by(status='approved').count(),
        'sent': MessageQueue.query.filter_by(status='sent').count(),
        'failed': MessageQueue.query.filter_by(status='failed').count(),
        'retries': MessageQueue.query.filter(MessageQueue.retry_count > 0).count(),
    }

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save_settings':
            previous_integration = settings.integration_method
            requested_integration = request.form.get('integration_method', INTEGRATION_QR_SCAN)
            if requested_integration not in {INTEGRATION_QR_SCAN, INTEGRATION_CLOUD_API}:
                flash('Select a valid WhatsApp integration method.', 'danger')
                return redirect(url_for('main.automation_panel', tab='connection'))

            api_token = (request.form.get('whatsapp_api_token') or '').strip()
            phone_number_id = (request.form.get('whatsapp_phone_number_id') or '').strip()
            business_account_id = (request.form.get('whatsapp_business_account_id') or '').strip()
            api_token = api_token or settings.whatsapp_api_token
            phone_number_id = phone_number_id or settings.whatsapp_phone_number_id
            business_account_id = business_account_id or settings.whatsapp_business_account_id
            if requested_integration == INTEGRATION_CLOUD_API and not all(
                    (api_token, phone_number_id, business_account_id)):
                flash('Cloud API requires an access token, Phone Number ID, and WABA ID.', 'danger')
                return redirect(url_for('main.automation_panel', tab='connection'))

            settings.enabled = request.form.get('enabled') == 'on'
            settings.integration_method = requested_integration
            settings.whatsapp_api_token = api_token
            settings.whatsapp_phone_number_id = phone_number_id
            settings.whatsapp_business_account_id = business_account_id
            requested_mode = request.form.get('mode', settings.mode)
            if requested_mode not in {'approval', 'auto', 'delayed'}:
                requested_mode = settings.mode
            if requested_mode == 'approval' and settings.mode != 'approval':
                MessageQueue.query.filter(
                    MessageQueue.status.in_(['approved', 'sending', 'sending_auto'])
                ).update(
                    {'status': 'pending', 'updated_at': datetime.utcnow()},
                    synchronize_session=False,
                )
            if requested_integration != previous_integration:
                reset_status = 'approved' if settings.mode != 'approval' else 'pending'
                MessageQueue.query.filter(
                    MessageQueue.status.in_(['sending', 'sending_auto'])
                ).update(
                    {'status': reset_status, 'updated_at': datetime.utcnow()},
                    synchronize_session=False,
                )
            settings.mode = requested_mode
            settings.notify_absent = request.form.get('notify_absent') == 'on'
            settings.notify_late = request.form.get('notify_late') == 'on'
            settings.notify_results = request.form.get('notify_results') == 'on'
            settings.notify_fee_reminders = request.form.get('notify_fee_reminders') == 'on'
            settings.notify_fee_receipts = request.form.get('notify_fee_receipts') == 'on'
            settings.template_absent = request.form.get('template_absent', settings.template_absent)
            settings.template_late = request.form.get('template_late', settings.template_late)
            settings.template_result = request.form.get('template_result', settings.template_result)
            log_action('settings_change', entity_type='AutomationSettings',
                       entity_id=settings.id,
                       summary=f'WhatsApp automation settings updated by {current_user.username}',
                      after={'enabled': settings.enabled, 'mode': settings.mode,
                          'integration_method': settings.integration_method,
                              'notify_absent': settings.notify_absent,
                              'notify_late': settings.notify_late,
                              'notify_results': settings.notify_results})
            db.session.commit()
            flash('WhatsApp automation settings saved successfully!', 'success')
            return redirect(url_for('main.automation_panel', tab='connection'))

        if action == 'queue_broadcast':
            audience = request.form.get('audience')
            message_template = (request.form.get('message') or '').strip()
            class_id = request.form.get('class_id', type=int)
            student_id = request.form.get('student_id', type=int)
            due_date = (request.form.get('due_date') or '').strip()

            if not message_template or len(message_template) > 4096:
                flash('Enter a message of 1 to 4,096 characters.', 'danger')
                return redirect(url_for('main.automation_panel', tab='broadcast'))
            if due_date:
                try:
                    due_date = date.fromisoformat(due_date).isoformat()
                except ValueError:
                    flash('Choose a valid due date.', 'danger')
                    return redirect(url_for('main.automation_panel', tab='broadcast'))

            if audience in {'whole_school', 'class', 'student'}:
                if audience == 'whole_school':
                    recipients = StudentModel.query.filter_by(is_active=True).all()
                elif audience == 'class':
                    if not db.session.get(ClassModel, class_id):
                        flash('Choose a valid class for this broadcast.', 'danger')
                        return redirect(url_for('main.automation_panel', tab='broadcast'))
                    recipients = StudentModel.query.filter_by(
                        is_active=True, class_id=class_id).all()
                else:
                    student = db.session.get(StudentModel, student_id)
                    recipients = [student] if student and student.is_active else []
            elif audience == 'staff':
                recipients = (TeacherModel.query.filter_by(is_active=True)
                              .filter(TeacherModel.contact_number.isnot(None)).all())
            else:
                flash('Choose a valid message audience.', 'danger')
                return redirect(url_for('main.automation_panel', tab='broadcast'))

            school = SchoolSettings.query.first()
            school_name = school.school_name if school else 'School'
            queued = skipped = 0
            queue_status = 'pending' if settings.mode == 'approval' else 'approved'
            for recipient in recipients:
                is_staff = audience == 'staff'
                phone = (recipient.contact_number if is_staff
                         else recipient.guardian_phone)
                normalized_phone = normalize_whatsapp_number(phone or '')
                if not normalized_phone:
                    skipped += 1
                    continue

                recipient_name = (recipient.teacher_name if is_staff
                                  else recipient.student_name)
                class_name = ''
                if not is_staff and recipient.class_info:
                    class_name = recipient.class_info.name
                values = {
                    'student_name': recipient_name if not is_staff else '',
                    'staff_name': recipient_name if is_staff else '',
                    'fee_amount': f'{(recipient.monthly_fee or 0):,.2f}' if not is_staff else '',
                    'due_date': due_date or date.today().isoformat(),
                    'class_name': class_name,
                    'school_name': school_name,
                }
                message = message_template
                for key, value in values.items():
                    message = message.replace('{' + key + '}', str(value))
                db.session.add(MessageQueue(
                    phone=normalized_phone,
                    message=message,
                    status=queue_status,
                    trigger='custom_broadcast',
                    student_id=None if is_staff else recipient.id,
                    ref_date=date.today(),
                ))
                queued += 1

            if queued:
                db.session.commit()
                flash(f'{queued} message(s) queued; {skipped} recipient(s) skipped without a valid phone.', 'success')
            else:
                db.session.rollback()
                flash('No messages were queued. Check the selected audience phone numbers.', 'warning')
            return redirect(url_for('main.automation_panel', tab='broadcast'))

        if action == 'queue_message':
            student_id = request.form.get('student_id', type=int)
            trigger = request.form.get('trigger', 'attendance_absent')
            student = StudentModel.query.get(student_id)
            if not student:
                flash('Student not found.', 'danger')
                return redirect(url_for('main.automation_panel', tab='broadcast'))

            message = build_whatsapp_message(trigger, {
                'student_name': student.student_name,
                'date': date.today().isoformat(),
                'grade': 'A',
                'obtained': '90',
                'total': '100',
                'percentage': '90',
            })
            msg = MessageQueue(
                phone=normalize_whatsapp_number(student.guardian_phone),
                message=message,
                status='pending' if settings.mode == 'approval' else 'approved',
                trigger=trigger,
                student_id=student.id,
                ref_date=date.today(),
            )
            db.session.add(msg)
            db.session.commit()
            flash('WhatsApp message queued successfully.', 'success')
            return redirect(url_for('main.automation_panel', tab='queue'))

        if action in {'approve', 'reject', 'retry'}:
            msg_id = request.form.get('message_id', type=int)
            msg = MessageQueue.query.get_or_404(msg_id)
            expected_status = 'failed' if action == 'retry' else 'pending'
            if msg.status != expected_status:
                flash(f'Message cannot be {action}d from its current status.', 'warning')
                return redirect(url_for('main.automation_panel', tab='queue'))
            if action == 'approve':
                msg.status = 'approved'
                msg.error_msg = None
            elif action == 'reject':
                msg.status = 'rejected'
            elif action == 'retry':
                msg.status = 'approved'
                msg.retry_count = (msg.retry_count or 0) + 1
                msg.error_msg = None
            db.session.commit()
            flash(f'Message {action}d successfully.', 'success')
            return redirect(url_for('main.automation_panel', tab='queue'))

    return render_template(
        'automation.html',
        settings=settings,
        students=students,
        queue_items=queue_items,
        queue_summary=queue_summary,
        queue_pagination=queue_pagination,
        active_tab=active_tab,
        status_filter=status_filter,
        trigger_filter=trigger_filter,
        search_term=search_term,
        quote=quote,
        bridge_install=get_whatsapp_service_status().get('install'),
        classes=ClassModel.query.order_by(ClassModel.name).all(),
    )


@main.route('/brand-logo')
def brand_logo():
    """Serve the school logo from the data folder (installed products keep
    the install directory read-only), falling back to the legacy static copy
    from development setups."""
    settings = SchoolSettings.query.first()
    filename = (settings.logo_filename if settings else None) or ''
    if filename:
        data_copy = Path(current_app.config['DATA_DIR']) / 'uploads' / filename
        if data_copy.is_file():
            return send_file(data_copy, max_age=3600)
        legacy_copy = Path(current_app.root_path) / 'static' / filename
        if legacy_copy.is_file():
            return send_file(legacy_copy, max_age=3600)
    from flask import abort
    abort(404)


@main.route('/api/whatsapp/status', methods=['GET'])
@bridge_access_required
def whatsapp_status():
    return get_whatsapp_service_status()


@main.route('/api/whatsapp/qr', methods=['GET'])
@bridge_access_required
def whatsapp_qr():
    try:
        response = requests.get(f'{_node_service_url()}/qr', timeout=3)
        if response.ok:
            return response.json()
        return {'ok': False, 'message': 'QR not ready yet.'}, 404
    except requests.RequestException:
        return {'ok': False, 'message': 'WhatsApp service unavailable.'}, 503


@main.route('/api/whatsapp/integration', methods=['GET'])
@bridge_access_required
def whatsapp_integration():
    configuration = integration_configuration()
    if configuration['integration_method'] == INTEGRATION_CLOUD_API:
        cloud_api = configuration['cloud_api']
        if not all((cloud_api['access_token'], cloud_api['phone_number_id'],
                    cloud_api['business_account_id'])):
            return {'ok': False, 'message': 'Cloud API credentials are incomplete.'}, 409
    return {'ok': True, **configuration}


@main.route('/api/whatsapp/test', methods=['POST'])
@main.route('/api/whatsapp/send-test', methods=['POST'])
@bridge_access_required
def whatsapp_test_message():
    payload = request.get_json(silent=True) or {}
    phone = (payload.get('phone') or '').strip()
    student_id = payload.get('student_id')

    if not phone and student_id:
        student = StudentModel.query.get(student_id)
        if not student:
            return {'ok': False, 'message': 'Student not found.'}, 404
        phone = student.guardian_phone

    normalized_phone = normalize_whatsapp_number(phone) if phone else None
    if phone and not normalized_phone:
        return {'ok': False, 'message': 'Enter a valid WhatsApp phone number.'}, 400

    try:
        response = requests.post(
            f'{_node_service_url()}/send-test',
            json={'phone': normalized_phone, 'message': 'School Manager test message: WhatsApp connection is working.'},
            timeout=20,
        )
        payload = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'ok': False}
        return payload if response.ok else (payload, 400)
    except requests.RequestException:
        return {'ok': False, 'message': 'WhatsApp service unavailable.'}, 503


@main.route('/api/whatsapp/pending', methods=['GET'])
@bridge_access_required
def whatsapp_pending_messages():
    settings = AutomationSettings.get()
    configuration = integration_configuration(settings)
    expected_integration = request.args.get('integration_method')
    if expected_integration and expected_integration != configuration['integration_method']:
        return {'ok': False, 'message': 'WhatsApp integration changed. Refresh dispatch configuration.'}, 409
    if configuration['integration_method'] == INTEGRATION_CLOUD_API:
        cloud_api = configuration['cloud_api']
        if not all((cloud_api['access_token'], cloud_api['phone_number_id'],
                    cloud_api['business_account_id'])):
            return {'ok': False, 'message': 'Cloud API credentials are incomplete.'}, 409
    dispatchable_statuses = ['approved']
    if settings.mode != 'approval':
        dispatchable_statuses.append('pending')
    candidates = (MessageQueue.query
                  .filter(MessageQueue.status.in_(dispatchable_statuses))
                  .order_by(MessageQueue.created_at.asc(), MessageQueue.id.asc()).all())
    items = []
    for item in candidates:
        claimed_status = 'sending' if settings.mode == 'approval' else 'sending_auto'
        claimed = (MessageQueue.query
                   .filter_by(id=item.id, status=item.status)
               .update({'status': claimed_status, 'updated_at': datetime.utcnow()},
                           synchronize_session=False))
        if claimed:
            item.status = claimed_status
            items.append(item)
    db.session.commit()
    return {
        **configuration,
        'items': [
            {
                'id': item.id,
                'phone': item.phone,
                'message': item.message,
                'trigger': item.trigger,
                'status': item.status,
            }
            for item in items
        ]
    }


@main.route('/api/whatsapp/update-status', methods=['POST'])
@bridge_access_required
def whatsapp_update_status():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get('id')
    status = payload.get('status')
    error_message = payload.get('error_message')

    if item_id is None or not status:
        return {'ok': False, 'message': 'Missing id or status.'}, 400

    item = MessageQueue.query.get(item_id)
    if not item:
        return {'ok': False, 'message': 'Message not found.'}, 404
    if status not in {'sent', 'failed'}:
        return {'ok': False, 'message': 'Unsupported message status.'}, 400
    if item.status not in {'sending', 'sending_auto'}:
        return {'ok': False, 'message': 'Message is not currently being sent.'}, 409

    previous_status = item.status
    item.status = status
    item.error_msg = error_message
    if status == 'failed' and previous_status != 'failed':
        item.retry_count = (item.retry_count or 0) + 1
    if status == 'sent':
        item.sent_at = datetime.utcnow()
        settings = AutomationSettings.get()
        settings.last_successful_send_at = datetime.utcnow()
    item.updated_at = datetime.utcnow()

    log_entry = DeliveryLog(
        message_id=item.id,
        status=status,
        error_msg=error_message,
        details=f"Automation status update via API from {request.remote_addr or 'unknown'}"
    )
    db.session.add(log_entry)
    db.session.commit()
    return {'ok': True, 'message': 'Status updated.'}


@main.route('/api/whatsapp/authorize-send', methods=['POST'])
@bridge_access_required
def whatsapp_authorize_send():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get('id')
    integration_method = payload.get('integration_method')
    if item_id is None:
        return {'ok': False, 'message': 'Missing id.'}, 400

    item = db.session.get(MessageQueue, item_id)
    if not item:
        return {'ok': False, 'message': 'Message not found.'}, 404
    if integration_method and integration_method != integration_configuration()['integration_method']:
        return {'ok': False, 'message': 'WhatsApp integration changed before dispatch.'}, 409
    if item.status not in {'sending', 'sending_auto'}:
        return {'ok': False, 'message': 'Message is no longer authorized for sending.'}, 409
    if AutomationSettings.get().mode == 'approval' and item.status != 'sending':
        return {'ok': False, 'message': 'Manual approval is required before sending.'}, 409

    return {'ok': True}


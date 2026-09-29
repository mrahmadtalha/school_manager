import os
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
from app.models import SchoolSettings, StudentModel, AutomationSettings, MessageQueue, DeliveryLog, ROLE_ADMIN
from app.routes import main
from app.security import role_required
from app.services import db_backup as db_backup_service
from app.services.audit import log_action
from app.services.whatsapp_automation import build_whatsapp_message, normalize_whatsapp_number


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
    try:
        response = requests.get(f'{_node_service_url()}/health', timeout=3)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        if response.ok:
            data.setdefault('serviceReachable', True)
            data.setdefault('phonePaired', bool(data.get('connected')))
            data.setdefault('messageSent', bool(data.get('messageSent')))
            if data.get('message'):
                return data
            if data.get('lastError'):
                data['message'] = data['lastError']
                return data
            data['message'] = 'WhatsApp service is running.' if data.get('connected') else 'Waiting for WhatsApp to connect.'
            return data
        return {'ok': False, 'connected': False, 'serviceReachable': False, 'phonePaired': False, 'messageSent': False, 'status': 'offline', 'message': 'WhatsApp service unavailable'}
    except requests.RequestException:
        return {'ok': False, 'connected': False, 'serviceReachable': False, 'phonePaired': False, 'messageSent': False, 'status': 'offline', 'message': 'WhatsApp service unavailable'}


@main.route('/settings', methods=['GET', 'POST'])
def school_settings():
    settings = SchoolSettings.query.first()
    if request.method == 'POST':
        settings.school_name = request.form.get('school_name', 'School Manager').strip()
        settings.tagline = request.form.get('tagline', '').strip()
        settings.address = request.form.get('address', '').strip()
        settings.phone = request.form.get('phone', '').strip()
        settings.email = request.form.get('email', '').strip()
        settings.school_start_time = request.form.get('school_start_time', '08:30').strip() or '08:30'
        settings.school_end_time = request.form.get('school_end_time', '15:00').strip() or '15:00'
        settings.weekend_off = request.form.get('weekend_off') == 'on'
        settings.custom_off_days = request.form.get('custom_off_days', '').strip()
        settings.primary_color = request.form.get('primary_color', '#0d6efd').strip()
        settings.secondary_color = request.form.get('secondary_color', '#6c757d').strip()

        log_action('settings_change', entity_type='SchoolSettings',
                   entity_id=settings.id,
                   summary=f'School settings updated by {current_user.username}',
                   after={'school_name': settings.school_name,
                          'tagline': settings.tagline,
                          'address': settings.address,
                          'phone': settings.phone,
                          'email': settings.email,
                          'school_start_time': settings.school_start_time,
                          'school_end_time': settings.school_end_time,
                          'weekend_off': settings.weekend_off,
                          'custom_off_days': settings.custom_off_days,
                          'primary_color': settings.primary_color,
                          'secondary_color': settings.secondary_color})

        logo = request.files.get('logo')
        if logo and logo.filename:
            ext = logo.filename.rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                logo_path = os.path.join(current_app.root_path, 'static', 'logo.' + ext)
                logo.save(logo_path)
                settings.logo_filename = 'logo.' + ext
            else:
                flash('Logo must be PNG, JPG, GIF or WEBP.', 'warning')

        db.session.commit()
        flash('School settings saved successfully!', 'success')
        return redirect(url_for('main.school_settings'))

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
    return render_template('settings.html', settings=settings, backup_state=backup_state, grading_scale=grading_scale, student_custom_fields=student_custom_fields, teacher_custom_fields=teacher_custom_fields)


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
        return redirect(url_for('main.school_settings'))
        
    from app.models.settings import set_grading_scale
    set_grading_scale(scale_list)
    flash('Grading scale updated successfully!', 'success')
    return redirect(url_for('main.school_settings'))

@main.route('/settings/custom_fields/<entity_type>', methods=['POST'])
@role_required(ROLE_ADMIN)
def school_settings_custom_fields(entity_type):
    if entity_type not in ['student', 'teacher']:
        abort(400)
    
    names = request.form.getlist('field_name[]')
    labels = request.form.getlist('field_label[]')
    types = request.form.getlist('field_type[]')
    
    fields_list = []
    for n, l, t in zip(names, labels, types):
        if n.strip() and l.strip():
            fields_list.append({
                'name': n.strip().lower().replace(' ', '_'),
                'label': l.strip(),
                'type': t.strip()
            })
            
    from app.models.settings import set_custom_fields
    set_custom_fields(entity_type, fields_list)
    flash(f'{entity_type.capitalize()} custom fields updated successfully!', 'success')
    return redirect(url_for('main.school_settings'))

@main.route('/settings/backups/run', methods=['POST'])
@role_required(ROLE_ADMIN)
def run_backup_now():
    try:
        target = db_backup_service.backup_database()
    except Exception as error:
        flash(f'Backup failed: {error}', 'danger')
        return redirect(url_for('main.school_settings'))

    size_kb = max(1, target.stat().st_size // 1024)
    log_action('export', entity_type='Backup',
               summary=f'Manual backup created: {target.name} ({size_kb} KB)')
    db.session.commit()
    flash(f'Backup created: {target.name} ({size_kb} KB).', 'success')
    return redirect(url_for('main.school_settings'))


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

    query = MessageQueue.query
    if status_filter:
        query = query.filter(MessageQueue.status == status_filter)
    if trigger_filter:
        query = query.filter(MessageQueue.trigger == trigger_filter)
    if search_term:
        like_term = f'%{search_term}%'
        query = query.filter((MessageQueue.phone.like(like_term)) | (MessageQueue.trigger.like(like_term)))

    queue_items = query.order_by(MessageQueue.created_at.desc()).all()

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
            settings.enabled = request.form.get('enabled') == 'on'
            settings.mode = request.form.get('mode', settings.mode)
            settings.notify_absent = request.form.get('notify_absent') == 'on'
            settings.notify_late = request.form.get('notify_late') == 'on'
            settings.notify_results = request.form.get('notify_results') == 'on'
            settings.template_absent = request.form.get('template_absent', settings.template_absent)
            settings.template_late = request.form.get('template_late', settings.template_late)
            settings.template_result = request.form.get('template_result', settings.template_result)
            log_action('settings_change', entity_type='AutomationSettings',
                       entity_id=settings.id,
                       summary=f'WhatsApp automation settings updated by {current_user.username}',
                       after={'enabled': settings.enabled, 'mode': settings.mode,
                              'notify_absent': settings.notify_absent,
                              'notify_late': settings.notify_late,
                              'notify_results': settings.notify_results})
            db.session.commit()
            flash('WhatsApp automation settings saved successfully!', 'success')
            return redirect(url_for('main.automation_panel'))

        if action == 'queue_message':
            student_id = request.form.get('student_id', type=int)
            trigger = request.form.get('trigger', 'attendance_absent')
            student = StudentModel.query.get(student_id)
            if not student:
                flash('Student not found.', 'danger')
                return redirect(url_for('main.automation_panel'))

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
            return redirect(url_for('main.automation_panel'))

        if action in {'approve', 'reject', 'retry'}:
            msg_id = request.form.get('message_id', type=int)
            msg = MessageQueue.query.get_or_404(msg_id)
            if action == 'approve':
                msg.status = 'approved'
                msg.error_msg = None
            elif action == 'reject':
                msg.status = 'rejected'
            elif action == 'retry':
                msg.status = 'pending'
                msg.retry_count = (msg.retry_count or 0) + 1
                msg.error_msg = None
            db.session.commit()
            flash(f'Message {action}d successfully.', 'success')
            return redirect(url_for('main.automation_panel'))

    return render_template(
        'automation.html',
        settings=settings,
        students=students,
        queue_items=queue_items,
        queue_summary=queue_summary,
        status_filter=status_filter,
        trigger_filter=trigger_filter,
        search_term=search_term,
        quote=quote,
    )


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


@main.route('/api/whatsapp/test', methods=['POST'])
@bridge_access_required
def whatsapp_test_message():
    payload = request.get_json(silent=True) or {}
    phone = payload.get('phone')
    student_id = payload.get('student_id')

    if not phone:
        student = StudentModel.query.get(student_id) if student_id else StudentModel.query.filter_by(is_active=True).first()
        if not student:
            return {'ok': False, 'message': 'No student or phone supplied.'}, 400
        phone = student.guardian_phone

    try:
        response = requests.post(
            f'{_node_service_url()}/send-test',
            json={'phone': normalize_whatsapp_number(phone), 'message': 'School Manager test message: WhatsApp connection is working.'},
            timeout=8,
        )
        payload = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'ok': False}
        return payload if response.ok else (payload, 400)
    except requests.RequestException:
        return {'ok': False, 'message': 'WhatsApp service unavailable.'}, 503


@main.route('/api/whatsapp/pending', methods=['GET'])
@bridge_access_required
def whatsapp_pending_messages():
    items = MessageQueue.query.filter(MessageQueue.status.in_(['approved', 'pending'])).order_by(MessageQueue.created_at.asc()).all()
    return {
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


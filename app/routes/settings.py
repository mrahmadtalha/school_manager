import os
from datetime import date, datetime
from urllib.parse import quote

import requests
from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)

from app.database import db
from app.models import SchoolSettings, StudentModel, AutomationSettings, MessageQueue, DeliveryLog
from app.routes import main
from app.services.whatsapp_automation import build_whatsapp_message, normalize_whatsapp_number

NODE_SERVICE_BASE_URL = 'http://127.0.0.1:3001'


def get_whatsapp_service_status():
    try:
        response = requests.get(f'{NODE_SERVICE_BASE_URL}/health', timeout=3)
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

    return render_template('settings.html', settings=settings)


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
def whatsapp_status():
    return get_whatsapp_service_status()


@main.route('/api/whatsapp/qr', methods=['GET'])
def whatsapp_qr():
    try:
        response = requests.get(f'{NODE_SERVICE_BASE_URL}/qr', timeout=3)
        if response.ok:
            return response.json()
        return {'ok': False, 'message': 'QR not ready yet.'}, 404
    except requests.RequestException:
        return {'ok': False, 'message': 'WhatsApp service unavailable.'}, 503


@main.route('/api/whatsapp/test', methods=['POST'])
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
            f'{NODE_SERVICE_BASE_URL}/send-test',
            json={'phone': normalize_whatsapp_number(phone), 'message': 'School Manager test message: WhatsApp connection is working.'},
            timeout=8,
        )
        payload = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'ok': False}
        return payload if response.ok else (payload, 400)
    except requests.RequestException:
        return {'ok': False, 'message': 'WhatsApp service unavailable.'}, 503


@main.route('/api/whatsapp/pending', methods=['GET'])
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


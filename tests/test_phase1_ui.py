"""Automation tab clean-up, late time in the message, queue page memory,
fees filters and the classes page state."""
from datetime import date

from app.database import db
from app.models import ClassModel, MessageQueue, StudentModel
from app.services.attendance_service import save_student_attendance
from app.services.automation_events import build_event_context, render_event_message
from app.services.fee_ledger import current_month, ensure_charge


# ---- Automation: Quick Broadcast is gone, the log is a DataTable that keeps its page
def test_quick_broadcast_tab_is_removed(admin_client):
    body = admin_client.get('/automation').get_data(as_text=True)
    assert 'Quick Broadcast' not in body and 'broadcast-panel' not in body
    assert 'Message Queue &amp; Logs' in body
    # an old bookmark to the removed tab simply opens the first tab
    assert admin_client.get('/automation?tab=broadcast').status_code == 200


def test_queue_actions_return_to_the_same_filtered_view(admin_client, app):
    with app.app_context():
        msg = MessageQueue(phone='923001112222', message='x', status='failed',
                           trigger='custom_broadcast')
        db.session.add(msg)
        db.session.commit()
        msg_id = msg.id
    resp = admin_client.post('/automation?tab=queue&status=failed&search=923',
                             data={'action': 'retry', 'message_id': msg_id})
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert 'tab=queue' in location and 'status=failed' in location and 'search=923' in location


# ---- Late arrival: the message carries the arrival time
def test_late_message_text_has_the_arrival_time():
    ctx = build_event_context(None, 'attendance_late', {
        'student_name': 'Ali', 'date': '2026-09-21', 'late_time': '08:47', 'late_minutes': 17})
    text = render_event_message('attendance_late', ctx)
    # a clear arrival time only - never "17 minutes late"
    assert 'at *8:47 AM*' in text and 'minutes late' not in text
    # afternoon + seconds
    ctx = build_event_context(None, 'attendance_late', {
        'student_name': 'Ali', 'date': '2026-09-21', 'late_time': '13:05:30', 'late_minutes': 135})
    text = render_event_message('attendance_late', ctx)
    assert '*1:05 PM*' in text and 'minute' not in text and '135' not in text


def test_templates_saved_before_the_change_also_get_the_time():
    old = 'Your child arrived *LATE* to school today ({date}).\n\nRegards'
    ctx = build_event_context(None, 'attendance_late', {
        'student_name': 'Ali', 'date': '2026-09-21', 'late_time': '08:47', 'late_minutes': 17})
    text = render_event_message('attendance_late', ctx, old)
    assert 'today (2026-09-21) at *8:47 AM*.' in text
    # a template that already shows the time itself is left alone
    mine = 'Late at {late_time}'
    assert render_event_message('attendance_late', ctx, mine) == 'Late at 8:47 AM'


def test_no_time_means_the_old_wording(app):
    ctx = build_event_context(None, 'attendance_late', {'student_name': 'Ali', 'date': '2026-09-21'})
    assert 'arrived *LATE* on 2026-09-21.' in render_event_message('attendance_late', ctx)


def test_marking_a_student_late_queues_a_message_with_the_time(app, seed):
    from app.models import AutomationSettings, SchoolSettings
    with app.app_context():
        automation = AutomationSettings.get()
        automation.enabled = True
        automation.notify_late = True
        automation.mode = 'approval'
        settings = SchoolSettings.query.first() or SchoolSettings()
        db.session.add(settings)
        settings.school_start_time = '08:30'
        settings.attendance_grace_minutes = 5
        db.session.commit()
        class_obj = db.session.get(ClassModel, seed['class_id'])
        target = StudentModel.query.filter_by(class_id=class_obj.id, is_active=True).first()
        save_student_attendance(class_obj.id, date(2026, 9, 21), {
            f'status_{target.id}': 'Present', f'checkin_time_{target.id}': '08:47'}, [class_obj])
        queued = MessageQueue.query.filter_by(trigger='attendance_late').all()
        assert queued, 'a late message should be queued'
        assert 'at *8:47 AM*' in queued[-1].message and 'minutes late' not in queued[-1].message


# ---- Fees page
def test_billing_month_is_a_dropdown_of_pending_months(admin_client, app, seed):
    with app.app_context():
        pupil = db.session.get(StudentModel, seed['student_id'])
        ensure_charge(pupil, 'March 2022', amount=1000.0)
        ensure_charge(pupil, 'March 2025', amount=1000.0)
        db.session.commit()
    body = admin_client.get('/fees?class_id=%d' % seed['class_id']).get_data(as_text=True)
    assert '<select class="form-select" name="month_year"' in body
    assert 'value="March 2022"' in body and 'value="March 2025"' in body
    assert 'value="%s"' % current_month() in body
    assert 'value="April 2019"' not in body          # a month nobody owes is not offered
    # newest first
    assert body.index('value="March 2025"') < body.index('value="March 2022"')


def test_set_monthly_fee_button_sits_with_the_header_buttons(admin_client, seed):
    body = admin_client.get('/fees').get_data(as_text=True)
    button = body.index('data-bs-target="#bulkClassFeeModal"')
    assert button < body.index('Filter Card')                  # up with Admission Fees etc.
    assert body.count('data-bs-target="#bulkClassFeeModal"') == 1


# ---- Classes page keeps its state across the reload after saving
def test_classes_page_remembers_open_classes_and_scroll(admin_client):
    body = admin_client.get('/classes').get_data(as_text=True)
    assert 'classesPageState' in body and 'shown.bs.collapse' in body

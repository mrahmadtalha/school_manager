"""Fee reminders: defaulters from reconciliation, queueing, idempotency, routes."""

from datetime import date

from app.database import db
from app.models import AutomationSettings, MessageQueue, StudentModel
from app.services import fee_ledger
from app.services import fee_reminders as reminders

MONTH = 'September 2026'


def _add_debt(app, student_name, charge, paid, phone=None):
    with app.app_context():
        student = StudentModel.query.filter_by(student_name=student_name).one()
        fee_ledger.ensure_charge(student, MONTH, amount=charge)
        if paid:
            fee_ledger.record_payment(student, MONTH, paid)
        if phone is not None:
            student.guardian_phone = phone
        db.session.commit()
        return student.id


def test_defaulters_match_reconciliation(app, seed):
    _add_debt(app, 'Ali Khan', charge=2000, paid=800)
    _add_debt(app, 'Sara Ali', charge=2000, paid=2000)

    with app.app_context():
        rows = reminders.defaulter_rows(MONTH)
        assert [row['student'].student_name for row in rows] == ['Ali Khan']
        assert rows[0]['balance'] == 1200.0

        rec_rows, _totals, _disc = fee_ledger.reconcile(MONTH)
        rec_balance = {row['student'].student_name: row['balance'] for row in rec_rows}
        assert rec_balance['Ali Khan'] == 1200.0
        assert rec_balance['Sara Ali'] == 0.0


def test_queue_is_idempotent_and_normalizes_phone(app, seed):
    student_id = _add_debt(app, 'Ali Khan', charge=2000, paid=800, phone='0300-1234567')

    with app.app_context():
        summary = reminders.queue_fee_reminders(MONTH)
        assert summary['queued'] == 1
        assert summary['skipped_existing'] == 0
        assert summary['skipped_no_phone'] == 0

        rows = MessageQueue.query.filter_by(trigger='fee_reminder').all()
        assert len(rows) == 1
        item = rows[0]
        assert item.status == 'pending'
        assert item.student_id == student_id
        assert item.ref_date == date(2026, 9, 1)
        assert item.phone == '923001234567'
        assert 'Ali Khan' in item.message
        assert MONTH in item.message
        assert 'Rs. 1,200' in item.message

        again = reminders.queue_fee_reminders(MONTH)
        assert again['queued'] == 0
        assert again['skipped_existing'] == 1
        assert MessageQueue.query.filter_by(trigger='fee_reminder').count() == 1


def test_rejected_reminder_can_be_requeued(app, seed):
    _add_debt(app, 'Ali Khan', charge=2000, paid=800)

    with app.app_context():
        reminders.queue_fee_reminders(MONTH)
        item = MessageQueue.query.filter_by(trigger='fee_reminder').one()
        item.status = 'rejected'
        db.session.commit()

        summary = reminders.queue_fee_reminders(MONTH)
        assert summary['queued'] == 1
        assert MessageQueue.query.filter_by(trigger='fee_reminder').count() == 2


def test_no_phone_is_skipped(app, seed):
    _add_debt(app, 'Ali Khan', charge=2000, paid=800, phone='')

    with app.app_context():
        summary = reminders.queue_fee_reminders(MONTH)
        assert summary['queued'] == 0
        assert summary['skipped_no_phone'] == 1
        assert MessageQueue.query.filter_by(trigger='fee_reminder').count() == 0


def test_reminders_respect_automation_setting(app, seed):
    _add_debt(app, 'Ali Khan', charge=2000, paid=800)
    with app.app_context():
        AutomationSettings.get().notify_fee_reminders = False
        db.session.commit()
        try:
            reminders.queue_fee_reminders(MONTH)
        except ValueError as error:
            assert 'turned off' in str(error)
        else:
            raise AssertionError('Disabled fee reminders should not be queued.')
        assert MessageQueue.query.filter_by(trigger='fee_reminder').count() == 0


def test_routes_preview_and_queue(admin_client, app, seed):
    _add_debt(app, 'Ali Khan', charge=2000, paid=800)

    preview = admin_client.get('/fees/reminders', query_string={'month_year': MONTH})
    body = preview.get_data(as_text=True)
    assert preview.status_code == 200
    assert 'Ali Khan' in body
    assert 'Queue 1 reminder' in body

    queued = admin_client.post('/fees/reminders/queue', data={'month_year': MONTH},
                               follow_redirects=True)
    assert queued.status_code == 200
    with app.app_context():
        assert MessageQueue.query.filter_by(trigger='fee_reminder').count() == 1


def test_routes_require_admin(teacher_client, app, seed):
    # Note: admin_client and teacher_client share one client fixture in conftest,
    # so role checks use a single client per test.
    assert teacher_client.get('/fees/reminders').status_code == 403
    assert teacher_client.post('/fees/reminders/queue',
                               data={'month_year': MONTH}).status_code == 403


def test_invalid_month_is_reported(admin_client, app, seed):
    page = admin_client.get('/fees/reminders', query_string={'month_year': 'Not A Month'})
    assert page.status_code == 200
    assert 'Unknown month' in page.get_data(as_text=True)

    post = admin_client.post('/fees/reminders/queue', data={'month_year': 'Not A Month'},
                             follow_redirects=True)
    assert 'Unknown month' in post.get_data(as_text=True)
    with app.app_context():
        assert MessageQueue.query.filter_by(trigger='fee_reminder').count() == 0

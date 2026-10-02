"""The audit ledger must be able to reconstruct who changed what, and when."""

from datetime import date

from app.database import db
from app.models import (
    AttendanceModel, AuditLog, FeeTransaction, StudentMarkModel, StudentModel,
    TestModel,
)
from app.services import audit as audit_service


def _logs(entity_type):
    return (AuditLog.query.filter_by(entity_type=entity_type)
            .order_by(AuditLog.id.asc()).all())


def test_student_create_is_audited_with_actor_and_after_values(admin_client, app, seed):
    response = admin_client.post('/students/add', data={
        'roll_number': '1003',
        'student_name': 'Bilal Ahmed',
        'father_name': 'Ahmed Khan',
        'guardian_phone': '03009998888',
        'address': 'Street 9',
        'class_id': str(seed['class_id']),
        'section_id': str(seed['section_id']),
        'monthly_fee': '1800',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        student = StudentModel.query.filter_by(roll_number=1003).one()
        entries = [row for row in _logs('StudentModel')
                   if row.action == 'create' and row.entity_id == student.id]
        assert entries, 'no create audit entry for the new student'

        entry = entries[-1]
        assert entry.username == 'admin'
        assert entry.role == 'admin'
        assert entry.created_at is not None
        assert entry.after['roll_number'] == 1003
        assert entry.after['student_name'] == 'Bilal Ahmed'
        assert entry.before is None


def test_student_edit_records_before_and_after(admin_client, app, seed):
    student_id = seed['student_id']

    response = admin_client.post(f'/students/edit/{student_id}', data={
        'roll_number': '1001',
        'student_name': 'Ali Khan Updated',
        'father_name': 'Imran Khan',
        'guardian_phone': '03001234567',
        'address': 'Street 1',
        'class_id': str(seed['class_id']),
        'section_id': str(seed['section_id']),
        'monthly_fee': '2600',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        entries = [row for row in _logs('StudentModel')
                   if row.action == 'update' and row.entity_id == student_id]
        assert entries

        entry = entries[-1]
        assert entry.username == 'admin'
        assert 'student_name' in entry.changed_fields
        assert entry.before['student_name'] == 'Ali Khan'
        assert entry.after['student_name'] == 'Ali Khan Updated'


def test_attendance_correction_is_traceable(admin_client, app, seed):
    class_id = seed['class_id']
    student_id = seed['student_id']
    other_id = seed['other_student_id']
    day = '2026-09-21'

    first = admin_client.post('/attendance/students', data={
        'class_id': str(class_id),
        'date': day,
        f'status_{student_id}': 'Present',
        f'status_{other_id}': 'Present',
    }, follow_redirects=False)
    assert first.status_code == 302

    # Correct the first student to Absent.
    second = admin_client.post('/attendance/students', data={
        'class_id': str(class_id),
        'date': day,
        f'status_{student_id}': 'Absent',
        f'status_{other_id}': 'Present',
    }, follow_redirects=False)
    assert second.status_code == 302

    with app.app_context():
        attendance = AttendanceModel.query.filter_by(
            target_type='student', target_id=student_id, date=date(2026, 9, 21)).one()
        assert attendance.status == 'Absent'

        entries = [row for row in _logs('AttendanceModel')
                   if row.entity_id == attendance.id and row.username == 'admin']
        assert entries, 'attendance change was not audited'

        create_entry = [e for e in entries if e.action == 'create']
        update_entries = [e for e in entries if e.action == 'update']
        assert create_entry, 'creation of the attendance row was not audited'

        status_change = [e for e in update_entries if (e.after or {}).get('status') == 'Absent']
        assert status_change, 'the correction to Absent was not audited with its new value'
        assert status_change[-1].before.get('status') in ('Present', None)


def test_grade_entry_and_correction_are_traceable(admin_client, app, seed):
    with app.app_context():
        test = TestModel(test_title='Audit Test', test_date=date(2026, 10, 1),
                         test_type='Monthly', class_id=seed['class_id'],
                         subject_id=seed['subject_id'], total_marks=100)
        db.session.add(test)
        db.session.commit()
        test_id = test.id

    student_id = seed['student_id']
    batch_query = {
        'title': 'Audit Test',
        'date': '2026-10-01',
        'class_id': seed['class_id'],
    }
    first = admin_client.post('/tests/batch_marks', query_string=batch_query, data={
        f'marks_{student_id}_{test_id}': '70',
    }, follow_redirects=False)
    assert first.status_code == 302

    second = admin_client.post('/tests/batch_marks', query_string=batch_query, data={
        f'marks_{student_id}_{test_id}': '55',
    }, follow_redirects=False)
    assert second.status_code == 302

    with app.app_context():
        mark = StudentMarkModel.query.filter_by(test_id=test_id, student_id=student_id).one()
        assert mark.marks_obtained == 55.0

        entries = [row for row in _logs('StudentMarkModel')
                   if row.entity_id == mark.id and row.username == 'admin']
        assert entries

        corrections = [e for e in entries
                       if e.action == 'update' and (e.after or {}).get('marks_obtained') == 55.0]
        assert corrections, 'grade correction not captured with before/after'
        assert corrections[-1].before.get('marks_obtained') == 70.0
        assert corrections[-1].after.get('grade') == 'C'


def test_fee_payment_is_audited(admin_client, app, seed):
    student_id = seed['student_id']
    month = 'September 2026'

    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={month}')
    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': month,
        'amount_paid': '1000',
        'amount_due_override': '2500',
        'method': 'bank',
        'reference': 'RCPT-1',
        'remarks': 'first instalment',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        payments = FeeTransaction.query.filter_by(student_id=student_id, month_year=month,
                                                  txn_type='payment').all()
        assert len(payments) == 1
        assert payments[0].amount == 1000.0
        assert payments[0].method == 'bank'
        assert payments[0].reference == 'RCPT-1'
        assert payments[0].created_by_name == 'admin'

        actions = [row for row in _logs('FeeTransaction')
                   if row.action == 'create' and row.after and row.after.get('txn_type') == 'payment']
        assert actions and actions[-1].username == 'admin'

        explicit = [row for row in _logs('FeeTransaction')
                    if row.action == 'payment' and row.username == 'admin']
        assert explicit, 'explicit payment audit entry missing'


def test_login_logout_and_failed_login_are_audited(client, app):
    client.post('/login', data={'username': 'admin', 'password': 'wrong'})
    client.post('/login', data={'username': 'admin', 'password': 'adminpass123'})
    client.get('/logout')

    with app.app_context():
        actions = {row.action for row in AuditLog.query.all()}
        assert 'login_failed' in actions
        assert 'login' in actions
        assert 'logout' in actions


def test_audit_pages_render(admin_client, app, seed):
    log_page = admin_client.get('/audit-log')
    assert log_page.status_code == 200
    assert 'Audit Log' in log_page.get_data(as_text=True)

    csv_page = admin_client.get('/audit-log/export.csv')
    assert csv_page.status_code == 200
    assert csv_page.mimetype == 'text/csv'
    assert 'timestamp,username,role' in csv_page.get_data(as_text=True)

    history = admin_client.get(f'/students/{seed["student_id"]}/history')
    assert history.status_code == 200
    assert 'Ali Khan' in history.get_data(as_text=True)


def test_history_helpers_return_expected_rows(app, seed):
    with app.app_context():
        audit_service.log_action('settings_change', entity_type='StudentModel',
                                 entity_id=seed['student_id'], summary='unit-test entry')
        db.session.commit()

        rows = audit_service.history_for('StudentModel', seed['student_id'])
        assert any(row.summary == 'unit-test entry' for row in rows)


def test_audit_filters_apply(app, seed, admin_client):
    with app.app_context():
        audit_service.log_action('settings_change', entity_type='SchoolSettings',
                                 summary='filter-me-please')
        db.session.commit()

    response = admin_client.get('/audit-log?entity_type=SchoolSettings&search=filter-me-please')
    assert response.status_code == 200
    assert 'filter-me-please' in response.get_data(as_text=True)

    empty = admin_client.get('/audit-log?entity_type=DoesNotExist')
    assert empty.status_code == 200
    assert 'No audit entries match' in empty.get_data(as_text=True)

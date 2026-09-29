"""Data written through the UI must survive a full application restart."""

from datetime import date

from app.database import db
from app.models import (
    AttendanceModel, FeeRecordModel, FeeTransaction, StudentMarkModel, StudentModel,
    TestModel,
)
from tests.conftest import ADMIN_PASSWORD, login, seed_reference_data

MONTH = 'September 2026'
DB_NAME = 'persistence.db'


def _write_records(application, data):
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)

    created = client.post('/students/add', data={
        'roll_number': '1500',
        'student_name': 'Bilal Persist',
        'father_name': 'Ahmed Persist',
        'guardian_phone': '03005556666',
        'address': 'Persist Street',
        'class_id': str(data['class_id']),
        'section_id': str(data['section_id']),
        'monthly_fee': '1500',
    }, follow_redirects=False)
    assert created.status_code == 302

    student_id = None
    with application.app_context():
        student_id = StudentModel.query.filter_by(roll_number=1500).one().id
        test = TestModel(test_title='Persistence Test', test_date=date(2026, 9, 20),
                         test_type='Monthly', class_id=data['class_id'],
                         subject_id=data['subject_id'], total_marks=100)
        db.session.add(test)
        db.session.commit()
        test_id = test.id

    attendance = client.post('/attendance/students', data={
        'class_id': str(data['class_id']),
        'date': '2026-09-20',
        f'status_{student_id}': 'Late',
        f'late_time_{student_id}': '08:55',
    }, follow_redirects=False)
    assert attendance.status_code == 302

    marks = client.post(f'/tests/marks/{test_id}', data={
        f'marks_{student_id}': '88',
    }, follow_redirects=False)
    assert marks.status_code == 302

    client.get(f'/fees?class_id={data["class_id"]}&month_year={MONTH}')
    payment = client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '1500', 'method': 'cash', 'reference': 'PERSIST-1',
    }, follow_redirects=False)
    assert payment.status_code == 302

    return student_id, test_id


def test_records_survive_an_application_restart(fresh_app_factory, tmp_path):
    first_app = fresh_app_factory(tmp_path, DB_NAME)
    with first_app.app_context():
        db.drop_all()
        db.create_all()
        data = seed_reference_data()
        db.session.commit()

    student_id, test_id = _write_records(first_app, data)

    with first_app.app_context():
        db.session.remove()
        db.engine.dispose()

    # A brand new application instance against the same database file,
    # verifying the values came from storage, not from memory.
    second_app = fresh_app_factory(tmp_path, DB_NAME)
    client = second_app.test_client()
    assert login(client, 'admin', ADMIN_PASSWORD).status_code == 302

    with second_app.app_context():
        student = StudentModel.query.filter_by(roll_number=1500).one()
        assert student.id == student_id
        assert student.student_name == 'Bilal Persist'
        assert student.monthly_fee == 1500.0

        attendance = AttendanceModel.query.filter_by(
            target_type='student', target_id=student_id, date=date(2026, 9, 20)).one()
        assert attendance.status == 'Late'
        assert attendance.late_time == '08:55'

        mark = StudentMarkModel.query.filter_by(test_id=test_id, student_id=student_id).one()
        assert mark.marks_obtained == 88.0
        assert mark.grade == 'A+'

        record = FeeRecordModel.query.filter_by(student_id=student_id, month_year=MONTH).one()
        assert record.amount_due == 1500.0
        assert record.amount_paid == 1500.0
        assert record.status == 'Paid'

        payments = FeeTransaction.query.filter_by(student_id=student_id, month_year=MONTH,
                                                  txn_type='payment').all()
        assert len(payments) == 1
        assert payments[0].reference == 'PERSIST-1'

    # And the restarted app can still render the pages that show that data.
    assert client.get('/students').status_code == 200
    assert client.get(f'/students/{student_id}/report').status_code == 200
    assert client.get(f'/fees/receipt/{student_id}/{MONTH}').status_code == 200

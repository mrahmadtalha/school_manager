"""Advance credit / write-off with FEATURE_ADVANCE_CREDIT_WRITEOFF ON.

The shared ``app`` fixture pins the flag OFF (tests/conftest.py), and the
flag-off behaviour is asserted by the fee tests.  This module builds its own
app with the flag ON so the other mode gets real coverage without touching any
existing test.

Hand calculations:

    Overpayment: one month charged 2,500; pay 4,000 ->
        2,500 settles the charge, 1,500 stays as advance credit.
    No dues:     nothing charged; pay 1,000 -> 1,000 held as credit.
    Write-off:   three months charged 1,000 each = 3,000 owed ->
        writing off takes outstanding to 0 while charged stays 3,000 and
        the written-off amount is reported separately from "paid".
"""

from datetime import date

import pytest

from app import create_app
from app.database import db
from app.models import (AdminUser, ClassModel, FeeTransaction, ROLE_ADMIN,
                        StudentModel)
from app.services.fee_ledger import (advance_credit_enabled, ensure_charge,
                                     ledger_totals, payment_allocation_lines,
                                     recompute_fee_record, record_payment,
                                     record_writeoff, student_credit_paisa,
                                     student_outstanding_paisa)

MONTH = 'October 2026'
PREV = 'September 2026'


@pytest.fixture()
def app_on(tmp_path):
    """An app with advance credit / write-off switched ON, own database file."""
    application = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'FEATURE_ADVANCE_CREDIT_WRITEOFF': True,
        'SQLALCHEMY_DATABASE_URI':
            'sqlite:///' + (tmp_path / 'advance-credit.db').as_posix(),
    })
    with application.app_context():
        db.drop_all()
        db.create_all()
        admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='Advance Admin')
        admin.set_password('advance-credit-test-pass')
        db.session.add(admin)
        db.session.commit()
        application.config['ADMIN_ID'] = admin.id
        yield application
        db.session.remove()


@pytest.fixture()
def admin_client(app_on):
    """Signed-in admin session (no dependency on the login form flow)."""
    client = app_on.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(app_on.config['ADMIN_ID'])
        sess['_fresh'] = True
    return client


@pytest.fixture()
def student(app_on):
    """One student on their own class; 2,500/month, nothing charged yet."""
    with app_on.app_context():
        klass = ClassModel(name='Advance Credit Class', monthly_fee=2500.0)
        db.session.add(klass)
        db.session.flush()
        pupil = StudentModel(roll_number=970001, student_name='Credit Kid',
                             father_name='Credit Father',
                             guardian_phone='03001970001', address='X',
                             class_id=klass.id, monthly_fee=2500.0)
        db.session.add(pupil)
        db.session.flush()
        pupil_id, class_id = pupil.id, klass.id
        db.session.commit()
        return {'student_id': pupil_id, 'class_id': class_id}


def test_flag_is_actually_on(app_on):
    with app_on.app_context():
        assert advance_credit_enabled() is True


def test_overpayment_is_accepted_and_becomes_advance_credit(app_on, student):
    """2,500 charged; 4,000 paid -> 2,500 allocated, 1,500 held as credit."""
    with app_on.app_context():
        pupil = db.session.get(StudentModel, student['student_id'])
        ensure_charge(pupil, MONTH)
        db.session.commit()

        payment = record_payment(pupil, MONTH, 4000.0, method='cash',
                                 payment_date=date(2026, 10, 9))
        db.session.commit()

        assert payment.amount == 4000.0
        assert student_outstanding_paisa(pupil.id) == 0
        # 4,000 paid - 2,500 allocated = 1,500 credit
        assert student_credit_paisa(pupil.id) == 150000
        assert payment_allocation_lines(payment) == [(MONTH, 2500.0),
                                                     ('Advance credit', 1500.0)]


def test_payment_with_no_dues_is_recorded_as_credit(app_on, student):
    """Service level: a student who owes nothing can still pay ahead."""
    with app_on.app_context():
        pupil = db.session.get(StudentModel, student['student_id'])
        assert student_outstanding_paisa(pupil.id) == 0

        payment = record_payment(pupil, MONTH, 1000.0, method='cash',
                                 payment_date=date(2026, 10, 9))
        db.session.commit()

        assert student_credit_paisa(pupil.id) == 100000
        assert student_outstanding_paisa(pupil.id) == 0
        assert payment.amount == 1000.0


def test_route_accepts_a_payment_with_no_dues(admin_client, app_on, student):
    """Route level (D3): the 'This student has no dues.' block is flag-aware.

    With the flag on, the same POST that is refused when the flag is off must
    be recorded as a payment rather than blocked.  The advance-credit part of
    this scenario is covered at service level by
    test_payment_with_no_dues_is_recorded_as_credit: the route parses the
    amount with ``float(request.form...)``, so the raw test_client value is
    recorded exactly as 1,000.00.
    """
    response = admin_client.post('/fees/pay/%d' % student['student_id'], data={
        'month_year': MONTH, 'amount_paid': '1000', 'method': 'cash',
        'reference': '',
    }, follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'This student has no dues.' not in body
    with app_on.app_context():
        assert FeeTransaction.query.filter_by(student_id=student['student_id'],
                                              txn_type='payment',
                                              is_void=False).count() == 1


def test_writeoff_clears_dues_and_stays_separate_from_paid(app_on, student):
    """Three months (3,000) written off: outstanding 0, charged still 3,000."""
    with app_on.app_context():
        pupil = db.session.get(StudentModel, student['student_id'])
        # The student's own fee is what gets charged (the class default is not
        # inherited here), so pin the amount: 3 x 1,000 = 3,000 owed.
        for label in ('August 2026', PREV, MONTH):
            ensure_charge(pupil, label, amount=1000.0)
            db.session.commit()
            recompute_fee_record(pupil.id, label)
        db.session.commit()

        assert student_outstanding_paisa(pupil.id) == 300000      # 3,000.00

        txn, affected = record_writeoff(pupil, note='untraceable')
        db.session.commit()

        assert student_outstanding_paisa(pupil.id) == 0
        assert student_credit_paisa(pupil.id) == 0
        charged, paid, written_off = ledger_totals(pupil.id, MONTH)
        assert charged == 1000.0
        assert paid == 0.0                  # written off is never "paid"
        assert written_off == 1000.0
        assert txn.txn_type == 'writeoff'
        assert affected


def test_writeoff_route_works_when_the_flag_is_on(admin_client, app_on, student):
    """The write-off POST is refused with the flag off; with it on it records."""
    student_id = student['student_id']
    with app_on.app_context():
        pupil = db.session.get(StudentModel, student_id)
        ensure_charge(pupil, MONTH)
        db.session.commit()
        assert student_outstanding_paisa(student_id) == 250000

    response = admin_client.post('/fees/students/%d/writeoff' % student_id,
                                 data={'reason': 'owner decision'},
                                 follow_redirects=True)
    assert response.status_code == 200
    assert 'This feature is turned off.' not in response.get_data(as_text=True)
    with app_on.app_context():
        assert FeeTransaction.query.filter_by(student_id=student_id,
                                              txn_type='writeoff',
                                              is_void=False).count() == 1
        assert student_outstanding_paisa(student_id) == 0


def test_fee_page_offers_collect_form_for_a_paid_up_student(admin_client, app_on,
                                                            student):
    """With credit on, a fully paid student still gets the Collect Fee modal
    so an advance payment can be recorded."""
    with app_on.app_context():
        pupil = db.session.get(StudentModel, student['student_id'])
        ensure_charge(pupil, MONTH)
        record_payment(pupil, MONTH, 2500.0, method='cash',
                       payment_date=date(2026, 10, 9))
        db.session.commit()
        assert student_outstanding_paisa(pupil.id) == 0

    body = admin_client.get('/fees?class_id=%d' % student['class_id']) \
        .get_data(as_text=True)
    assert 'id="payModal%d"' % student['student_id'] in body
    assert 'name="amount_paid"' in body

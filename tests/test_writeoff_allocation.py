"""Requirement 19 — fee write-off, allocation and advance-credit rules.

Covers the defects found in the live data:

* allocation could only settle ``charge`` rows, never ``adjustment`` rows, so a
  month corrected by an adjustment showed a permanent phantom shortfall;
* write-offs therefore allocated nothing, leaving dues unpaid while the money
  side reported advance credit;
* nothing stopped advance credit existing at the same time as outstanding dues.

Rules asserted here:
  1. a write-off reduces outstanding dues;
  2. written-off money is never "paid" and never advance credit;
  3. a surplus payment keeps clearing dues and only becomes advance credit once
     nothing is owed;
  4. "specific month" settles that month first, then the remainder oldest-first;
  5. a write-off that settles nothing is never displayed as advance credit.

The ``app_on`` fixture uses the flag-ON mode, because that is the mode the
impossible state was produced under.
"""

from datetime import date

import pytest

from app import create_app
from app.database import db
from app.models import (AdminUser, ClassModel, FeePaymentAllocation,
                        FeeTransaction, ROLE_ADMIN, StudentModel)
from app.services.fee_ledger import (allocate_transaction, ensure_charge,
                                     ledger_totals, payment_allocation_lines,
                                     recompute_fee_record, record_adjustment,
                                     record_payment, record_writeoff,
                                     student_credit_paisa,
                                     student_dues_months,
                                     student_outstanding_paisa)

MONTH = 'October 2026'
PREV = 'September 2026'
PREV2 = 'August 2026'


@pytest.fixture()
def app_on(tmp_path):
    """Advance credit / write-off ON, own throwaway database."""
    application = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'FEATURE_ADVANCE_CREDIT_WRITEOFF': True,
        'SQLALCHEMY_DATABASE_URI':
            'sqlite:///' + (tmp_path / 'req19.db').as_posix(),
    })
    with application.app_context():
        db.drop_all()
        db.create_all()
        admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='Req19 Admin')
        admin.set_password('req19-test-pass')
        db.session.add(admin)
        db.session.commit()
        application.config['ADMIN_ID'] = admin.id
        yield application
        db.session.remove()


@pytest.fixture()
def admin_client(app_on):
    client = app_on.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(app_on.config['ADMIN_ID'])
        sess['_fresh'] = True
    return client


@pytest.fixture()
def student(app_on):
    """One student, 1,000/month, on their own class; nothing charged yet."""
    with app_on.app_context():
        klass = ClassModel(name='Req19 Class', monthly_fee=1000.0)
        db.session.add(klass)
        db.session.flush()
        pupil = StudentModel(roll_number=991900, student_name='Req Nineteen',
                             father_name='Req Father', guardian_phone='03001991900',
                             address='X', class_id=klass.id, monthly_fee=1000.0)
        db.session.add(pupil)
        db.session.flush()
        ids = {'student_id': pupil.id, 'class_id': klass.id}
        db.session.commit()
        return ids


def _charge(app, student_id, *months, amount=1000.0):
    pupil = db.session.get(StudentModel, student_id)
    for month in months:
        ensure_charge(pupil, month, amount=amount)
        db.session.commit()
        recompute_fee_record(pupil.id, month)


# --------------------------------------------------------------------------- 1
def test_writeoff_reduces_dues_and_is_not_paid(app_on, student):
    """Two months owed; writing off clears the dues but never counts as paid."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(app_on, sid, PREV, MONTH)
        assert student_outstanding_paisa(sid) == 200000        # 2,000

        txn, _affected = record_writeoff(db.session.get(StudentModel, sid),
                                         note='untraceable')
        db.session.commit()

        assert student_outstanding_paisa(sid) == 0
        assert student_credit_paisa(sid) == 0
        assert txn.txn_type == 'writeoff'
        charged, paid, written_off = ledger_totals(sid, MONTH)
        assert charged == 1000.0
        assert paid == 0.0, 'written-off money must never read as paid'
        assert written_off == 1000.0


# --------------------------------------------------------------------------- 2
def test_writeoff_allocates_against_adjustments_too(app_on, student):
    """A month that is only an ADJUSTMENT can still be settled.

    This is the live-data defect: allocation used to match ``charge`` rows only,
    so an adjustment could never be cleared by a write-off or a payment.
    """
    with app_on.app_context():
        sid = student['student_id']
        _charge(app_on, sid, MONTH)                 # 1,000 charge
        pupil = db.session.get(StudentModel, sid)
        record_adjustment(pupil, MONTH, 120.0, note='arrears correction')
        db.session.commit()
        recompute_fee_record(sid, MONTH)

        assert student_outstanding_paisa(sid) == 112000       # 1,120
        assert student_dues_months(sid) == [(MONTH, 1120.0)]

        record_writeoff(pupil, note='cleared')
        db.session.commit()

        # The adjustment is settled, so no phantom shortfall survives.
        assert student_outstanding_paisa(sid) == 0
        assert student_dues_months(sid) == []


# --------------------------------------------------------------------------- 3
def test_surplus_never_becomes_credit_while_dues_remain(app_on, student):
    """The requirement's example: 240 owed across two months, 1,000 paid.

    Allocation must chase the dues down first.  Once nothing is owed the rest is
    credit — but credit may never exist beside outstanding dues.
    """
    with app_on.app_context():
        sid = student['student_id']
        pupil = db.session.get(StudentModel, sid)
        # 120 owed in each of two months.
        ensure_charge(pupil, PREV, amount=120.0)
        ensure_charge(pupil, MONTH, amount=120.0)
        db.session.commit()
        recompute_fee_record(sid, PREV)
        recompute_fee_record(sid, MONTH)

        assert student_outstanding_paisa(sid) == 24000        # 240
        assert student_credit_paisa(sid) == 0

        payment = record_payment(pupil, MONTH, 1000.0, method='cash',
                                 payment_date=date(2026, 10, 10))
        db.session.commit()

        # 240 clears the dues; the remaining 760 is genuine credit.
        assert student_credit_paisa(sid) == 76000             # 760
        assert student_outstanding_paisa(sid) == 0
        # Every rupee is accounted for: 240 settled charges, 760 is credit.
        allocated = payment.amount_paisa - student_credit_paisa(sid)
        assert allocated == 24000


# --------------------------------------------------------------------------- 4
def test_no_credit_bytes_left_when_a_month_is_still_owed(app_on, student):
    """Three months owed, one payment that cannot cover them all: no credit."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(app_on, sid, PREV2, PREV, MONTH)               # 3,000 owed
        pupil = db.session.get(StudentModel, sid)

        record_payment(pupil, MONTH, 1000.0, method='cash',
                       payment_date=date(2026, 10, 10))
        db.session.commit()

        assert student_outstanding_paisa(sid) == 200000        # 2,000 still owed
        assert student_credit_paisa(sid) == 0, 'credit must be impossible while dues remain'


# --------------------------------------------------------------------------- 5
def test_specific_month_settles_that_month_then_oldest_first(app_on, student):
    """'Specific month' targets one month, then the remainder follows oldest-first."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(app_on, sid, PREV2, PREV, MONTH)               # 1,000 each
        pupil = db.session.get(StudentModel, sid)

        payment = record_payment(pupil, MONTH, 2500.0, method='cash',
                                 payment_date=date(2026, 10, 10),
                                 apply_month=MONTH)
        db.session.commit()

        rows = (FeePaymentAllocation.query
                .filter_by(payment_txn_id=payment.id, is_void=False)
                .join(FeeTransaction,
                      FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
                .all())
        by_month = {}
        for allocation in rows:
            label = allocation.charge_txn.month_year
            by_month[label] = by_month.get(label, 0) + allocation.amount_paisa

        assert by_month.get(MONTH) == 100000, 'target month settled first'
        assert by_month.get(PREV2) == 100000, 'remainder went to the OLDEST month'
        assert by_month.get(PREV) == 50000
        # 2,500 paid against 3,000 charged: the last 500 is still owed and no
        # part of the payment became credit.
        assert student_outstanding_paisa(sid) == 50000
        assert student_credit_paisa(sid) == 0


# --------------------------------------------------------------------------- 6
def test_writeoff_that_settles_nothing_is_not_shown_as_credit(app_on, student):
    """A write-off is never cash: an unapplied one must not display as credit."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(app_on, sid, MONTH)
        pupil = db.session.get(StudentModel, sid)

        txn, _affected = record_writeoff(pupil, note='cleared')
        db.session.commit()

        lines = payment_allocation_lines(txn)
        months = [month for month, _amount in lines]
        assert 'Advance credit' not in months
        assert student_credit_paisa(sid) == 0


# --------------------------------------------------------------------------- 7
def test_existing_writeoffs_realign_after_the_fix(app_on, student):
    """A write-off recorded BEFORE the fix allocates correctly when re-run.

    Mirrors the live rows: a charge plus an adjustment left 120 unsettled, and
    the write-off had allocated nothing because it only looked at charges.
    """
    with app_on.app_context():
        sid = student['student_id']
        _charge(app_on, sid, MONTH)
        pupil = db.session.get(StudentModel, sid)
        record_adjustment(pupil, MONTH, 120.0, note='correction')
        db.session.commit()
        recompute_fee_record(sid, MONTH)

        # Simulate the legacy write-off: recorded, but allocated to nothing.
        legacy = FeeTransaction(student_id=sid, month_year=MONTH,
                                txn_type='writeoff', amount=1120.0,
                                note='legacy')
        db.session.add(legacy)
        db.session.flush()
        assert student_outstanding_paisa(sid) == 112000        # still owed

        allocate_transaction(legacy, actor='repair')
        db.session.commit()
        recompute_fee_record(sid, MONTH)
        db.session.commit()

        assert student_outstanding_paisa(sid) == 0
        charged, paid, written_off = ledger_totals(sid, MONTH)
        assert written_off == 1120.0
        assert paid == 0.0
        assert student_credit_paisa(sid) == 0


# --------------------------------------------------------------------------- 8
def test_advance_payment_only_accepted_when_nothing_is_owed(app_on, student,
                                                            admin_client):
    """Dues pending -> an 'advance' post is applied to the dues instead."""
    sid = student['student_id']
    with app_on.app_context():
        _charge(app_on, sid, PREV)

    response = admin_client.post('/fees/pay/%d' % sid, data={
        'month_year': MONTH, 'amount_paid': '3000', 'method': 'cash',
        'reference': '', 'apply_to': 'advance',
    }, follow_redirects=True)
    assert response.status_code == 200

    with app_on.app_context():
        # Dues were September's 1,000 plus the billing month's 1,000 that the
        # route raises.  The 3,000 clears both, and only the genuine 1,000
        # surplus is held as credit.
        assert student_outstanding_paisa(sid) == 0
        assert student_credit_paisa(sid) == 100000


# --------------------------------------------------------------------------- 9
def test_fees_page_offers_advance_only_without_dues(app_on, student, admin_client):
    """No dues -> the form offers Advance Payment; dues -> it must not."""
    sid = student['student_id']
    with app_on.app_context():
        _charge(app_on, sid, MONTH)

    body = admin_client.get('/fees?class_id=%d&month_year=%s'
                            % (student['class_id'], MONTH.replace(' ', '%20'))
                            ).get_data(as_text=True)
    # The student owes money, so advance credit must not be selectable.
    segment = body.split('id="apply_to_%d"' % sid)
    assert len(segment) > 1, 'collect form not found for the student'
    block = segment[1].split('</select>')[0]
    assert 'value="advance"' not in block

    with app_on.app_context():
        pupil = db.session.get(StudentModel, sid)
        record_payment(pupil, MONTH, 1000.0, method='cash',
                       payment_date=date(2026, 10, 10))
        db.session.commit()
        assert student_outstanding_paisa(sid) == 0

    body = admin_client.get('/fees?class_id=%d&month_year=%s'
                            % (student['class_id'], MONTH.replace(' ', '%20'))
                            ).get_data(as_text=True)
    segment = body.split('id="apply_to_%d"' % sid)
    if len(segment) > 1:
        block = segment[1].split('</select>')[0]
        assert 'value="advance"' in block, 'paid-up student must be offered advance'

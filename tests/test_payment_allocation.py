"""Option B payment allocation: oldest dues first by default.

New payments settle the student's oldest unpaid charges first, then forward;
anything beyond every charge stays as advance credit.  The fee form's
"Specific month" override settles that month first.  Legacy rows (stamped by
the migration with their original month) re-allocate exactly as they did
before the rule change, so migrated figures never move.

Fixtures return plain IDs: ORM objects created inside one ``app_context``
detach when it exits, so every test re-queries with ``db.session.get`` inside
its own context.
"""

from datetime import date

import pytest

from app.bootstrap import migrate_payment_apply_month
from app.database import db
from app.models import (ClassModel, FeePaymentAllocation, FeeTransaction,
                        StudentModel, SystemSettingModel)
from app.services import financial_summary as fs, payroll_service
from app.services.fee_ledger import (ensure_charge, record_payment,
                                     record_refund, student_credit_paisa,
                                     student_month_outstanding_paisa,
                                     student_outstanding_paisa,
                                     void_transaction)


@pytest.fixture()
def arrears_world(app):
    """One student with a 2,500 charge in each of the last two months."""
    with app.app_context():
        # students.class_id is NOT NULL — every student needs a class row.
        klass = ClassModel(name='Allocation Class', monthly_fee=2500.0)
        db.session.add(klass)
        db.session.flush()
        student = StudentModel(roll_number=8200, student_name='Allocate Ali',
                               father_name='F Ali',
                               guardian_phone='030055551200', address='X',
                               class_id=klass.id, monthly_fee=2500.0)
        db.session.add(student)
        db.session.commit()
        current = _month_key()
        prev = payroll_service.shift_month(current, -1)
        ensure_charge(student, fs.month_label(prev))
        ensure_charge(student, fs.month_label(current))
        db.session.commit()
        student_id = student.id
    return student_id, prev, current


def _month_key():
    today = date.today()
    return '%04d-%02d' % (today.year, today.month)


def _allocations_by_month(payment):
    rows = (db.session.query(
                FeeTransaction.month_year,
                db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
            .join(FeePaymentAllocation,
                  FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
            .filter(FeePaymentAllocation.payment_txn_id == payment.id,
                    FeePaymentAllocation.is_void.is_(False))
            .group_by(FeeTransaction.month_year).all())
    return {month: round(value / 100.0, 2) for month, value in rows}


def test_default_allocates_oldest_dues_first(app, arrears_world):
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        payment = record_payment(student, fs.month_label(current), 4000.0,
                                 method='cash', payment_date=date.today())
        db.session.commit()

        split = _allocations_by_month(payment)
        assert split[fs.month_label(prev)] == 2500.0        # oldest first
        assert split[fs.month_label(current)] == 1500.0     # leftover
        assert student_outstanding_paisa(student.id) == 100000   # 1,000.00
        assert student_month_outstanding_paisa(
            student.id, fs.month_label(prev)) == 0
        assert student_month_outstanding_paisa(
            student.id, fs.month_label(current)) == 100000


def test_specific_month_override_settles_that_month_first(app, arrears_world):
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        payment = record_payment(student, fs.month_label(current), 4000.0,
                                 method='cash', payment_date=date.today(),
                                 apply_month=fs.month_label(current))
        db.session.commit()

        split = _allocations_by_month(payment)
        assert split[fs.month_label(current)] == 2500.0     # override month first
        assert split[fs.month_label(prev)] == 1500.0        # remainder oldest-first


def test_overpayment_is_rejected_when_credit_is_off(app, arrears_world):
    """Advance credit is switched off: a payment above the student's total
    outstanding dues is rejected and creates nothing."""
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        raised = False
        try:
            record_payment(student, fs.month_label(current), 6000.0,
                           method='cash', payment_date=date.today())
        except ValueError as error:
            raised = True
            assert "more than the student's total dues of Rs 5000.00" in str(error)
        assert raised, 'overpayment must be rejected'
        db.session.rollback()
        assert student_outstanding_paisa(student.id) == 500000   # 5,000.00
        assert student_credit_paisa(student.id) == 0


def test_void_frees_exactly_the_charges_it_settled(app, arrears_world):
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        payment = record_payment(student, fs.month_label(current), 4000.0,
                                 method='cash', payment_date=date.today())
        db.session.commit()
        assert student_outstanding_paisa(student.id) == 100000

        void_transaction(payment, reason='duplicate entry')
        db.session.commit()

        # Every allocation of the payment is voided: both months are fully
        # outstanding again and nothing partial is left behind.
        assert _allocations_by_month(payment) == {}
        assert student_outstanding_paisa(student.id) == 500000   # 5,000.00
        assert student_month_outstanding_paisa(
            student.id, fs.month_label(prev)) == 250000
        assert student_month_outstanding_paisa(
            student.id, fs.month_label(current)) == 250000


def test_refund_rebuilds_with_the_default_order(app, arrears_world):
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        payment = record_payment(student, fs.month_label(current), 4000.0,
                                 method='cash', payment_date=date.today())
        record_refund(payment, 1000.0, note='partial refund')
        db.session.commit()

        # Effective 3,000 re-allocates oldest-first: September stays fully
        # settled, October drops to 500.
        split = _allocations_by_month(payment)
        assert split[fs.month_label(prev)] == 2500.0
        assert split[fs.month_label(current)] == 500.0


def test_legacy_row_keeps_its_original_order_on_refund(app, arrears_world):
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        # A pre-rule payment: stamped with its own month (what the migration
        # does to legacy rows), so it allocated its own month first.
        payment = record_payment(student, fs.month_label(current), 4000.0,
                                 method='cash', payment_date=date.today(),
                                 apply_month=fs.month_label(current))
        assert _allocations_by_month(payment) == {
            fs.month_label(current): 2500.0, fs.month_label(prev): 1500.0}

        record_refund(payment, 1000.0, note='partial refund')
        db.session.commit()

        # The rebuild follows the stamped override, not the new default —
        # the refund frees the NEWEST money, exactly as it went in.
        split = _allocations_by_month(payment)
        assert split[fs.month_label(current)] == 2500.0
        assert split[fs.month_label(prev)] == 500.0


def test_migration_stamps_legacy_rows_without_reallocation(app, arrears_world):
    student_id, prev, current = arrears_world
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        payment = record_payment(student, fs.month_label(current), 1500.0,
                                 method='cash', payment_date=date.today())
        before = _allocations_by_month(payment)
        assert payment.apply_month is None               # a new-rule payment

        # Simulate the upgrade boot: clear the one-time flag so the stamping
        # runs again, then invoke the migration.
        SystemSettingModel.query.filter_by(
            key='payment_apply_month_stamped').delete()
        db.session.commit()
        migrate_payment_apply_month(app)

        db.session.expire(payment)
        assert payment.apply_month == payment.month_year  # stamped
        assert _allocations_by_month(payment) == before   # allocations untouched

        # Payments recorded AFTER the stamp are new-rule rows (no stamp).
        later = record_payment(student, fs.month_label(current), 100.0,
                               method='cash', payment_date=date.today())
        assert later.apply_month is None

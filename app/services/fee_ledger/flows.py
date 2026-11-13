"""Recording money: payments, adjustments, refunds, write-offs and voids."""

from datetime import date

from app.timeutil import utcnow
from app.database import db
from app.models import (FeePaymentAllocation, FeeTransaction, TXN_PAYMENT, TXN_ADJUSTMENT, TXN_REFUND,
                        TXN_WRITEOFF, SETTLING_TYPES, to_rupees)
from app.services.audit import current_actor

from .allocation import _refunded_paisa, allocate_transaction
from .common import (_round, advance_credit_enabled, current_month, generate_unique_reference)
from .totals import _recompute_months, student_outstanding_paisa


def record_payment(student, month_year, amount, method=None, reference=None,
                   note=None, created_by=None, payment_date=None,
                   apply_month=None):
    """Append a payment transaction for the month and allocate it.

    Default allocation (option B): the student's oldest unpaid charges first,
    then forward; anything left over after every charge stays as advance
    credit (no overpayment rejection).  ``apply_month`` (the fee form's
    "Specific month" choice) settles THAT month's charges first, then the
    remainder oldest-first.  ``month_year`` stays the payment's own month —
    the month the form was recorded from — and drives reporting only.
    """
    amount = _round(amount)
    if amount <= 0:
        raise ValueError('Payment amount must be greater than zero.')
    total_dues = to_rupees(student_outstanding_paisa(student.id))
    if not advance_credit_enabled() and amount > total_dues + 1e-9:
        raise ValueError("Amount is more than the student's total dues of Rs %.2f."
                         % total_dues)

    ref = generate_unique_reference(reference)
    _, username, _ = current_actor()
    txn = FeeTransaction(
        student_id=student.id,
        month_year=month_year,
        txn_type=TXN_PAYMENT,
        amount=amount,
        method=(method or 'cash')[:30],
        reference=ref[:80],
        note=(note or None) and str(note)[:255],
        payment_date=payment_date or date.today(),
        apply_month=(apply_month or None) and str(apply_month)[:20],
        created_by_id=created_by if created_by is not None else None,
        created_by_name=username,
    )
    db.session.add(txn)
    db.session.flush()
    affected = allocate_transaction(txn, actor=username or 'system')
    _recompute_months(student.id, affected | {month_year})
    return txn


def record_adjustment(student, month_year, amount, note=None):
    amount = _round(amount)
    _, username, _ = current_actor()
    txn = FeeTransaction(
        student_id=student.id, month_year=month_year, txn_type=TXN_ADJUSTMENT,
        amount=amount, note=(note or 'Adjustment'), created_by_name=username,
    )
    db.session.add(txn)
    db.session.flush()
    return txn


def record_refund(payment_txn, amount, note=None, payment_date=None):
    """Refund part of a payment; the payment re-allocates its remainder."""
    amount = _round(amount)
    if amount <= 0:
        raise ValueError('Refund amount must be greater than zero.')
    refundable = to_rupees(payment_txn.amount_paisa - _refunded_paisa(payment_txn.id))
    if amount > refundable + 1e-9:
        raise ValueError('Refund exceeds the un-refunded amount of this payment '
                         '(maximum: %.2f PKR).' % refundable)

    _, username, _ = current_actor()
    refund = FeeTransaction(
        student_id=payment_txn.student_id,
        month_year=payment_txn.month_year,
        txn_type=TXN_REFUND,
        amount=amount,
        method=payment_txn.method,
        note=(note or 'Refund')[:255],
        payment_date=payment_date or date.today(),
        related_txn_id=payment_txn.id,
        created_by_name=username,
    )
    db.session.add(refund)
    db.session.flush()
    affected = allocate_transaction(payment_txn, actor=username or 'system')
    affected.add(payment_txn.month_year)
    _recompute_months(payment_txn.student_id, affected)
    return refund, affected


def record_writeoff(student, note=None):
    """Write off a student's entire outstanding balance (owner decision).

    Creates a write-off transaction and allocates it like a payment, so the
    receivables leave the outstanding totals but remain reported separately.
    """
    outstanding = student_outstanding_paisa(student.id)
    if outstanding <= 0:
        raise ValueError('This student has no outstanding balance to write off.')

    _, username, _ = current_actor()
    txn = FeeTransaction(
        student_id=student.id,
        month_year=current_month(),
        txn_type=TXN_WRITEOFF,
        amount=to_rupees(outstanding),
        note=(note or 'Dues written off')[:255],
        created_by_name=username,
    )
    db.session.add(txn)
    db.session.flush()
    affected = allocate_transaction(txn, actor=username or 'system')
    affected.add(txn.month_year)
    _recompute_months(student.id, affected)
    return txn, affected


def void_transaction(txn, reason=None, actor_name=None):
    """Void a ledger row with a mandatory reason; never deletes.

    Voids the allocations that depended on it and re-allocates the affected
    settling transactions, then returns the set of affected month labels.
    """
    if txn.is_void:
        return set()
    txn.is_void = True
    txn.void_reason = (reason or 'No reason recorded')[:255]
    txn.voided_at = utcnow()
    txn.voided_by_name = actor_name or (current_actor()[1] or 'system')
    if reason:
        txn.note = (txn.note or '') + f' | voided: {reason}'

    affected = set()
    payments_to_reallocate = set()

    if txn.txn_type in SETTLING_TYPES:
        for allocation in FeePaymentAllocation.query.filter_by(
                payment_txn_id=txn.id, is_void=False).all():
            charge = allocation.charge_txn
            if charge is not None:
                affected.add(charge.month_year)
            allocation.is_void = True
        # A voided payment cannot keep refunds hanging off it.
        for refund in FeeTransaction.query.filter_by(related_txn_id=txn.id,
                                                     txn_type=TXN_REFUND,
                                                     is_void=False).all():
            refund.is_void = True
            refund.void_reason = 'Original payment voided'
            refund.voided_at = utcnow()
            refund.voided_by_name = txn.voided_by_name
            affected.add(refund.month_year)
    elif txn.txn_type == TXN_REFUND:
        if txn.related_txn_id:
            payments_to_reallocate.add(txn.related_txn_id)
        affected.add(txn.month_year)
    else:  # charge or adjustment
        affected.add(txn.month_year)
        for allocation in FeePaymentAllocation.query.filter_by(
                charge_txn_id=txn.id, is_void=False).all():
            allocation.is_void = True
            if allocation.payment_txn_id:
                payments_to_reallocate.add(allocation.payment_txn_id)

    for payment_id in payments_to_reallocate:
        payment = db.session.get(FeeTransaction, payment_id)
        if payment is not None and not payment.is_void:
            affected |= allocate_transaction(payment, actor=txn.voided_by_name or 'system')
    if affected:
        _recompute_months(txn.student_id, affected)
    return affected

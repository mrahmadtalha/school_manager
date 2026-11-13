"""Derived totals: ledger figures, outstanding and credit, the fee-record summary, reconciliation and repair of summaries."""

from sqlalchemy import func

from app.database import db
from app.models import (FeePaymentAllocation, FeeRecordModel, FeeTransaction, StudentModel, TXN_CHARGE,
                        TXN_PAYMENT, TXN_ADJUSTMENT, TXN_REFUND, TXN_WRITEOFF, to_rupees)

from .common import _month_sort_key, _round


def _recompute_months(student_id, months):
    """Refresh the cached summaries for every month the ledger touched."""
    for month in months or ():
        recompute_fee_record(student_id, month)


def ledger_totals(student_id, month_year=None):
    """Return ``(charged, paid, written_off)`` derived from ledger + allocations.

    ``charged`` sums active charges and adjustments; ``paid`` sums active
    payment allocations settled against that month's charges (so a payment
    counts towards the month it actually settles, not the month it was keyed
    into).  Write-offs are reported separately, never as paid.
    """
    query = FeeTransaction.query.filter_by(student_id=student_id, is_void=False)
    if month_year:
        query = query.filter_by(month_year=month_year)
    charged = 0.0
    for txn in query.all():
        if txn.txn_type in (TXN_CHARGE, TXN_ADJUSTMENT):
            charged += txn.amount or 0.0

    paid_paisa = 0
    writeoff_paisa = 0
    allocation_query = (FeePaymentAllocation.query
                        .join(FeeTransaction, FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
                        .filter(FeePaymentAllocation.is_void.is_(False),
                                FeeTransaction.student_id == student_id))
    if month_year:
        allocation_query = allocation_query.filter(FeeTransaction.month_year == month_year)
    for allocation in allocation_query.all():
        settler = allocation.payment_txn
        if settler is None or settler.is_void:
            continue
        if settler.txn_type == TXN_PAYMENT:
            paid_paisa += allocation.amount_paisa
        elif settler.txn_type == TXN_WRITEOFF:
            writeoff_paisa += allocation.amount_paisa

    return _round(charged), to_rupees(paid_paisa), to_rupees(writeoff_paisa)


def month_written_off(student_id, month_year):
    _charged, _paid, written_off = ledger_totals(student_id, month_year)
    return written_off


def student_outstanding_paisa(student_id):
    """Everything the student still owes, across all months (integer paisa)."""
    charged = (db.session.query(func.coalesce(func.sum(FeeTransaction.amount_paisa), 0))
               .filter(FeeTransaction.student_id == student_id,
                       FeeTransaction.txn_type.in_((TXN_CHARGE, TXN_ADJUSTMENT)),
                       FeeTransaction.is_void.is_(False)).scalar()) or 0
    settled = (db.session.query(func.coalesce(func.sum(FeePaymentAllocation.amount_paisa), 0))
               .join(FeeTransaction, FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
               .filter(FeeTransaction.student_id == student_id,
                       FeePaymentAllocation.is_void.is_(False)).scalar()) or 0
    return max(0, charged - settled)


def student_credit_paisa(student_id):
    """Unallocated PAYMENT balance held as advance credit (integer paisa).

    Only real money counts here: a write-off is a bookkeeping entry, never
    cash.  Because allocation settles every money-owed row (charges *and*
    adjustments), anything still unallocated means nothing was left owing —
    so advance credit and outstanding dues can never coexist.
    """
    paid_in = (db.session.query(func.coalesce(func.sum(FeeTransaction.amount_paisa), 0))
               .filter(FeeTransaction.student_id == student_id,
                       FeeTransaction.txn_type == TXN_PAYMENT,
                       FeeTransaction.is_void.is_(False)).scalar()) or 0
    refunded = (db.session.query(func.coalesce(func.sum(FeeTransaction.amount_paisa), 0))
                .filter(FeeTransaction.student_id == student_id,
                        FeeTransaction.txn_type == TXN_REFUND,
                        FeeTransaction.is_void.is_(False)).scalar()) or 0
    allocated = (db.session.query(func.coalesce(func.sum(FeePaymentAllocation.amount_paisa), 0))
                 .join(FeeTransaction, FeePaymentAllocation.payment_txn_id == FeeTransaction.id)
                 .filter(FeeTransaction.student_id == student_id,
                         FeeTransaction.txn_type == TXN_PAYMENT,
                         FeePaymentAllocation.is_void.is_(False)).scalar()) or 0
    return max(0, paid_in - refunded - allocated)


def _status_for(charged, settled):
    """Status after payments AND write-offs settle the charge."""
    if charged <= 0 and settled <= 0:
        return 'Pending'
    if settled + 0.005 >= charged and charged > 0:
        return 'Paid'
    if settled > 0:
        return 'Partial'
    return 'Pending'


def recompute_fee_record(student_id, month_year, remarks=None):
    """Rebuild the cached summary row from the ledger + allocations."""
    charged, paid, written_off = ledger_totals(student_id, month_year)

    record = FeeRecordModel.query.filter_by(student_id=student_id, month_year=month_year).first()
    if record is None:
        record = FeeRecordModel(student_id=student_id, month_year=month_year)
        db.session.add(record)

    record.amount_due = charged
    record.amount_paid = paid
    record.amount_written_off = written_off
    record.status = _status_for(charged, paid + written_off)

    last_payment = (FeeTransaction.query
                    .filter_by(student_id=student_id, month_year=month_year,
                               txn_type=TXN_PAYMENT, is_void=False)
                    .order_by(FeeTransaction.payment_date.desc(),
                              FeeTransaction.created_at.desc(), FeeTransaction.id.desc())
                    .first())
    record.payment_date = (last_payment.payment_date or last_payment.created_at.date()) \
        if last_payment else None
    if remarks is not None:
        record.remarks = remarks[:200] if remarks else None
    return record


def transactions_for(student_id, month_year):
    return (FeeTransaction.query
            .filter_by(student_id=student_id, month_year=month_year)
            .order_by(FeeTransaction.created_at.asc(), FeeTransaction.id.asc())
            .all())


def student_summary(student_id):
    """Per-month summary rows for one student, newest first."""
    months = [row[0] for row in
              db.session.query(FeeTransaction.month_year)
              .filter_by(student_id=student_id)
              .distinct().all()]
    months.sort(key=_month_sort_key, reverse=True)

    rows = []
    for month in months:
        charged, paid, written_off = ledger_totals(student_id, month)
        rows.append({
            'month_year': month,
            'charged': charged,
            'paid': paid,
            'written_off': written_off,
            'balance': _round(charged - paid - written_off),
            'transactions': transactions_for(student_id, month),
        })
    return rows


def reconcile(month_year=None):
    """Compare the derived summary cache against the ledger + allocations.

    Returns ``(rows, totals, discrepancies)``.
    """
    txn_query = FeeTransaction.query.filter_by(is_void=False)
    if month_year:
        txn_query = txn_query.filter_by(month_year=month_year)

    keys = sorted({(t.student_id, t.month_year) for t in txn_query.all()},
                  key=lambda k: (_month_sort_key(k[1]), k[0]), reverse=True)

    students = {s.id: s for s in StudentModel.query.all()}
    rows, discrepancies = [], []
    total_charged = total_paid = 0.0

    for student_id, month in keys:
        student = students.get(student_id)
        if student is None:
            continue
        charged, paid, written_off = ledger_totals(student_id, month)
        stored = FeeRecordModel.query.filter_by(student_id=student_id, month_year=month).first()

        row = {
            'student': student,
            'month_year': month,
            'charged': charged,
            'paid': paid,
            'written_off': written_off,
            'balance': _round(charged - paid - written_off),
            'stored_due': _round(stored.amount_due) if stored else None,
            'stored_paid': _round(stored.amount_paid) if stored else None,
            'stored_status': stored.status if stored else None,
            'balanced': bool(stored
                             and _round(stored.amount_due) == charged
                             and _round(stored.amount_paid) == paid
                             and _round(stored.amount_written_off) == written_off),
        }
        rows.append(row)
        total_charged += charged
        total_paid += paid

        if stored is None or not row['balanced']:
            discrepancies.append(row)

    totals = {
        'charged': _round(total_charged),
        'paid': _round(total_paid),
        'balance': _round(total_charged - total_paid),
        'rows': len(rows),
    }
    return rows, totals, discrepancies


def repair_summaries(month_year=None):
    """Recompute every summary row touched by the ledger."""
    txn_query = FeeTransaction.query.filter_by(is_void=False)
    if month_year:
        txn_query = txn_query.filter_by(month_year=month_year)
    keys = {(t.student_id, t.month_year) for t in txn_query.all()}
    for student_id, month in keys:
        recompute_fee_record(student_id, month)
    db.session.commit()
    return len(keys)

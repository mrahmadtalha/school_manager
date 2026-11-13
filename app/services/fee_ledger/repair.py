"""Allocation repair: find settlements whose charge is gone and re-allocate them."""

from app.database import db
from app.models import FeePaymentAllocation, FeeTransaction, SETTLING_TYPES

from .allocation import allocate_transaction
from .totals import _recompute_months


def orphaned_settlements(student_id=None):
    """Settling rows that have NO active allocation (read-only).

    Returns ``[FeeTransaction, ...]`` oldest first.  A row here is money the
    ledger holds but which settles no charge; for a payment that is the false
    advance credit requirement 19 describes.

    Two queries, not one per row, so this stays cheap enough to call on every
    application start.
    """
    query = (FeeTransaction.query
             .filter(FeeTransaction.is_void.is_(False))
             .filter(FeeTransaction.txn_type.in_(SETTLING_TYPES)))
    if student_id is not None:
        query = query.filter(FeeTransaction.student_id == student_id)
    candidates = query.order_by(FeeTransaction.id.asc()).all()
    if not candidates:
        return []

    settled = {row[0] for row in
               db.session.query(FeePaymentAllocation.payment_txn_id)
               .filter(FeePaymentAllocation.payment_txn_id.in_(
                   [t.id for t in candidates]),
                   FeePaymentAllocation.is_void.is_(False))
               .distinct().all()}
    return [txn for txn in candidates if txn.id not in settled]


def repair_allocations(student_id=None, actor='repair'):
    """Give settling rows that settle nothing a real allocation.

    Walks the affected transactions **oldest first** and re-allocates each
    one, so earlier money claims earlier dues exactly as it would have at the
    time it was taken.  Each row keeps its own ``apply_month`` choice (a named
    month first, then oldest-first) — the repair never invents a different
    order.

    Idempotent by design: a transaction that already has an active allocation
    is left completely alone, so re-running changes nothing and cannot move an
    already-correct figure.

    Returns ``{'repaired': int, 'students': set, 'months': set}``; the caller
    is responsible for committing.
    """
    orphans = orphaned_settlements(student_id)
    repaired = 0
    students = set()
    months = set()
    for txn in orphans:
        affected = allocate_transaction(txn, actor=actor)
        months |= affected
        students.add(txn.student_id)
        repaired += 1
        if txn.month_year:
            months.add(txn.month_year)

    for student in students:
        _recompute_months(student, months)
    return {'repaired': repaired, 'students': students, 'months': months}

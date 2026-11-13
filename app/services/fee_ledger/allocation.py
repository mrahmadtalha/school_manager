"""Allocations: which charges a payment or write-off settles (oldest month first) and the per-month balances built from them."""

from datetime import datetime

from sqlalchemy import func

from app.database import db
from app.models import (FeePaymentAllocation, FeeTransaction, TXN_CHARGE, TXN_PAYMENT, TXN_ADJUSTMENT,
                        TXN_REFUND, TXN_WRITEOFF, SETTLING_TYPES)

from .common import _month_sort_key, advance_credit_enabled


def payment_allocation_lines(txn):
    """Where a settling transaction's money actually went (display only).

    Returns ``[(month_label, rupees), ...]``, oldest month first, plus one
    trailing ``('Advance credit', rupees)`` line when part of the payment could
    not be allocated to any charge.  Never changes the ledger.
    """
    if txn is None or txn.id is None:
        return []
    rows = (FeePaymentAllocation.query
            .filter_by(payment_txn_id=txn.id, is_void=False).all())
    by_month = {}
    for allocation in rows:
        charge = allocation.charge_txn
        if charge is None:
            continue
        by_month[charge.month_year] = (by_month.get(charge.month_year, 0)
                                       + allocation.amount_paisa)
    lines = [(month, round(paisa / 100.0, 2))
             for month, paisa in sorted(by_month.items(),
                                        key=lambda item: _month_sort_key(item[0]))]
    leftover = round(txn.amount or 0.0, 2) - round(sum(b for _m, b in lines), 2)
    # An unallocated remainder is NOT always advance credit.  Only real money
    # (a payment) can become credit; a write-off that settles nothing is simply
    # a write-off "not applied to any month", never cash the school holds.  The
    # "Advance credit" wording belongs to the advance-credit feature, so it is
    # only ever shown while that switch is on — a receipt must not reveal the
    # concept the flag hides.
    if leftover > 0.005:
        if txn.txn_type == TXN_WRITEOFF:
            lines.append(('Not applied to any month', round(leftover, 2)))
        elif advance_credit_enabled():
            lines.append(('Advance credit', round(leftover, 2)))
    return lines


def payment_allocation_summary(txn):
    """The allocation lines as one plain sentence (for flash messages)."""
    lines = payment_allocation_lines(txn)
    if not lines:
        return ''
    return '; '.join('Rs %s applied to %s' % ('{:,.0f}'.format(amount), month)
                     for month, amount in lines)


def _charge_sorted(charges):
    return sorted(charges, key=lambda t: (t.created_at or datetime.min, t.id))


def _student_month_keys(student_id):
    """All of the student's ledger months, oldest first."""
    months = [row[0] for row in db.session.query(FeeTransaction.month_year)
              .filter_by(student_id=student_id).distinct().all()]
    return sorted(months, key=_month_sort_key)


def _settled_paisa(charge_txn_id):
    return (db.session.query(func.coalesce(func.sum(FeePaymentAllocation.amount_paisa), 0))
            .filter(FeePaymentAllocation.charge_txn_id == charge_txn_id,
                    FeePaymentAllocation.is_void.is_(False)).scalar()) or 0


#: Ledger rows a settling transaction may be applied against.  Adjustments
#: are money owed exactly like charges — every month and outstanding figure
#: adds the two together — so allocation has to be able to settle them too.
#: Without this, a month corrected by an adjustment shows a permanent phantom
#: shortfall that no payment can ever clear.
SETTLEABLE_TYPES = (TXN_CHARGE, TXN_ADJUSTMENT)


def _month_charged_paisa(student_id, month_year):
    return (db.session.query(func.coalesce(func.sum(FeeTransaction.amount_paisa), 0))
            .filter(FeeTransaction.student_id == student_id,
                    FeeTransaction.month_year == month_year,
                    FeeTransaction.txn_type.in_((TXN_CHARGE, TXN_ADJUSTMENT)),
                    FeeTransaction.is_void.is_(False)).scalar()) or 0


def _month_settled_paisa(student_id, month_year):
    return (db.session.query(func.coalesce(func.sum(FeePaymentAllocation.amount_paisa), 0))
            .join(FeeTransaction, FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
            .filter(FeeTransaction.student_id == student_id,
                    FeeTransaction.month_year == month_year,
                    FeePaymentAllocation.is_void.is_(False)).scalar()) or 0


def student_month_outstanding_paisa(student_id, month_year):
    """Rupees still owed for ONE ledger month (integer paisa), from the ledger.

    Charges and adjustments of the month minus everything settled against
    them (payments and write-offs) — the same arithmetic every other summary
    figure uses, so the dues list can never disagree with the totals.
    """
    return max(0, _month_charged_paisa(student_id, month_year)
               - _month_settled_paisa(student_id, month_year))


def student_dues_months(student_id):
    """Months where the student still owes money, oldest first.

    Returns ``[(month_year, outstanding_rupees)]`` with a balance > 0 only,
    computed straight from the ledger (charges + adjustments minus every
    settling allocation).  Feeds the Collect Fee form's "Specific month"
    dropdown.
    """
    charges = (FeeTransaction.query
               .filter_by(student_id=student_id, is_void=False)
               .filter(FeeTransaction.txn_type.in_((TXN_CHARGE, TXN_ADJUSTMENT)))
               .all())
    if not charges:
        return []
    per_month = {}
    for charge in charges:
        per_month[charge.month_year] = (per_month.get(charge.month_year, 0)
                                        + charge.amount_paisa)
    settled = (db.session.query(
                   FeeTransaction.month_year,
                   db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
               .join(FeePaymentAllocation,
                     FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
               .filter(FeeTransaction.id.in_([c.id for c in charges]),
                       FeePaymentAllocation.is_void.is_(False))
               .group_by(FeeTransaction.month_year).all())
    for month, paid_paisa in settled:
        per_month[month] = per_month.get(month, 0) - paid_paisa
    months = [(month, round(paisa / 100.0, 2))
              for month, paisa in per_month.items() if paisa > 0]
    months.sort(key=lambda item: _month_sort_key(item[0]))
    return months


def _refunded_paisa(payment_txn_id):
    return (db.session.query(func.coalesce(func.sum(FeeTransaction.amount_paisa), 0))
            .filter(FeeTransaction.related_txn_id == payment_txn_id,
                    FeeTransaction.txn_type == TXN_REFUND,
                    FeeTransaction.is_void.is_(False)).scalar()) or 0


def allocate_transaction(txn, actor='system'):
    """(Re-)allocate a payment or write-off across outstanding charges.

    Default order (option B): the student's OLDEST unpaid charges first, then
    forward in chronological order; anything beyond every charge stays as
    advance credit.  When the transaction carries an ``apply_month`` override
    (the fee form's "Specific month" choice — also stamped onto pre-rule
    legacy rows as their original month), that month is settled first and the
    remainder follows oldest-first.  Existing allocations of the transaction
    are voided and rebuilt, so this is safe to call again after refunds or
    voids change the effective amount.

    Returns the set of month labels whose summaries changed.
    """
    if txn.txn_type not in SETTLING_TYPES or txn.is_void:
        return []

    affected = set()
    for old in FeePaymentAllocation.query.filter_by(payment_txn_id=txn.id,
                                                    is_void=False).all():
        charge = old.charge_txn
        if charge is not None:
            affected.add(charge.month_year)
        old.is_void = True

    effective = txn.amount_paisa
    if txn.txn_type == TXN_PAYMENT:
        effective -= _refunded_paisa(txn.id)
    remaining = max(0, effective)

    months = _student_month_keys(txn.student_id)
    apply_month = getattr(txn, 'apply_month', None)
    if apply_month:
        month_order = [apply_month] + [m for m in months if m != apply_month]
    else:
        month_order = months
    for month in month_order:
        if remaining <= 0:
            break
        month_remaining = _month_charged_paisa(txn.student_id, month) \
            - _month_settled_paisa(txn.student_id, month)
        if month_remaining <= 0:
            continue
        charges = _charge_sorted(FeeTransaction.query
                                 .filter_by(student_id=txn.student_id, month_year=month,
                                            is_void=False)
                                 .filter(FeeTransaction.txn_type.in_(SETTLEABLE_TYPES)).all())
        for charge in charges:
            if remaining <= 0 or month_remaining <= 0:
                break
            available = charge.amount_paisa - _settled_paisa(charge.id)
            if available <= 0:
                continue
            give = min(available, month_remaining, remaining)
            db.session.add(FeePaymentAllocation(
                payment_txn_id=txn.id, charge_txn_id=charge.id,
                amount_paisa=give, created_by_name=actor))
            remaining -= give
            month_remaining -= give
            affected.add(month)
    return affected

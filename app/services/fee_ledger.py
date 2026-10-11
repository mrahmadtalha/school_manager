"""Fee ledger service (financial v2).

``fee_transactions`` is the source of truth (append-only, voidable, never
deleted).  ``fee_records`` is a derived per-student/per-month summary that is
always recomputed from the ledger + allocations so the two can never disagree.

**Allocations** link a settling transaction (a payment or a write-off) to the
specific charges it settles.  New money settles the student's outstanding
charges **oldest month first** (the month named on the form first, then any
older arrears).  Whatever is left after every outstanding charge is settled
stays unallocated — that is the student's advance credit, applied
automatically to future charges by the next allocation run.

**Refunds** are negative cash tied to their original payment
(``related_txn_id``); creating one reduces the payment's effective amount and
the payment is re-allocated, which raises the outstanding balance back.

**Voids** never delete: a voided row is flagged with a mandatory reason and
excluded from every total; affected allocations are voided with it and the
remaining payments re-allocate.
"""

from datetime import date, datetime

from flask import current_app
from sqlalchemy import func

from app.database import db
from app.models import (
    FeePaymentAllocation, FeeRecordModel, FeeTransaction, StudentModel,
    TXN_CHARGE, TXN_PAYMENT, TXN_ADJUSTMENT, TXN_REFUND, TXN_WRITEOFF,
    SETTLING_TYPES, to_paisa, to_rupees,
)
from app.services.audit import current_actor


def current_month():
    return datetime.now().strftime('%B %Y')


def advance_credit_enabled():
    """Advance credit / write-off master switch (default off).

    Read from the live app config so both modes are testable; with no app
    context (pure unit calls) the historical flag-off behaviour is kept.
    """
    try:
        return bool(current_app.config.get('FEATURE_ADVANCE_CREDIT_WRITEOFF', False))
    except RuntimeError:
        return False


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


def _round(value):
    return round(float(value or 0.0), 2)


def month_charge_amount(student):
    return _round(student.monthly_fee or 0.0)


def ensure_charge(student, month_year, amount=None):
    """Create the monthly charge transaction when the month has none yet."""
    existing = (FeeTransaction.query
                .filter_by(student_id=student.id, month_year=month_year,
                           txn_type=TXN_CHARGE, is_void=False)
                .first())
    if existing:
        return existing

    amount = month_charge_amount(student) if amount is None else _round(amount)
    _, username, _ = current_actor()
    txn = FeeTransaction(
        student_id=student.id,
        month_year=month_year,
        txn_type=TXN_CHARGE,
        amount=amount,
        note='Monthly fee charged',
        created_by_name=username,
    )
    db.session.add(txn)
    return txn


def set_month_charge(student, month_year, amount):
    """Force the charge for a month to ``amount`` (used by fee overrides)."""
    txn = ensure_charge(student, month_year, amount=amount)
    txn.amount = _round(amount)
    txn.note = 'Monthly fee charged (amount updated)'
    return txn


class DuplicateReferenceError(ValueError):
    """Raised when a slip/reference number is already used by another payment."""

    def __init__(self, reference, suggestion=None):
        self.reference = reference
        self.suggestion = suggestion
        super().__init__(f'Slip / Reference No "{reference}" has already been used.')


def reference_in_use(reference):
    """True when a non-voided transaction already carries this slip/reference no.

    The comparison ignores surrounding spaces and upper/lower case, so
    ``slip-1`` and ``SLIP-1`` count as the same number.
    """
    candidate = (reference or '').strip()[:80]
    if not candidate:
        return False
    return (FeeTransaction.query
            .filter(func.lower(FeeTransaction.reference) == candidate.lower(),
                    FeeTransaction.is_void.is_(False))
            .first()) is not None


def next_reference(prefix='SLIP'):
    """Return the next free auto slip number, e.g. ``SLIP-20261003-0004``."""
    today = datetime.now().strftime('%Y%m%d')
    pattern = f'{prefix}-{today}-%'
    serial = (db.session.query(func.coalesce(func.max(func.cast(
        func.substr(FeeTransaction.reference, len(f'{prefix}-{today}-') + 1, 255), db.Integer
    )), 0)).filter(FeeTransaction.reference.like(pattern)).scalar() or 0) + 1

    while True:
        generated = f'{prefix}-{today}-{serial:04d}'
        if not reference_in_use(generated):
            return generated
        serial += 1


def generate_unique_reference(reference=None, *, prefix='SLIP'):
    """Return a slip/reference number that is guaranteed to be unused.

    A typed-in number is kept as it is when free and rejected with
    ``DuplicateReferenceError`` when taken.  A blank value gets a freshly
    generated number.
    """
    candidate = (reference or '').strip()
    if candidate:
        candidate = candidate[:80]
        if reference_in_use(candidate):
            raise DuplicateReferenceError(candidate, suggestion=next_reference(prefix))
        return candidate
    return next_reference(prefix)


# ------------------------------------------------------------------ allocations

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


# ----------------------------------------------------------------- record flows

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
    txn.voided_at = datetime.utcnow()
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
            refund.voided_at = datetime.utcnow()
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


def _recompute_months(student_id, months):
    """Refresh the cached summaries for every month the ledger touched."""
    for month in months or ():
        recompute_fee_record(student_id, month)


# ----------------------------------------------------------------- derived totals

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


def _month_sort_key(month_year):
    try:
        return datetime.strptime(month_year, '%B %Y')
    except (TypeError, ValueError):
        return datetime(1900, 1, 1)


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


# ------------------------------------------------------------ allocation repair

#: Settling transactions that predate the allocation rule can sit in the
#: ledger with no allocation rows at all: the money is recorded, but it
#: settles nothing.  ``student_credit_paisa`` only counts PAYMENT money that
#: was never allocated, so such a row is reported as advance credit while the
#: charges it should have cleared stay outstanding — the impossible "owes
#: money and holds credit" state.  These helpers find and rebuild those rows.


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

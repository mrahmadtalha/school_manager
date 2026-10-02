"""Fee ledger service.

``fee_transactions`` is the source of truth (append-only).  ``fee_records`` is a
derived per-student/per-month summary that is always recomputed from the ledger
so the two can never disagree.
"""

from datetime import datetime

from sqlalchemy import func

from app.database import db
from app.models import (
    FeeRecordModel, FeeTransaction, StudentModel,
    TXN_CHARGE, TXN_PAYMENT, TXN_ADJUSTMENT,
)
from app.services.audit import current_actor, log_action


def current_month():
    return datetime.now().strftime('%B %Y')


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


def generate_unique_reference(reference=None, *, prefix='SLIP'):
    """Create a unique slip/reference number for a payment."""
    candidate = (reference or '').strip()
    if candidate:
        existing = FeeTransaction.query.filter_by(reference=candidate, is_void=False).first()
        if existing is None:
            return candidate[:80]

    today = datetime.now().strftime('%Y%m%d')
    pattern = f'{prefix}-{today}-%'
    serial = (db.session.query(func.coalesce(func.max(func.cast(
        func.substr(FeeTransaction.reference, len(f'{prefix}-{today}-') + 1, 255), db.Integer
    )), 0)).filter(FeeTransaction.reference.like(pattern)).scalar() or 0) + 1

    while True:
        generated = f'{prefix}-{today}-{serial:04d}'
        exists = FeeTransaction.query.filter_by(reference=generated, is_void=False).first()
        if exists is None:
            return generated
        serial += 1


def record_payment(student, month_year, amount, method=None, reference=None,
                   note=None, created_by=None):
    """Append a payment transaction for the month."""
    amount = _round(amount)
    if amount <= 0:
        raise ValueError('Payment amount must be greater than zero.')

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
        created_by_id=created_by if created_by is not None else None,
        created_by_name=username,
    )
    db.session.add(txn)
    return txn


def record_adjustment(student, month_year, amount, note=None):
    amount = _round(amount)
    _, username, _ = current_actor()
    txn = FeeTransaction(
        student_id=student.id, month_year=month_year, txn_type=TXN_ADJUSTMENT,
        amount=amount, note=(note or 'Adjustment'), created_by_name=username,
    )
    db.session.add(txn)
    return txn


def void_transaction(txn, note=None):
    txn.is_void = True
    if note:
        txn.note = (txn.note or '') + f' | voided: {note}'
    return txn


# -- derived totals -----------------------------------------------------

def ledger_totals(student_id, month_year=None):
    """Return ``(charged, paid)`` derived purely from the ledger."""
    query = FeeTransaction.query.filter_by(student_id=student_id, is_void=False)
    if month_year:
        query = query.filter_by(month_year=month_year)
    charged = paid = 0.0
    for txn in query.all():
        if txn.txn_type == TXN_PAYMENT:
            paid += txn.amount or 0.0
        else:  # charge + adjustment
            charged += txn.amount or 0.0
    return _round(charged), _round(paid)


def _status_for(charged, paid):
    if charged <= 0 and paid <= 0:
        return 'Pending'
    if paid + 0.001 >= charged and charged > 0:
        return 'Paid'
    if paid > 0:
        return 'Partial'
    return 'Pending'


def recompute_fee_record(student_id, month_year, remarks=None):
    """Rebuild the cached summary row from the ledger."""
    charged, paid = ledger_totals(student_id, month_year)

    record = FeeRecordModel.query.filter_by(student_id=student_id, month_year=month_year).first()
    if record is None:
        record = FeeRecordModel(student_id=student_id, month_year=month_year)
        db.session.add(record)

    record.amount_due = charged
    record.amount_paid = paid
    record.status = _status_for(charged, paid)

    last_payment = (FeeTransaction.query
                    .filter_by(student_id=student_id, month_year=month_year,
                               txn_type=TXN_PAYMENT, is_void=False)
                    .order_by(FeeTransaction.created_at.desc(), FeeTransaction.id.desc())
                    .first())
    record.payment_date = last_payment.created_at.date() if last_payment else None
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
        charged, paid = ledger_totals(student_id, month)
        rows.append({
            'month_year': month,
            'charged': charged,
            'paid': paid,
            'balance': _round(charged - paid),
            'transactions': transactions_for(student_id, month),
        })
    return rows


def _month_sort_key(month_year):
    try:
        return datetime.strptime(month_year, '%B %Y')
    except (TypeError, ValueError):
        return datetime(1900, 1, 1)


def reconcile(month_year=None):
    """Compare the derived summary cache against the ledger.

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
        charged, paid = ledger_totals(student_id, month)
        stored = FeeRecordModel.query.filter_by(student_id=student_id, month_year=month).first()

        row = {
            'student': student,
            'month_year': month,
            'charged': charged,
            'paid': paid,
            'balance': _round(charged - paid),
            'stored_due': _round(stored.amount_due) if stored else None,
            'stored_paid': _round(stored.amount_paid) if stored else None,
            'stored_status': stored.status if stored else None,
            'balanced': bool(stored
                             and _round(stored.amount_due) == charged
                             and _round(stored.amount_paid) == paid),
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

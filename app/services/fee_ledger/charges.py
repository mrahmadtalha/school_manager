"""Monthly fee charges: the amount a student is charged and creating or changing it."""

from app.database import db
from app.models import FeeTransaction, TXN_CHARGE
from app.services.audit import current_actor

from .common import _round


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

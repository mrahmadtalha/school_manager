"""Small shared pieces of the fee ledger: the current month, rounding, month sorting and payment references."""

from datetime import datetime

from flask import current_app
from sqlalchemy import func

from app.database import db
from app.models import FeeTransaction


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


def _round(value):
    return round(float(value or 0.0), 2)


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


def _month_sort_key(month_year):
    try:
        return datetime.strptime(month_year, '%B %Y')
    except (TypeError, ValueError):
        return datetime(1900, 1, 1)

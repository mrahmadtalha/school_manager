"""Other Income service (Phase 3a)."""
from datetime import datetime

from app.database import db
from app.models import OtherIncome, OtherIncomeCategory
from app.models.fees import to_paisa


def seed_default_categories():
    """Create the default categories once; returns how many were added."""
    created = 0
    from app.models.other_income import DEFAULT_OTHER_INCOME_CATEGORIES
    for name in DEFAULT_OTHER_INCOME_CATEGORIES:
        if not OtherIncomeCategory.query.filter_by(name=name).first():
            db.session.add(OtherIncomeCategory(name=name))
            created += 1
    if created:
        db.session.commit()
    return created


def active_categories():
    return (OtherIncomeCategory.query.filter_by(is_active=True)
            .order_by(OtherIncomeCategory.name).all())


# Categories whose money is recorded on another page.  Typing it here as well
# would count it twice (or leave a receipt that belongs to no student).
MANAGED_ADMISSION = 'admission fee'
MANAGED_ID_CARDS = 'id cards'
MANAGED_CERTIFICATES = 'certificates'
MANAGED_CANTEEN = 'canteen'


def managed_elsewhere(category):
    """``None`` when the category may be typed on the Other Income page, else
    ``(message, endpoint, anchor)`` telling the user where it is recorded."""
    name = ((getattr(category, 'name', None) or '').strip()).lower()
    if name == MANAGED_ADMISSION:
        return ('Admission money is received from the student\'s own Admission '
                'Fees page (so the student\'s balance goes down and a receipt is printed).',
                'main.admission_register', '')
    if name in (MANAGED_ID_CARDS, MANAGED_CERTIFICATES):
        from app.models.issued_document import DOC_CERTIFICATE, DOC_ID_CARD
        from app.services import document_fees
        if name == MANAGED_ID_CARDS:
            gated = document_fees.is_gated(DOC_ID_CARD)
        else:
            gated = (document_fees.is_gated(DOC_CERTIFICATE)
                     or any(document_fees.is_gated(DOC_CERTIFICATE, ct)
                            for ct in document_fees.CERT_TYPES))
        if gated:
            return ('A fee is set for this on the Documents page, so the money is '
                    'recorded there when the card / certificate is issued.',
                    'main.documents_hub', '')
    return None


def manual_categories():
    """Active categories that may be typed on the Other Income page."""
    from app.services import canteen_service
    result = []
    for category in active_categories():
        if managed_elsewhere(category) is not None:
            continue
        if (canteen_service.is_canteen_income_category(category)
                and not canteen_service.is_open_for_other_income()):
            continue
        result.append(category)
    return result


def record_income(category, amount_rupees, income_date, description=None,
                  actor=None):
    """Append an other-income row (paisa, never float)."""
    amount = to_paisa(amount_rupees)
    if amount <= 0:
        raise ValueError('Amount must be greater than zero.')
    if category is None:
        raise ValueError('Please choose a category.')
    user_id = getattr(actor, 'id', None)
    username = getattr(actor, 'username', None) or 'system'
    row = OtherIncome(
        category_id=category.id, amount_paisa=amount,
        income_date=income_date,
        description=(description or None) and str(description)[:200],
        created_by_id=user_id, created_by_name=username)
    db.session.add(row)
    return row


def void_income(row, reason, actor=None):
    """Void a row with a mandatory reason; it leaves every total."""
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void an income record.')
    if row.is_void:
        raise ValueError('This record is already voided.')
    row.is_void = True
    row.void_reason = reason[:255]
    row.voided_at = datetime.utcnow()
    row.voided_by_name = getattr(actor, 'username', None) or 'system'
    return row


def month_total(start, end):
    """Active other income (rupees) received in the inclusive date range."""
    total = (db.session.query(
                 db.func.coalesce(db.func.sum(OtherIncome.amount_paisa), 0))
             .filter(OtherIncome.is_void.is_(False),
                     OtherIncome.income_date >= start,
                     OtherIncome.income_date <= end).scalar()) or 0
    return round(total / 100.0, 2)

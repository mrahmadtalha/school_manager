"""Admission fee receipts: numbering, receiving a payment and voiding one."""

from datetime import date

from sqlalchemy import Integer, cast, func

from app.database import db
from app.models import OtherIncome, OtherIncomeCategory
from app.models.fees import to_paisa
from app.services import other_income_service
from app.services.audit import log_action

from .balances import received_paisa
from .common import CATEGORY_NAME, PAYMENT_METHODS, RECEIPT_PREFIX, money
from .terms import extras_paisa, has_terms, total_net_paisa


def get_category():
    category = OtherIncomeCategory.query.filter(
        func.lower(OtherIncomeCategory.name) == CATEGORY_NAME.lower()).first()
    if category is None:
        category = OtherIncomeCategory(name=CATEGORY_NAME)
        db.session.add(category)
        db.session.flush()
    elif not category.is_active:
        category.is_active = True
    return category


def next_receipt_no():
    start = len(RECEIPT_PREFIX) + 1
    top = (db.session.query(func.max(
        cast(func.substr(OtherIncome.receipt_no, start), Integer)))
        .filter(OtherIncome.receipt_no.like(RECEIPT_PREFIX + '%')).scalar()) or 0
    return '%s%04d' % (RECEIPT_PREFIX, top + 1)


def receive_payment(student, amount_rupees, pay_date=None, method='cash',
                    actor=None, note=None):
    """Record money received against the agreed admission fee.  Does not commit."""
    if not has_terms(student):
        raise ValueError('No admission fee is set for this student.')
    amount = to_paisa(amount_rupees)
    if amount <= 0:
        raise ValueError('The amount must be greater than zero.')
    pay_date = pay_date or date.today()
    if pay_date > date.today():
        raise ValueError('The payment date cannot be in the future.')
    balance = max(0, total_net_paisa(student) - received_paisa(student.id))
    if balance == 0:
        raise ValueError('The admission fee is already fully received.')
    if amount > balance:
        raise ValueError('The amount is more than the balance (%s).' % money(balance))
    method = (method or 'cash').strip().lower()
    if method not in PAYMENT_METHODS:
        method = 'cash'

    category = get_category()
    label = 'Admission fee' if not extras_paisa(student) else 'Admission fee / books / uniform'
    description = '%s - %s (Roll %s)' % (label, student.student_name,
                                         student.roll_number)
    if (note or '').strip():
        description = '%s - %s' % (description, note.strip())
    row = OtherIncome(
        category_id=category.id, income_date=pay_date, amount_paisa=amount,
        description=description[:200], student_id=student.id,
        receipt_no=next_receipt_no(), payment_method=method,
        created_by_id=getattr(actor, 'id', None),
        created_by_name=getattr(actor, 'username', None) or 'system')
    db.session.add(row)
    db.session.flush()
    log_action('payment', entity_type='AdmissionFee', entity_id=student.id,
               summary='Admission fee %s received from %s (%s)' % (
                   money(amount), student.student_name, row.receipt_no))
    return row


def void_payment(row, reason, actor=None):
    """Void an admission payment (reason mandatory); the balance re-opens."""
    if row.student_id is None:
        raise ValueError('This is not an admission fee payment.')
    other_income_service.void_income(row, reason, actor=actor)
    log_action('void', entity_type='AdmissionFee', entity_id=row.student_id,
               summary='Admission fee receipt %s voided: %s' % (
                   row.receipt_no, reason.strip()[:120]))
    return row

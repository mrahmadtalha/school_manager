"""Fees and receipts for ID cards and certificates (Phase 5).

* The fee amounts are School settings kept in the system-settings store (no
  schema change): one fee for the student ID card, one fee for certificates
  (with an optional own fee per certificate type) and, for each, an optional
  *duplicate* fee (blank = the same as the first fee).
* The feature is opt-in: while every fee is 0 nothing changes - a single
  student's card or certificate downloads straight away and no record is kept.
* Once a fee is set, a single student's card / certificate is *issued*: one
  ``IssuedDocument`` row plus, when money is taken, one Other Income receipt
  (``DOC-0001``).  Printing the same document again for the same student is a
  duplicate: the administrator chooses free or the duplicate fee.
* The receipt is NOT linked to the student's admission account
  (``OtherIncome.student_id`` stays empty), so it can never change an
  admission-fee balance.
"""
from datetime import date

from sqlalchemy import Integer, cast, func

from app.database import db
from app.models import (IssuedDocument, OtherIncome, OtherIncomeCategory,
                        StudentModel)
from app.models.fees import to_paisa, to_rupees
from app.models.issued_document import DOC_CERTIFICATE, DOC_ID_CARD
from app.models.settings import get_system_value, set_system_value
from app.services import other_income_service
from app.services.audit import log_action

RECEIPT_PREFIX = 'DOC-'
PAYMENT_METHODS = ('cash', 'bank', 'online', 'other')
CATEGORY_BY_KIND = {DOC_ID_CARD: 'ID Cards', DOC_CERTIFICATE: 'Certificates'}
CERT_TYPES = ('bonafide', 'character', 'leaving', 'merit')
KIND_LABELS = {DOC_ID_CARD: 'Student ID card', DOC_CERTIFICATE: 'Certificate'}

KEY_ID_CARD = 'docfee_id_card'
KEY_ID_CARD_DUP = 'docfee_id_card_dup'
KEY_CERT = 'docfee_cert'
KEY_CERT_DUP = 'docfee_cert_dup'


def _cert_key(cert_type):
    return 'docfee_cert_' + cert_type


def money(paisa):
    return 'Rs. {:,.0f}'.format(to_rupees(paisa)) if (paisa or 0) % 100 == 0 \
        else 'Rs. {:,.2f}'.format(to_rupees(paisa))


def cert_label(cert_type):
    from app.routes.documents import CERTIFICATE_TYPES
    return CERTIFICATE_TYPES.get(cert_type, 'Certificate')


def title_for(kind, cert_type=None):
    if kind == DOC_ID_CARD:
        return 'Student ID card'
    return '%s certificate' % cert_label(cert_type)


# --------------------------------------------------------------------------- #
# Fee settings
# --------------------------------------------------------------------------- #

def _read(key):
    """Stored paisa, or ``None`` when blank / never set."""
    raw = (get_system_value(key, '') or '').strip()
    if raw == '':
        return None
    try:
        return max(0, to_paisa(float(raw)))
    except ValueError:
        return None


def fee_settings():
    """Everything the fee box needs, as rupees (``None`` = blank)."""
    def rupees(key):
        value = _read(key)
        return None if value is None else to_rupees(value)
    return {
        'id_card': rupees(KEY_ID_CARD),
        'id_card_dup': rupees(KEY_ID_CARD_DUP),
        'cert': rupees(KEY_CERT),
        'cert_dup': rupees(KEY_CERT_DUP),
        'by_type': {ct: rupees(_cert_key(ct)) for ct in CERT_TYPES},
    }


def _parse_amount(raw, label):
    text = (raw or '').strip().replace(',', '')
    if text == '':
        return ''
    try:
        amount = float(text)
    except ValueError:
        raise ValueError('%s must be a number.' % label)
    if amount < 0:
        raise ValueError('%s cannot be negative.' % label)
    if amount > 1000000:
        raise ValueError('%s is too large.' % label)
    return '%g' % round(amount, 2)


def save_fee_settings(form):
    """Validate everything first, then store; raises ValueError (nothing saved)."""
    values = {
        KEY_ID_CARD: _parse_amount(form.get('id_card'), 'The ID card fee'),
        KEY_ID_CARD_DUP: _parse_amount(form.get('id_card_dup'),
                                       'The ID card duplicate fee'),
        KEY_CERT: _parse_amount(form.get('cert'), 'The certificate fee'),
        KEY_CERT_DUP: _parse_amount(form.get('cert_dup'),
                                    'The certificate duplicate fee'),
    }
    for cert_type in CERT_TYPES:
        values[_cert_key(cert_type)] = _parse_amount(
            form.get('cert_' + cert_type), 'The %s fee' % cert_label(cert_type))
    for key, value in values.items():
        set_system_value(key, value)
    return values


def first_fee_paisa(kind, cert_type=None):
    if kind == DOC_ID_CARD:
        return _read(KEY_ID_CARD) or 0
    own = _read(_cert_key(cert_type)) if cert_type else None
    if own is not None:
        return own
    return _read(KEY_CERT) or 0


def duplicate_fee_paisa(kind, cert_type=None):
    """Duplicate fee; blank means the same as the first fee."""
    own = _read(KEY_ID_CARD_DUP if kind == DOC_ID_CARD else KEY_CERT_DUP)
    return first_fee_paisa(kind, cert_type) if own is None else own


def is_gated(kind, cert_type=None):
    """True once a fee applies to this document (first issue or duplicate)."""
    return bool(first_fee_paisa(kind, cert_type)
                or duplicate_fee_paisa(kind, cert_type))


# --------------------------------------------------------------------------- #
# Issued documents
# --------------------------------------------------------------------------- #

def previous_issues(student_id, kind, cert_type=None):
    """Earlier issues of the same document that still count (oldest first)."""
    query = IssuedDocument.query.filter_by(student_id=student_id, doc_kind=kind)
    if kind == DOC_CERTIFICATE:
        query = query.filter_by(cert_type=cert_type)
    return [row for row in query.order_by(IssuedDocument.id).all()
            if row.is_effective]


def next_receipt_no():
    start = len(RECEIPT_PREFIX) + 1
    top = (db.session.query(func.max(
        cast(func.substr(OtherIncome.receipt_no, start), Integer)))
        .filter(OtherIncome.receipt_no.like(RECEIPT_PREFIX + '%')).scalar()) or 0
    return '%s%04d' % (RECEIPT_PREFIX, top + 1)


def _category(kind):
    name = CATEGORY_BY_KIND[kind]
    category = OtherIncomeCategory.query.filter(
        func.lower(OtherIncomeCategory.name) == name.lower()).first()
    if category is None:
        category = OtherIncomeCategory(name=name)
        db.session.add(category)
        db.session.flush()
    elif not category.is_active:
        category.is_active = True
    return category


def plan(student, kind, cert_type=None):
    """What an issue would do now: ``{previous, is_duplicate, first, dup}``."""
    earlier = previous_issues(student.id, kind, cert_type)
    return {
        'previous': earlier,
        'is_duplicate': bool(earlier),
        'first_fee': first_fee_paisa(kind, cert_type),
        'dup_fee': duplicate_fee_paisa(kind, cert_type),
    }


def issue(student, kind, cert_type=None, session=None, issue_date=None,
          remarks=None, method='cash', duplicate_free=False, actor=None):
    """Record one issue (and its receipt when money is taken).  Does not commit.

    ``duplicate_free`` only matters when this is a duplicate: the
    administrator chose not to charge for it.
    """
    if kind not in (DOC_ID_CARD, DOC_CERTIFICATE):
        raise ValueError('Unknown document type.')
    if kind == DOC_CERTIFICATE and cert_type not in CERT_TYPES:
        raise ValueError('Please choose a certificate type.')
    if kind == DOC_ID_CARD:
        cert_type = None
    info = plan(student, kind, cert_type)
    if info['is_duplicate']:
        fee = 0 if duplicate_free else info['dup_fee']
    else:
        fee = info['first_fee']
    method = (method or 'cash').strip().lower()
    if method not in PAYMENT_METHODS:
        method = 'cash'
    issue_date = issue_date or date.today()
    user_id = getattr(actor, 'id', None)
    username = getattr(actor, 'username', None) or 'system'

    title = title_for(kind, cert_type)
    income = None
    if fee > 0:
        description = '%s%s - %s (Roll %s)' % (
            title, ' (duplicate)' if info['is_duplicate'] else '',
            student.student_name, student.roll_number)
        income = OtherIncome(
            category_id=_category(kind).id, income_date=date.today(),
            amount_paisa=fee, description=description[:200],
            receipt_no=next_receipt_no(), payment_method=method,
            created_by_id=user_id, created_by_name=username)
        db.session.add(income)
        db.session.flush()
    row = IssuedDocument(
        doc_kind=kind, cert_type=cert_type, student_id=student.id,
        session=(session or '')[:50] or None, issue_date=issue_date,
        remarks=(remarks or '')[:200] or None,
        is_duplicate=info['is_duplicate'], fee_paisa=fee,
        income_id=income.id if income is not None else None,
        created_by_id=user_id, created_by_name=username)
    db.session.add(row)
    db.session.flush()
    log_action('create', entity_type='IssuedDocument', entity_id=row.id,
               summary='%s issued to %s%s - %s' % (
                   title, student.student_name,
                   ' (duplicate)' if row.is_duplicate else '',
                   ('fee %s, receipt %s' % (money(fee), income.receipt_no))
                   if income is not None else 'no fee'))
    return row


def void_issue(row, reason, actor=None):
    """Void an issue (reason mandatory); the fee receipt, if any, is voided too."""
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void this.')
    if row.is_void:
        raise ValueError('This issue is already voided.')
    if row.income is not None and not row.income.is_void:
        other_income_service.void_income(row.income, reason, actor=actor)
    row.is_void = True
    row.void_reason = reason[:255]
    from datetime import datetime
    row.voided_at = datetime.utcnow()
    row.voided_by_name = getattr(actor, 'username', None) or 'system'
    log_action('void', entity_type='IssuedDocument', entity_id=row.id,
               summary='%s voided: %s' % (title_for(row.doc_kind, row.cert_type),
                                         reason[:120]))
    return row


def recent_issues(limit=15):
    return (IssuedDocument.query
            .order_by(IssuedDocument.id.desc()).limit(limit).all())


def build_pdf(row, app_root):
    """The PDF for an issued record, rebuilt exactly as it was issued."""
    from app.services import id_documents
    school = id_documents.school_branding(app_root)
    session = row.session or id_documents.default_academic_session()
    student = row.student
    if row.doc_kind == DOC_ID_CARD:
        return id_documents.build_id_cards_pdf(
            [id_documents.student_card_payload(student)], school, session)
    return id_documents.build_certificates_pdf(
        [student], school, row.cert_type, session, row.issue_date,
        row.remarks or '')


def pdf_name(row):
    student = row.student
    if row.doc_kind == DOC_ID_CARD:
        return 'id_card_%s.pdf' % student.roll_number
    return '%s_%s.pdf' % (row.cert_type, student.roll_number)

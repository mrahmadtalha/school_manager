"""One-time admission fee.

How the money is kept
---------------------
* The **terms** live on the student: standard fee, optional concession and the
  agreed (net) amount, all in integer paisa.  ``admission_fee_net_paisa`` is
  NULL for every student who has no admission fee on record, which includes
  every student that existed before this feature, so nobody becomes "pending"
  and no old number changes.
* The **money received** is stored as ``OtherIncome`` rows in the "Admission
  Fee" category, linked to the student (``student_id``) and numbered
  (``receipt_no``).  Because Other Income already feeds the financial
  overview, the dashboard account book and the comparisons, admission income
  shows up there without touching any of those formulas.  A student can have
  several payments (instalments); voiding a payment re-opens the balance.
* The monthly fee ledger is NOT used: it assumes exactly one monthly charge per
  student per month, so an admission charge would break it.

The feature is opt-in: nothing admission-related is shown until the school sets
a universal or a per-class admission fee.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Integer, cast, func, or_

from app.database import db
from app.models import (ClassModel, OtherIncome, OtherIncomeCategory,
                        ROLE_ADMIN, SchoolSettings, StudentModel)
from app.models.fees import to_paisa, to_rupees
from app.services import other_income_service
from app.services.audit import log_action

CATEGORY_NAME = 'Admission Fee'
RECEIPT_PREFIX = 'ADM-'
DISCOUNT_TYPES = ('percentage', 'fixed', 'waived')
PAYMENT_METHODS = ('cash', 'bank', 'online', 'other')
STATUSES = ('pending', 'partial', 'paid', 'waived')
STATUS_LABELS = {
    'not_applicable': 'Not applicable',
    'pending': 'Pending',
    'partial': 'Partial',
    'paid': 'Paid',
    'waived': 'Waived',
}


def is_admin(user):
    """Same rule as app/security.py: a missing role means administrator."""
    return (getattr(user, 'role', None) or ROLE_ADMIN) == ROLE_ADMIN


def money(paisa):
    return 'Rs. {:,.0f}'.format(to_rupees(paisa)) if (paisa or 0) % 100 == 0 \
        else 'Rs. {:,.2f}'.format(to_rupees(paisa))


# --------------------------------------------------------------------------- #
# School-wide and per-class settings
# --------------------------------------------------------------------------- #

def _settings_row(create=False):
    row = SchoolSettings.query.first()
    if row is None and create:
        row = SchoolSettings(school_name='School Manager')
        db.session.add(row)
        db.session.flush()
    return row


def default_paisa():
    row = _settings_row()
    return to_paisa(row.default_admission_fee) if row and \
        row.default_admission_fee is not None else 0


def class_override_paisa(class_obj):
    """``None`` when the class follows the school default."""
    if class_obj is None or class_obj.admission_fee is None:
        return None
    return to_paisa(class_obj.admission_fee)


def effective_paisa(class_id):
    """Admission fee for a class: its own value, else the school default."""
    class_obj = db.session.get(ClassModel, class_id) if class_id else None
    override = class_override_paisa(class_obj)
    return default_paisa() if override is None else override


def is_enabled():
    """Opt-in switch: true once any admission fee amount has been set."""
    if default_paisa() > 0:
        return True
    return db.session.query(ClassModel.id).filter(
        ClassModel.admission_fee.isnot(None), ClassModel.admission_fee > 0
    ).first() is not None


def fee_by_class():
    """``{class_id(str): rupees}`` for the student form's auto-fill."""
    default = default_paisa()
    result = {}
    for class_obj in ClassModel.query.all():
        override = class_override_paisa(class_obj)
        result[str(class_obj.id)] = to_rupees(default if override is None else override)
    return result


def settings_context():
    """Everything the Fees page settings dialog needs."""
    default = default_paisa()
    rows = []
    for class_obj in ClassModel.query.order_by(ClassModel.id).all():
        override = class_override_paisa(class_obj)
        rows.append({
            'id': class_obj.id,
            'name': class_obj.name,
            'override': None if override is None else to_rupees(override),
            'effective': to_rupees(default if override is None else override),
        })
    return {'default': to_rupees(default) if default else None,
            'classes': rows, 'enabled': is_enabled()}


def _parse_optional_amount(value, label):
    """'' -> None (inherit), otherwise a non-negative rupee amount."""
    text = (value or '').strip().replace(',', '')
    if text == '':
        return None
    try:
        amount = float(text)
    except ValueError:
        raise ValueError('%s must be a number.' % label)
    if amount < 0:
        raise ValueError('%s cannot be negative.' % label)
    return round(amount, 2)


def save_settings(default_value, class_values):
    """Store the universal fee and each class's own fee (blank = follow default).

    Existing students are never touched: a changed fee only applies to
    students admitted afterwards.
    """
    default_amount = _parse_optional_amount(default_value, 'The school admission fee')
    parsed = {}
    for class_id, raw in class_values.items():
        parsed[class_id] = _parse_optional_amount(raw, 'The class admission fee')
    row = _settings_row(create=True)
    row.default_admission_fee = default_amount
    for class_obj in ClassModel.query.all():
        if class_obj.id in parsed:
            class_obj.admission_fee = parsed[class_obj.id]
    return default_amount, parsed


# --------------------------------------------------------------------------- #
# Concession maths
# --------------------------------------------------------------------------- #

def compute_net(standard_paisa, discount_type, discount_value):
    """-> ``(net_paisa, concession_paisa)``; raises ValueError on bad input."""
    standard = int(standard_paisa or 0)
    kind = (discount_type or '').strip().lower() or None
    if kind in (None, 'none'):
        return standard, 0
    if kind not in DISCOUNT_TYPES:
        raise ValueError('Unknown concession type.')
    if kind == 'waived':
        return 0, standard
    try:
        value = float(discount_value or 0)
    except (TypeError, ValueError):
        raise ValueError('Please enter a valid concession value.')
    if value <= 0:
        return standard, 0
    if kind == 'percentage':
        if value > 100:
            raise ValueError('The concession percentage must be between 0 and 100.')
        concession = int((Decimal(standard) * Decimal(str(value)) / 100)
                         .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    else:
        concession = to_paisa(value)
        if concession > standard:
            raise ValueError('The concession cannot be more than the admission fee.')
    return standard - concession, concession


# --------------------------------------------------------------------------- #
# Per-student terms and status
# --------------------------------------------------------------------------- #

def has_terms(student):
    return student.admission_fee_net_paisa is not None


def concession_paisa(student):
    if not has_terms(student):
        return 0
    return max(0, (student.admission_fee_standard_paisa or 0)
               - (student.admission_fee_net_paisa or 0))


def active_payments(student_id):
    return (OtherIncome.query.filter(OtherIncome.student_id == student_id,
                                     OtherIncome.is_void.is_(False))
            .order_by(OtherIncome.income_date, OtherIncome.id).all())


def all_payments(student_id):
    return (OtherIncome.query.filter(OtherIncome.student_id == student_id)
            .order_by(OtherIncome.income_date.desc(), OtherIncome.id.desc()).all())


def prior_paid_paisa(student_id):
    """Money received before this software (imported); never counted as income."""
    return (db.session.query(StudentModel.admission_fee_prior_paid_paisa)
            .filter(StudentModel.id == student_id).scalar()) or 0


def income_received_paisa(student_id):
    """Receipts recorded here (these ARE income)."""
    return (db.session.query(func.coalesce(func.sum(OtherIncome.amount_paisa), 0))
            .filter(OtherIncome.student_id == student_id,
                    OtherIncome.is_void.is_(False)).scalar()) or 0


def received_paisa(student_id):
    """Everything received so far: receipts plus imported opening payments."""
    return income_received_paisa(student_id) + prior_paid_paisa(student_id)


def status_for(student, received=None):
    if not has_terms(student):
        return 'not_applicable'
    net = student.admission_fee_net_paisa
    if net == 0 and ((student.admission_fee_standard_paisa or 0) > 0
                     or student.admission_discount_type == 'waived'):
        return 'waived'
    if received is None:
        received = received_paisa(student.id)
    if received >= net:
        return 'paid'
    return 'partial' if received > 0 else 'pending'


def summary(student):
    """Plain numbers for the detail page and the receipt."""
    received = received_paisa(student.id)
    net = student.admission_fee_net_paisa or 0
    return {
        'applicable': has_terms(student),
        'standard': student.admission_fee_standard_paisa or 0,
        'concession': concession_paisa(student),
        'net': net,
        'received': received,
        'prior_paid': student.admission_fee_prior_paid_paisa or 0,
        'balance': max(0, net - received),
        'status': status_for(student, received),
        'discount_type': student.admission_discount_type,
        'discount_value': student.admission_discount_value,
        'note': student.admission_note,
        'date': student.admission_fee_date,
    }


def apply_terms(student, standard_rupees, discount_type=None, discount_value=None,
                note=None, fee_date=None):
    """Record (or replace) a student's admission terms.  Does not commit.

    ``standard_rupees`` of 0 clears the terms (no admission fee).
    """
    standard = to_paisa(standard_rupees)
    if standard < 0:
        raise ValueError('The admission fee cannot be negative.')
    if standard == 0:
        student.admission_fee_standard_paisa = None
        student.admission_fee_net_paisa = None
        student.admission_discount_type = None
        student.admission_discount_value = None
        student.admission_note = None
        student.admission_fee_date = None
        student.admission_fee_prior_paid_paisa = None
        return None
    net, concession = compute_net(standard, discount_type, discount_value)
    kind = (discount_type or '').strip().lower() or None
    student.admission_fee_standard_paisa = standard
    student.admission_fee_net_paisa = net
    if kind in (None, 'none') or concession == 0 and kind != 'waived':
        student.admission_discount_type = None
        student.admission_discount_value = None
    else:
        student.admission_discount_type = kind
        student.admission_discount_value = (
            None if kind == 'waived' else float(discount_value))
    student.admission_note = ((note or '').strip()[:200]) or None
    student.admission_fee_date = fee_date or student.admission_fee_date or date.today()
    return net


def adjust_terms(student, standard_rupees, discount_type=None, discount_value=None,
                 note=None):
    """Admin change of an existing student's terms (also first-time setup for
    students admitted before the feature).  Never goes below what was received.
    """
    received = received_paisa(student.id)
    standard = to_paisa(standard_rupees)
    if standard == 0:
        if received > 0:
            raise ValueError(
                '%s is already received, so the admission fee cannot be removed. '
                'Void the payment first.' % money(received))
        net = 0
    else:
        net, _ = compute_net(standard, discount_type, discount_value)
        if net < received:
            raise ValueError(
                '%s is already received, so the agreed fee cannot be lower than '
                'that. Void a payment first if it was taken by mistake.' % money(received))
    before = _terms_text(student)
    apply_terms(student, standard_rupees, discount_type, discount_value, note)
    after = _terms_text(student)
    log_action('update', entity_type='AdmissionFee', entity_id=student.id,
               summary='Admission fee terms changed for %s' % student.student_name,
               before=before, after=after)
    return summary(student)


def _terms_text(student):
    if not has_terms(student):
        return {'admission_fee': 'none'}
    return {
        'standard': to_rupees(student.admission_fee_standard_paisa),
        'concession_type': student.admission_discount_type,
        'concession_value': student.admission_discount_value,
        'net': to_rupees(student.admission_fee_net_paisa),
        'note': student.admission_note,
    }


# --------------------------------------------------------------------------- #
# Receiving money
# --------------------------------------------------------------------------- #

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
    balance = max(0, student.admission_fee_net_paisa - received_paisa(student.id))
    if balance == 0:
        raise ValueError('The admission fee is already fully received.')
    if amount > balance:
        raise ValueError('The amount is more than the balance (%s).' % money(balance))
    method = (method or 'cash').strip().lower()
    if method not in PAYMENT_METHODS:
        method = 'cash'

    category = get_category()
    description = 'Admission fee - %s (Roll %s)' % (student.student_name,
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


# --------------------------------------------------------------------------- #
# Form hook used by "Add student"
# --------------------------------------------------------------------------- #

def _form_amount(raw, default_rupees, label):
    text = (raw or '').strip().replace(',', '')
    if text == '':
        return default_rupees
    try:
        value = float(text)
    except ValueError:
        raise ValueError('Please enter a valid %s.' % label)
    if value < 0:
        raise ValueError('The %s cannot be negative.' % label)
    return value


def apply_on_admission(student, form, actor, can_manage):
    """Create the admission terms for a brand-new student.  Does not commit.

    * Nothing happens until the school has set an admission fee.
    * Administrators may edit the amount, give a concession and take the
      money at once.  For everyone else (a teacher adding a student) the
      standard fee is recorded as **pending** and no money is taken.

    Returns ``None`` or ``{'student', 'receipt'(row or None)}``.
    """
    if not is_enabled():
        return None
    default_rupees = to_rupees(effective_paisa(student.class_id))
    if can_manage:
        standard = _form_amount(form.get('admission_fee'), default_rupees,
                                'admission fee')
        discount_type = form.get('admission_discount_type')
        discount_value = form.get('admission_discount_value')
        note = form.get('admission_note')
    else:
        standard, discount_type, discount_value, note = default_rupees, None, None, None
    if to_paisa(standard) == 0:
        return None

    db.session.flush()
    net = apply_terms(student, standard, discount_type, discount_value, note,
                      fee_date=student.admission_date or date.today())
    receipt = None
    if can_manage and (form.get('admission_received_now') or '') == '1' and net:
        amount = _form_amount(form.get('admission_received_amount'),
                              to_rupees(net), 'amount received')
        if to_paisa(amount) > 0:
            receipt = receive_payment(student, amount, date.today(),
                                      form.get('admission_method') or 'cash',
                                      actor=actor)
    log_action('create', entity_type='AdmissionFee', entity_id=student.id,
               summary='Admission fee %s set for %s (%s)' % (
                   money(net), student.student_name,
                   STATUS_LABELS[status_for(student)]))
    return {'student': student, 'receipt': receipt}


# --------------------------------------------------------------------------- #
# Register
# --------------------------------------------------------------------------- #

def register(class_id=None, status=None, search=None, date_from=None, date_to=None):
    """Rows for the Admission Fees register plus totals.

    Only students that have admission terms are listed.  Totals count the
    listed rows, voided payments excluded.
    """
    query = StudentModel.query.filter(StudentModel.admission_fee_net_paisa.isnot(None))
    if class_id:
        query = query.filter(StudentModel.class_id == class_id)
    if search:
        like = '%' + search.strip() + '%'
        query = query.filter(or_(StudentModel.student_name.ilike(like),
                                    StudentModel.father_name.ilike(like),
                                    StudentModel.admission_number.ilike(like)))
    if date_from:
        query = query.filter(StudentModel.admission_fee_date >= date_from)
    if date_to:
        query = query.filter(StudentModel.admission_fee_date <= date_to)
    students = query.order_by(StudentModel.admission_fee_date.desc(),
                              StudentModel.id.desc()).all()

    ids = [s.id for s in students]
    received_map = {}
    if ids:
        for student_id, total in (db.session.query(
                OtherIncome.student_id, func.sum(OtherIncome.amount_paisa))
                .filter(OtherIncome.student_id.in_(ids),
                        OtherIncome.is_void.is_(False))
                .group_by(OtherIncome.student_id).all()):
            received_map[student_id] = total or 0

    rows = []
    for student in students:
        prior = student.admission_fee_prior_paid_paisa or 0
        received = received_map.get(student.id, 0) + prior
        row_status = status_for(student, received)
        if status and row_status != status:
            continue
        net = student.admission_fee_net_paisa
        rows.append({
            'student': student,
            'standard': student.admission_fee_standard_paisa or 0,
            'concession': concession_paisa(student),
            'net': net,
            'received': received,
            'prior': prior,
            'balance': max(0, net - received),
            'status': row_status,
        })

    totals = {
        'count': len(rows),
        'standard': sum(r['standard'] for r in rows),
        'concession': sum(r['concession'] for r in rows),
        'net': sum(r['net'] for r in rows),
        'received': sum(r['received'] for r in rows),
        'prior': sum(r['prior'] for r in rows),
        'balance': sum(r['balance'] for r in rows),
        'by_status': {key: sum(1 for r in rows if r['status'] == key)
                      for key in STATUSES},
    }
    return rows, totals


# --------------------------------------------------------------------------- #
# Bulk import hook, exports and financial lines
# --------------------------------------------------------------------------- #

def apply_on_import(student, standard_rupees, discount_type, discount_value,
                    paid_rupees, record_as_income, income_date, actor):
    """Admission terms for a student created by the Excel/CSV import.

    ``paid_rupees`` is money the family already paid.  By default it is kept
    as an opening amount that is NOT income (so no past month changes); with
    ``record_as_income`` it becomes a normal numbered receipt dated
    ``income_date``.  Does not commit.
    """
    standard = to_paisa(standard_rupees)
    if standard <= 0:
        return None
    db.session.flush()
    net = apply_terms(student, standard_rupees, discount_type, discount_value, None,
                      fee_date=student.admission_date or date.today())
    paid = to_paisa(paid_rupees)
    receipt = None
    if paid > 0:
        if paid > net:
            raise ValueError('Admission Fee Paid (%s) is more than the agreed fee (%s).'
                             % (money(paid), money(net)))
        if record_as_income:
            receipt = receive_payment(student, to_rupees(paid), income_date or date.today(),
                                      'cash', actor=actor, note='imported')
        else:
            student.admission_fee_prior_paid_paisa = paid
    log_action('create', entity_type='AdmissionFee', entity_id=student.id,
               summary='Admission fee %s imported for %s (%s)' % (
                   money(net), student.student_name, STATUS_LABELS[status_for(student)]))
    return {'student': student, 'receipt': receipt}


def student_map(student_ids):
    """``{student_id: {...}}`` for the student list/export columns.

    Students without terms are simply absent from the map.
    """
    ids = list(student_ids or [])
    if not ids:
        return {}
    students = (StudentModel.query.filter(StudentModel.id.in_(ids),
                                          StudentModel.admission_fee_net_paisa.isnot(None))
                .all())
    income = {}
    for student_id, total in (db.session.query(
            OtherIncome.student_id, func.sum(OtherIncome.amount_paisa))
            .filter(OtherIncome.student_id.in_([s.id for s in students]),
                    OtherIncome.is_void.is_(False))
            .group_by(OtherIncome.student_id).all()):
        income[student_id] = total or 0
    result = {}
    for student in students:
        received = income.get(student.id, 0) + (student.admission_fee_prior_paid_paisa or 0)
        net = student.admission_fee_net_paisa
        result[student.id] = {
            'net': to_rupees(net),
            'received': to_rupees(received),
            'balance': to_rupees(max(0, net - received)),
            'status': STATUS_LABELS[status_for(student, received)],
        }
    return result


def income_total(start, end):
    """Admission-fee income (rupees) received in the inclusive date range.

    This is a *part of* Other Income (already inside Cash In), shown on its own
    line; it is never added on top of any total.
    """
    total = (db.session.query(func.coalesce(func.sum(OtherIncome.amount_paisa), 0))
             .filter(OtherIncome.student_id.isnot(None),
                     OtherIncome.is_void.is_(False),
                     OtherIncome.income_date >= start,
                     OtherIncome.income_date <= end).scalar()) or 0
    return round(total / 100.0, 2)

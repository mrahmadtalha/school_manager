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
a universal or a per-class admission fee (or class books / uniform).

New-admission package
---------------------
Besides the admission fee a class can carry **books** and **uniform** (price
per set x number of sets).  They are set once per class in the settings, are
copied onto the student at admission (editable on the form) and are paid
together with the admission fee on ONE receipt.  The agreed total is
``admission net + books + uniform``; a partial payment is applied in that
order (admission, books, uniform) and the rest stays pending, exactly like the
admission fee on its own.  The concession applies to the admission fee only.
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
COMPONENT_LABELS = (('admission', 'Admission fee'), ('books', 'Books'),
                    ('uniform', 'Uniform'))
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
    return db.session.query(ClassModel.id).filter(or_(
        ClassModel.admission_fee > 0, ClassModel.books_fee > 0,
        ClassModel.uniform_fee > 0)).first() is not None


def fee_by_class():
    """``{class_id(str): rupees}`` for the student form's auto-fill."""
    default = default_paisa()
    result = {}
    for class_obj in ClassModel.query.all():
        override = class_override_paisa(class_obj)
        result[str(class_obj.id)] = to_rupees(default if override is None else override)
    return result


def class_items(class_obj):
    """``{'books', 'uniform', 'sets'}`` configured for a class (rupees / count)."""
    if class_obj is None:
        return {'books': 0.0, 'uniform': 0.0, 'sets': 1}
    return {'books': float(class_obj.books_fee or 0),
            'uniform': float(class_obj.uniform_fee or 0),
            'sets': int(class_obj.uniform_sets or 1)}


def items_by_class():
    """``{class_id(str): {admission, books, uniform, sets}}`` for the form's auto-fill."""
    default = default_paisa()
    result = {}
    for class_obj in ClassModel.query.all():
        override = class_override_paisa(class_obj)
        item = class_items(class_obj)
        item['admission'] = to_rupees(default if override is None else override)
        result[str(class_obj.id)] = item
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
            'books': class_obj.books_fee,
            'uniform': class_obj.uniform_fee,
            'sets': class_obj.uniform_sets,
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


def _parse_sets(value):
    """'' -> None (one set), otherwise a whole number of sets >= 1."""
    text = (value or '').strip()
    if text == '':
        return None
    try:
        sets = int(float(text))
    except ValueError:
        raise ValueError('The number of uniform sets must be a whole number.')
    if sets < 1 or sets > 20:
        raise ValueError('The number of uniform sets must be between 1 and 20.')
    return sets


def save_settings(default_value, class_values, class_items_values=None):
    """Store the universal fee and each class's own fee (blank = follow default).

    ``class_items_values`` is ``{class_id: {'books', 'uniform', 'sets'}}`` of raw
    form text; blank books / uniform means the class has none.

    Existing students are never touched: a changed fee only applies to
    students admitted afterwards.
    """
    default_amount = _parse_optional_amount(default_value, 'The school admission fee')
    parsed = {}
    for class_id, raw in class_values.items():
        parsed[class_id] = _parse_optional_amount(raw, 'The class admission fee')
    items = {}
    for class_id, raw in (class_items_values or {}).items():
        items[class_id] = {
            'books': _parse_optional_amount(raw.get('books'), 'The books fee'),
            'uniform': _parse_optional_amount(raw.get('uniform'), 'The uniform price'),
            'sets': _parse_sets(raw.get('sets')),
        }
    row = _settings_row(create=True)
    row.default_admission_fee = default_amount
    for class_obj in ClassModel.query.all():
        if class_obj.id in parsed:
            class_obj.admission_fee = parsed[class_obj.id]
        if class_obj.id in items:
            class_obj.books_fee = items[class_obj.id]['books']
            class_obj.uniform_fee = items[class_obj.id]['uniform']
            class_obj.uniform_sets = items[class_obj.id]['sets']
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

def books_paisa(student):
    return student.books_fee_paisa or 0


def uniform_paisa(student):
    return (student.uniform_qty or 0) * (student.uniform_unit_paisa or 0)


def extras_paisa(student):
    """Books + uniform agreed for this student."""
    return books_paisa(student) + uniform_paisa(student)


def has_terms(student):
    return (student.admission_fee_net_paisa is not None
            or student.books_fee_paisa is not None
            or student.uniform_qty is not None)


def total_net_paisa(student):
    """Everything agreed: admission (after concession) + books + uniform."""
    return (student.admission_fee_net_paisa or 0) + extras_paisa(student)


def components(student):
    """The parts of the agreed total, in the order a payment settles them.

    ``[{'key', 'label', 'qty', 'unit', 'due'}]`` (paisa); only parts that exist.
    """
    parts = []
    if student.admission_fee_net_paisa is not None and (
            student.admission_fee_net_paisa > 0
            or (student.admission_fee_standard_paisa or 0) > 0):
        net = student.admission_fee_net_paisa
        parts.append({'key': 'admission', 'label': 'Admission fee', 'qty': 1,
                      'unit': net, 'due': net})
    if books_paisa(student) > 0:
        parts.append({'key': 'books', 'label': 'Books', 'qty': 1,
                      'unit': books_paisa(student), 'due': books_paisa(student)})
    if uniform_paisa(student) > 0:
        parts.append({'key': 'uniform', 'label': 'Uniform',
                      'qty': student.uniform_qty, 'unit': student.uniform_unit_paisa,
                      'due': uniform_paisa(student)})
    return parts


def allocate(student, paid_paisa):
    """Split an amount received over the parts: admission, then books, then uniform.

    The split is always *derived* from the total received, never stored, so
    voiding a receipt simply re-opens the right part.
    """
    left = max(0, int(paid_paisa or 0))
    lines = []
    for part in components(student):
        take = min(left, part['due'])
        left -= take
        lines.append(dict(part, paid=take, balance=part['due'] - take))
    return lines


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
    net = total_net_paisa(student)
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
    total = total_net_paisa(student)
    return {
        'applicable': has_terms(student),
        'standard': student.admission_fee_standard_paisa or 0,
        'concession': concession_paisa(student),
        'net': net,                      # admission fee after concession
        'books': books_paisa(student),
        'uniform_qty': student.uniform_qty or 0,
        'uniform_unit': student.uniform_unit_paisa or 0,
        'uniform': uniform_paisa(student),
        'extras': extras_paisa(student),
        'total': total,                  # admission + books + uniform
        'lines': allocate(student, received),
        'received': received,
        'prior_paid': student.admission_fee_prior_paid_paisa or 0,
        'balance': max(0, total - received),
        'status': status_for(student, received),
        'discount_type': student.admission_discount_type,
        'discount_value': student.admission_discount_value,
        'note': student.admission_note,
        'date': student.admission_fee_date,
    }


def set_items(student, books_rupees, uniform_qty, uniform_unit_rupees):
    """Record the books and uniform agreed for a student (0 / blank = none).

    Does not commit.  Returns ``(books_paisa, uniform_paisa)``.
    """
    books = to_paisa(books_rupees)
    unit = to_paisa(uniform_unit_rupees)
    try:
        qty = int(float(uniform_qty or 0))
    except (TypeError, ValueError):
        raise ValueError('Please enter a whole number of uniform sets.')
    if books < 0 or unit < 0 or qty < 0:
        raise ValueError('Books and uniform amounts cannot be negative.')
    if qty > 20:
        raise ValueError('The number of uniform sets must be between 0 and 20.')
    student.books_fee_paisa = books or None
    if qty > 0 and unit > 0:
        student.uniform_qty, student.uniform_unit_paisa = qty, unit
    else:
        student.uniform_qty = student.uniform_unit_paisa = None
    return books, qty * unit if qty > 0 and unit > 0 else 0


def apply_terms(student, standard_rupees, discount_type=None, discount_value=None,
                note=None, fee_date=None, keep_row=False):
    """Record (or replace) a student's admission terms.  Does not commit.

    ``standard_rupees`` of 0 clears the terms (no admission fee).  With
    ``keep_row`` (books / uniform are agreed) a zero fee is kept as an empty
    admission part instead, so the student still has a record.
    """
    standard = to_paisa(standard_rupees)
    if standard < 0:
        raise ValueError('The admission fee cannot be negative.')
    if standard == 0 and keep_row:
        student.admission_fee_standard_paisa = 0
        student.admission_fee_net_paisa = 0
        student.admission_discount_type = None
        student.admission_discount_value = None
        student.admission_note = ((note or '').strip()[:200]) or student.admission_note
        student.admission_fee_date = fee_date or student.admission_fee_date or date.today()
        return 0
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
                 note=None, books_rupees=None, uniform_qty=None,
                 uniform_unit_rupees=None):
    """Admin change of an existing student's terms (also first-time setup for
    students admitted before the feature).  Never goes below what was received.

    Books / uniform are changed only when at least one of those three values
    is given; otherwise the student's current books and uniform stay.
    """
    received = received_paisa(student.id)
    standard = to_paisa(standard_rupees)
    change_items = not (books_rupees is None and uniform_qty is None
                        and uniform_unit_rupees is None)
    if change_items:
        books = to_paisa(books_rupees)
        try:
            qty = int(float(uniform_qty or 0))
        except (TypeError, ValueError):
            raise ValueError('Please enter a whole number of uniform sets.')
        unit = to_paisa(uniform_unit_rupees)
        if books < 0 or qty < 0 or unit < 0:
            raise ValueError('Books and uniform amounts cannot be negative.')
        extras = books + (qty * unit if qty > 0 and unit > 0 else 0)
    else:
        extras = extras_paisa(student)
    if standard == 0:
        net = 0
        if extras == 0 and received > 0:
            raise ValueError(
                '%s is already received, so the admission fee cannot be removed. '
                'Void the payment first.' % money(received))
    else:
        net, _ = compute_net(standard, discount_type, discount_value)
    if (net + extras < received) and not (standard == 0 and extras == 0):
        raise ValueError(
            '%s is already received, so the agreed fee cannot be lower than '
            'that. Void a payment first if it was taken by mistake.' % money(received))
    before = _terms_text(student)
    if change_items:
        set_items(student, books_rupees, uniform_qty, uniform_unit_rupees)
    apply_terms(student, standard_rupees, discount_type, discount_value, note,
                keep_row=extras_paisa(student) > 0)
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
        'books': to_rupees(books_paisa(student)),
        'uniform': '%s x %s' % (student.uniform_qty or 0,
                                to_rupees(student.uniform_unit_paisa or 0)),
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
    item = class_items(db.session.get(ClassModel, student.class_id)
                       if student.class_id else None)
    if can_manage:
        standard = _form_amount(form.get('admission_fee'), default_rupees,
                                'admission fee')
        discount_type = form.get('admission_discount_type')
        discount_value = form.get('admission_discount_value')
        note = form.get('admission_note')
        books = _form_amount(form.get('books_fee'), item['books'], 'books fee')
        sets = _form_amount(form.get('uniform_qty'), item['sets'], 'number of uniform sets')
        unit = _form_amount(form.get('uniform_price'), item['uniform'], 'uniform price')
    else:
        standard, discount_type, discount_value, note = default_rupees, None, None, None
        books, sets, unit = item['books'], item['sets'], item['uniform']
    books_p, uniform_p = set_items(student, books, sets, unit)
    extras = books_p + uniform_p
    if to_paisa(standard) == 0 and extras == 0:
        return None

    db.session.flush()
    admission_net = apply_terms(student, standard, discount_type, discount_value, note,
                                fee_date=student.admission_date or date.today(),
                                keep_row=extras > 0)
    net = (admission_net or 0) + extras
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
    query = StudentModel.query.filter(or_(
        StudentModel.admission_fee_net_paisa.isnot(None),
        StudentModel.books_fee_paisa.isnot(None),
        StudentModel.uniform_qty.isnot(None)))
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
        net = total_net_paisa(student)          # admission + books + uniform
        rows.append({
            'student': student,
            'standard': student.admission_fee_standard_paisa or 0,
            'concession': concession_paisa(student),
            'extras': extras_paisa(student),
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
        'extras': sum(r['extras'] for r in rows),
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
    students = (StudentModel.query.filter(
        StudentModel.id.in_(ids),
        or_(StudentModel.admission_fee_net_paisa.isnot(None),
            StudentModel.books_fee_paisa.isnot(None),
            StudentModel.uniform_qty.isnot(None))).all())
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
        net = total_net_paisa(student)
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

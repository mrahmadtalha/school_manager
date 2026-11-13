"""Applying the admission fee when a student is admitted, registered or imported."""

from datetime import date

from sqlalchemy import func, or_

from app.database import db
from app.models import ClassModel, OtherIncome, StudentModel
from app.models.fees import to_paisa, to_rupees
from app.services.audit import log_action

from .balances import status_for
from .common import STATUSES, STATUS_LABELS, money
from .edit import _sets, apply_terms, set_items
from .receipts import receive_payment
from .settings import class_items, effective_paisa, is_enabled
from .terms import concession_paisa, extras_paisa, total_net_paisa


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
        # Books and uniform PRICES are fixed by the class; the form only says what this
        # student takes: books yes / no, and how many uniform sets.
        # Book sets: the new "books_qty" box; older forms send books_taken = 1 / 0.
        if (form.get('books_qty') or '').strip() != '':
            book_sets = _sets(form.get('books_qty'), 'book')
        else:
            book_sets = 0 if (form.get('books_taken') or '1').strip() == '0' else 1
        books = item['books']
        sets = _form_amount(form.get('uniform_qty'), item['sets'], 'number of uniform sets')
        unit = item['uniform']
    else:
        standard, discount_type, discount_value, note = default_rupees, None, None, None
        books, sets, unit = item['books'], item['sets'], item['uniform']
        book_sets = 1
    books_p, uniform_p = set_items(student, books, sets, unit, book_sets)
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

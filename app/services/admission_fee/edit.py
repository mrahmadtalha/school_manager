"""Changing the agreed terms of a student after admission (books, uniform, discount) and the audit note it leaves."""

from datetime import date

from app.models.fees import to_paisa, to_rupees
from app.services.audit import log_action

from .balances import received_paisa, summary
from .common import money
from .terms import (books_qty, books_unit_paisa, compute_net, extras_paisa, has_terms)


def _sets(value, label, default=0):
    """A whole number of sets between 0 and 20 (blank -> ``default``)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        raise ValueError('Please enter a whole number of %s sets.' % label)
    if number < 0:
        raise ValueError('Books and uniform amounts cannot be negative.')
    if number > 20:
        raise ValueError('The number of %s sets must be between 0 and 20.' % label)
    return number


def set_items(student, books_rupees, uniform_qty, uniform_unit_rupees, books_sets=1):
    """Record the books and uniform agreed for a student (0 / blank = none).

    ``books_rupees`` is the price of ONE set of books and ``books_sets`` how many
    sets the student takes (default 1, so older callers keep working).
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
    book_sets = _sets(books_sets, 'book', default=1)
    if books > 0 and book_sets > 0:
        student.books_fee_paisa, student.books_qty = books, book_sets
    else:
        student.books_fee_paisa = student.books_qty = None
        books = 0
        book_sets = 0
    if qty > 0 and unit > 0:
        student.uniform_qty, student.uniform_unit_paisa = qty, unit
    else:
        student.uniform_qty = student.uniform_unit_paisa = None
    return books * book_sets, qty * unit if qty > 0 and unit > 0 else 0


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
                 uniform_unit_rupees=None, books_sets=None):
    """Admin change of an existing student's terms (also first-time setup for
    students admitted before the feature).  Never goes below what was received.

    Books / uniform are changed only when at least one of those three values
    is given; otherwise the student's current books and uniform stay.
    """
    received = received_paisa(student.id)
    standard = to_paisa(standard_rupees)
    change_items = not (books_rupees is None and uniform_qty is None
                        and uniform_unit_rupees is None and books_sets is None)
    if change_items:
        if books_sets is None:       # not sent: keep the sets the student already has
            books_sets = books_qty(student) or 1
        book_sets = _sets(books_sets, 'book', default=1)
        books = to_paisa(books_rupees) * book_sets
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
        set_items(student, books_rupees, uniform_qty, uniform_unit_rupees, book_sets)
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
        'books': '%s x %s' % (books_qty(student), to_rupees(books_unit_paisa(student))),
        'uniform': '%s x %s' % (student.uniform_qty or 0,
                                to_rupees(student.uniform_unit_paisa or 0)),
        'note': student.admission_note,
    }

"""The agreed terms of one student: discount, books, uniform, the total, and how a payment is split between them."""

from decimal import ROUND_HALF_UP, Decimal
from app.models.fees import to_paisa

from .common import DISCOUNT_TYPES


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


def books_unit_paisa(student):
    """Price of ONE set of books (``books_fee_paisa`` holds the price per set)."""
    return student.books_fee_paisa or 0


def books_qty(student):
    """Number of book sets (0 = none).  Older records have no count: that means 1."""
    if not student.books_fee_paisa:
        return 0
    return student.books_qty or 1


def books_paisa(student):
    return books_unit_paisa(student) * books_qty(student)


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
        parts.append({'key': 'books', 'label': 'Books', 'qty': books_qty(student),
                      'unit': books_unit_paisa(student), 'due': books_paisa(student)})
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

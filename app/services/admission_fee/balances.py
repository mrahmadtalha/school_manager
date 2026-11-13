"""What a student has paid so far, the status (pending / partial / paid) and the summary shown on screen."""

from sqlalchemy import func

from app.database import db
from app.models import OtherIncome, StudentModel

from .terms import (allocate, books_paisa, books_qty, books_unit_paisa, concession_paisa, extras_paisa,
                    has_terms, total_net_paisa, uniform_paisa)


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
        'books_qty': books_qty(student),
        'books_unit': books_unit_paisa(student),
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

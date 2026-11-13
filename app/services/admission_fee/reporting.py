"""Admission fee figures for lists and the financial summary."""

from sqlalchemy import func, or_

from app.database import db
from app.models import OtherIncome, StudentModel
from app.models.fees import to_rupees

from .balances import status_for
from .common import STATUS_LABELS
from .terms import total_net_paisa


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

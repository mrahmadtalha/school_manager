"""Stage: admission-fee terms, admission receipts and the books / uniform handed to new students.

Uses the real admission-fee and student-stock services, so a student's
status (paid / partial / pending / waived), the receipts (``ADM-0001`` ...)
and the stock that left the shelf are what the screens would have produced.
"""

from datetime import timedelta

from app.database import db
from app.models import OtherIncome, SchoolSettings, StudentIssue, StudentModel
from app.services import inventory_service as inv
from app.services import student_stock
from app.services.admission_fee.edit import apply_terms, set_items
from app.services.admission_fee.receipts import receive_payment
from app.services.admission_fee.terms import total_net_paisa

from .data import (ADMISSION_CONCESSION_NOTES, CLASS_ADMISSION_OVERRIDES, DEFAULT_ADMISSION_FEE,
                   PAYMENT_METHODS_MIX, UNIFORM_SETS_AT_ADMISSION)
from .helpers import _today


def _configure_fees(rng, classes, book_sets, uniform_sets):
    """School default, class overrides and the class books / uniform prices."""
    settings = SchoolSettings.query.first()
    if settings.default_admission_fee is None:
        settings.default_admission_fee = DEFAULT_ADMISSION_FEE
    for position, class_obj in enumerate(classes):
        if class_obj.admission_fee is None and class_obj.name in CLASS_ADMISSION_OVERRIDES:
            class_obj.admission_fee = CLASS_ADMISSION_OVERRIDES[class_obj.name]
        books_set = (book_sets or {}).get(class_obj.id)
        uniform_set = (uniform_sets or {}).get(class_obj.id)
        if class_obj.books_fee is None:
            class_obj.books_fee = (inv.set_price_paisa(books_set) / 100.0 if books_set is not None
                                   else float(900 + position * 120))
        if class_obj.uniform_fee is None:
            class_obj.uniform_fee = (inv.set_price_paisa(uniform_set) / 100.0 if uniform_set is not None
                                     else float(1400 + position * 40))
        if class_obj.uniform_sets is None:
            class_obj.uniform_sets = UNIFORM_SETS_AT_ADMISSION


def _stage_admission(rng, cfg, progress, classes, period_start, period_end, book_sets, uniform_sets):
    """Returns ``{'admission_terms', 'admission_receipts', 'stock_issues'}``."""
    today = _today()
    _configure_fees(rng, classes, book_sets, uniform_sets)
    db.session.flush()

    classes_by_id = {c.id: c for c in classes}
    default_fee = SchoolSettings.query.first().default_admission_fee
    students = StudentModel.query.order_by(StudentModel.id).all()
    terms = receipts = issues = 0

    for index, student in enumerate(students):
        class_obj = classes_by_id.get(student.class_id)
        if class_obj is None or student.admission_fee_net_paisa is not None \
                or student.books_fee_paisa is not None:
            continue            # already has terms: a second run never doubles receipts
        admission = student.admission_date or period_start
        standard = class_obj.admission_fee if class_obj.admission_fee is not None else default_fee

        roll = rng.random()
        if roll < 0.04:
            discount_type, discount_value = 'waived', None
        elif roll < 0.10:
            discount_type, discount_value = 'percentage', float(rng.choice([25, 50]))
        elif roll < 0.20:
            discount_type, discount_value = 'fixed', float(rng.choice([500, 1000, 1500]))
        else:
            discount_type = discount_value = None
        note = rng.choice(ADMISSION_CONCESSION_NOTES) if discount_type else None

        roll = rng.random()
        book_count = 0 if roll < 0.06 else (2 if roll < 0.12 else 1)
        uniform_count = rng.choice([1, 2, 2, 3])
        books_p, uniform_p = set_items(student, class_obj.books_fee, uniform_count,
                                       class_obj.uniform_fee, book_count)
        apply_terms(student, standard, discount_type, discount_value, note,
                    fee_date=admission, keep_row=(books_p + uniform_p) > 0)
        db.session.flush()
        total = total_net_paisa(student)
        if total <= 0:
            continue
        terms += 1

        if admission >= period_start:
            # Admitted while the software was in use: receipts + stock leave the shelf.
            roll = rng.random()
            first = total if roll < 0.62 else (
                int(total * rng.uniform(0.4, 0.7) // 100) * 100 if roll < 0.82 else 0)
            if first > 0:
                pay_day = min(admission + timedelta(days=rng.randint(0, 7)), today)
                receive_payment(student, first / 100.0, pay_day, rng.choice(PAYMENT_METHODS_MIX),
                                actor=None)
                receipts += 1
                left = total - first
                if left > 0 and rng.random() < 0.45:
                    second_day = pay_day + timedelta(days=rng.randint(10, 40))
                    if second_day <= today:
                        part = left if rng.random() < 0.6 else max(100, int(left // 200) * 100)
                        receive_payment(student, part / 100.0, second_day,
                                        rng.choice(PAYMENT_METHODS_MIX), actor=None)
                        receipts += 1
            if book_sets is not None:
                student.stock_tracked = True
                wanted = student_stock.wanted_sets(student)
                for kind in student_stock.KINDS:
                    target = student_stock.class_set(student.class_id, kind)
                    if wanted[kind] <= 0 or target is None:
                        continue
                    when = min(admission + timedelta(days=rng.randint(0, 10)), today)
                    try:
                        student_stock.issue_set(student, target, kind, wanted[kind],
                                                actor='admin', issue_date=when)
                        issues += 1
                    except ValueError:
                        continue            # not enough stock: left for "Issue now"
        else:
            # Admitted before the software: the money was received earlier (imported opening payment).
            roll = rng.random()
            if roll < 0.82:
                student.admission_fee_prior_paid_paisa = total
            elif roll < 0.92:
                student.admission_fee_prior_paid_paisa = int(total * rng.uniform(0.4, 0.8) // 100) * 100
        if index % 60 == 0:
            db.session.commit()
        progress.report('admission', index / max(1, len(students)))

    db.session.commit()
    progress.report('admission', 1.0)
    return {'admission_terms': terms,
            'admission_receipts': OtherIncome.query.filter(OtherIncome.student_id.isnot(None)).count(),
            'stock_issues': StudentIssue.query.count()}

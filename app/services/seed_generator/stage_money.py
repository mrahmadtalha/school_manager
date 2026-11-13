"""Stages: other income, canteen totals and issued ID cards / certificates."""

from datetime import datetime, timedelta

from app.database import db
from app.models import CanteenEntry, IssuedDocument, OtherIncome, OtherIncomeCategory, StudentModel
from app.models.issued_document import DOC_CERTIFICATE, DOC_ID_CARD
from app.services import canteen_service, document_fees, other_income_service

from .data import (CANTEEN_PURCHASE_NOTES, CANTEEN_SUPPLIERS, DOCUMENT_FEES, OTHER_INCOME_ITEMS)
from .helpers import _session_label, _today


def _day_in(rng, m_start, m_end, today):
    last = min(m_end, today)
    return m_start + timedelta(days=rng.randint(0, max(0, (last - m_start).days)))


def _stage_other_income(rng, cfg, progress, months):
    """Events, trips, activities and miscellaneous money (a few corrected by a void)."""
    today = _today()
    categories = {c.name: c for c in OtherIncomeCategory.query.all()}
    count = 0
    for m_index, (_label, m_start, m_end) in enumerate(months):
        for _ in range(rng.randint(2, 5)):
            name, text, (low, high) = rng.choice(OTHER_INCOME_ITEMS)
            category = categories.get(name)
            if category is None:
                continue
            row = other_income_service.record_income(
                category, round(rng.uniform(low, high), 2), _day_in(rng, m_start, m_end, today),
                description=text)
            row.payment_method = rng.choice(['cash', 'cash', 'bank'])
            count += 1
            if rng.random() < 0.04:
                db.session.flush()
                other_income_service.void_income(row, 'Entered under the wrong head')
        db.session.commit()
        progress.report('other_income', (m_index + 1) / len(months))
    return count


def _stage_canteen(rng, cfg, progress, months):
    """Canteen kept as daily / weekly totals, with supplier credit (udhaar) and instalments."""
    today = _today()
    canteen_service.set_mode(canteen_service.MODE_TOTALS)
    db.session.flush()
    entries = []
    credit_bills = []
    for m_index, (_label, m_start, m_end) in enumerate(months):
        for week in range(4):
            day = min(m_start + timedelta(days=week * 7 + 6), m_end, today)
            if day < m_start:
                continue
            entries.append(canteen_service.record_total(
                'sale', round(rng.uniform(14000, 42000), 2), day, note=f'Week {week + 1} sales'))
        for _ in range(rng.randint(2, 4)):
            day = _day_in(rng, m_start, m_end, today)
            total = round(rng.uniform(6000, 22000), 2)
            on_credit = rng.random() < 0.4
            entry = canteen_service.record_total(
                'purchase', total, day, note=rng.choice(CANTEEN_PURCHASE_NOTES),
                supplier=rng.choice(CANTEEN_SUPPLIERS),
                paid_rupees=round(total * rng.uniform(0.2, 0.6), 2) if on_credit else None)
            entries.append(entry)
            if on_credit:
                credit_bills.append(entry)
        db.session.flush()
        progress.report('canteen', 0.8 * (m_index + 1) / len(months))

    for bill in credit_bills:
        if bill.balance_paisa <= 0 or rng.random() < 0.25:     # a quarter stay unpaid
            continue
        pay_day = min(bill.entry_date + timedelta(days=rng.randint(5, 30)), today)
        if pay_day <= bill.entry_date:
            continue
        part = bill.balance_paisa if rng.random() < 0.65 else max(100, bill.balance_paisa // 2)
        try:
            canteen_service.pay_entry(bill, part / 100.0, pay_day, rng.choice(['cash', 'bank']),
                                      note='Supplier instalment')
        except ValueError:
            continue
    # one plain total typed twice is voided
    for entry in entries:
        if entry.kind == 'sale' and not entry.is_void and entry.entry_date < today - timedelta(days=20):
            canteen_service.void_entry(entry, 'Typed twice by mistake')
            break
    db.session.commit()
    progress.report('canteen', 1.0)
    return CanteenEntry.query.count()


def _stage_documents(rng, cfg, progress, period_start):
    """ID cards and certificates issued with fee receipts, duplicates and a void."""
    today = _today()
    document_fees.save_fee_settings(DOCUMENT_FEES)
    students = StudentModel.query.order_by(StudentModel.id).all()
    issued = []

    def issue(student, kind, cert_type, day, remarks=None, free_duplicate=False):
        row = document_fees.issue(student, kind, cert_type, session=_session_label(day),
                                  issue_date=day, remarks=remarks,
                                  method=rng.choice(['cash', 'cash', 'bank']),
                                  duplicate_free=free_duplicate)
        moment = datetime.combine(day, datetime.min.time()) + timedelta(hours=rng.randint(9, 14))
        row.created_at = min(moment, datetime.now())
        if row.income is not None:          # the receipt carries the day the card was issued
            row.income.income_date = day
            row.income.created_at = row.created_at
        issued.append(row)
        return row

    window = max(1, (today - period_start).days)
    for student in students:
        admitted = student.admission_date or period_start
        if rng.random() < 0.30:             # ID card
            day = min(max(admitted, period_start) + timedelta(days=rng.randint(3, 30)), today)
            issue(student, DOC_ID_CARD, None, day)
            if rng.random() < 0.10:         # lost card: duplicate, usually charged
                issue(student, DOC_ID_CARD, None, min(day + timedelta(days=rng.randint(30, 120)), today),
                      free_duplicate=rng.random() < 0.3)
        if student.status == 'slc_issued' and student.leaving_date:
            issue(student, DOC_CERTIFICATE, 'leaving', min(student.leaving_date, today),
                  remarks='School leaving certificate')
        elif rng.random() < 0.10:
            cert = rng.choice(['bonafide', 'character', 'merit'])
            issue(student, DOC_CERTIFICATE, cert, period_start + timedelta(days=rng.randint(0, window)),
                  remarks='Issued on parent\'s request')
    db.session.flush()
    for row in issued:                       # one mistaken issue is voided
        if row.fee_paisa > 0 and not row.is_void:
            document_fees.void_issue(row, 'Wrong student selected')
            break
    db.session.commit()
    progress.report('documents', 1.0)
    return IssuedDocument.query.count()

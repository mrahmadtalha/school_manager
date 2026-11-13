"""Fee side of the summary: collections, outstanding dues, fee buckets and former-student figures."""

from app.database import db
from app.models import FeeTransaction, TXN_PAYMENT, TXN_REFUND
from app.services.payroll_service import month_bounds, month_label, parse_month

from .common import _cash_date_column, _label_for_key, _money
from .periods import all_months_in_period, months_in_range


def fee_collections(start, end):
    """Cash In from fees: payments received in the window (by explicit payment
    date), minus refunds. Voided rows are never counted."""
    if not start or not end:
        return 0.0
    cash_date = _cash_date_column()
    rows = FeeTransaction.query.filter(
        FeeTransaction.txn_type.in_((TXN_PAYMENT, TXN_REFUND)),
        FeeTransaction.is_void.is_(False),
        cash_date >= start.isoformat(),
        cash_date <= end.isoformat(),
    ).all()
    total = sum((r.amount or 0) if r.txn_type == TXN_PAYMENT else -(r.amount or 0)
                for r in rows)
    return _money(total)


def _total_outstanding():
    """All receivables: charges + adjustments minus settled (payments, write-offs)."""
    from app.models import FeePaymentAllocation
    charged = (db.session.query(
                   db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
               .filter(FeeTransaction.is_void.is_(False),
                       FeeTransaction.txn_type.in_(('charge', 'adjustment'))).scalar()) or 0
    settled = (db.session.query(
                   db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
               .filter(FeePaymentAllocation.is_void.is_(False)).scalar()) or 0
    return _money((charged - settled) / 100.0)


def former_students_summary():
    """Count + total dues of former students, and the written-off total."""
    from app.models import FeePaymentAllocation, StudentModel, TXN_WRITEOFF
    from app.models.fees import to_rupees
    students = StudentModel.query.filter_by(is_active=False).all()
    rows = []
    total = 0.0
    for student in students:
        charged = (db.session.query(
                       db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
                   .filter(FeeTransaction.student_id == student.id,
                           FeeTransaction.is_void.is_(False),
                           FeeTransaction.txn_type.in_(('charge', 'adjustment'))).scalar()) or 0
        settled = (db.session.query(
                       db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
                   .join(FeeTransaction,
                         FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
                   .filter(FeeTransaction.student_id == student.id,
                           FeePaymentAllocation.is_void.is_(False)).scalar()) or 0
        balance = round((charged - settled) / 100.0, 2)
        if balance > 0:
            rows.append({'student': student, 'balance': balance})
            total = _money(total + balance)
    written_off = (db.session.query(
                       db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
                   .filter(FeeTransaction.is_void.is_(False),
                           FeeTransaction.txn_type == TXN_WRITEOFF).scalar()) or 0
    rows.sort(key=lambda item: -item['balance'])
    from app.models import STUDENT_STATUS_LABELS
    by_status = {}
    for item in rows:
        status = item['student'].status or 'struck_off'
        entry = by_status.setdefault(status, {'count': 0, 'total': 0.0,
                                              'label': STUDENT_STATUS_LABELS.get(status, status)})
        entry['count'] += 1
        entry['total'] = _money(entry['total'] + item['balance'])
    return {'count': len(rows), 'total': total, 'rows': rows,
            'by_status': by_status,
            'written_off': _money(to_rupees(written_off))}


def fee_month_overview(month_key):
    """One month's fee picture: expected, collected, remaining, rate.

    'collected' counts only money that settled THIS month's own charges;
    money received in the month that settled OLDER months is reported as
    arrears recovery and never as this month's collection.
    """
    split = collection_split(month_key)
    expected = _money(((db.session.query(
        db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
        .filter(FeeTransaction.is_void.is_(False),
                FeeTransaction.txn_type.in_(('charge', 'adjustment')),
                FeeTransaction.month_year == month_label(month_key)).scalar()) or 0)
        / 100.0)
    collected = split['current']
    remaining = _money(max(0.0, expected - collected))
    rate = round(collected * 100.0 / expected, 1) if expected > 0 else None
    return {'month': month_key, 'label': month_label(month_key),
            'expected': expected, 'collected': collected,
            'arrears': split['arrears'], 'remaining': remaining, 'rate': rate}


def student_outstanding_rows(class_id=None, section_id=None, month_year=None,
                             status_filter='active'):
    """Student-wise outstanding dues for the money page's filtered list.

    ``month_year`` ('YYYY-MM') limits the look to that month's own fee
    record; without it the figure is the student's full ledger outstanding.
    ``status_filter``: 'active' (default), 'former' (left students) or 'all'.
    """
    from app.models import STUDENT_STATUS_LABELS, StudentModel
    from app.services.fee_ledger import (student_month_outstanding_paisa,
                                         student_outstanding_paisa)

    query = StudentModel.query
    if status_filter == 'former':
        query = query.filter(StudentModel.is_active.is_(False))
    elif status_filter != 'all':
        query = query.filter(StudentModel.is_active.is_(True))
    if class_id:
        query = query.filter(StudentModel.class_id == class_id)
    if section_id:
        query = query.filter(StudentModel.section_id == section_id)

    label = month_label(month_year) if month_year and parse_month(month_year) else None
    rows = []
    for student in query.order_by(StudentModel.student_name).all():
        if label:
            # Ledger truth, not the derived fee-record cache: the dues list
            # must always agree with the rest of the summary.
            outstanding = round(student_month_outstanding_paisa(student.id, label)
                                / 100.0, 2)
        else:
            outstanding = round(student_outstanding_paisa(student.id) / 100.0, 2)
        if outstanding <= 0:
            continue    # a dues list shows students who actually owe money
        rows.append({
            'student': student,
            'class_name': student.class_info.name if student.class_info else '—',
            'section_name': (student.section_info.name if student.section_info
                             else '—'),
            'status_label': STUDENT_STATUS_LABELS.get(student.status, student.status),
            'leaving_date': student.leaving_date,
            'outstanding': outstanding,
        })
    rows.sort(key=lambda item: -item['outstanding'])
    return rows


def collection_split(month_year):
    """Current-month collection vs arrears recovered, by allocation target.

    'current' = payments (by payment date in the month) that settled charges of
    the same month; 'arrears' = payments that settled OLDER months' charges.
    Arrears recovery is never counted as current-month fee revenue.
    """
    from app.models import FeePaymentAllocation
    start, end = month_bounds(month_year)
    if not start:
        return {'current': 0.0, 'arrears': 0.0}
    charge_alias = db.aliased(FeeTransaction)
    cash_date = _cash_date_column()
    rows = (db.session.query(FeePaymentAllocation.amount_paisa, charge_alias.month_year)
            .join(FeeTransaction, FeePaymentAllocation.payment_txn_id == FeeTransaction.id)
            .join(charge_alias, FeePaymentAllocation.charge_txn_id == charge_alias.id)
            .filter(FeeTransaction.txn_type == TXN_PAYMENT,
                    FeeTransaction.is_void.is_(False),
                    FeePaymentAllocation.is_void.is_(False),
                    cash_date >= start.isoformat(),
                    cash_date <= end.isoformat())
            .all())
    label = _label_for_key(month_year)
    current = arrears = 0
    for amount_paisa, charge_month in rows:
        if charge_month == label:
            current += amount_paisa
        else:
            arrears += amount_paisa
    return {'current': _money(current / 100.0), 'arrears': _money(arrears / 100.0)}


def month_fee_buckets(start, end):
    """Per-ledger-month charged and outstanding paisa for a date range.

    Charged = active charges + adjustments; outstanding = charged minus every
    settling allocation (payments and write-offs) against that month's
    charges.  The shared engine's fees-remaining source.
    """
    from app.models import FeePaymentAllocation
    keys = months_in_range(start, end)
    if not keys:
        return {'charged': {}, 'outstanding': {}}
    labels = [month_label(key) for key in keys]
    charged_by_label = dict(db.session.query(
        FeeTransaction.month_year,
        db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
        .filter(FeeTransaction.is_void.is_(False),
                FeeTransaction.txn_type.in_(('charge', 'adjustment')),
                FeeTransaction.month_year.in_(labels))
        .group_by(FeeTransaction.month_year).all())
    settled_by_label = dict(db.session.query(
        FeeTransaction.month_year,
        db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
        .join(FeePaymentAllocation,
              FeePaymentAllocation.charge_txn_id == FeeTransaction.id)
        .filter(FeeTransaction.is_void.is_(False),
                FeeTransaction.month_year.in_(labels),
                FeePaymentAllocation.is_void.is_(False))
        .group_by(FeeTransaction.month_year).all())
    # Ledger rows use month labels ('October 2026'); map each label back to
    # the engine's 'YYYY-MM' key so the buckets line up with the period months.
    key_by_label = {month_label(k): k for k in keys}
    charged_by_key = {key_by_label.get(m, ''): int(v or 0)
                      for m, v in charged_by_label.items()}
    settled_by_key = {key_by_label.get(m, ''): int(v or 0)
                      for m, v in settled_by_label.items()}
    charged = {k: charged_by_key.get(k, 0) for k in keys}
    outstanding = {k: max(0, charged[k] - settled_by_key.get(k, 0))
                   for k in keys}
    return {'charged': charged, 'outstanding': outstanding}


def _billed_students_count(start, end):
    """Distinct students billed (charged/adjusted) inside the date range."""
    labels = [month_label(key) for key in months_in_range(start, end)]
    if not labels:
        return 0
    return (db.session.query(
                db.func.count(db.func.distinct(FeeTransaction.student_id)))
            .filter(FeeTransaction.is_void.is_(False),
                    FeeTransaction.txn_type.in_(('charge', 'adjustment')),
                    FeeTransaction.month_year.in_(labels)).scalar()) or 0


def _formers_left_count(start, end):
    """Students whose leaving date falls inside the date range."""
    from app.models import StudentModel
    return (StudentModel.query
            .filter(StudentModel.is_active.is_(False),
                    StudentModel.leaving_date >= start,
                    StudentModel.leaving_date <= end).count())


def _period_fee_collection(period):
    """(own-month collections, arrears recovered) summed over a period."""
    collected = arrears = 0.0
    for key in all_months_in_period(period):
        split = collection_split(key)
        collected += split['current']
        arrears += split['arrears']
    return _money(collected), _money(arrears)


def former_revenue_impact():
    """Estimated monthly revenue impact of students who left (estimate only).

    Sums the monthly fee of former students, SLC Issued and Struck Off shown
    separately.  Graduated students are expected to leave, so they are not
    part of the impact.
    """
    from app.models import STUDENT_STATUS_LABELS, StudentModel
    impact = {}
    for status in ('slc_issued', 'struck_off'):
        students = (StudentModel.query
                    .filter_by(is_active=False, status=status).all())
        entry = {'label': STUDENT_STATUS_LABELS.get(status, status),
                 'count': 0, 'monthly': 0.0}
        for student in students:
            if (student.monthly_fee or 0) > 0:
                entry['count'] += 1
                entry['monthly'] = _money(entry['monthly'] + student.monthly_fee)
        impact[status] = entry
    return impact

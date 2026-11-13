"""Stages: daily attendance, fee charges/payments and expenses."""

from datetime import datetime, timedelta

from app.database import db
from app.models import (AttendanceModel, Expense, ExpenseCategory, FeeRecordModel, FeeTransaction,
                        SchoolSettings, StudentModel, TeacherModel, TXN_ADJUSTMENT, TXN_CHARGE, TXN_PAYMENT,
                        TXN_REFUND, TXN_WRITEOFF)

from .data import (EXPENSE_AMOUNTS, EXPENSE_NOTES, EXTRA_CHARGE_EVENTS, PAYMENT_METHODS_MIX,
                   PAYMENT_PICK_WEIGHTS, PAYMENT_PROFILES,
                   PROFILE_PICK_WEIGHTS, STUDENT_PROFILES, _BULK_CHUNK)
from .helpers import (_minutes_to_time, _pick, _start_minutes, _today, _weighted_status)


def _stage_attendance(rng, cfg, progress, period_start, period_end, teacher_leaving):
    """One row per person per school day, chunked through Core inserts."""
    from app.services.teacher_payroll import get_school_working_days

    settings = SchoolSettings.query.first()
    school_days = get_school_working_days(period_start, period_end, settings)
    start_minutes = _start_minutes(settings.school_start_time)
    profile_weights = dict(STUDENT_PROFILES)

    students = [
        (s.id, s.class_id, s.admission_date or period_start,
         s.leaving_date if not s.is_active else None,
         _pick(rng, list(profile_weights), PROFILE_PICK_WEIGHTS))
        for s in StudentModel.query.all()
    ]
    teachers = [
        (t.id, t.joining_date or period_start, teacher_leaving.get(t.id))
        for t in TeacherModel.query.all()
    ]

    teacher_month_counts = {}
    pending = 0
    total_days = max(1, len(school_days))
    attendance_table = AttendanceModel.__table__
    row_keys = ('date', 'target_type', 'target_id', 'status', 'class_id',
                'is_locked', 'late_time', 'late_minutes', 'qr_time')
    qr_since = period_end - timedelta(days=14)     # the guard's phone scanned the recent days

    for day_index, day in enumerate(school_days):
        rows = []
        for sid, class_id, admission, leaving, profile in students:
            if day < admission or (leaving and day > leaving):
                continue
            status = _weighted_status(rng, profile_weights[profile])
            late_time = late_minutes = None
            if status == 'Late':
                late_minutes = rng.randint(5, 45)
                late_time = _minutes_to_time(start_minutes + late_minutes)
            qr_time = None
            if day >= qr_since and status in ('Present', 'Late') and rng.random() < 0.85:
                qr_time = late_time or _minutes_to_time(start_minutes - rng.randint(1, 25))
            rows.append({'date': day, 'target_type': 'student', 'target_id': sid,
                         'status': status, 'class_id': class_id, 'is_locked': False,
                         'late_time': late_time, 'late_minutes': late_minutes,
                         'qr_time': qr_time})

        for tid, joining, leaving in teachers:
            if day < joining or (leaving and day > leaving):
                continue
            status = rng.choices(['Present', 'Absent', 'Leave', 'Late'],
                                 weights=[90, 4, 3, 3], k=1)[0]
            late_time = late_minutes = None
            if status == 'Late':
                late_minutes = rng.randint(5, 30)
                late_time = _minutes_to_time(start_minutes + late_minutes)
            rows.append({'date': day, 'target_type': 'teacher', 'target_id': tid,
                         'status': status, 'class_id': None, 'is_locked': False,
                         'late_time': late_time, 'late_minutes': late_minutes})
            month_key = (tid, f'{day.year:04d}-{day.month:02d}')
            counts = teacher_month_counts.setdefault(
                month_key, {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0})
            counts[status] = counts.get(status, 0) + 1

        if rows:
            # executemany compiles one INSERT from the first row; keep the
            # key set identical across all rows.
            db.session.execute(attendance_table.insert(),
                               [{key: row.get(key) for key in row_keys} for row in rows])
            pending += len(rows)
            if pending >= _BULK_CHUNK:
                db.session.commit()
                pending = 0
        progress.report('attendance', day_index / total_days)

    db.session.commit()
    progress.report('attendance', 1.0)
    return teacher_month_counts


_TXN_KEYS = ('id', 'student_id', 'month_year', 'txn_type', 'amount_paisa', 'method', 'reference',
             'note', 'is_void', 'void_reason', 'voided_at', 'voided_by_name', 'payment_date',
             'apply_month', 'related_txn_id', 'created_at', 'created_by_name')


def _stage_fees(rng, cfg, progress, months, period_start, period_end):
    """Monthly charges, payments, extra charges, refunds, voids and write-offs.

    Everything goes onto the append-only ledger with the **real column names**
    (``amount_paisa``, ``payment_date``, ...) and every payment / write-off is
    allocated to charges exactly like ``fee_ledger.allocate_transaction`` does
    (the named month first, then oldest dues first; what is left over is the
    student's advance credit).  The ``fee_records`` cache is then derived from
    the ledger so it can never disagree with it.
    """
    from app.models import FeePaymentAllocation

    today = _today()
    now = datetime.now()
    students = [s for s in StudentModel.query.order_by(StudentModel.id).all() if s.monthly_fee]
    txn_table = FeeTransaction.__table__
    alloc_table = FeePaymentAllocation.__table__
    record_table = FeeRecordModel.__table__
    methods = PAYMENT_METHODS_MIX
    cashiers = ['admin', 'accountant1', 'accountant1']

    next_id = (db.session.query(db.func.coalesce(db.func.max(FeeTransaction.id), 0)).scalar() or 0) + 1
    slip_serial = {}

    def slip(day):
        slip_serial[day] = slip_serial.get(day, 0) + 1
        return f'SLIP-{day:%Y%m%d}-{slip_serial[day]:04d}'

    def at(day, hour_low=9, hour_high=15):
        moment = datetime.combine(day, datetime.min.time()) + timedelta(
            hours=rng.randint(hour_low, hour_high), minutes=rng.randint(0, 59))
        return min(moment, now - timedelta(minutes=rng.randint(1, 30)))

    def money(rupees):                        # rupees -> whole-rupee paisa
        return int(round(rupees)) * 100

    # One-off class events ("Extra charge: Picnic") so the extra-charge feature has data.
    events = {}
    for class_id in sorted({st.class_id for st in students}):
        for label, _m_start, _m_end in months[:-1] or months:
            if rng.random() < 0.12:
                name, amount = rng.choice(EXTRA_CHARGE_EVENTS)
                events[(class_id, label)] = (name, amount)

    txn_buf, alloc_buf, record_buf = [], [], []
    record_count = 0

    def flush(force=False):
        nonlocal txn_buf, alloc_buf, record_buf
        if not force and len(txn_buf) + len(alloc_buf) < _BULK_CHUNK:
            return
        if txn_buf:
            db.session.execute(txn_table.insert(), txn_buf)
        if alloc_buf:
            db.session.execute(alloc_table.insert(), alloc_buf)
        if record_buf:
            db.session.execute(record_table.insert(), record_buf)
        db.session.commit()
        txn_buf, alloc_buf, record_buf = [], [], []

    def row(**values):
        data = dict.fromkeys(_TXN_KEYS)
        data.update(is_void=False, created_by_name='system')
        data.update(values)
        return data

    for s_index, student in enumerate(students):
        fee = money(float(student.monthly_fee))
        admission = student.admission_date or period_start
        leaving = student.leaving_date if not student.is_active else None
        profile = _pick(rng, PAYMENT_PROFILES, PAYMENT_PICK_WEIGHTS)
        rows = []
        charges = {}            # month label -> [charge dict]
        month_order = []
        settle_events = []      # payments / write-offs to allocate, in recorded order
        last_label = None

        for label, m_start, m_end in months:
            if m_end < admission or (leaving and m_start > leaving):
                continue
            is_current = m_start <= today <= m_end
            charge_day = min(max(m_start, admission) + timedelta(days=3), today)
            charged_at = datetime.combine(charge_day, datetime.min.time()) + timedelta(hours=8)
            charge = {'id': next_id, 'paisa': fee, 'at': charged_at, 'left': fee, 'month': label}
            next_id += 1
            rows.append(row(id=charge['id'], student_id=student.id, month_year=label,
                            txn_type=TXN_CHARGE, amount_paisa=fee, note='Monthly fee charged',
                            created_at=charged_at, created_by_name='system'))
            charges[label] = [charge]
            month_order.append(label)
            last_label = label
            due = fee

            event = events.get((student.class_id, label))
            if event:
                extra = {'id': next_id, 'paisa': money(event[1]), 'at': charged_at + timedelta(minutes=5),
                         'left': money(event[1]), 'month': label}
                next_id += 1
                rows.append(row(id=extra['id'], student_id=student.id, month_year=label,
                                txn_type=TXN_ADJUSTMENT, amount_paisa=extra['paisa'],
                                note=f'Extra charge: {event[0]}', created_at=extra['at'],
                                created_by_name=rng.choice(cashiers)))
                charges[label].append(extra)
                due += extra['paisa']

            if not is_current:
                pay_chance = {'prompt': 0.98, 'regular': 0.90, 'late': 0.75, 'defaulter': 0.45}[profile]
            else:
                pay_chance = {'prompt': 0.85, 'regular': 0.55, 'late': 0.30, 'defaulter': 0.10}[profile]
            if rng.random() >= pay_chance:
                continue

            amount = due
            partial = profile in ('late', 'defaulter') and rng.random() < 0.45
            if partial:
                amount = max(5000, int(round(due * rng.uniform(0.3, 0.7) / 5000.0)) * 5000)
            advance = False
            if is_current and profile == 'prompt' and rng.random() < 0.06:
                amount = due + fee * rng.randint(1, 2)        # paid ahead: leaves advance credit
                advance = True
            offset = {'prompt': rng.randint(4, 9), 'regular': rng.randint(10, 20),
                      'late': rng.randint(25, 40), 'defaulter': rng.randint(20, 35)}[profile]
            pay_day = min(max(m_start, admission) + timedelta(days=offset), today)
            cashier = rng.choice(cashiers)

            def add_payment(paisa, day, note):
                nonlocal next_id
                paid_at = at(day)
                if paid_at <= charge['at']:
                    paid_at = charge['at'] + timedelta(minutes=30)
                pay = {'id': next_id, 'paisa': paisa, 'at': paid_at, 'month': label, 'refund': 0,
                       'method': rng.choice(methods)}
                next_id += 1
                rows.append(row(id=pay['id'], student_id=student.id, month_year=label,
                                txn_type=TXN_PAYMENT, amount_paisa=paisa,
                                method=pay['method'], reference=slip(day), note=note,
                                payment_date=day, apply_month=label, created_at=paid_at,
                                created_by_name=cashier))
                settle_events.append(pay)
                return pay

            first = add_payment(amount, pay_day, 'Advance fee received' if advance
                                else ('Part payment' if partial else 'Fee received'))
            if partial and rng.random() < 0.5:
                later_day = pay_day + timedelta(days=rng.randint(7, 20))
                if later_day <= today:
                    left = due - amount
                    add_payment(left if rng.random() < 0.6 else max(5000, left // 2),
                                later_day, 'Balance instalment')

            if not partial and not advance and rng.random() < 0.025:      # part of it returned
                refund_paisa = max(1000, int(first['paisa'] * rng.uniform(0.1, 0.3) // 1000) * 1000)
                refund_day = pay_day + timedelta(days=rng.randint(2, 9))
                if refund_day <= today and refund_paisa < first['paisa']:
                    refund_at = at(refund_day)
                    rows.append(row(id=next_id, student_id=student.id, month_year=label,
                                    txn_type=TXN_REFUND, amount_paisa=refund_paisa,
                                    method=first['method'], payment_date=refund_day,
                                    related_txn_id=first['id'], created_at=refund_at,
                                    note='Refund: amount returned to parent',
                                    created_by_name='admin'))
                    next_id += 1
                    first['refund'] = refund_paisa

            if rng.random() < 0.015:        # duplicate slip typed twice, then voided
                dup_at = first['at'] + timedelta(minutes=2)
                rows.append(row(id=next_id, student_id=student.id, month_year=label,
                                txn_type=TXN_PAYMENT, amount_paisa=first['paisa'],
                                method='cash', reference=slip(pay_day), is_void=True,
                                void_reason='Entered twice by mistake', voided_at=dup_at + timedelta(minutes=10),
                                voided_by_name='admin', payment_date=pay_day, apply_month=label,
                                created_at=dup_at, created_by_name=cashier,
                                note='Duplicate entry | voided: Entered twice by mistake'))
                next_id += 1

            if rng.random() < 0.03:
                surcharge = int(round(fee * 0.05))
                sc = {'id': next_id, 'paisa': surcharge, 'month': label,
                      'at': min(datetime.combine(m_end, datetime.min.time()) + timedelta(hours=10), now),
                      'left': surcharge}
                next_id += 1
                rows.append(row(id=sc['id'], student_id=student.id, month_year=label,
                                txn_type=TXN_ADJUSTMENT, amount_paisa=surcharge,
                                note='Late payment surcharge', created_at=sc['at'],
                                created_by_name='system'))
                charges[label].append(sc)

        # ---- allocate payments exactly like fee_ledger.allocate_transaction --------
        settled = {}                          # (charge id) -> paisa settled
        per_month = {}                        # label -> {'paid': x, 'off': y}
        allocations = []

        def allocate(event, kind):
            remaining = max(0, event['paisa'] - event.get('refund', 0))
            order = [event['month']] + [m for m in month_order if m != event['month']] \
                if kind == 'payment' else list(month_order)
            for label in order:
                if remaining <= 0:
                    break
                for charge in sorted(charges.get(label, []), key=lambda c: (c['at'], c['id'])):
                    if remaining <= 0:
                        break
                    if charge['at'] > event['at']:
                        continue              # that charge did not exist yet
                    available = charge['paisa'] - settled.get(charge['id'], 0)
                    if available <= 0:
                        continue
                    give = min(available, remaining)
                    settled[charge['id']] = settled.get(charge['id'], 0) + give
                    remaining -= give
                    bucket = per_month.setdefault(charge['month'], {'paid': 0, 'off': 0})
                    bucket['paid' if kind == 'payment' else 'off'] += give
                    allocations.append({'payment_txn_id': event['id'], 'charge_txn_id': charge['id'],
                                        'amount_paisa': give, 'is_void': False,
                                        'created_at': event['at'],
                                        'created_by_name': 'system'})

        for event in sorted(settle_events, key=lambda e: (e['at'], e['id'])):
            allocate(event, 'payment')

        # Dues of a student who left are sometimes written off (owner decision).
        if (not student.is_active and student.status in ('struck_off', 'slc_issued')
                and last_label and rng.random() < 0.55):
            outstanding = sum(c['paisa'] - settled.get(c['id'], 0)
                              for group in charges.values() for c in group)
            if outstanding > 0:
                off_at = at(min(today, (leaving or today) + timedelta(days=12)))
                off_at = max(off_at, max(c['at'] for g in charges.values() for c in g))
                write = {'id': next_id, 'paisa': outstanding, 'at': off_at, 'month': last_label}
                next_id += 1
                rows.append(row(id=write['id'], student_id=student.id, month_year=last_label,
                                txn_type=TXN_WRITEOFF, amount_paisa=outstanding,
                                note='Dues written off (student left the school)',
                                created_at=off_at, created_by_name='admin'))
                allocate(write, 'writeoff')

        # ---- the cache row of every month (derived from the ledger) --------------
        for label in month_order:
            due_paisa = sum(c['paisa'] for c in charges[label])
            bucket = per_month.get(label, {'paid': 0, 'off': 0})
            done = bucket['paid'] + bucket['off']
            if due_paisa <= 0 and done <= 0:
                status = 'Pending'
            elif done >= due_paisa and due_paisa > 0:
                status = 'Paid'
            elif done > 0:
                status = 'Partial'
            else:
                status = 'Pending'
            paid_rows = [r for r in rows if r['txn_type'] == TXN_PAYMENT and not r['is_void']
                         and r['month_year'] == label]
            last_date = None
            if paid_rows:
                last = max(paid_rows, key=lambda r: (r['payment_date'], r['created_at'], r['id']))
                last_date = last['payment_date']
            record_buf.append({'student_id': student.id, 'month_year': label,
                               'amount_due_paisa': due_paisa, 'amount_paid_paisa': bucket['paid'],
                               'amount_written_off_paisa': bucket['off'], 'status': status,
                               'payment_date': last_date, 'remarks': None})
            record_count += 1

        txn_buf.extend(rows)
        alloc_buf.extend(allocations)
        flush()
        progress.report('fees', s_index / max(1, len(students)))

    flush(force=True)
    progress.report('fees', 1.0)
    return record_count


def _stage_expenses(rng, cfg, progress, months):
    categories = {c.name: c.id for c in ExpenseCategory.query.all()}
    category_names = [name for name in EXPENSE_AMOUNTS if name in categories]
    if not category_names:
        progress.report('expenses', 1.0)
        return 0

    count = 0
    for m_index, (_label, m_start, m_end) in enumerate(months):
        rows = []
        for i in range(rng.randint(3, 7)):
            name = rng.choice(category_names)
            low, high = EXPENSE_AMOUNTS[name]
            day = m_start + timedelta(days=rng.randint(0, (m_end - m_start).days))
            rows.append(Expense(
                category_id=categories[name],
                amount=round(rng.uniform(low, high), 2),
                payment_method=rng.choice(['Cash', 'Bank', 'Cheque']),
                date=min(day, _today()),
                receipt_no=f'EXP-{m_start:%Y%m}-{i + 1:02d}',
                description=rng.choice(EXPENSE_NOTES),
                logged_by_name='system',
            ))
        db.session.add_all(rows)
        count += len(rows)
        db.session.commit()
        progress.report('expenses', m_index / max(1, len(months)))
    progress.report('expenses', 1.0)
    return count

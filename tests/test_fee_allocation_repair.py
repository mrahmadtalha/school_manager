"""Requirement 19 — allocation repair for the corrupted live rows.

The defects these tests pin down:

* a settling row (payment or write-off) could sit in the ledger with NO
  allocation at all — historically because allocation only matched ``charge``
  rows and never ``adjustment`` rows;
* such a row was reported as advance credit while the charge it should have
  cleared stayed outstanding, i.e. dues and credit coexisted;
* there was no production repair routine — the only test that covered the live
  rows called ``allocate_transaction`` by hand.

Rules asserted here:
  1. orphaned settling rows are detectable, oldest first;
  2. repairing them settles the real dues, never invents credit, and never
     reports written-off money as paid;
  3. the repair is idempotent — a second run changes nothing;
  4. it never touches a row that already has an allocation;
  5. after repair, dues and credit can no longer coexist;
  6. the repair is a deliberate action: it is not run by app startup, and the
     admin-triggered route repairs the rows behind a safety backup.
"""

import pytest

from app import create_app
from app.database import db
from app.models import (AdminUser, ClassModel, FeePaymentAllocation,
                        FeeTransaction, ROLE_ADMIN, StudentModel)
from app.services.fee_ledger import (ensure_charge, ledger_totals,
                                     orphaned_settlements, record_adjustment,
                                     record_payment, record_writeoff,
                                     recompute_fee_record, repair_allocations,
                                     student_credit_paisa, student_dues_months,
                                     student_outstanding_paisa)

MONTH = 'October 2026'
PREV = 'September 2026'
PREV2 = 'August 2026'


@pytest.fixture()
def app_on(tmp_path):
    """Advance credit / write-off ON, own throwaway database."""
    application = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'FEATURE_ADVANCE_CREDIT_WRITEOFF': True,
        'SQLALCHEMY_DATABASE_URI':
            'sqlite:///' + (tmp_path / 'req19_repair.db').as_posix(),
    })
    with application.app_context():
        db.drop_all()
        db.create_all()
        admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='Repair Admin')
        admin.set_password('repair-test-pass')
        db.session.add(admin)
        db.session.commit()
        application.config['ADMIN_ID'] = admin.id
        yield application
        db.session.remove()


@pytest.fixture()
def student(app_on):
    """One student at 1,000/month on their own class; nothing charged yet."""
    with app_on.app_context():
        klass = ClassModel(name='Repair Class', monthly_fee=1000.0)
        db.session.add(klass)
        db.session.flush()
        pupil = StudentModel(roll_number=991901, student_name='Repair Student',
                             father_name='F', guardian_phone='03001991901',
                             address='X', class_id=klass.id, monthly_fee=1000.0)
        db.session.add(pupil)
        db.session.flush()
        ids = {'student_id': pupil.id, 'class_id': klass.id}
        db.session.commit()
        return ids


def _charge(student_id, *months, amount=1000.0):
    pupil = db.session.get(StudentModel, student_id)
    for month in months:
        ensure_charge(pupil, month, amount=amount)
        db.session.commit()
        recompute_fee_record(pupil.id, month)


def _strip_allocations(payment_txn_id):
    """Simulate the pre-fix ledger: money recorded, settling nothing."""
    for allocation in FeePaymentAllocation.query.filter_by(
            payment_txn_id=payment_txn_id, is_void=False).all():
        allocation.is_void = True
    db.session.commit()


# ------------------------------------------------------------------ 1
def test_orphaned_settlements_are_found_oldest_first(app_on, student):
    """A payment stripped of its allocations is reported as an orphan."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(sid, PREV2, PREV)
        pupil = db.session.get(StudentModel, sid)
        first = record_payment(pupil, PREV, 1000.0, method='cash')
        second = record_payment(pupil, MONTH, 1000.0, method='cash')
        db.session.commit()

        assert orphaned_settlements(sid) == []

        _strip_allocations(second.id)
        _strip_allocations(first.id)

        found = orphaned_settlements(sid)
        assert [t.id for t in found] == [first.id, second.id], 'oldest first'
        assert orphaned_settlements() == found, 'school-wide scan finds them too'


# ------------------------------------------------------------------ 2
def test_repair_settles_dues_without_inventing_credit(app_on, student):
    """The exact live defect: orphaned money showed as credit while dues stood."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(sid, PREV2, PREV)
        pupil = db.session.get(StudentModel, sid)
        payment = record_payment(pupil, PREV, 1500.0, method='cash')
        db.session.commit()

        _strip_allocations(payment.id)
        # The defect: money recorded but nothing settled.
        assert student_outstanding_paisa(sid) == 200000        # 2,000 owed
        assert student_credit_paisa(sid) == 150000             # 1,500 "credit"

        result = repair_allocations(actor='test')
        db.session.commit()

        assert result['repaired'] == 1
        assert result['students'] == {sid}
        # Dues really cleared: 1,500 across two 1,000 months.
        assert student_outstanding_paisa(sid) == 50000        # 500 left
        assert student_credit_paisa(sid) == 0, 'no credit while dues remain'
        charged, paid, written_off = ledger_totals(sid)
        assert (charged, paid, written_off) == (2000.0, 1500.0, 0.0)


# ------------------------------------------------------------------ 3
def test_repair_is_idempotent(app_on, student):
    """A second run must not move a single figure."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(sid, PREV)
        pupil = db.session.get(StudentModel, sid)
        payment = record_payment(pupil, MONTH, 700.0, method='cash')
        db.session.commit()
        _strip_allocations(payment.id)

        repair_allocations(actor='test')
        db.session.commit()
        first = (ledger_totals(sid), student_outstanding_paisa(sid),
                 student_credit_paisa(sid))

        second = repair_allocations(actor='test')
        db.session.commit()

        assert second['repaired'] == 0, 'nothing left to repair'
        assert (ledger_totals(sid), student_outstanding_paisa(sid),
                student_credit_paisa(sid)) == first


# ------------------------------------------------------------------ 4
def test_repair_leaves_correct_rows_alone(app_on, student):
    """A row that already has allocations keeps them byte for byte."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(sid, PREV)
        pupil = db.session.get(StudentModel, sid)
        good = record_payment(pupil, MONTH, 400.0, method='cash')
        orphan = record_payment(pupil, MONTH, 300.0, method='cash')
        db.session.commit()

        before = sorted((a.charge_txn_id, a.amount_paisa) for a in
                        FeePaymentAllocation.query.filter_by(
                            payment_txn_id=good.id, is_void=False).all())
        assert before, 'the good payment should have allocated to the charge'

        _strip_allocations(orphan.id)
        result = repair_allocations(actor='test')
        db.session.commit()

        assert result['repaired'] == 1, 'only the orphan was touched'
        after = sorted((a.charge_txn_id, a.amount_paisa) for a in
                       FeePaymentAllocation.query.filter_by(
                           payment_txn_id=good.id, is_void=False).all())
        assert after == before


# ------------------------------------------------------------------ 5
def test_writeoff_orphan_reports_as_written_off_not_paid(app_on, student):
    """A repaired write-off clears dues and is never counted as cash."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(sid, MONTH)
        record_adjustment(db.session.get(StudentModel, sid), MONTH, 120.0,
                          note='correction')
        db.session.commit()
        recompute_fee_record(sid, MONTH)
        assert student_outstanding_paisa(sid) == 112000        # 1,120 owed

        # A legacy write-off: recorded, allocated to nothing.
        legacy = FeeTransaction(student_id=sid, month_year=MONTH,
                                txn_type='writeoff', amount=1120.0, note='legacy')
        db.session.add(legacy)
        db.session.commit()

        assert orphaned_settlements(sid) == [legacy]
        assert student_credit_paisa(sid) == 0, 'a write-off is never credit'

        repair_allocations(actor='test')
        db.session.commit()

        assert student_outstanding_paisa(sid) == 0
        charged, paid, written_off = ledger_totals(sid)
        assert written_off == 1120.0
        assert paid == 0.0, 'written-off money is not cash'
        assert student_credit_paisa(sid) == 0
        assert student_dues_months(sid) == []


# ------------------------------------------------------------------ 6
def test_no_student_shows_dues_and_credit_together_after_repair(app_on, student):
    """The whole-school invariant requirement 19 asks for."""
    with app_on.app_context():
        sid = student['student_id']
        _charge(sid, PREV2, PREV)
        pupil = db.session.get(StudentModel, sid)

        payments = [record_payment(pupil, PREV, 400.0, method='cash'),
                    record_payment(pupil, MONTH, 250.0, method='cash')]
        db.session.commit()
        for txn in payments:
            _strip_allocations(txn.id)
        writeoff = FeeTransaction(student_id=sid, month_year=MONTH,
                                 txn_type='writeoff', amount=300.0, note='legacy')
        db.session.add(writeoff)
        db.session.commit()

        # Pre-repair the impossible state exists.
        assert student_outstanding_paisa(sid) > 0
        assert student_credit_paisa(sid) > 0

        repair_allocations(actor='test')
        db.session.commit()

        owed = student_outstanding_paisa(sid)
        credit = student_credit_paisa(sid)
        assert not (owed > 0 and credit > 0), \
            'dues and advance credit must never coexist (owed=%s credit=%s)' % (
                owed, credit)


# ------------------------------------------------------------------ 7
def test_startup_does_not_touch_the_ledger(tmp_path):
    """Launching the app must never modify financial data.

    Allocation repair writes ledger rows, so it is a deliberate admin action
    (POST /fees/reconciliation/repair) and must not run at startup.
    """
    db_path = tmp_path / 'no_startup_repair.db'
    uri = 'sqlite:///' + db_path.as_posix()

    app1 = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'FEATURE_ADVANCE_CREDIT_WRITEOFF': True,
        'SQLALCHEMY_DATABASE_URI': uri,
    })
    with app1.app_context():
        db.drop_all()
        db.create_all()
        # Mark the legacy backfill as already done, so the only thing this test
        # can observe at the next startup is the repair hook (which must NOT run).
        # drop_all() erased the flag that create_app() had set.
        from app.models import SystemSettingModel
        db.session.add(SystemSettingModel(key='financial_v2_backfilled', value='1'))
        db.session.commit()
        klass = ClassModel(name='Startup Class', monthly_fee=1000.0)
        db.session.add(klass)
        db.session.flush()
        pupil = StudentModel(roll_number=991902, student_name='Startup Student',
                             father_name='F', guardian_phone='03001991902',
                             address='X', class_id=klass.id, monthly_fee=1000.0)
        db.session.add(pupil)
        db.session.commit()
        sid = pupil.id
        _charge(sid, PREV)
        payment = record_payment(pupil, MONTH, 1000.0, method='cash')
        db.session.commit()
        _strip_allocations(payment.id)
        assert student_outstanding_paisa(sid) == 100000
        assert student_credit_paisa(sid) == 100000
        before = FeePaymentAllocation.query.filter_by(is_void=False).count()

    # Second start must leave the orphan exactly where it was.
    app2 = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'FEATURE_ADVANCE_CREDIT_WRITEOFF': True,
        'SQLALCHEMY_DATABASE_URI': uri,
    })
    with app2.app_context():
        assert len(orphaned_settlements(sid)) == 1, \
            'startup must not repair anything'
        assert FeePaymentAllocation.query.filter_by(is_void=False).count() == before
        assert student_outstanding_paisa(sid) == 100000
        assert student_credit_paisa(sid) == 100000


# ------------------------------------------------------------------ 8
def test_admin_repair_route_backs_up_then_fixes(app_on, student, monkeypatch):
    """The reconciliation-page action takes a safety backup, then repairs."""
    sid = student['student_id']
    backup_calls = []

    def fake_backup(*args, **kwargs):
        class _Path:
            name = 'fake-backup.db'

            def __str__(self):
                return '/tmp/fake-backup.db'

        backup_calls.append(True)
        return _Path()

    with app_on.app_context():
        _charge(sid, MONTH)
        pupil = db.session.get(StudentModel, sid)
        payment = record_payment(pupil, MONTH, 1000.0, method='cash')
        db.session.commit()
        _strip_allocations(payment.id)
        assert len(orphaned_settlements(sid)) == 1

    import app.services.db_backup as backup_module
    monkeypatch.setattr(backup_module, 'backup_database', fake_backup)

    client = app_on.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(app_on.config['ADMIN_ID'])
        sess['_fresh'] = True

    response = client.post('/fees/reconciliation/repair', follow_redirects=True)
    assert response.status_code == 200
    assert backup_calls, 'a safety backup must be taken before repairing'

    with app_on.app_context():
        assert orphaned_settlements(sid) == []
        assert student_outstanding_paisa(sid) == 0
        assert student_credit_paisa(sid) == 0


def test_repair_route_is_idempotent_when_nothing_to_do(app_on, student):
    """With a clean ledger the action changes nothing and says so."""
    with app_on.app_context():
        _charge(student['student_id'], MONTH)
        assert orphaned_settlements() == []

    client = app_on.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(app_on.config['ADMIN_ID'])
        sess['_fresh'] = True

    response = client.post('/fees/reconciliation/repair', follow_redirects=True)
    assert response.status_code == 200
    assert b'Nothing to repair' in response.data

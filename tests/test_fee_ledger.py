"""The fee ledger must be append-only and reconcile exactly."""

from app.database import db
from app.models import AutomationSettings, FeeRecordModel, FeeTransaction, MessageQueue, StudentModel
from app.services.fee_ledger import ledger_totals, reconcile, recompute_fee_record

MONTH = 'September 2026'
OTHER_MONTH = 'October 2026'


def _fee_records(app, student_id, month=MONTH):
    return FeeRecordModel.query.filter_by(student_id=student_id, month_year=month).first()


def test_viewing_fees_creates_the_monthly_charge(admin_client, app, seed):
    response = admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')
    assert response.status_code == 200

    with app.app_context():
        charges = FeeTransaction.query.filter_by(student_id=seed['student_id'],
                                                 month_year=MONTH,
                                                 txn_type='charge').all()
        assert len(charges) == 1
        assert charges[0].amount == 2500.0

        record = _fee_records(app, seed['student_id'])
        assert record is not None
        assert record.amount_due == 2500.0
        assert record.amount_paid == 0.0
        assert record.status == 'Pending'


def test_partial_then_full_payment_reconciles(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')

    partial = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '1000', 'method': 'cash',
    }, follow_redirects=False)
    assert partial.status_code == 302

    with app.app_context():
        record = _fee_records(app, student_id)
        assert record.status == 'Partial'
        assert record.amount_paid == 1000.0
        assert record.balance == 1500.0

    final = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '1500', 'method': 'bank', 'reference': 'SLIP-9',
    }, follow_redirects=False)
    assert final.status_code == 302

    with app.app_context():
        record = _fee_records(app, student_id)
        assert record.status == 'Paid'
        assert record.amount_paid == 2500.0
        assert record.balance == 0.0

        # The summary must equal the sum of the individual transactions.
        charged, paid = ledger_totals(student_id, MONTH)
        assert charged == record.amount_due
        assert paid == record.amount_paid

        payments = FeeTransaction.query.filter_by(student_id=student_id, month_year=MONTH,
                                                  txn_type='payment').all()
        assert len(payments) == 2
        assert round(sum(p.amount for p in payments), 2) == record.amount_paid


def test_reconciliation_reports_no_discrepancy_for_consistent_data(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')
    admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '1200', 'method': 'cash',
    }, follow_redirects=False)

    with app.app_context():
        _, totals, discrepancies = reconcile(MONTH)
        assert totals['charged'] >= 2500.0
        assert totals['paid'] >= 1200.0
        assert discrepancies == []

    page = admin_client.get(f'/fees/reconciliation?month_year={MONTH}')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'Ledger and summary agree' in body
    assert 'Total charged' in body


def test_reconciliation_detects_a_tampered_summary(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')

    with app.app_context():
        record = _fee_records(app, student_id)
        record.amount_due = 999999.0  # simulate drift
        db.session.commit()

        _, _, discrepancies = reconcile(MONTH)
        assert discrepancies, 'drift between cache and ledger was not detected'

    page = admin_client.get(f'/fees/reconciliation?month_year={MONTH}')
    assert page.status_code == 200
    assert 'discrepanc' in page.get_data(as_text=True).lower()

    # And the cache can be rebuilt from the ledger.
    with app.app_context():
        recompute_fee_record(student_id, MONTH)
        db.session.commit()
        _, _, discrepancies_after = reconcile(MONTH)
        assert discrepancies_after == []


def test_ledger_totals_span_multiple_months(admin_client, app, seed):
    student_id = seed['student_id']
    for month in (MONTH, OTHER_MONTH):
        admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={month}')

    with app.app_context():
        charged, paid = ledger_totals(student_id)
        assert charged == 5000.0
        assert paid == 0.0

    ledger_page = admin_client.get(f'/fees/student/{student_id}')
    assert ledger_page.status_code == 200
    assert MONTH in ledger_page.get_data(as_text=True)


def test_fee_receipt_shows_transaction_history(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')
    admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '500', 'method': 'online', 'reference': 'ONLINE-1',
    }, follow_redirects=False)

    receipt = admin_client.get(f'/fees/receipt/{student_id}/{MONTH}')
    assert receipt.status_code == 200
    body = receipt.get_data(as_text=True)
    assert 'Ledger Transactions' in body
    assert 'Payment received' in body
    assert 'ONLINE-1' in body


def test_partial_payment_rejects_overpayment_and_autogenerates_reference(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')

    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH,
        'amount_paid': '1000',
        'method': 'cash',
        'reference': '',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        payments = FeeTransaction.query.filter_by(student_id=student_id, month_year=MONTH,
                                                  txn_type='payment').all()
        assert len(payments) == 1
        assert payments[0].reference is not None
        assert payments[0].reference.startswith('SLIP-')
        assert payments[0].amount == 1000.0

    blocked = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH,
        'amount_paid': '2000',
        'method': 'bank',
    }, follow_redirects=False)
    assert blocked.status_code == 302

    with app.app_context():
        payments = FeeTransaction.query.filter_by(student_id=student_id, month_year=MONTH,
                                                  txn_type='payment').all()
        assert len(payments) == 1

    allowed = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH,
        'amount_paid': '1500',
        'method': 'online',
    }, follow_redirects=False)
    assert allowed.status_code == 302

    with app.app_context():
        payments = FeeTransaction.query.filter_by(student_id=student_id, month_year=MONTH,
                                                  txn_type='payment').all()
        assert len(payments) == 2
        assert sum(p.amount for p in payments) == 2500.0

    search = admin_client.get(f'/fees?month_year={MONTH}&ref_query={payments[0].reference}')
    assert search.status_code == 200
    assert 'Fee Ledger' in search.get_data(as_text=True)


def test_enabled_payment_slip_is_queued_with_reference(admin_client, app, seed):
    student_id = seed['student_id']
    with app.app_context():
        settings = AutomationSettings.get()
        settings.enabled = True
        settings.notify_fee_receipts = True
        settings.mode = 'approval'
        db.session.commit()

    admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')
    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '500', 'method': 'cash',
    }, follow_redirects=False)

    assert response.status_code == 302
    with app.app_context():
        payment = FeeTransaction.query.filter_by(
            student_id=student_id, month_year=MONTH, txn_type='payment').one()
        slip = MessageQueue.query.filter_by(trigger='fee_receipt', student_id=student_id).one()
        assert slip.status == 'pending'
        assert payment.reference in slip.message
        assert '500.00 PKR received' in slip.message
        assert '2,000.00 PKR' in slip.message


def test_void_transactions_are_excluded_from_totals(app, seed):
    from app.services.fee_ledger import record_adjustment, void_transaction

    student_id = seed['student_id']
    with app.app_context():
        student = db.session.get(StudentModel, student_id)
        txn = record_adjustment(student, MONTH, 300.0, note='late fine')
        db.session.commit()

        charged, _ = ledger_totals(student_id, MONTH)
        assert charged == 300.0

        void_transaction(txn, note='mistake')
        db.session.commit()

        charged_after, _ = ledger_totals(student_id, MONTH)
        assert charged_after == 0.0

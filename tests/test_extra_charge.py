"""Event / trip extra charge, and the due override that must stay one month only."""

from app.database import db
from app.models import FeeTransaction, StudentModel
from app.services.fee_ledger import ledger_totals

MONTH = 'September 2026'


def test_extra_charge_adds_to_the_month_and_keeps_monthly_fee(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.post('/fees/generate-charges', data={
        'month_year': MONTH, 'class_id': str(seed['class_id'])})

    response = admin_client.post('/fees/extra-charge', data={
        'class_id': str(seed['class_id']), 'month_year': MONTH,
        'event_name': 'Picnic', 'amount': '500'}, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        charged, _paid, _written = ledger_totals(student_id, MONTH)
        assert charged == 3000.0                      # 2500 fee + 500 picnic
        assert db.session.get(StudentModel, student_id).monthly_fee == 2500.0


def test_extra_charge_twice_does_not_charge_twice(admin_client, app, seed):
    student_id = seed['student_id']
    data = {'class_id': str(seed['class_id']), 'month_year': MONTH,
            'event_name': 'Trip', 'amount': '300'}
    admin_client.post('/fees/extra-charge', data=data)
    admin_client.post('/fees/extra-charge', data=data)

    with app.app_context():
        rows = FeeTransaction.query.filter_by(
            student_id=student_id, month_year=MONTH,
            txn_type='adjustment', is_void=False).all()
        assert len(rows) == 1


def test_extra_charge_needs_a_name_and_a_positive_amount(admin_client, app, seed):
    admin_client.post('/fees/extra-charge', data={
        'class_id': str(seed['class_id']), 'month_year': MONTH,
        'event_name': '', 'amount': '500'})
    admin_client.post('/fees/extra-charge', data={
        'class_id': str(seed['class_id']), 'month_year': MONTH,
        'event_name': 'Picnic', 'amount': '0'})
    with app.app_context():
        assert FeeTransaction.query.filter_by(
            student_id=seed['student_id'], txn_type='adjustment').count() == 0


def test_due_override_changes_only_that_month(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.post('/fees/generate-charges', data={
        'month_year': MONTH, 'class_id': str(seed['class_id'])})

    admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '0', 'amount_due_override': '3000'},
        follow_redirects=True)

    with app.app_context():
        charge = FeeTransaction.query.filter_by(
            student_id=student_id, month_year=MONTH,
            txn_type='charge', is_void=False).one()
        assert charge.amount == 3000.0                # this month changed
        assert db.session.get(StudentModel, student_id).monthly_fee == 2500.0


def test_paying_a_month_with_an_extra_charge_is_not_an_override(admin_client, app, seed):
    """The collect form posts the month's WHOLE due (fee + extra).  That must be
    recognised as unchanged, with or without earlier payments."""
    student_id = seed['student_id']
    admin_client.post('/fees/generate-charges', data={
        'month_year': MONTH, 'class_id': str(seed['class_id'])})
    admin_client.post('/fees/extra-charge', data={
        'class_id': str(seed['class_id']), 'month_year': MONTH,
        'event_name': 'Picnic', 'amount': '500'})

    for amount in ('1000', '500'):                    # second one has an earlier payment
        response = admin_client.post(f'/fees/pay/{student_id}', data={
            'month_year': MONTH, 'amount_paid': amount,
            'amount_due_override': '3000', 'method': 'cash'}, follow_redirects=True)
        assert b'can no longer be overwritten' not in response.data

    with app.app_context():
        charge = FeeTransaction.query.filter_by(
            student_id=student_id, month_year=MONTH,
            txn_type='charge', is_void=False).one()
        assert charge.amount == 2500.0                # the fee was never rewritten
        charged, paid, _written = ledger_totals(student_id, MONTH)
        assert charged == 3000.0 and paid == 1500.0


def test_override_on_a_month_with_extra_keeps_the_extra(admin_client, app, seed):
    student_id = seed['student_id']
    admin_client.post('/fees/generate-charges', data={
        'month_year': MONTH, 'class_id': str(seed['class_id'])})
    admin_client.post('/fees/extra-charge', data={
        'class_id': str(seed['class_id']), 'month_year': MONTH,
        'event_name': 'Picnic', 'amount': '500'})
    admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': '0', 'amount_due_override': '3200'})
    with app.app_context():
        charged, _paid, _written = ledger_totals(student_id, MONTH)
        assert charged == 3200.0                      # fee 2700 + picnic 500
        assert db.session.get(StudentModel, student_id).monthly_fee == 2500.0

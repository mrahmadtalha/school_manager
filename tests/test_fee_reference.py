"""Slip / Reference numbers: auto-filled in the Collect Fee form and never reused."""

from app.models import FeeTransaction
from app.services.fee_ledger import next_reference, reference_in_use

MONTH = 'September 2026'


def _pay(client, student_id, reference, amount='500'):
    return client.post(f'/fees/pay/{student_id}', data={
        'month_year': MONTH, 'amount_paid': amount, 'method': 'cash',
        'reference': reference,
    }, follow_redirects=True)


def _payments(app, student_id):
    with app.app_context():
        return FeeTransaction.query.filter_by(
            student_id=student_id, month_year=MONTH, txn_type='payment', is_void=False).all()


def test_collect_fee_form_is_prefilled_with_an_editable_reference(admin_client, app, seed):
    page = admin_client.get(f'/fees?class_id={seed["class_id"]}&month_year={MONTH}')
    body = page.get_data(as_text=True)
    with app.app_context():
        expected = next_reference()
    assert f'value="{expected}"' in body
    assert 'name="reference"' in body
    # the field must stay editable
    field = body[body.index('name="reference"'):][:300]
    assert 'readonly' not in field and 'disabled' not in field


def test_prefilled_reference_is_saved_as_is(admin_client, app, seed):
    with app.app_context():
        suggested = next_reference()
    _pay(admin_client, seed['student_id'], suggested)
    payments = _payments(app, seed['student_id'])
    assert [p.reference for p in payments] == [suggested]


def test_duplicate_reference_is_rejected(admin_client, app, seed):
    student_id = seed['student_id']
    _pay(admin_client, student_id, 'DUP-1', '500')
    response = _pay(admin_client, student_id, 'DUP-1', '300')

    assert 'has already been used' in response.get_data(as_text=True)
    payments = _payments(app, student_id)
    assert len(payments) == 1 and payments[0].amount == 500.0


def test_duplicate_check_ignores_case_and_spaces(admin_client, app, seed):
    student_id = seed['student_id']
    _pay(admin_client, student_id, 'Slip-77')
    response = _pay(admin_client, student_id, '  slip-77 ')

    assert 'has already been used' in response.get_data(as_text=True)
    assert len(_payments(app, student_id)) == 1
    with app.app_context():
        assert reference_in_use('SLIP-77')


def test_rejected_duplicate_changes_nothing(admin_client, app, seed):
    student_id = seed['student_id']
    _pay(admin_client, student_id, 'DUP-2', '500')
    before = len(_payments(app, student_id))
    _pay(admin_client, student_id, 'DUP-2', '100')
    assert len(_payments(app, student_id)) == before


def test_blank_reference_still_gets_an_automatic_number(admin_client, app, seed):
    _pay(admin_client, seed['student_id'], '', '400')
    payments = _payments(app, seed['student_id'])
    assert len(payments) == 1 and payments[0].reference.startswith('SLIP-')


def test_voided_reference_can_be_reused(admin_client, app, seed):
    from app.database import db
    student_id = seed['student_id']
    _pay(admin_client, student_id, 'VOID-1', '500')
    with app.app_context():
        txn = FeeTransaction.query.filter_by(reference='VOID-1').first()
        txn.is_void = True
        db.session.commit()
        assert not reference_in_use('VOID-1')
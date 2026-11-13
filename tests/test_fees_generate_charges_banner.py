"""Regression: "Generate charges" button vanished for one class after "Set Monthly Fee for Entire Class".

A school ran the bulk class-fee update before the month's charges were generated.  The update
left an empty (Rs 0) summary row for every student of that class, so the fees page believed
the month was already billed, showed Rs 0 and hid the "N student(s) have no fee charge posted"
banner for that class only.  Other classes (and other schools) were fine.
"""

import pytest

from app.database import db
from app.models import ClassModel, FeeRecordModel, FeeTransaction, StudentModel
from app.services.fee_ledger.common import current_month

BANNER = 'have no fee charge posted'


@pytest.fixture()
def class_three(app):
    klass = ClassModel(name='Class 3', monthly_fee=None)
    db.session.add(klass)
    db.session.flush()
    for number in range(3):
        db.session.add(StudentModel(roll_number=3300 + number, student_name=f'Three {number}',
                                    father_name='F', guardian_phone=f'0300111330{number}',
                                    address='X', class_id=klass.id, monthly_fee=2000.0))
    db.session.commit()
    FeeTransaction.query.delete()
    FeeRecordModel.query.delete()
    db.session.commit()
    return klass.id


def _page(client, class_id):
    return client.get(f'/fees?class_id={class_id}').get_data(as_text=True)


def test_bulk_class_fee_update_keeps_the_generate_button(admin_client, class_three):
    assert BANNER in _page(admin_client, class_three)
    admin_client.post('/fees/class-bulk-update', data={
        'class_id': class_three, 'monthly_fee': '3000', 'confirm_bulk_update': 'yes'})
    assert StudentModel.query.filter_by(class_id=class_three).first().monthly_fee == 3000.0
    assert BANNER in _page(admin_client, class_three)
    assert FeeRecordModel.query.count() == 0          # no empty rows were left behind


def test_existing_empty_rows_still_show_the_button_and_generate_fixes_them(admin_client, class_three):
    """Databases already damaged by the old behaviour (empty rows, no charge)."""
    month = current_month()
    for student in StudentModel.query.filter_by(class_id=class_three):
        db.session.add(FeeRecordModel(student_id=student.id, month_year=month, amount_due=0.0,
                                      amount_paid=0.0, status='Pending'))
    db.session.commit()

    assert BANNER in _page(admin_client, class_three)

    admin_client.post('/fees/generate-charges', data={'month_year': month, 'class_id': class_three})
    assert FeeTransaction.query.filter_by(txn_type='charge', is_void=False).count() == 3
    for record in FeeRecordModel.query.filter_by(month_year=month):
        assert record.amount_due == 2000.0
    assert BANNER not in _page(admin_client, class_three)


def test_a_deliberately_voided_charge_is_not_nagged_about(admin_client, class_three):
    """Voiding a charge means "do not bill this student this month"."""
    from app.services.fee_ledger import ensure_charge, recompute_fee_record

    month = current_month()
    students = StudentModel.query.filter_by(class_id=class_three).all()
    for student in students:
        ensure_charge(student, month)
    db.session.commit()
    for student in students:
        charge = FeeTransaction.query.filter_by(student_id=student.id, txn_type='charge').first()
        charge.is_void = True
        recompute_fee_record(student.id, month)
    db.session.commit()

    assert BANNER not in _page(admin_client, class_three)

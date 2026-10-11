"""Phase 3a: Other Income — model, flows into Cash In / Net Position, voids,
roles, and the page."""
from datetime import date

import pytest

from app.database import db
from app.models import (ClassModel, OtherIncome, OtherIncomeCategory,
                        StudentModel)
from app.services import financial_summary as fs, other_income_service
from app.services.fee_ledger import ensure_charge, record_payment


@pytest.fixture()
def world(app):
    with app.app_context():
        other_income_service.seed_default_categories()
        klass = ClassModel(name='Other Income 3a', monthly_fee=2000.0)
        db.session.add(klass)
        db.session.flush()
        student = StudentModel(roll_number=8400, student_name='OI Student',
                               father_name='F OI', guardian_phone='03001118400',
                               address='X', class_id=klass.id, monthly_fee=2000.0)
        db.session.add(student)
        db.session.commit()
        # One fee payment in October: 2,000.
        ensure_charge(student, 'October 2026')
        record_payment(student, 'October 2026', 2000.0, method='cash',
                       payment_date=date(2026, 10, 5))
        db.session.commit()
        return {'student_id': student.id}


def _snap(month='2026-10'):
    return fs.month_snapshot(month)


def test_record_and_engine_flow(app, world):
    with app.app_context():
        canteen = OtherIncomeCategory.query.filter_by(name='Canteen').one()
        row = other_income_service.record_income(
            canteen, 1500.50, date(2026, 10, 12), description='snack sales',
            actor=None)
        db.session.commit()

        snap = _snap()
        assert row.amount == 1500.50                    # rupees, paisa-exact
        assert snap['other_income'] == 1500.50
        assert snap['fee_income'] == 2000.0
        assert snap['cash_in'] == 3500.50               # fees + other income
        assert snap['net'] == snap['cash_in'] - snap['cash_out']


def test_voided_income_leaves_every_total(app, world):
    with app.app_context():
        canteen = OtherIncomeCategory.query.filter_by(name='Canteen').one()
        row = other_income_service.record_income(canteen, 800.0,
                                                 date(2026, 10, 14))
        db.session.commit()
        assert _snap()['other_income'] == 800.0

        other_income_service.void_income(row, 'entered twice')
        db.session.commit()

        snap = _snap()
        assert snap['other_income'] == 0.0
        assert snap['cash_in'] == 2000.0                # back to fees only
        assert row.is_void and row.void_reason == 'entered twice'

        # A void without a reason is refused.
        row2 = other_income_service.record_income(
            OtherIncomeCategory.query.filter_by(name='Events').one(),
            100.0, date(2026, 10, 15))
        db.session.commit()
        with pytest.raises(ValueError):
            other_income_service.void_income(row2, '')
        assert not row2.is_void


def test_page_form_and_void_via_real_posts(admin_client, app, world):
    with app.app_context():
        category_id = OtherIncomeCategory.query.filter_by(name='Trips').one().id

    response = admin_client.post('/other-income/add', data={
        'category_id': str(category_id), 'amount': '2500',
        'income_date': '2026-10-20', 'description': 'trip tickets',
    }, follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Other income of Rs. 2,500.00 recorded for Trips' in body
    assert '2,500.00' in body

    with app.app_context():
        row = OtherIncome.query.filter_by(is_void=False).one()
        row_id = row.id

    void = admin_client.post(f'/other-income/{row_id}/void', data={
        'reason': 'cancelled trip',
    }, follow_redirects=True)
    assert 'Record voided' in void.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(OtherIncome, row_id).is_void

    # Void without a reason: refused, still active.
    with app.app_context():
        row2 = other_income_service.record_income(
            OtherIncomeCategory.query.filter_by(name='Events').one(),
            300.0, date(2026, 10, 21))
        db.session.commit()
        row2_id = row2.id
    refused = admin_client.post(f'/other-income/{row2_id}/void', data={},
                                follow_redirects=True)
    assert 'reason is required' in refused.get_data(as_text=True)
    with app.app_context():
        assert not db.session.get(OtherIncome, row2_id).is_void


def test_roles_teacher_cannot_enter(teacher_client, app, world):
    response = teacher_client.get('/other-income', follow_redirects=False)
    assert response.status_code == 403
    response = teacher_client.post('/other-income/add', data={
        'category_id': '1', 'amount': '100', 'income_date': '2026-10-20',
    }, follow_redirects=False)
    assert response.status_code == 403
    with app.app_context():
        assert OtherIncome.query.count() == 0


def test_summary_page_shows_other_income_card(admin_client, app, world):
    with app.app_context():
        canteen = OtherIncomeCategory.query.filter_by(name='Canteen').one()
        other_income_service.record_income(canteen, 750.25,
                                           date(2026, 10, 22))
        db.session.commit()

    body = admin_client.get('/financials/summary?month=2026-10') \
        .get_data(as_text=True)
    assert 'Rs. 750.25' in body                       # the card, not 0.00
    assert 'record other income' in body

"""Fees page writes nothing on load; monthly charges are posted explicitly.

The ledger stays the source of truth: a student without a cached fee summary
is rendered straight from their transactions, and only
``POST /fees/generate-charges`` creates the month's charge rows.
"""

from app.database import db
from app.models import FeeRecordModel, FeeTransaction, StudentModel
from app.services.fee_ledger import current_month
from tests.conftest import TEACHER_PASSWORD, login


def _count_txns(app, month_year):
    with app.app_context():
        return FeeTransaction.query.filter_by(month_year=month_year).count()


def test_fees_page_load_creates_no_transactions(admin_client, app, seed):
    with app.app_context():
        assert StudentModel.query.filter_by(class_id=seed['class_id']).count() == 2

    response = admin_client.get('/fees?class_id=%d&month_year=February 2027' % seed['class_id'])

    assert response.status_code == 200
    assert _count_txns(app, 'February 2027') == 0
    with app.app_context():
        assert FeeRecordModel.query.filter_by(month_year='February 2027').count() == 0


def test_fees_page_prompts_for_missing_charges(admin_client, app, seed):
    body = admin_client.get(
        '/fees?class_id=%d&month_year=February 2027' % seed['class_id']
    ).get_data(as_text=True)
    assert 'Generate monthly charges' in body


def test_generate_charges_posts_one_charge_per_student(admin_client, app, seed):
    month = current_month()
    response = admin_client.post('/fees/generate-charges',
                                 data={'month_year': month, 'class_id': str(seed['class_id'])},
                                 follow_redirects=False)

    assert response.status_code == 302
    with app.app_context():
        charges = FeeTransaction.query.filter_by(month_year=month, txn_type='charge').all()
        assert len(charges) == 2                     # the two seed students
        assert {c.amount for c in charges} == {2500.0, 2000.0}
        records = FeeRecordModel.query.filter_by(month_year=month).all()
        assert len(records) == 2
        assert all(r.status == 'Pending' for r in records)


def test_generate_charges_is_idempotent(admin_client, app, seed):
    month = current_month()
    admin_client.post('/fees/generate-charges',
                      data={'month_year': month, 'class_id': str(seed['class_id'])})
    admin_client.post('/fees/generate-charges',
                      data={'month_year': month, 'class_id': str(seed['class_id'])})

    with app.app_context():
        assert FeeTransaction.query.filter_by(
            month_year=month, txn_type='charge').count() == 2


def test_generate_charges_respects_class_filter(admin_client, app, seed):
    month = current_month()
    with app.app_context():
        from app.models import ClassModel
        other_class = ClassModel(name='Class 9')
        db.session.add(other_class)
        db.session.flush()
        db.session.add(StudentModel(
            roll_number=1001, student_name='Other Kid', father_name='Other Father',
            guardian_phone='03005555555', address='Street 9',
            class_id=other_class.id, monthly_fee=1500.0))
        db.session.commit()

    admin_client.post('/fees/generate-charges',
                      data={'month_year': month, 'class_id': str(seed['class_id'])})

    with app.app_context():
        # Only the filtered class was billed; the other student got nothing.
        assert FeeTransaction.query.filter_by(month_year=month).count() == 2


def test_generate_charges_works_for_a_past_month(admin_client, app, seed):
    response = admin_client.post('/fees/generate-charges',
                                 data={'month_year': 'January 2026',
                                       'class_id': str(seed['class_id'])},
                                 follow_redirects=False)
    assert response.status_code == 302
    with app.app_context():
        charges = FeeTransaction.query.filter_by(month_year='January 2026',
                                                 txn_type='charge').all()
        assert len(charges) == 2


def test_generate_charges_requires_admin_or_accountant(client, app):
    login(client, 'teacher', TEACHER_PASSWORD)
    response = client.post('/fees/generate-charges', data={'month_year': current_month()})
    assert response.status_code == 403
    assert _count_txns(app, current_month()) == 0

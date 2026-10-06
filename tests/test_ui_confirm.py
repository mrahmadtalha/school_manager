"""Temporary probe: verify data-confirm appears when rows actually exist."""

from datetime import date

from app.database import db
from app.models import Expense, ExpenseCategory, StudentModel


def test_expenses_delete_confirm_renders_with_a_row(admin_client, app, seed):
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name='Confirm Probe').first()
        if cat is None:
            cat = ExpenseCategory(name='Confirm Probe')
            db.session.add(cat)
            db.session.flush()
        db.session.add(Expense(category_id=cat.id, amount=50.0,
                               payment_method='Cash', date=date.today(),
                               logged_by_name='t'))
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)
    print('has data-confirm:', 'data-confirm="Delete this expense? This cannot be undone."' in body)
    print('has ok label   :', 'data-confirm-ok="Delete expense"' in body)
    print('native confirm :', "confirm('Delete this expense" in body)
    assert 'data-confirm="Delete this expense? This cannot be undone."' in body
    assert "confirm('Delete this expense" not in body


def test_bulk_restore_confirm_renders_with_an_archived_row(admin_client, app, seed):
    with app.app_context():
        student = db.session.get(StudentModel, seed['student_id'])
        student.is_active = False
        student.status = 'slc_issued'
        db.session.commit()

    body = admin_client.get('/students/archived').get_data(as_text=True)
    print('archived page has data-confirm:', 'data-confirm="Restore ALL' in body)
    print('archived page native confirm   :', 'onsubmit="return confirm(' in body)
    assert 'data-confirm="Restore ALL' in body
    assert 'onsubmit="return confirm(' not in body
    assert 'data-confirm-ok="Restore all"' in body

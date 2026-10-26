"""Expenses page redesign: month stays in force with a search, plain-language add form,
void reason box, Excel export link."""

from datetime import date

from app.database import db
from app.models import Expense, ExpenseCategory
from app.services import payroll_service


def _category(name='Redesign Cat'):
    category = ExpenseCategory.query.filter_by(name=name).first()
    if category is None:
        category = ExpenseCategory(name=name)
        db.session.add(category)
        db.session.flush()
    return category


def _expense(category, when, amount, description=None):
    expense = Expense(category_id=category.id, amount=amount, payment_method='Cash',
                      date=when, description=description, logged_by_name='tester')
    db.session.add(expense)
    db.session.flush()
    return expense


def _month_first_day(offset):
    key = payroll_service.shift_month(payroll_service.current_month_key(), offset)
    year, month = payroll_service.parse_month(key)
    return key, date(year, month, 1)


def _main_table(body):
    start = body.index('id="expenseMainTable"')
    return body[start:body.index('</table>', start)]


def test_picked_month_stays_in_force_with_a_category(admin_client, app):
    with app.app_context():
        category = _category()
        _, this_month = _month_first_day(0)
        last_key, last_month = _month_first_day(-1)
        _expense(category, this_month, 10.0, 'RedesignThisMonth')
        _expense(category, last_month, 20.0, 'RedesignLastMonth')
        db.session.commit()
        category_id = category.id

    table = _main_table(admin_client.get(
        f'/expenses?month={last_key}&category_id={category_id}').get_data(as_text=True))
    assert 'RedesignLastMonth' in table
    assert 'RedesignThisMonth' not in table

    # No month given: a category still looks through every month (unchanged).
    table = _main_table(admin_client.get(
        f'/expenses?category_id={category_id}').get_data(as_text=True))
    assert 'RedesignLastMonth' in table and 'RedesignThisMonth' in table


def test_month_dropdown_lists_the_months(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()
    last_key, _ = _month_first_day(-1)
    body = admin_client.get('/expenses').get_data(as_text=True)
    assert f'<option value="{last_key}"' in body
    assert 'name="month"' in body


def test_add_form_asks_plain_questions_and_void_has_a_reason_box(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()
    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'What kind of expense is it?' in body
    assert 'How much did you pay?' in body
    assert 'How did you pay?' in body
    assert 'id="voidExpenseModal"' in body
    assert 'Entered by mistake' in body


def test_excel_workbook_export_is_offered(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()
    body = admin_client.get('/expenses').get_data(as_text=True)
    assert '/expenses/export.xlsx' in body
    assert 'Excel workbook' in body

"""Staff Salaries page redesign: one card per teacher, month dropdown, plain-language
Pay / Void windows, state chips. The save / pay / void behaviour itself is covered in
test_payroll_expenses.py."""

from datetime import date

from app.database import db
from app.models import TeacherModel
from app.services import payroll_service


def _teacher(code='PR1', name='Redesign Teacher', salary=30000.0):
    teacher = TeacherModel.query.filter_by(teacher_id_str=code).first()
    if teacher is None:
        teacher = TeacherModel(teacher_id_str=code, teacher_name=name, qualification='MA',
                               monthly_salary=salary, salary_type='monthly',
                               joining_date=date(2025, 1, 1))
        db.session.add(teacher)
        db.session.commit()
    return teacher


def _body(admin_client, query=''):
    response = admin_client.get('/payroll' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_page_uses_the_flat_family_look(admin_client, app):
    with app.app_context():
        _teacher()
    body = _body(admin_client)
    assert 'class="pr-page"' in body
    assert 'class="pr-bar"' in body
    assert 'class="pr-band"' in body
    assert 'Redesign Teacher' in body
    assert 'Take-home' in body and 'Still to pay' in body


def test_month_is_a_dropdown_with_previous_and_next(admin_client, app):
    with app.app_context():
        _teacher()
    last_key = payroll_service.shift_month(payroll_service.current_month_key(), -1)
    body = _body(admin_client)
    assert 'name="month"' in body
    assert f'<option value="{last_key}"' in body
    for text in ('Previous', 'Next', 'This Month'):
        assert text in body, text


def test_selected_old_month_is_always_in_the_dropdown(admin_client, app):
    with app.app_context():
        _teacher()
    body = _body(admin_client, '?month=2019-03')
    assert '<option value="2019-03" selected' in body
    assert 'March 2019' in body


def test_form_field_names_are_unchanged_and_not_duplicated(admin_client, app):
    with app.app_context():
        teacher = _teacher()
        tid = teacher.id
    body = _body(admin_client)
    for prefix in ('include', 'base', 'bonus', 'deductions', 'notes'):
        assert body.count(f'name="{prefix}_{tid}"') == 1, prefix
    assert 'id="payrollForm"' in body and 'id="bulkPaidForm"' in body


def test_search_and_state_chips_are_offered(admin_client, app):
    with app.app_context():
        _teacher()
    body = _body(admin_client)
    assert 'id="prSearch"' in body
    assert 'data-filter="all"' in body
    assert 'data-filter="unsaved"' in body      # nothing is saved yet this month
    assert 'data-mode="cards"' in body and 'data-mode="list"' in body


def test_pay_window_asks_plain_questions(admin_client, app):
    with app.app_context():
        _teacher()
    body = _body(admin_client)
    assert 'How much are you paying now?' in body
    assert 'How did you pay?' in body
    assert 'On which day?' in body
    for method in ('value="Cash"', 'value="Bank"', 'value="Cheque"'):
        assert method in body, method


def test_void_asks_the_reason_in_a_proper_box(admin_client, app):
    with app.app_context():
        _teacher()
    body = _body(admin_client)
    assert 'id="voidSalaryModal"' in body
    assert 'Entered by mistake' in body
    assert 'window.prompt' not in body


def test_paid_teacher_card_is_locked_and_says_paid(admin_client, app):
    with app.app_context():
        teacher = _teacher('PR2', 'Locked Paid Teacher', 12000.0)
        month = payroll_service.current_month_key()
        payroll_service.generate(month, {'include_%d' % teacher.id: 'on'}, generated_by='tester')
        from app.models import StaffPayroll
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id, month_year=month).one()
        payroll_service.record_salary_payment(record, record.net_salary, date.today())
        db.session.commit()
    body = _body(admin_client)
    assert 'data-status="paid"' in body
    assert 'data-filter="paid"' in body

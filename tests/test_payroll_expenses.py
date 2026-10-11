"""Unit tests for the payroll + expense modules (see also test_teacher_payroll.py)."""
from datetime import date

from app.database import db
from app.models import (AttendanceModel, Expense, ExpenseCategory, StaffPayroll,
                        TeacherModel)
from app.services import expense_service, payroll_service
from app.services.payroll_service import (amount_in_words, month_bounds, month_label,
                                          parse_month, shift_month, suggested_row,
                                          teacher_month_stats)


def test_amount_in_words_vectors():
    assert amount_in_words(0) == 'Zero Rupees Only'
    assert amount_in_words(500) == 'Five Hundred Rupees Only'
    assert amount_in_words(45000) == 'Forty-Five Thousand Rupees Only'
    assert amount_in_words(1200.50) == 'One Thousand Two Hundred Rupees and Fifty Paisa Only'
    assert amount_in_words(105000) == 'One Hundred and Five Thousand Rupees Only'


def test_month_helpers():
    assert parse_month('2026-09') == (2026, 9)
    assert parse_month('bad') is None
    assert parse_month('2026-13') is None
    assert month_label('2026-09') == 'September 2026'
    assert shift_month('2026-01', -1) == '2025-12'
    assert shift_month('2026-12', 1) == '2027-01'
    start, end = month_bounds('2026-02')
    assert start == date(2026, 2, 1) and end == date(2026, 2, 28)


def test_seed_default_categories(app):
    with app.app_context():
        assert ExpenseCategory.query.count() == 0
        # 6 operational defaults + the system-reserved Salaries category.
        assert expense_service.seed_default_categories() == 7
        assert expense_service.seed_default_categories() == 0
        assert ExpenseCategory.query.count() == 7
        salaries = ExpenseCategory.query.filter_by(name='Salaries').one()
        assert salaries.is_system


def test_suggested_row_uses_attendance(app):
    with app.app_context():
        teacher = TeacherModel(teacher_id_str='TP1', teacher_name='Pay Test',
                               qualification='MA', monthly_salary=31000.0,
                               salary_type='monthly', joining_date=date(2025, 1, 1))
        db.session.add(teacher)
        db.session.commit()

        month = '2026-04'
        days = []
        cursor = date(2026, 4, 1)
        while len(days) < 6:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor = date.fromordinal(cursor.toordinal() + 1)
        statuses = ['Present', 'Absent', 'Present', 'Absent', 'Late', 'Leave']
        for day, status in zip(days, statuses):
            db.session.add(AttendanceModel(date=day, target_type='teacher',
                                           target_id=teacher.id, status=status))
        db.session.commit()

        stats = teacher_month_stats(teacher, month)
        assert stats['absent'] == 2 and stats['late'] == 1 and stats['leave'] == 1
        assert stats['working_days'] >= 20

        calc = suggested_row(teacher, month, per_late_amount=500.0)
        daily = round(31000.0 / stats['working_days'], 2)
        assert abs(calc['daily_rate'] - daily) < 0.001
        assert abs(calc['auto_deduction'] - round(daily * 2 + 500.0, 2)) < 0.001

        calc2 = suggested_row(teacher, month, per_late_amount=500.0,
                              leave_as_absent=True)
        assert abs(calc2['auto_deduction'] - round(daily * 3 + 500.0, 2)) < 0.001


def test_expense_service_summary_and_csv(app):
    with app.app_context():
        category = ExpenseCategory(name='Unit Test Cat')
        db.session.add(category)
        db.session.commit()
        db.session.add(Expense(category_id=category.id, amount=100.0,
                               payment_method='Cash', date=date(2026, 4, 5),
                               receipt_no='U-1', logged_by_name='tester'))
        db.session.commit()

        rows = expense_service.filter_expenses(category_id=category.id)
        assert len(rows) == 1
        summary = expense_service.summary(rows)
        assert summary['total'] == 100.0 and summary['count'] == 1
        csv_text = expense_service.ledger_csv(rows)
        assert 'U-1' in csv_text and 'TOTAL' in csv_text and 'Unit Test Cat' in csv_text


def test_payroll_generate_idempotent_and_locked(app):
    with app.app_context():
        teacher = TeacherModel(teacher_id_str='TP2', teacher_name='Pay Gen Test',
                               qualification='MA', monthly_salary=20000.0,
                               salary_type='monthly', joining_date=date(2025, 1, 1))
        db.session.add(teacher)
        db.session.commit()

        month = '2026-04'
        form = {
            'include_%d' % teacher.id: 'on',
            'base_%d' % teacher.id: '20000',
            'bonus_%d' % teacher.id: '1000',
            'deductions_%d' % teacher.id: '500',
        }
        result = payroll_service.generate(month, form, generated_by='tester')
        assert result['created'] == 1
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=month).first()
        assert record.net_salary == 20500.0 and record.bonus == 1000.0

        result2 = payroll_service.generate(month, form, generated_by='tester')
        assert result2['created'] == 0 and result2['updated'] == 1
        assert StaffPayroll.query.filter_by(month_year=month).count() == 1

        record.payment_status = 'Paid'
        db.session.commit()
        form['bonus_%d' % teacher.id] = '9999'
        payroll_service.generate(month, form, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=month).first()
        assert record.bonus == 1000.0


def test_payroll_page_renders_for_saved_calculation(admin_client, app):
    """JOB 1 regression: /payroll must not 500 when a saved record exists.

    The route passes ``payroll_service.preview_rows()`` rows to payroll.html,
    and those rows are dicts whose paid/remaining figures are keyed ``paid``
    and ``remaining``.  The template used to ask for ``row.remaining_amount``
    - the *model* property name, which only exists on ``row.record`` - so
    rendering raised

        jinja2.exceptions.UndefinedError:
        'dict object' has no attribute 'remaining_amount' (payroll.html line 300)

    and the page returned "500 Unexpected error" as soon as a saved payroll
    record existed.  Hand calculation for the record below:
        net = base 20,000 + bonus 1,000 - deductions 500 = 20,500
        paid        = 12,000        (one recorded payment)
        remaining   = 20,500 - 12,000 = 8,500
    """
    with app.app_context():
        teacher = TeacherModel(teacher_id_str='TP9', teacher_name='Pay Page Test',
                               qualification='MA', monthly_salary=20000.0,
                               salary_type='monthly', joining_date=date(2025, 1, 1))
        db.session.add(teacher)
        db.session.commit()

        month = '2026-04'
        payroll_service.generate(month, {
            'include_%d' % teacher.id: 'on',
            'base_%d' % teacher.id: '20000',
            'bonus_%d' % teacher.id: '1000',
            'deductions_%d' % teacher.id: '500',
        }, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=month).one()
        assert record.net_salary == 20500.0

        # A partial payment forces the "Pay rest" branch that rendered the
        # missing attribute, and gives row.remaining a non-zero value.
        payroll_service.record_salary_payment(record, 12000.0,
                                              payment_date=date(2026, 4, 20))
        db.session.commit()
        assert record.paid_amount == 12000.0
        assert record.remaining_amount == 8500.0

    response = admin_client.get('/payroll?month=%s' % month)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Pay Page Test' in body
    assert 'remaining_amount' not in body
    assert 'data-amount="8500.00"' in body


def test_system_category_rejects_crafted_rename_and_deactivate_posts(admin_client, app):
    """Server-side lock: direct POSTs must not edit or toggle system categories."""
    with app.app_context():
        expense_service.seed_default_categories()
        salaries = ExpenseCategory.query.filter_by(name='Salaries').one()
        salaries_id = salaries.id
        # Any seeded operational category works as the non-system control.
        utilities = ExpenseCategory.query.filter_by(name='Utilities').one()
        assert utilities.is_system is False
        utilities_id = utilities.id

    rename = admin_client.post(f'/expenses/categories/{salaries_id}/edit',
                               data={'name': 'Staff Wages', 'description': 'renamed'},
                               follow_redirects=True)
    assert rename.status_code == 200
    assert b'cannot be edited' in rename.data

    deactivate = admin_client.post(f'/expenses/categories/{salaries_id}/toggle',
                                   follow_redirects=True)
    assert deactivate.status_code == 200
    assert b'cannot be deactivated' in deactivate.data

    with app.app_context():
        saved = db.session.get(ExpenseCategory, salaries_id)
        assert saved.name == 'Salaries'
        assert saved.is_system is True
        assert saved.is_active is True

    # The lock is specific to system categories: a normal one still edits fine.
    normal = admin_client.post(f'/expenses/categories/{utilities_id}/edit',
                               data={'name': 'Utility Bills', 'description': ''},
                               follow_redirects=True)
    assert normal.status_code == 200
    with app.app_context():
        assert db.session.get(ExpenseCategory, utilities_id).name == 'Utility Bills'

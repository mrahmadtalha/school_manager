"""The seven mandatory reconciliation tests (Financial Module Spec v3, §10).

These encode the invariants the owner dashboard depends on.  If any of them
fails, no financial number on any page can be trusted.
"""

from datetime import date, datetime

import pytest

from app.database import db
from app.models import (ClassModel, Expense, ExpenseCategory, FeeRecordModel,
                        FeeTransaction, SalaryPayment, StaffPayroll, StudentModel,
                        SubjectLibrary, TeacherModel, TXN_PAYMENT, TXN_REFUND,
                        TXN_WRITEOFF)
from app.services import expense_service, fee_ledger, financial_summary as fs
from app.services.fee_ledger import (
    allocate_transaction, ensure_charge, ledger_totals, record_payment,
    record_writeoff, student_credit_paisa, student_outstanding_paisa,
    void_transaction,
)
from app.services.payroll_service import record_salary_payment

MONTH = 'October 2026'


@pytest.fixture()
def money_world(app):
    """One class, two students with charges, payments, salary and expenses."""
    teacher = TeacherModel(teacher_id_str='TF1', teacher_name='Ms Finance',
                           qualification='MSc')
    klass = ClassModel(name='Finance 1', monthly_fee=2500.0)
    db.session.add_all([teacher, klass])
    db.session.flush()
    lib = SubjectLibrary(name='Mathematics')
    db.session.add(lib)
    db.session.flush()

    students = []
    for i, name in enumerate(('Ali Finance', 'Sara Finance'), start=1):
        student = StudentModel(roll_number=9000 + i, student_name=name,
                               father_name='Father %d' % i,
                               guardian_phone='0300123456%d' % i, address='X',
                               class_id=klass.id, monthly_fee=2500.0)
        db.session.add(student)
        students.append(student)
    db.session.commit()

    return {'teacher': teacher, 'class': klass, 'students': students}


def _charge(student, month=MONTH, amount=None):
    charge = ensure_charge(student, month, amount=amount)
    db.session.flush()
    return charge


def test_1_student_balances_equal_summary_outstanding(app, money_world):
    """Rule 1: sum of all student balances = summary's total outstanding."""
    s1, s2 = money_world['students']
    with app.app_context():
        _charge(s1)
        _charge(s2)
        record_payment(s1, MONTH, 1000, payment_date=date(2026, 10, 5))
        record_payment(s2, MONTH, 2500, payment_date=date(2026, 10, 6))
        db.session.commit()

        per_student = [student_outstanding_paisa(s.id) for s in (s1, s2)]
        # The cached summary rows must agree with the ledger-derived balances.
        records = FeeRecordModel.query.all()
        cached_total = sum(r.amount_due_paisa - r.amount_paid_paisa
                           - r.amount_written_off_paisa for r in records)
        summary_outstanding = round(fs._total_outstanding() * 100)

        assert cached_total == sum(per_student)
        assert summary_outstanding >= 0
        # The summary's outstanding is the school-wide figure; this fixture's
        # students are its only debtors, so the two must match exactly.
        assert summary_outstanding == sum(per_student)


def test_2_allocations_equal_payments_minus_credit(app, money_world):
    """Rule 2: allocations = active payments minus unallocated credit.

    With FEATURE_ADVANCE_CREDIT_WRITEOFF PINNED OFF by the shared ``app``
    fixture (tests/conftest.py), overpayments are rejected at the source, so
    the credit term is always zero and allocations equal payments exactly.
    Flag-ON behaviour lives in tests/test_advance_credit_on.py."""
    s1, s2 = money_world['students']
    with app.app_context():
        _charge(s1)
        _charge(s2)
        record_payment(s1, MONTH, 1000, payment_date=date(2026, 10, 5))
        # Exact-balance payment: fully allocated, nothing left as credit.
        record_payment(s2, MONTH, 2500, payment_date=date(2026, 10, 6))
        db.session.commit()

        from app.models import FeePaymentAllocation
        from app.models.fees import to_rupees
        allocated = to_rupees(db.session.query(
            db.func.coalesce(db.func.sum(FeePaymentAllocation.amount_paisa), 0))
            .filter(FeePaymentAllocation.is_void.is_(False)).scalar())
        payments = to_rupees(db.session.query(
            db.func.coalesce(db.func.sum(FeeTransaction.amount_paisa), 0))
            .filter(FeeTransaction.txn_type == TXN_PAYMENT,
                    FeeTransaction.is_void.is_(False)).scalar())
        credit = to_rupees(sum(student_credit_paisa(s.id) for s in (s1, s2)))
        assert credit == 0          # the flag-off world holds no advance credit

        assert round(payments, 2) == round(allocated + credit, 2)


def test_3_salary_payments_equal_payroll_paid_and_summary(app, money_world):
    """Rule 3: salary payments = payroll paid = summary's salaries paid."""
    teacher = money_world['teacher']
    with app.app_context():
        record = StaffPayroll(teacher_id=teacher.id, month_year='2026-10',
                              base_salary=30000, net_salary=30000)
        db.session.add(record)
        db.session.flush()

        record_salary_payment(record, 20000, date(2026, 10, 28), 'Cash',
                              actor=None)
        record_salary_payment(record, 10000, date(2026, 10, 30), 'Bank',
                              actor=None)
        db.session.commit()

        payments_total = sum(p.amount for p in SalaryPayment.query.filter_by(
            is_void=False))
        assert round(payments_total, 2) == 30000.0
        assert record.paid_amount == 30000.0
        assert record.payment_status == 'Paid'

        summary = fs.salaries_paid_total(date(2026, 10, 1), date(2026, 10, 31))
        assert summary == 30000.0


def test_4_salaries_in_expenses_come_only_from_payroll(app, money_world):
    """Rule 4: Salaries expense rows are payroll-fed; manual entry is blocked."""
    teacher = money_world['teacher']
    with app.app_context():
        category = expense_service.ensure_salaries_category()
        record = StaffPayroll(teacher_id=teacher.id, month_year='2026-10',
                              net_salary=30000)
        db.session.add(record)
        db.session.flush()
        payment = record_salary_payment(record, 30000, date(2026, 10, 28),
                                        actor=None)
        db.session.commit()

        salaries_rows = Expense.query.join(ExpenseCategory).filter(
            ExpenseCategory.name == 'Salaries', Expense.is_void.is_(False)).all()
        assert len(salaries_rows) == 1
        assert salaries_rows[0].id == payment.expense_id

        # Manual entry through the route refuses the reserved category.
        admin_client = app.test_client()
        from tests.conftest import ADMIN_PASSWORD, login
        login(admin_client, 'admin', ADMIN_PASSWORD)
        response = admin_client.post('/expenses/add', data={
            'category_id': category.id, 'amount': '500',
            'payment_method': 'Cash', 'date': '2026-10-15',
        }, follow_redirects=True)
        assert b'reserved for payroll' in response.data
        assert Expense.query.filter_by(category_id=category.id).count() == 1


def test_5_voided_records_appear_in_no_total(app, money_world):
    """Rule 5: voiding removes a record from every total, never from history."""
    s1 = money_world['students'][0]
    with app.app_context():
        _charge(s1)
        payment = record_payment(s1, MONTH, 1500, payment_date=date(2026, 10, 5))
        record_payment(s1, MONTH, 1000, payment_date=date(2026, 10, 6))
        db.session.commit()

        before_outstanding = student_outstanding_paisa(s1.id)
        assert before_outstanding == 0  # 2500 charge fully settled

        void_transaction(payment, reason='wrong receipt')
        db.session.commit()

        assert payment.is_void and payment.void_reason == 'wrong receipt'
        assert payment.allocations and all(a.is_void for a in payment.allocations)
        # The charge is only covered by the surviving 1000 payment now.
        assert student_outstanding_paisa(s1.id) == 150000
        charged, paid, written_off = ledger_totals(s1.id, MONTH)
        assert paid == 1000.0

        # And the cash summary ignores the voided payment.
        cash = fs.fee_collections(date(2026, 10, 1), date(2026, 10, 31))
        assert cash == 1000.0


def test_6_cash_in_minus_cash_out_equals_net_position(app, money_world):
    """Rule 6: for any period, Net Position = Cash In - Cash Out."""
    teacher = money_world['teacher']
    s1 = money_world['students'][0]
    with app.app_context():
        category = expense_service.ensure_salaries_category()
        _charge(s1)
        record_payment(s1, MONTH, 2000, payment_date=date(2026, 10, 5))
        record_salary_payment(
            StaffPayroll(teacher_id=teacher.id, month_year='2026-10',
                         net_salary=30000) if False else _payroll(teacher),
            5000, date(2026, 10, 20), actor=None)
        db.session.add(Expense(category_id=category.id if category else 1,
                               amount=700, payment_method='Cash',
                               date=date(2026, 10, 21), logged_by_name='tester'))
        db.session.commit()

        window = (date(2026, 10, 1), date(2026, 10, 31))
        cash_in = fs.fee_collections(*window)
        cash_out = fs.expenses_total(*window)
        snapshot = fs.month_snapshot('2026-10')
        assert snapshot['net_position'] == round(cash_in - cash_out, 2)
        assert snapshot['net'] == snapshot['net_position']


def _payroll(teacher):
    record = StaffPayroll(teacher_id=teacher.id, month_year='2026-10',
                          net_salary=30000)
    db.session.add(record)
    db.session.flush()
    return record


def test_7_editing_current_settings_changes_no_history(app, money_world):
    """Rule 7: changing fees/salaries today rewrites no historical figure."""
    s1 = money_world['students'][0]
    teacher = money_world['teacher']
    with app.app_context():
        _charge(s1, MONTH, 2500)
        record_payment(s1, MONTH, 2500, payment_date=date(2026, 10, 5))
        record = StaffPayroll(teacher_id=teacher.id, month_year='2026-09',
                              net_salary=30000)
        db.session.add(record)
        db.session.flush()
        record_salary_payment(record, 30000, date(2026, 9, 28), actor=None)
        db.session.commit()

        fee_before = ledger_totals(s1.id, MONTH)
        salary_before = (record.net_salary, record.paid_amount)
        cash_before = fs.fee_collections(date(2026, 10, 1), date(2026, 10, 31))
        salaries_before = fs.salaries_paid_total(date(2026, 9, 1), date(2026, 9, 30))

        # "Current" settings change: the student's and class's fee settings,
        # and the teacher's profile salary — none of it may touch history.
        s1.monthly_fee = 9999.0
        money_world['class'].monthly_fee = 9999.0
        teacher.monthly_salary = 99999.0
        db.session.commit()

        assert ledger_totals(s1.id, MONTH) == fee_before
        assert (record.net_salary, record.paid_amount) == salary_before
        assert fs.fee_collections(date(2026, 10, 1), date(2026, 10, 31)) == cash_before
        assert fs.salaries_paid_total(date(2026, 9, 1), date(2026, 9, 30)) == salaries_before

        # New charges bill at the NEW fee, while the old charge is untouched.
        november = 'November 2026'
        new_charge = ensure_charge(s1, november)
        assert new_charge.amount == 9999.0
        assert ledger_totals(s1.id, MONTH)[0] == 2500.0


def test_8_current_collection_and_arrears_split_adds_up(app, money_world):
    """Current-month collection and arrears recovery are reported separately
    and together equal the period's Cash In."""
    student = money_world['students'][0]
    older, current = 'August 2026', 'September 2026'
    _charge(student, month=older)                      # 2500 arrear
    _charge(student, month=current)                    # 2500 current charge
    db.session.flush()
    record_payment(student, current, 5000.0, method='cash',
                   payment_date=date(2026, 9, 15))
    db.session.commit()

    split = fs.collection_split('2026-09')
    assert split['current'] == 2500.0
    assert split['arrears'] == 2500.0

    snap = fs.month_snapshot('2026-09')
    assert snap['fee_collected_current'] == 2500.0
    assert snap['arrears_recovered'] == 2500.0
    assert snap['cash_in'] == 5000.0
    assert round(snap['fee_collected_current'] + snap['arrears_recovered'], 2) \
        == snap['cash_in']

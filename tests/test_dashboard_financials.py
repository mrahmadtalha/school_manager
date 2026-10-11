"""The dashboard account-book must agree with /financials/summary exactly.

Owner decision (a): the dashboard's net figures use the SAME cash-basis
engine as the summary page — Cash In − Cash Out, salaries counted once via
the Salaries expense rows, payroll accrual never mixed into net.
"""

from datetime import date

from app.database import db
from app.models import (ClassModel, Expense, ExpenseCategory, StaffPayroll,
                        StudentModel, SubjectLibrary, TeacherModel)
from app.services import (dashboard_service, expense_service,
                          financial_summary as fs, payroll_service)
from app.services.fee_ledger import ensure_charge, record_payment
from app.services.payroll_service import record_salary_payment


def _month_key():
    today = date.today()
    return '%04d-%02d' % (today.year, today.month)


def _world(app):
    teacher = TeacherModel(teacher_id_str='TB1', teacher_name='Ms Balance',
                           qualification='MA')
    klass = ClassModel(name='Balance 1', monthly_fee=2000.0)
    db.session.add_all([teacher, klass])
    db.session.flush()
    db.session.add(SubjectLibrary(name='Mathematics'))
    db.session.flush()
    student = StudentModel(roll_number=9500, student_name='Balance Ali',
                           father_name='Father Balance',
                           guardian_phone='03009999999', address='X',
                           class_id=klass.id, monthly_fee=2000.0)
    db.session.add(student)
    db.session.commit()
    return teacher, student


def _payroll_form(teacher_id, base):
    return {
        'include_%d' % teacher_id: 'on',
        'base_%d' % teacher_id: str(base),
        'bonus_%d' % teacher_id: '0',
        'deductions_%d' % teacher_id: '0',
    }


def test_dashboard_net_matches_summary_for_month_and_session(app):
    month_key = _month_key()
    month_label = fs.month_label(month_key)
    teacher, student = _world(app)

    with app.app_context():
        # The app fixture wipes boot-seeded rows; seed the categories this
        # test reads ('Utilities', plus the system-reserved Salaries).
        expense_service.seed_default_categories()
        # 2,000 arrear last month + 2,000 current charge; one 4,000 payment
        # this month settles both (oldest first).
        prev = payroll_service.shift_month(month_key, -1)
        ensure_charge(student, fs.month_label(prev))
        ensure_charge(student, month_label)
        record_payment(student, month_label, 4000.0, method='cash',
                       payment_date=date.today())
        # 500 non-salary expense, cash this month.
        utilities = ExpenseCategory.query.filter_by(name='Utilities').one()
        db.session.add(Expense(category_id=utilities.id, amount=500.0,
                               date=date.today()))
        # 1,500 payroll accrual, UNPAID — must not touch any net figure.
        payroll_service.generate(month_key, _payroll_form(teacher.id, 1500),
                                 generated_by='tester')
        db.session.commit()

        book = dashboard_service.account_book()
        month_snap = fs.month_snapshot(month_key)

        assert book['month_net'] == month_snap['net']
        assert book['month_net'] == 3500.0  # 4,000 in − 500 out; accrual unpaid

        session_year = date.today().year if date.today().month >= 4 \
            else date.today().year - 1
        period = fs.period_descriptor('session:%d' % session_year)
        window = fs._window_totals(period['start'], period['end'])
        revenue, expenses, payroll = (window['revenue'], window['expenses'],
                                      window['payroll'])
        session_snap = fs.period_snapshot(period, revenue, expenses, payroll)
        assert book['session_net'] == session_snap['net']

        # The 6-month series must carry the summary's cash figures.
        last = book['series'][-1]
        assert last['revenue'] == month_snap['cash_in'] == 4000.0
        assert last['costs'] == month_snap['cash_out'] == 500.0
        assert last['net'] == 3500.0
        assert month_snap['payroll_pending'] == 1500.0
        assert month_snap['net'] == 3500.0


def test_salary_payment_counts_once_in_dashboard_net(app):
    """A paid salary appears in Cash Out via its Salaries expense row only —
    the dashboard net must equal the summary net, not double-count it.

    Uses ``record_salary_payment`` deliberately: it is the ONLY production
    entry point for salary payments (routes/payroll.py pay + bulk-pay), and
    with no categories seeded this also proves it self-heals the reserved
    Salaries category so the mirror row can never be silently skipped."""
    month_key = _month_key()
    teacher, student = _world(app)

    with app.app_context():
        ensure_charge(student, fs.month_label(month_key))
        record_payment(student, fs.month_label(month_key), 2000.0, method='cash',
                       payment_date=date.today())
        payroll_service.generate(month_key, _payroll_form(teacher.id, 1000),
                                 generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=month_key).one()
        record_salary_payment(record, 1000.0, payment_date=date.today())
        db.session.commit()

        book = dashboard_service.account_book()
        snap = fs.month_snapshot(month_key)
        assert snap['salaries_paid'] == 1000.0
        assert snap['cash_out'] == 1000.0  # only the Salaries mirror row
        assert snap['cash_in'] == 2000.0
        assert book['month_net'] == snap['net'] == 1000.0

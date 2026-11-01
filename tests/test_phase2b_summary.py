"""Phase 2b: comparisons, charts, alerts, insights on /financials/summary.

Fixed two-month dataset with hand-calculated expectations (October 2026 vs
September 2026):

    September: charged 3,500 (Ali 2,500 + Sara 1,000); Ali paid 2,500;
               Utilities 500.  -> Cash In 2,500, Cash Out 500, Net +2,000.
    October:   charged 3,500; Ali paid 2,000, Sara paid 1,300 (1,000 of it
               settles September's arrears, 300 this month); Utilities 1,500,
               Maintenance 400; salary 3,000 paid in full.
               -> Cash In 3,300, Fee Collection 2,300, Cash Out 4,900,
                  Salaries 3,000, Other Expenses 1,900, Net -1,600,
                  October fees remaining 1,200.
    A former student (SLC Issued, left 10 Oct 2026) owes 600 from May 2026:
    total outstanding 1,800, older arrears 600.
"""

import re
from datetime import date

import pytest

from app.database import db
from app.models import (ClassModel, Expense, ExpenseCategory, StudentModel,
                        TeacherModel)
from app.services import dashboard_service, expense_service, financial_summary as fs, \
    payroll_service
from app.services.fee_ledger import ensure_charge, record_payment
from app.services.payroll_service import record_salary_payment
from app.models import StaffPayroll

MONTH = '2026-10'
PREV = '2026-09'


@pytest.fixture()
def world(app):
    with app.app_context():
        expense_service.seed_default_categories()
        teacher = TeacherModel(teacher_id_str='P2B', teacher_name='Ms Compare',
                               qualification='MA')
        klass = ClassModel(name='Phase 2b', monthly_fee=2500.0)
        db.session.add_all([teacher, klass])
        db.session.flush()

        ali = StudentModel(roll_number=8300, student_name='Compare Ali',
                           father_name='F Ali', guardian_phone='03001118300',
                           address='X', class_id=klass.id, monthly_fee=2500.0)
        sara = StudentModel(roll_number=8301, student_name='Compare Sara',
                            father_name='F Sara', guardian_phone='03001118301',
                            address='X', class_id=klass.id, monthly_fee=1000.0)
        former = StudentModel(roll_number=8302, student_name='Gone Student',
                              father_name='F Gone', guardian_phone='03001118302',
                              address='X', class_id=klass.id, monthly_fee=1200.0,
                              is_active=False, status='slc_issued',
                              leaving_reason='moved', leaving_date=__import__(
                                  'datetime').date(2026, 10, 10))
        db.session.add_all([ali, sara, former])
        db.session.commit()

        # September
        ensure_charge(ali, 'September 2026')
        ensure_charge(sara, 'September 2026')
        record_payment(ali, 'September 2026', 2500.0, method='cash',
                       payment_date=__import__('datetime').date(2026, 9, 15))
        utilities = ExpenseCategory.query.filter_by(name='Utilities').one()
        db.session.add(Expense(category_id=utilities.id, amount=500.0,
                               date=__import__('datetime').date(2026, 9, 20)))

        # October
        ensure_charge(ali, 'October 2026')
        ensure_charge(sara, 'October 2026')
        record_payment(ali, 'October 2026', 2000.0, method='cash',
                       payment_date=__import__('datetime').date(2026, 10, 5))
        record_payment(sara, 'October 2026', 1300.0, method='cash',
                       payment_date=__import__('datetime').date(2026, 10, 8))
        db.session.add(Expense(category_id=utilities.id, amount=1500.0,
                               date=__import__('datetime').date(2026, 10, 12)))
        maintenance = ExpenseCategory.query.filter_by(name='Maintenance').one()
        db.session.add(Expense(category_id=maintenance.id, amount=400.0,
                               date=__import__('datetime').date(2026, 10, 20)))

        # October payroll, paid in full (mirror Salaries expense 3,000).
        payroll_service.generate(MONTH, {
            'include_%d' % teacher.id: 'on',
            'base_%d' % teacher.id: '3000',
            'bonus_%d' % teacher.id: '0',
            'deductions_%d' % teacher.id: '0',
        }, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=MONTH).one()
        record_salary_payment(record, 3000.0,
                              payment_date=__import__('datetime').date(2026, 10, 25))

        # The former student's old unpaid charge.
        ensure_charge(former, 'May 2026', amount=600.0)
        db.session.commit()
        return {'ali_id': ali.id, 'sara_id': sara.id, 'former_id': former.id,
                'class_id': klass.id, 'teacher_id': teacher.id}


def test_summary_renders_hand_calculated_numbers(admin_client, app, world):
    response = admin_client.get('/financials/summary?month=%s' % MONTH)
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    # Cards (cash basis, rupees — a 100x or double-count bug fails these).
    assert 'Rs. 3,300.00' in body          # Cash In
    assert 'Rs. 4,900.00' in body          # Cash Out (expenses + salaries once)
    assert 'Rs. 3,000.00' in body          # Salaries Paid
    assert 'Rs. 1,900.00' in body          # Other Expenses (Salaries excluded)
    assert 'Rs. -1,600.00' in body         # Net Position (cash only)
    assert 'Rs. 1,800.00' in body          # Fees Remaining (all months)

    # Month comparison table: current vs previous with amount and percentage.
    assert 'This month vs previous month' in body
    assert 'Rs 800.00 higher (32.0%)' in body      # Cash In 3,300 vs 2,500
    assert 'Rs 200.00 lower (8.0%)' in body        # Fee collection 2,300 vs 2,500
    assert 'Rs 4,400.00 higher (880.0%)' in body   # Cash Out 4,900 vs 500
    assert 'new this period' in body               # Salaries 3,000 vs 0
    assert 'Rs 3,600.00 lower (180.0%)' in body    # Net -1,600 vs +2,000
    assert 'Rs 1,200.00' in body                   # October fees remaining

    # The former student is counted once in the comparison and the alert.
    assert '1 former student(s) owe Rs 600.00' in body


def test_no_earlier_data_and_no_percentages_when_history_missing(admin_client,
                                                                 app):
    with app.app_context():
        klass = ClassModel(name='Fresh Class', monthly_fee=1000.0)
        db.session.add(klass)
        db.session.flush()
        student = StudentModel(roll_number=8310, student_name='Fresh Only',
                               father_name='F Fresh', guardian_phone='03001118310',
                               address='X', class_id=klass.id, monthly_fee=1000.0)
        db.session.add(student)
        db.session.commit()
        ensure_charge(student, 'October 2026')
        record_payment(student, 'October 2026', 400.0, method='cash',
                       payment_date=__import__('datetime').date(2026, 10, 6))
        db.session.commit()

    body = admin_client.get('/financials/summary?month=%s' % MONTH) \
        .get_data(as_text=True)
    assert 'No earlier data' in body
    assert 'Not enough history yet' in body
    # No percentage wording in the comparison tables (never divide by zero).
    comparisons_html = body.split('Period comparisons')[1].split('Custom range')[0]
    assert '(%' not in comparisons_html
    assert '%)' not in comparisons_html
    assert 'lower than last month' not in body
    # The 'vs last month' wording also appears in the (always-present) preset
    # buttons, so this assertion belongs to the "What changed" insight block
    # rather than the whole page.
    insights_html = body.split('What changed')[1]
    assert 'vs last month' not in insights_html


def test_alerts_and_insights_content(admin_client, world):
    body = admin_client.get('/financials/summary?month=%s' % MONTH) \
        .get_data(as_text=True)
    assert 'fees is still remaining' in body
    assert 'Rs 1,200.00' in body
    assert 'Rs 1,200.00' in body
    assert 'of older arrears is still recoverable' in body
    assert 'Rs 600.00' in body
    assert 'of salary is still unpaid' not in body          # paid in full
    assert 'of older arrears was recovered this month' in body
    assert 'Rs 1,000.00' in body                            # Sara's arrears part
    # Category-rise alert: Utilities 500 -> 1,500 (+200%, +Rs 1,000).
    assert 'Utilities expenses are up 200.0% vs last month (+Rs 1,000.00)' in body
    # Collection drop alert must NOT fire: 8% < 10% threshold and Rs 200 < 1,000.
    assert 'Fee collection is' not in body.split('Alerts')[1].split('What changed')[0]
    # Insights are factual and mention the net change.
    assert 'Fee collection is 8.0% lower than last month' in body
    assert 'Net Position fell by Rs 3,600.00 (cash basis)' in body
    assert 'Utilities is up 200.0% vs last month' in body
    # Estimated revenue impact of leavers.
    assert 'Estimated monthly revenue impact' in body
    assert 'SLC Issued: 1 student(s) · Rs 1,200.00/month' in body


def test_category_chart_and_breakdown_exclude_salaries(admin_client, world):
    body = admin_client.get('/financials/summary?month=%s' % MONTH) \
        .get_data(as_text=True)
    match = re.search(r'"category_labels":\s*\[(.*?)\]', body)
    assert match, 'chart payload missing category labels'
    labels = match.group(1)
    assert 'Utilities' in labels and 'Maintenance' in labels
    assert 'Salaries' not in labels
    # The breakdown table total excludes salaries too.
    assert 'Total (salaries excluded)' in body


def test_dashboard_net_equals_summary_net(app, world, monkeypatch):
    # The dashboard reads 'today'; pin it inside the October 2026 data set so
    # the test keeps working after the real calendar moves on.
    class _Oct2026(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 31)

    monkeypatch.setattr(dashboard_service, 'date', _Oct2026)
    with app.app_context():
        snap = fs.month_snapshot(MONTH)
        book = dashboard_service.account_book()
        assert snap['net'] == -1600.0
        assert book['month_net'] == snap['net']
        assert book['series'][-1]['net'] == snap['net']


def test_custom_range_comparison_changes_numbers(admin_client, world):
    october = admin_client.get('/financials/summary?month=%s&range_start=2026-10-01'
                               '&range_end=2026-10-31' % MONTH).get_data(as_text=True)
    assert '01 Oct 2026 to 31 Oct 2026' in october
    assert '31 Aug 2026 to 30 Sep 2026' in october      # preceding equal range
    assert 'Custom range vs preceding period' in october

    september = admin_client.get('/financials/summary?month=%s&range_start=2026-09-01'
                                 '&range_end=2026-09-30' % MONTH).get_data(as_text=True)
    assert '02 Aug 2026 to 31 Aug 2026' in september    # preceding 30 days
    assert '01 Sep 2026 to 30 Sep 2026' in september    # as the current range
    # The custom current range for September carries September's own numbers.
    assert 'No earlier data' in september               # August has nothing


def test_page_hides_advance_credit_and_written_off(admin_client, world):
    body = admin_client.get('/financials/summary?month=%s' % MONTH) \
        .get_data(as_text=True)
    assert 'Advance credit' not in body
    assert 'Written off' not in body

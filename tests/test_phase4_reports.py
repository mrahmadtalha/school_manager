"""Phase 4: Reports & Insights — rule-based metrics, generated insight text,
recommendations, exports.

Fixed two-month dataset with hand-calculated expectations (October 2026 vs
September 2026):

    September: Ali charged 2,500, paid 2,500; Sara charged 1,000, unpaid;
               Utilities 500; no salary.
               -> Cash In 2,500, Cash Out 500, Net +2,000, rate 100.0%.
    October:   Ali charged 2,500, paid 1,500; Sara charged 1,000, paid 1,300
               (1,000 settles September's arrears, 300 this month);
               Utilities 2,000; teacher salary 3,000 paid in full;
               inventory: 10 shirts bought @ 900 (Rs 9,000 stock purchase),
               2 sold @ 1,200 -> Sales 2,400, COGS 1,800, gross profit 600.
               -> Cash In 5,200 (fees 2,800 + sales 2,400),
                  Cash Out 14,000 (expenses 5,000 + stock purchases 9,000),
                  Net -8,800, Operating -1,600, rate 1,800/3,500 = 51.4%,
                  salary burden 3,000/5,200 = 57.7%,
                  Utilities +300.0% (+Rs 1,500), arrears recovered 1,000 (100.0%).
"""
from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.database import db
from app.models import (ClassModel, Expense, ExpenseCategory, Product,
                        StaffPayroll, StudentModel, TeacherModel)
from app.services import expense_service, payroll_service, report_insights
from app.services.fee_ledger import ensure_charge, record_payment
from app.services.inventory_service import record_purchase, record_sale
from app.services.payroll_service import record_salary_payment

MONTH = '2026-10'
PREV = '2026-09'


@pytest.fixture()
def world(app):
    with app.app_context():
        expense_service.seed_default_categories()
        teacher = TeacherModel(teacher_id_str='P4A', teacher_name='Ms Insight',
                               qualification='MA')
        klass = ClassModel(name='Phase 4', monthly_fee=2500.0)
        db.session.add_all([teacher, klass])
        db.session.flush()

        ali = StudentModel(roll_number=8500, student_name='Insight Ali',
                           father_name='F Ali', guardian_phone='03001118500',
                           address='X', class_id=klass.id, monthly_fee=2500.0)
        sara = StudentModel(roll_number=8501, student_name='Insight Sara',
                            father_name='F Sara', guardian_phone='03001118501',
                            address='X', class_id=klass.id, monthly_fee=1000.0)
        former = StudentModel(roll_number=8502, student_name='Left Student',
                              father_name='F Left', guardian_phone='03001118502',
                              address='X', class_id=klass.id, monthly_fee=1200.0,
                              is_active=False, status='slc_issued',
                              leaving_reason='moved', leaving_date=date(2026, 10, 10))
        db.session.add_all([ali, sara, former])
        db.session.commit()

        # September
        ensure_charge(ali, 'September 2026')
        ensure_charge(sara, 'September 2026')
        record_payment(ali, 'September 2026', 2500.0, method='cash',
                       payment_date=date(2026, 9, 15))
        utilities = ExpenseCategory.query.filter_by(name='Utilities').one()
        db.session.add(Expense(category_id=utilities.id, amount=500.0,
                               date=date(2026, 9, 20)))

        # October
        ensure_charge(ali, 'October 2026')
        ensure_charge(sara, 'October 2026')
        record_payment(ali, 'October 2026', 1500.0, method='cash',
                       payment_date=date(2026, 10, 5))
        record_payment(sara, 'October 2026', 1300.0, method='cash',
                       payment_date=date(2026, 10, 8))
        db.session.add(Expense(category_id=utilities.id, amount=2000.0,
                               date=date(2026, 10, 12)))

        payroll_service.generate(MONTH, {
            'include_%d' % teacher.id: 'on',
            'base_%d' % teacher.id: '3000',
            'bonus_%d' % teacher.id: '0',
            'deductions_%d' % teacher.id: '0',
        }, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=MONTH).one()
        record_salary_payment(record, 3000.0, payment_date=date(2026, 10, 25))

        # Inventory: buy 10 shirts @ 900, sell 2 @ 1,200.
        shirt = Product(name='P4 Shirt', category='Uniform',
                        sale_price_paisa=120000, min_stock_qty=5)
        db.session.add(shirt)
        db.session.commit()
        record_purchase(shirt, 10, 900.0, purchase_date=date(2026, 10, 1))
        record_sale(shirt, 2, sale_date=date(2026, 10, 6))
        db.session.commit()
        return {'teacher_id': teacher.id, 'shirt_id': shirt.id}


def test_metrics_hand_calculated(app, world):
    with app.app_context():
        m = report_insights.period_metrics(MONTH)

        assert m['enough_history'] is True
        # Cash basis (from the shared engine, unchanged meaning).
        assert m['cash']['cash_in'] == 5200.0
        assert m['cash']['cash_out'] == 14000.0      # 5,000 expenses + 9,000 stock
        assert m['cash']['net'] == -8800.0
        assert m['cash']['prev_net'] == 2000.0
        assert m['cash']['net_change'] == -10800.0
        assert m['cash']['cash_in_pct'] == 108.0     # 5,200 vs 2,500
        # Collection rate: 1,800 of 3,500 = 51.4% (September 2,500/3,500 = 71.4,
        # dragged by Sara's unpaid 1,000 — rate counts own-charge settlements).
        assert m['fees']['expected'] == 3500.0
        assert m['fees']['collected'] == 1800.0
        assert m['fees']['rate'] == 51.4
        assert m['fees']['prev_rate'] == 71.4
        assert m['fees']['rate_change'] == -20.0
        # Arrears: Sara's 1,000 recovered; nothing older remains.
        assert m['arrears']['recovered'] == 1000.0
        assert m['arrears']['recoverable'] == 0.0
        assert m['arrears']['rate'] == 100.0
        # Salary burden: 3,000 / 5,200 = 57.7% (September 0/2,500 = 0.0).
        assert m['salary_burden']['salary'] == 3000.0
        assert m['salary_burden']['burden'] == 57.7
        assert m['salary_burden']['prev_burden'] == 0.0
        # Expense trend: Utilities 500 -> 1,000 (+100.0%).
        utilities = next(t for t in m['expense_trends']
                         if t['name'] == 'Utilities')
        assert utilities == {'name': 'Utilities', 'current': 2000.0,
                             'previous': 500.0, 'change': 1500.0,
                             'pct': 300.0}
        # Sales performance (flag on): the spec's snapshot figures.
        assert m['sales']['revenue'] == 2400.0
        assert m['sales']['cogs'] == 1800.0
        assert m['sales']['gross_profit'] == 600.0
        assert m['sales']['purchases'] == 9000.0
        assert m['sales']['prev_revenue'] == 0.0
        assert m['operating_position'] == -1600.0    # 5,200 - 5,000 - 1,800
        # Students who left: 1 SLC-Issued at Rs 1,200/month.
        assert m['left_impact']['slc_issued'] == {
            'label': 'SLC Issued', 'count': 1, 'monthly': 1200.0}


def test_no_history_means_no_percentages(app):
    """A month whose previous month is empty stays silent, never divides by 0."""
    with app.app_context():
        klass = ClassModel(name='P4 Fresh', monthly_fee=1000.0)
        db.session.add(klass)
        db.session.flush()
        student = StudentModel(roll_number=8510, student_name='Fresh P4',
                               father_name='F Fresh',
                               guardian_phone='03001118510',
                               address='X', class_id=klass.id,
                               monthly_fee=1000.0)
        db.session.add(student)
        db.session.commit()
        ensure_charge(student, 'October 2026')
        record_payment(student, 'October 2026', 400.0, method='cash',
                       payment_date=date(2026, 10, 6))
        db.session.commit()

        m = report_insights.period_metrics(MONTH)
        assert m['enough_history'] is False
        # Nothing to compare against: no percentage anywhere.
        assert m['fees']['rate'] == 40.0             # 400 of 1,000
        assert m['fees']['prev_rate'] is None
        assert m['fees']['rate_change'] is None
        assert m['cash']['cash_in_pct'] is None
        assert m['cash']['cash_out_pct'] is None
        assert m['arrears']['rate'] is None
        assert m['salary_burden']['prev_burden'] is None
        for trend in m['expense_trends']:
            assert trend['pct'] is None


def test_insight_text_and_wording_rules(app, world):
    """Generated text: real figures, correct basis labels, no banned wording."""
    with app.app_context():
        lines = report_insights.insight_lines(MONTH)['lines']
        text = '\n'.join(lines)

        assert 'Fee collection is weaker than last month: 51.4% paid now, 71.4% last month.' in text
        assert 'Rs 1,000.00 of old unpaid fees was paid this month.' in text
        assert 'You received 108.0% more money than last month (Rs 5,200.00 now, Rs 2,500.00 last month).' in text
        assert 'Net Position is Rs 10,800.00 lower than last month.' in text
        assert 'Utilities spending went up 300.0% since last month (Rs 1,500.00 more).' in text
        assert 'Shop sales were Rs 2,400.00 and the items sold cost Rs 1,800.00 (profit on them: Rs 600.00).' in text
        # Owner requirement 1: a month WITH a purchase says purchases are
        # money paid out (Cash Out) but not expenses.
        assert ('Rs 9,000.00 was spent on buying stock. It is money paid out, '
                'but not an expense. The cost is counted when the items are '
                'sold.') in text
        assert ('Estimated Net Operating Position was Rs -1,600.00') in text
        assert 'Rs 1,200.00 less in monthly fees (estimate)' in text   # students who left

        # Owner requirement 2: wording rules on every generated line.
        for line in lines:
            if 'Net Position' in line:
                assert 'profit' not in line.lower(), line
            if 'Operating' in line:
                assert 'cash' not in line.lower(), line
        lowered = text.lower()
        assert 'predict' not in lowered and 'forecast' not in lowered
        assert 'artificial intelligence' not in lowered
        assert not __import__('re').search(r'\bAI\b', text)

        # Recommendations: actionable, rule-based.
        recs = '\n'.join(report_insights.recommendations(MONTH))
        assert "Only 51.4% of this month's fees are paid." in recs
        assert 'Utilities spending went up 300.0% since last month' in recs
        assert ('More money went out than came in this month (Net Position is '
                'below zero). Rs 9,000.00 of it was spent on stock, which you '
                'still have. It is not lost.') in recs
        for line in recs.split('\n'):
            if 'Net Position' in line:
                assert 'profit' not in line.lower(), line


def test_insights_page_renders(admin_client, app, world):
    body = admin_client.get('/financials/insights?month=%s' % MONTH).get_data(as_text=True)
    assert 'Fees paid this month' in body and '51.4%' in body
    assert 'Salaries vs money received' in body and '57.7%' in body
    assert 'Rs 10,800.00' in body                       # Net Position vs last month
    assert 'What changed since last month' in body
    assert 'Rs 9,000.00 was spent on buying stock. It is money paid out, but not an expense.' in body
    assert 'Estimated Net Operating Position' in body
    assert 'Utilities' in body and 'Rs 2,000.00' in body
    assert 'SLC Issued' in body and 'Rs 1,200.00' in body
    assert 'Financial Insights' in body                 # nav link
    assert 'What to do' in body
    assert 'Call the parents who have not paid yet.' in body


def test_insights_page_flag_off_hides_sales(app, admin_client, world):
    with app.app_context():
        app.config['FEATURE_INVENTORY_SALES'] = False
    try:
        body = admin_client.get('/financials/insights?month=%s' % MONTH).get_data(as_text=True)
        assert 'Estimated Net Operating Position' not in body
        assert 'was spent on buying stock' not in body
        assert 'profit on them' not in body
        assert 'Shop and stock' not in body
        assert 'Fees paid this month' in body           # cash/fee metrics remain
    finally:
        with app.app_context():
            app.config['FEATURE_INVENTORY_SALES'] = True


def test_insights_page_no_history(admin_client, app):
    with app.app_context():
        klass = ClassModel(name='P4 Page Fresh', monthly_fee=1000.0)
        db.session.add(klass)
        db.session.flush()
        student = StudentModel(roll_number=8520, student_name='Page Fresh P4',
                               father_name='F Fresh',
                               guardian_phone='03001118520',
                               address='X', class_id=klass.id,
                               monthly_fee=1000.0)
        db.session.add(student)
        db.session.commit()
        ensure_charge(student, 'October 2026')
        record_payment(student, 'October 2026', 400.0, method='cash',
                       payment_date=date(2026, 10, 6))
        db.session.commit()

    body = admin_client.get('/financials/insights?month=%s' % MONTH).get_data(as_text=True)
    assert 'Not enough history yet.' in body


def test_reports_hub_links_insights(admin_client, app):
    body = admin_client.get('/reports/hub?tab=finance').get_data(as_text=True)
    assert 'Financial Insights' in body
    assert 'Open insights' in body


def test_expenses_pdf_export_reusable(admin_client, app, world):
    """Spec: exportable expenses report — the existing route covers it."""
    response = admin_client.get('/expenses/export.pdf')
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.get_data()[:5] == b'%PDF-'


def test_expenses_xlsx_export_hand_calculated(admin_client, app, world):
    """Spec section 9 ("Exportable reports (PDF/Excel): ... expenses").

    Hand calculation for MONTH = 2026-10 and the ``world`` fixture.  The
    expense ledger is every ``Expense`` row in the month, and payroll writes
    one expense row per salary payment (payroll_service.record_salary_payment),
    so October holds:

        Utilities  Rs 2,000.00   2026-10-12
        Salaries   Rs 3,000.00   2026-10-25  (the paid teacher salary)

        TOTAL      Rs 5,000.00

    September's Rs 500.00 Utilities row is excluded by the month filter.
    """
    response = admin_client.get('/expenses/export.xlsx?month=%s' % MONTH)
    assert response.status_code == 200
    assert response.mimetype == (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    # XLSX files are ZIP containers, so they start with the ZIP signature.
    payload = response.get_data()
    assert payload[:2] == b'PK'

    sheet = load_workbook(BytesIO(payload)).active
    assert sheet.title == 'Expenses'
    grid = list(sheet.iter_rows(values_only=True))

    assert list(grid[0]) == ['Date', 'Category', 'Amount (Rs)', 'Payment Method',
                             'Receipt No', 'Description', 'Logged By']
    # Two data rows, then the TOTAL row.
    assert len(grid) == 4

    amounts = {}
    for row in grid[1:-1]:
        assert row[0] in ('2026-10-12', '2026-10-25'), row[0]
        amounts[row[1]] = row[2]
    assert amounts == {'Utilities': 2000.0, 'Salaries': 3000.0}

    # 2,000.00 + 3,000.00 = 5,000.00
    assert grid[-1][1] == 'TOTAL'
    assert grid[-1][2] == 5000.0
    assert grid[-1][2] == sum(amounts.values())

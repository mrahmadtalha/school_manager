"""Tests for financial period comparison on /financials/summary.

Covers period parsing (months, years, sessions), the comparison maths, the
page rendering, the comparison exports, and the query-count bound that keeps a
12-period comparison cheap.
"""

import csv
import io
from datetime import date, datetime

from app.database import db
from app.models import (
    Expense, ExpenseCategory, FeeTransaction, StaffPayroll, TeacherModel,
)
from app.services import financial_summary as fs
from app.services import payroll_service


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #

def _category(name='Comp Cat'):
    category = ExpenseCategory.query.filter_by(name=name).first()
    if category is None:
        category = ExpenseCategory(name=name)
        db.session.add(category)
        db.session.flush()
    return category


def _teacher():
    teacher = TeacherModel.query.first()
    if teacher is None:
        teacher = TeacherModel(teacher_id_str='TC1', teacher_name='Comp Teacher',
                               qualification='MA', monthly_salary=1000.0,
                               salary=1000.0)
        db.session.add(teacher)
        db.session.flush()
    return teacher


def _seed_month(month_key, revenue, expenses, payroll, paid=False):
    """One month of financial activity."""
    year, month = payroll_service.parse_month(month_key)
    category = _category()
    teacher = _teacher()
    day = date(year, month, 10)
    db.session.add(FeeTransaction(
        student_id=1, month_year=month_key, txn_type='payment', amount=revenue,
        is_void=False, created_at=datetime(year, month, 12, 10, 0)))
    if expenses:
        db.session.add(Expense(category_id=category.id, amount=expenses,
                               payment_method='Cash', date=day,
                               logged_by_name='tester'))
    if payroll:
        db.session.add(StaffPayroll(
            teacher_id=teacher.id, month_year=month_key, net_salary=payroll,
            payment_status='Paid' if paid else 'Pending'))
    db.session.flush()


def _month_offset_key(offset):
    return payroll_service.shift_month(payroll_service.current_month_key(), offset)


# --------------------------------------------------------------------------- #
# period parsing
# --------------------------------------------------------------------------- #

def test_period_descriptor_parses_months_years_and_sessions(app):
    with app.app_context():
        month = fs.period_descriptor('2026-09')
        assert month['kind'] == 'month'
        assert month['start'] == date(2026, 9, 1)
        assert month['end'] == date(2026, 9, 30)
        assert month['label'] == 'September 2026'

        year = fs.period_descriptor('year:2026')
        assert year['kind'] == 'year'
        assert year['start'] == date(2026, 1, 1)
        assert year['end'] == date(2026, 12, 31)
        assert year['label'] == '2026'

        session = fs.period_descriptor('session:2026')
        assert session['kind'] == 'session'
        assert session['start'] == date(2026, 4, 1)
        assert session['end'] == date(2027, 3, 31)
        assert '2026-2027' in session['label']


def test_period_descriptor_rejects_invalid_keys(app):
    with app.app_context():
        for bad in ('', None, 'nonsense', '2026-13', 'year:abc', 'year:1800',
                    'session:oops', 'session:1800'):
            assert fs.period_descriptor(bad) is None, bad


def test_months_in_range_spans_year_boundary(app):
    with app.app_context():
        months = fs.months_in_range(date(2026, 11, 1), date(2027, 2, 28))
        assert months == ['2026-11', '2026-12', '2027-01', '2027-02']
        assert fs.months_in_range(date(2026, 3, 1), date(2026, 3, 31)) == ['2026-03']


def test_session_bounds_are_april_to_march(app):
    with app.app_context():
        assert fs.session_bounds(2026) == (date(2026, 4, 1), date(2027, 3, 31))
        assert fs.current_session_start_year(date(2026, 4, 1)) == 2026
        assert fs.current_session_start_year(date(2026, 3, 31)) == 2025


# --------------------------------------------------------------------------- #
# comparison maths
# --------------------------------------------------------------------------- #

def test_period_snapshot_totals_are_correct(app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0, paid=True)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

        jan, feb = fs.period_snapshots(['2026-01', '2026-02'])
        assert jan['revenue'] == 1000.0
        assert jan['expenses'] == 100.0
        assert jan['payroll'] == 500.0
        assert jan['payroll_paid'] == 500.0
        assert jan['payroll_pending'] == 0.0
        assert jan['costs'] == 600.0
        assert jan['net'] == 400.0
        assert jan['month_count'] == 1

        assert feb['revenue'] == 2000.0
        assert feb['net'] == 1000.0
        assert feb['payroll_pending'] == 700.0


def test_year_period_equals_sum_of_its_months(app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

        year = fs.period_snapshots(['year:2026'])[0]
        assert year['revenue'] == 3000.0
        assert year['expenses'] == 400.0
        assert year['payroll'] == 1200.0
        assert year['net'] == 1400.0
        assert year['month_count'] == 12

        months = {m['month']: m for m in year['monthly']}
        assert len(year['monthly']) == 12
        assert months['2026-01']['net'] == 400.0
        assert months['2026-02']['net'] == 1000.0
        # Months with no activity are present but zero.
        assert months['2026-07']['net'] == 0.0


def test_voided_fee_payments_are_excluded(app):
    with app.app_context():
        _seed_month('2026-03', 500.0, 0.0, 0.0)
        db.session.add(FeeTransaction(
            student_id=1, month_year='2026-03', txn_type='payment', amount=9999.0,
            is_void=True, created_at=datetime(2026, 3, 15, 10, 0)))
        db.session.commit()

        snapshot = fs.period_snapshots(['2026-03'])[0]
        assert snapshot['revenue'] == 500.0


def test_two_period_comparison_reports_difference(app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

        snapshots = fs.period_snapshots(['2026-01', '2026-02'])
        result = fs.comparison_rows(snapshots)
        assert result['show_difference'] is True
        rows = {row['key']: row for row in result['rows']}

        assert rows['revenue']['amounts'] == [1000.0, 2000.0]
        assert rows['revenue']['difference'] == 1000.0
        assert rows['revenue']['difference_percent'] == 100.0
        assert rows['revenue']['direction'] == 'up'
        assert rows['revenue']['higher_is_better'] is True

        # Costs rising is reported as up, but flagged as "worse".
        assert rows['costs']['difference'] == 400.0
        assert rows['costs']['direction'] == 'up'
        assert rows['costs']['higher_is_better'] is False

        # Net change is surfaced as the headline highlight.
        assert result['highlight'][0]['change'] == 600.0
        assert result['highlight'][0]['improved'] is True


def test_difference_percent_when_previous_period_is_zero(app):
    with app.app_context():
        _seed_month('2026-01', 0.0, 0.0, 0.0)
        _seed_month('2026-02', 500.0, 0.0, 0.0)
        db.session.commit()

        rows = {row['key']: row
                for row in fs.comparison_rows(
                    fs.period_snapshots(['2026-01', '2026-02']))['rows']}
        assert rows['revenue']['difference'] == 500.0
        assert rows['revenue']['difference_percent'] == 100.0


def test_more_than_two_periods_omit_the_difference_column(app):
    with app.app_context():
        for index, key in enumerate(('2026-01', '2026-02', '2026-03'), 1):
            _seed_month(key, 100.0 * index, 10.0, 20.0)
        db.session.commit()

        result = fs.comparison_rows(fs.period_snapshots(['2026-01', '2026-02', '2026-03']))
        assert result['show_difference'] is False
        assert 'difference' not in result['rows'][0]
        assert result['highlight'] == []


def test_comparison_totals_sum_the_selected_periods(app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

        totals = fs.comparison_totals(fs.period_snapshots(['2026-01', '2026-02']))
        assert totals['revenue'] == 3000.0
        assert totals['expenses'] == 400.0
        assert totals['payroll'] == 1200.0
        assert totals['net'] == 1400.0


def test_mixed_month_and_year_periods_together(app):
    """A month beside a whole year — 'multiple data periods at the same time'."""
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

        snapshots = fs.period_snapshots(['2026-01', 'year:2026'])
        assert [s['kind'] for s in snapshots] == ['month', 'year']
        assert snapshots[0]['revenue'] == 1000.0
        assert snapshots[1]['revenue'] == 3000.0
        assert snapshots[0]['month_count'] == 1
        assert snapshots[1]['month_count'] == 12


def test_invalid_period_keys_are_ignored(app):
    with app.app_context():
        _seed_month('2026-01', 100.0, 0.0, 0.0)
        db.session.commit()
        assert fs.period_snapshots(['nonsense', '2026-13']) == []
        snapshots = fs.period_snapshots(['nonsense', '2026-01'])
        assert len(snapshots) == 1 and snapshots[0]['month_count'] == 1


# --------------------------------------------------------------------------- #
# efficiency bound
# --------------------------------------------------------------------------- #

def test_comparison_uses_a_bounded_number_of_queries(app):
    """Comparing N periods must not cost 3 queries per period.

    The window aggregation should stay flat as the period count grows, which is
    what keeps a 12-month comparison responsive.
    """
    from sqlalchemy import event

    with app.app_context():
        for offset in range(-6, 0):
            key = _month_offset_key(offset)
            _seed_month(key, 100.0, 10.0, 20.0)
        db.session.commit()

        engine = db.session.get_bind()
        counter = {'n': 0}

        def _before(*args, **kwargs):
            counter['n'] += 1

        event.listen(engine, 'before_cursor_execute', _before)
        try:
            counter['n'] = 0
            fs.period_snapshots([_month_offset_key(-1), _month_offset_key(-2)])
            two_period_queries = counter['n']

            counter['n'] = 0
            fs.period_snapshots([_month_offset_key(o) for o in range(-6, 0)])
            six_period_queries = counter['n']
        finally:
            event.remove(engine, 'before_cursor_execute', _before)

        # Flat: the same handful of grouped queries regardless of period count.
        assert two_period_queries == six_period_queries, (
            'comparison cost grew with period count: %d vs %d'
            % (two_period_queries, six_period_queries))
        # And it is a small constant, not 3 x periods.
        assert six_period_queries <= 6


# --------------------------------------------------------------------------- #
# page rendering
# --------------------------------------------------------------------------- #

def test_default_page_has_no_comparison_section(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 100.0, 0.0, 0.0)
        db.session.commit()

    body = admin_client.get('/financials/summary').get_data(as_text=True)
    # The single-month view is untouched...
    assert 'Financial Overview' in body
    assert 'Fee Collections' in body
    assert 'Expense Breakdown' in body
    # ...and comparison is offered but not active.
    assert 'Compare periods' in body
    assert 'id="comparisonTable"' not in body


def test_comparison_panel_lists_presets_and_months(admin_client, app):
    with app.app_context():
        _seed_month(_month_offset_key(-1), 100.0, 0.0, 0.0)
        db.session.commit()

    body = admin_client.get('/financials/summary').get_data(as_text=True)
    for label in ('This month vs last month', 'This month vs same month last year',
                  'Last 3 months', 'Last 6 months', 'Last 12 months',
                  'This year', 'Last year', 'This session (Apr–Mar)', 'Last session'):
        assert label in body, label
    assert 'name="periods"' in body
    assert 'Compare selected' in body


def test_preset_this_vs_last_month_renders_two_columns(admin_client, app):
    with app.app_context():
        _seed_month(_month_offset_key(-1), 111.0, 0.0, 0.0)
        _seed_month(_month_offset_key(0), 222.0, 0.0, 0.0)
        db.session.commit()
        current_label = fs.month_label(_month_offset_key(0))
        previous_label = fs.month_label(_month_offset_key(-1))

    body = admin_client.get(
        '/financials/summary?preset=this_vs_last').get_data(as_text=True)
    assert 'id="comparisonTable"' in body
    assert current_label in body
    assert previous_label in body
    # Two periods -> a difference column appears.
    assert 'Difference' in body
    # The headline "net position" change is explained in plain words.
    assert 'Net position' in body


def test_explicit_periods_selection_renders(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

    body = admin_client.get(
        '/financials/summary?periods=2026-01,2026-02').get_data(as_text=True)
    assert 'id="comparisonTable"' in body
    assert 'January 2026' in body and 'February 2026' in body
    assert 'Total' in body


def test_year_selection_shows_monthly_breakdown(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        db.session.commit()

    body = admin_client.get(
        '/financials/summary?periods=year:2026').get_data(as_text=True)
    assert 'id="comparisonTable"' in body
    assert 'month by month' in body
    assert '12 months' in body


def test_mixed_periods_render_together(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        db.session.commit()

    body = admin_client.get(
        '/financials/summary?periods=2026-01,year:2026').get_data(as_text=True)
    assert 'January 2026' in body
    assert '2026' in body
    assert 'id="comparisonTable"' in body


def test_selection_is_capped_and_explained(admin_client, app):
    with app.app_context():
        for offset in range(-14, 0):
            _seed_month(_month_offset_key(offset), 10.0, 0.0, 0.0)
        db.session.commit()
        keys = ','.join(_month_offset_key(-o) for o in range(1, 15))

    body = admin_client.get(
        f'/financials/summary?periods={keys}').get_data(as_text=True)
    assert 'id="comparisonTable"' in body
    # The user is told the list was shortened rather than silently truncated.
    assert 'Showing the first' in body


def test_unknown_preset_is_reported_not_crashed(admin_client, app):
    response = admin_client.get('/financials/summary?preset=does_not_exist')
    assert response.status_code == 200
    assert 'not recognised' in response.get_data(as_text=True)


def test_comparison_chart_payload_is_valid_json(admin_client, app):
    import json
    import re

    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

    body = admin_client.get(
        '/financials/summary?periods=2026-01,2026-02').get_data(as_text=True)
    match = re.search(r'<script id="cmpData" type="application/json">(.+?)</script>',
                      body, re.S)
    assert match, 'comparison chart payload missing'
    payload = json.loads(match.group(1))
    assert payload['labels'] == ['Jan 2026', 'Feb 2026']
    assert payload['revenue'] == [1000.0, 2000.0]
    assert payload['net'] == [400.0, 1000.0]


# --------------------------------------------------------------------------- #
# exports
# --------------------------------------------------------------------------- #

def test_comparison_csv_has_one_column_per_period(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

    response = admin_client.get(
        '/financials/summary/export.csv?periods=2026-01,2026-02')
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    header = next(r for r in rows if r and r[0] == 'Period')
    assert header == ['Period', 'January 2026', 'February 2026', 'Difference', 'Total']
    net_row = next(r for r in rows if r and r[0] == 'Net Surplus / (Deficit)')
    assert net_row[1:3] == ['400.00', '1000.00']
    # Monthly detail is included for each selected period.
    assert any('Monthly detail' in r for r in rows if r)


def test_comparison_pdf_is_valid(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        _seed_month('2026-02', 2000.0, 300.0, 700.0)
        db.session.commit()

    response = admin_client.get(
        '/financials/summary/export.pdf?periods=2026-01,2026-02')
    assert response.status_code == 200
    assert response.data.startswith(b'%PDF')
    assert 'attachment' in response.headers['Content-Disposition']


def test_single_month_exports_still_work(admin_client, app):
    """The pre-existing month exports must be unaffected by comparison mode."""
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        db.session.commit()

    csv_response = admin_client.get('/financials/summary/export.csv')
    assert csv_response.status_code == 200
    text = csv_response.get_data(as_text=True)
    assert 'Financial Summary' in text
    assert 'Difference' not in text

    pdf_response = admin_client.get('/financials/summary/export.pdf')
    assert pdf_response.status_code == 200
    assert pdf_response.data.startswith(b'%PDF')


def test_exports_fall_back_to_month_for_invalid_periods(admin_client, app):
    with app.app_context():
        _seed_month('2026-01', 1000.0, 100.0, 500.0)
        db.session.commit()

    response = admin_client.get('/financials/summary/export.csv?periods=nonsense')
    assert response.status_code == 200
    assert 'Financial Summary' in response.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# access control
# --------------------------------------------------------------------------- #

def test_comparison_page_still_requires_finance_roles(app, client, seed):
    """A signed-out visitor is bounced; a teacher is refused."""
    assert client.get('/financials/summary?preset=this_vs_last').status_code == 302

    from app.database import db as _db
    from app.models import AdminUser, ROLE_TEACHER
    from tests.conftest import login

    with app.app_context():
        if not AdminUser.query.filter_by(username='fin_teacher').first():
            user = AdminUser(username='fin_teacher', role=ROLE_TEACHER,
                             full_name='Fin Teacher')
            user.set_password('RolePass123')
            _db.session.add(user)
            _db.session.commit()

    login(client, 'fin_teacher', 'RolePass123')
    assert client.get('/financials/summary').status_code == 403
    assert client.get('/financials/summary?preset=this_vs_last').status_code == 403
    assert client.get(
        '/financials/summary/export.csv?periods=2026-01').status_code == 403

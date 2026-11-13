"""Plain-language alerts and insights shown on the Financial Overview."""

from app.services.payroll_service import shift_month

from .common import _inventory_enabled, _money
from .costs import expense_breakdown, salary_remaining_total
from .fees import (_period_fee_collection, _total_outstanding, collection_split,
                   former_students_summary, month_fee_buckets)
from .periods import all_months_in_period, period_descriptor
from .snapshots import month_snapshot


def summary_alerts(month_year):
    """Rule-based, plain-wording alerts for the summary page."""
    from flask import current_app

    drop_pct_threshold = current_app.config.get('ALERT_COLLECTION_DROP_PCT', 10)
    rise_pct_threshold = current_app.config.get('ALERT_EXPENSE_RISE_PCT', 20)
    min_change = current_app.config.get('ALERT_MIN_CHANGE_RUPEES', 1000)

    alerts = []
    snap = month_snapshot(month_year)
    buckets = month_fee_buckets(snap['start'], snap['end'])
    month_outstanding = _money(sum(buckets['outstanding'].values()) / 100.0)
    prev_key = shift_month(month_year, -1)
    prev_snap = month_snapshot(prev_key)
    prev_has_data = (prev_snap['cash_in'] or prev_snap['cash_out']
                     or prev_snap['payroll']
                     or any(buckets['charged'].get(m, 0)
                            for m in all_months_in_period(prev_snap)))

    if month_outstanding > 0:
        alerts.append({
            'kind': 'warning',
            'text': 'Rs %s of this month\'s fees is still remaining.'
                    % '{:,.2f}'.format(month_outstanding),
            'url': '/financials/student-outstanding?month=%s' % month_year,
            'link_text': 'See who owes'})
    total_outstanding = _total_outstanding()
    older_arrears = _money(max(0.0, total_outstanding - month_outstanding))
    if older_arrears > 0:
        alerts.append({
            'kind': 'warning',
            'text': 'Rs %s of older arrears is still recoverable.'
                    % '{:,.2f}'.format(older_arrears),
            'url': '/financials/student-outstanding',
            'link_text': 'See the dues list'})

    former = former_students_summary()
    if former['count'] > 0:
        alerts.append({
            'kind': 'warning',
            'text': '%d former student(s) owe Rs %s.'
                    % (former['count'], '{:,.2f}'.format(former['total'])),
            'url': '/financials/student-outstanding?status=former',
            'link_text': 'View their dues'})

    salary_unpaid = salary_remaining_total()
    if salary_unpaid > 0:
        alerts.append({
            'kind': 'warning',
            'text': 'Rs %s of salary is still unpaid.'
                    % '{:,.2f}'.format(salary_unpaid),
            'url': '/payroll',
            'link_text': 'Open payroll'})

    split = collection_split(month_year)
    if split['arrears'] > 0:
        alerts.append({
            'kind': 'info',
            'text': 'Rs %s of older arrears was recovered this month.'
                    % '{:,.2f}'.format(split['arrears']),
            'url': '/fees',
            'link_text': 'Open fees'})

    current_collection = split['current']
    previous_collection = collection_split(prev_key)['current']
    if prev_has_data and previous_collection > 0:
        drop = previous_collection - current_collection
        drop_pct = round(drop * 100.0 / previous_collection, 1)
        if drop > 0 and drop_pct >= drop_pct_threshold and drop >= min_change:
            alerts.append({
                'kind': 'warning',
                'text': 'Fee collection is %s%% lower than last month.'
                        % '{:,.1f}'.format(drop_pct),
                'url': '/fees',
                'link_text': 'Open fees'})

    current_categories = {row['name']: row['total']
                          for row in expense_breakdown(snap['start'], snap['end'])}
    previous_categories = {row['name']: row['total']
                           for row in expense_breakdown(prev_snap['start'],
                                                        prev_snap['end'])}
    for name, total in current_categories.items():
        previous_total = previous_categories.get(name, 0.0)
        rise = total - previous_total
        if previous_total > 0 and rise > 0:
            rise_pct = round(rise * 100.0 / previous_total, 1)
            if rise_pct >= rise_pct_threshold and rise >= min_change:
                alerts.append({
                    'kind': 'warning',
                    'text': '%s expenses are up %s%% vs last month (+Rs %s).'
                            % (name, '{:,.1f}'.format(rise_pct),
                               '{:,.2f}'.format(rise)),
                    'url': '/expenses',
                    'link_text': 'Open expenses'})

    if _inventory_enabled():
        from app.services import inventory_service
        low = inventory_service.low_stock_list()
        if low:
            names = ', '.join('%s (%d left)' % (p.name, p.stock_qty)
                              for p in low[:3])
            more = ' and %d more' % (len(low) - 3) if len(low) > 3 else ''
            alerts.append({
                'kind': 'warning',
                'text': 'Low stock: %s%s.' % (names, more),
                'url': '/inventory',
                'link_text': 'Open inventory'})
    return alerts


def summary_insights(month_year):
    """A short 'What changed' text built only from real numbers."""
    snap = month_snapshot(month_year)
    buckets = month_fee_buckets(snap['start'], snap['end'])
    prev_key = shift_month(month_year, -1)
    prev_snap = month_snapshot(prev_key)
    prev_has_data = (prev_snap['cash_in'] or prev_snap['cash_out']
                     or prev_snap['payroll']
                     or any(buckets['charged'].get(m, 0)
                            for m in all_months_in_period(prev_snap)))
    if not prev_has_data:
        return {'enough_history': False, 'lines': ['Not enough history yet.']}

    lines = []
    current_collection, _ = _period_fee_collection(
        period_descriptor(month_year))
    previous_collection, _ = _period_fee_collection(
        period_descriptor(prev_key))
    if previous_collection > 0:
        change_pct = round((current_collection - previous_collection) * 100.0
                           / previous_collection, 1)
        if change_pct >= 0:
            lines.append('Fee collection is %s%% higher than last month.'
                         % '{:,.1f}'.format(change_pct))
        else:
            lines.append('Fee collection is %s%% lower than last month.'
                         % '{:,.1f}'.format(-change_pct))
    net_change = _money(snap['net'] - prev_snap['net'])
    if net_change >= 0:
        lines.append('Net Position improved by Rs %s (cash basis).'
                     % '{:,.2f}'.format(net_change))
    else:
        lines.append('Net Position fell by Rs %s (cash basis).'
                     % '{:,.2f}'.format(-net_change))

    current_categories = {row['name']: row['total']
                          for row in expense_breakdown(snap['start'], snap['end'])}
    previous_categories = {row['name']: row['total']
                           for row in expense_breakdown(prev_snap['start'],
                                                        prev_snap['end'])}
    biggest = None
    for name, total in current_categories.items():
        previous_total = previous_categories.get(name, 0.0)
        if previous_total > 0:
            rise_pct = round((total - previous_total) * 100.0 / previous_total, 1)
            if rise_pct > 0 and (biggest is None or rise_pct > biggest[1]):
                biggest = (name, rise_pct)
    if biggest:
        lines.append('%s is up %s%% vs last month.' % (biggest[0],
                                                       '{:,.1f}'.format(biggest[1])))
    total_outstanding = _total_outstanding()
    if total_outstanding > 0:
        lines.append('About Rs %s in fees is still outstanding (estimated).'
                     % '{:,.2f}'.format(total_outstanding))
    salary_unpaid = salary_remaining_total()
    if salary_unpaid > 0:
        lines.append('Rs %s of salary is still unpaid (estimated).'
                     % '{:,.2f}'.format(salary_unpaid))
    return {'enough_history': True, 'lines': lines}

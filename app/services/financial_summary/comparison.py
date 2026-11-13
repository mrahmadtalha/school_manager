"""Period comparison: the metric rows, totals and the side-by-side comparison of two periods."""

from datetime import date, timedelta

from app.services.payroll_service import shift_month

from .common import _inventory_enabled, _money
from .fees import (_billed_students_count, _formers_left_count, _period_fee_collection,
                   month_fee_buckets)
from .periods import (all_months_in_period, current_session_start_year, period_descriptor)
from .snapshots import _window_totals, period_snapshot


#: Metrics shown in the comparison grid: (key, label, help text).
COMPARISON_METRICS = (
    ('revenue', 'Cash In — Fee Collections', 'Fee payments received in the period (cash)'),
    ('payroll', 'Salaries Paid (Cash)', 'Salary payments made in the period (cash)'),
    ('expenses', 'Cash Out — All Expenses', 'All expenses paid, salaries included (cash)'),
    ('payroll_accrual', 'Salary Payable (Accrual)', 'Net salaries recorded for the period'),
    ('net', 'Net Position', 'Cash In minus Cash Out'),
)


def comparison_rows(snapshots):
    """Metric rows for the comparison grid.

    Each row carries one value per period plus, when exactly two periods are
    selected, how much the second differs from the first.
    """
    show_difference = len(snapshots) == 2
    rows = []
    for key, label, help_text in COMPARISON_METRICS:
        values = [snapshot.get('payroll' if key == 'payroll_accrual' else key, 0.0)
                  for snapshot in snapshots]
        row = {'key': key, 'label': label, 'help': help_text, 'amounts': values}
        if show_difference:
            before, after = values[0], values[1]
            change = _money(after - before)
            if before:
                percent = round((change / abs(before)) * 100, 1)
            else:
                percent = None if not after else 100.0
            row['difference'] = change
            row['difference_percent'] = percent
            row['direction'] = 'up' if change > 0 else ('down' if change < 0 else 'flat')
            # For costs a rise is worse; the template decides the colour.
            row['higher_is_better'] = key in ('revenue', 'net')
        rows.append(row)
        if key == 'revenue' and _inventory_enabled():
            # Phase 3b: sales receipts sit inside Cash In — show them apart.
            values = [snapshot.get('sales', 0.0) for snapshot in snapshots]
            row = {'key': 'sales', 'label': 'of which Sales (inventory)',
                   'help': 'Uniform/book/stationery sales receipts, included in Cash In',
                   'amounts': values}
            if show_difference:
                before, after = values[0], values[1]
                change = _money(after - before)
                row['difference'] = change
                row['difference_percent'] = (
                    round((change / abs(before)) * 100, 1) if before
                    else (None if not after else 100.0))
                row['direction'] = ('up' if change > 0
                                    else ('down' if change < 0 else 'flat'))
                row['higher_is_better'] = True
            rows.append(row)

    highlight = []
    if show_difference:
        first, second = snapshots
        highlight = [
            {'label': 'Net position', 'first': first['net'], 'second': second['net'],
             'change': _money(second['net'] - first['net']),
             'improved': second['net'] >= first['net']},
        ]
    return {'rows': rows, 'show_difference': show_difference,
            'highlight': highlight}


def comparison_totals(snapshots):
    """Column totals across all selected periods (the TOTAL column)."""
    return {
        'label': 'Total',
        'revenue': _money(sum(s['revenue'] for s in snapshots)),
        'payroll': _money(sum(s['payroll'] for s in snapshots)),
        'expenses': _money(sum(s['expenses'] for s in snapshots)),
        'sales': _money(sum(s.get('sales', 0.0) for s in snapshots)),
        'cash_out': _money(sum(s['cash_out'] for s in snapshots)),
        'net': _money(sum(s['net'] for s in snapshots)),
    }


def _comparison_metric_rows(current, previous, no_earlier_data):
    """Metric rows for one comparison, with plain-language changes."""
    money_metrics = [
        ('Cash In', 'cash_in'),
        ('Fee Collection', 'fee_collection'),
    ]
    if _inventory_enabled():
        # Sales receipts are inside Cash In; show them apart (Phase 3b).
        money_metrics.append(('of which Sales (inventory)', 'sales'))
    money_metrics += [
        ('Cash Out', 'cash_out'),
        ('Salaries Paid', 'salaries_paid'),
        ('Other Expenses', 'other_expenses'),
        ('Net Position', 'net'),
        ('Fees Remaining at period end', 'fees_remaining_period'),
    ]
    count_metrics = (
        ('Students billed', 'students_billed'),
        ('Former students (left in period)', 'formers_left'),
    )
    rows = []
    for name, key in money_metrics:
        cur = _money(current.get(key) or 0.0)
        prev = _money(previous.get(key) or 0.0)
        change = _money(cur - prev)
        pct = None
        if no_earlier_data:
            change_text = 'No earlier data'
        elif prev == 0:
            change_text = 'new this period' if cur > 0 else 'unchanged'
        else:
            pct = round(change * 100.0 / prev, 1)
            word = 'higher' if change > 0 else 'lower'
            change_text = 'Rs %s %s (%s%%)' % (
                '{:,.2f}'.format(abs(change)), word, '{:,.1f}'.format(abs(pct)))
        rows.append({'name': name, 'kind': 'money', 'current': cur,
                     'previous': prev, 'change': change, 'pct': pct,
                     'change_text': change_text, 'no_earlier_data': no_earlier_data})
    for name, key in count_metrics:
        cur = int(current.get(key) or 0)
        prev = int(previous.get(key) or 0)
        change = cur - prev
        if no_earlier_data:
            change_text = 'No earlier data'
        elif change == 0:
            change_text = 'unchanged'
        else:
            change_text = '%d more' % change if change > 0 else '%d fewer' % (-change)
        rows.append({'name': name, 'kind': 'count', 'current': cur,
                     'previous': prev, 'change': change, 'pct': None,
                     'change_text': change_text, 'no_earlier_data': no_earlier_data})
    return rows


def build_comparison(title, current_desc, previous_desc):
    """One comparison: two periods through the shared engine + metric rows."""
    start = min(current_desc['start'], previous_desc['start'])
    end = max(current_desc['end'], previous_desc['end'])
    window = _window_totals(start, end)
    buckets = month_fee_buckets(start, end)
    current = period_snapshot(current_desc, window['revenue'], window['expenses'],
                              window['payroll'],
                              outstanding=buckets['outstanding'],
                              other_income=window['other_income'],
                              sales=window['sales_revenue'],
                              sales_cogs=window['sales_cogs'],
                              purchases=window['purchases'],
                              package_cogs=window['package_cogs'])
    previous = period_snapshot(previous_desc, window['revenue'], window['expenses'],
                               window['payroll'],
                               outstanding=buckets['outstanding'],
                               other_income=window['other_income'],
                               sales=window['sales_revenue'],
                               sales_cogs=window['sales_cogs'],
                               purchases=window['purchases'],
                               package_cogs=window['package_cogs'])
    for snap, desc in ((current, current_desc), (previous, previous_desc)):
        collected, arrears = _period_fee_collection(desc)
        snap['fee_collection'] = collected
        snap['arrears_recovered_period'] = arrears
        snap['students_billed'] = _billed_students_count(desc['start'], desc['end'])
        snap['formers_left'] = _formers_left_count(desc['start'], desc['end'])
    no_earlier_data = (
        previous['cash_in'] == 0 and previous['cash_out'] == 0
        and previous['payroll'] == 0
        and all(buckets['charged'].get(m, 0) == 0
                for m in all_months_in_period(previous_desc)))
    return {'title': title,
            'current': current, 'previous': previous,
            'rows': _comparison_metric_rows(current, previous, no_earlier_data),
            'no_earlier_data': no_earlier_data}


def summary_comparisons(month_year, range_start=None, range_end=None):
    """The three Phase 2b comparisons for the summary page."""
    packs = []
    prev_month = shift_month(month_year, -1)
    packs.append(build_comparison(
        'This month vs previous month',
        period_descriptor(month_year), period_descriptor(prev_month)))

    session_year = current_session_start_year(
        date(int(month_year[:4]), int(month_year[5:]), 1))
    packs.append(build_comparison(
        'This session vs previous session',
        period_descriptor('session:%d' % session_year),
        period_descriptor('session:%d' % (session_year - 1))))

    custom = None
    try:
        start = date.fromisoformat(range_start) if range_start else None
        end = date.fromisoformat(range_end) if range_end else None
    except (TypeError, ValueError):
        start = end = None
    if start and end and start <= end:
        length = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        current_desc = {'key': 'custom:current', 'kind': 'custom',
                        'start': start, 'end': end,
                        'label': '%s to %s' % (start.strftime('%d %b %Y'),
                                               end.strftime('%d %b %Y')),
                        'short_label': start.strftime('%d %b')}
        previous_desc = {'key': 'custom:previous', 'kind': 'custom',
                         'start': prev_start, 'end': prev_end,
                         'label': '%s to %s' % (prev_start.strftime('%d %b %Y'),
                                                prev_end.strftime('%d %b %Y')),
                         'short_label': prev_start.strftime('%d %b')}
        custom = build_comparison('Custom range vs preceding period',
                                  current_desc, previous_desc)
    return packs, custom

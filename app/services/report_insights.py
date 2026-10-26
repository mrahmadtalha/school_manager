"""Phase 4: rule-based report metrics for /financials/insights.

Every figure here is a ratio, comparison or threshold check on numbers
produced by the SHARED period engine (financial_summary.month_snapshot,
fee_month_overview, collection_split, month_fee_buckets, expense_breakdown,
former_revenue_impact) and inventory_service — nothing is calculated a
second way, so these metrics always reconcile with the summary page.

Rule-based only: comparisons, percentages, thresholds on real recorded data.
No prediction, no forecasting — wording states what already happened.
"""
from app.services import financial_summary as fs
from app.services import inventory_service


def _pct(change, base):
    """Percentage change, or None when the base is zero (never divide by 0)."""
    if not base:
        return None
    return round(change * 100.0 / base, 1)


def period_metrics(month_year):
    """All Phase 4 metrics for one month, hand-ready for the page.

    ``enough_history`` is False when the previous month carries no recorded
    activity at all — comparisons then stay silent instead of showing
    percentages against nothing.
    """
    prev_key = fs.shift_month(month_year, -1)
    snap = fs.month_snapshot(month_year)
    prev_snap = fs.month_snapshot(prev_key)
    fee = fs.fee_month_overview(month_year)
    prev_fee = fs.fee_month_overview(prev_key)
    buckets = fs.month_fee_buckets(snap['start'], snap['end'])
    prev_buckets = fs.month_fee_buckets(prev_snap['start'], prev_snap['end'])

    prev_has_data = (prev_snap['cash_in'] or prev_snap['cash_out']
                     or prev_snap['payroll']
                     or any(prev_buckets['charged'].get(m, 0)
                            for m in fs.all_months_in_period(prev_snap)))

    # --- Fee collection rate (current-month charges only, per spec) --------
    rate_change = (round(fee['rate'] - prev_fee['rate'], 1)
                   if fee['rate'] is not None and prev_fee['rate'] is not None
                   else None)

    # --- Arrears recovery ---------------------------------------------------
    month_outstanding = fs._money(
        sum(buckets['outstanding'].values()) / 100.0)
    total_outstanding = fs._total_outstanding()
    recoverable = fs._money(max(0.0, total_outstanding - month_outstanding))
    recovered = snap['arrears_recovered']
    arrears_rate = (round(recovered * 100.0 / (recovered + recoverable), 1)
                    if (recovered + recoverable) > 0 else None)

    # --- Salary burden: salaries paid as a share of Cash In -----------------
    burden = (round(snap['salaries_paid'] * 100.0 / snap['cash_in'], 1)
              if snap['cash_in'] > 0 else None)
    prev_burden = (round(prev_snap['salaries_paid'] * 100.0
                         / prev_snap['cash_in'], 1)
                   if prev_snap['cash_in'] > 0 else None)

    # --- Expense trends per category (Salaries excluded by the engine) ------
    current_cats = {row['name']: row['total'] for row in
                    fs.expense_breakdown(snap['start'], snap['end'])}
    previous_cats = {row['name']: row['total'] for row in
                     fs.expense_breakdown(prev_snap['start'], prev_snap['end'])}
    trends = []
    for name in sorted(set(current_cats) | set(previous_cats)):
        current = current_cats.get(name, 0.0)
        previous = previous_cats.get(name, 0.0)
        change = fs._money(current - previous)
        trends.append({'name': name, 'current': current, 'previous': previous,
                       'change': change, 'pct': _pct(change, previous)})

    # --- Income vs expenses (cash basis) ------------------------------------
    net_change = fs._money(snap['net'] - prev_snap['net'])

    # --- Sales performance (Phase 3b, flag-gated) ---------------------------
    sales = None
    if inventory_service.inventory_enabled():
        now = inventory_service.month_sales_breakdown(snap['start'], snap['end'])
        prev = inventory_service.month_sales_breakdown(prev_snap['start'],
                                                       prev_snap['end'])
        sales_now, cogs_now = now['sales'], now['cogs']
        sales_prev, cogs_prev = prev['sales'], prev['cogs']
        sales = {
            'revenue': sales_now, 'cogs': cogs_now,
            # Profit on items sold separately; the cost of stock handed over
            # inside admission packages is reported on its own line.
            'package_cogs': now['package_cogs'],
            'gross_profit': fs._money(sales_now - now['direct_cogs']),
            'prev_revenue': sales_prev, 'prev_cogs': cogs_prev,
            'prev_gross_profit': fs._money(sales_prev - prev['direct_cogs']),
            'purchases': snap['purchases'],
            'low_stock': inventory_service.low_stock_list(),
        }

    return {
        'month': month_year,
        'label': snap['label'],
        'enough_history': bool(prev_has_data),
        'cash': {
            'cash_in': snap['cash_in'], 'cash_out': snap['cash_out'],
            'net': snap['net'],
            'prev_cash_in': prev_snap['cash_in'],
            'prev_cash_out': prev_snap['cash_out'],
            'prev_net': prev_snap['net'],
            'net_change': net_change,
            'cash_in_pct': _pct(snap['cash_in'] - prev_snap['cash_in'],
                                prev_snap['cash_in']),
            'cash_out_pct': _pct(snap['cash_out'] - prev_snap['cash_out'],
                                 prev_snap['cash_out']),
        },
        'fees': {
            'expected': fee['expected'], 'collected': fee['collected'],
            'remaining': fee['remaining'], 'rate': fee['rate'],
            'prev_rate': prev_fee['rate'], 'rate_change': rate_change,
        },
        'arrears': {
            'recovered': recovered, 'recoverable': recoverable,
            'rate': arrears_rate, 'total_outstanding': total_outstanding,
        },
        'salary_burden': {
            'salary': snap['salaries_paid'], 'cash_in': snap['cash_in'],
            'burden': burden, 'prev_burden': prev_burden,
        },
        'expense_trends': trends,
        'sales': sales,
        'left_impact': fs.former_revenue_impact(),
        'operating_position': snap['operating_position'],
        'purchases': snap['purchases'],
    }


# Wording rules (owner requirement): Net Position is never called "profit",
# the Estimated Net Operating Position is never called "cash", and no line
# claims AI or prediction — these are comparisons of recorded data only.

def insight_lines(month_year):
    """Generated text from real data — one fact per line, or a silence guard."""
    m = period_metrics(month_year)
    if not m['enough_history']:
        return {'enough_history': False, 'lines': ['Not enough history yet.']}

    money = lambda v: '{:,.2f}'.format(v)
    lines = []

    fee = m['fees']
    if fee['rate'] is not None and fee['prev_rate'] is not None:
        points = round(fee['rate'] - fee['prev_rate'], 1)
        word = 'improved' if points >= 0 else 'dropped'
        lines.append('Fee collection rate %s by %s percentage points '
                     '(this month %s%%, last month %s%%).'
                     % (word, '{:,.1f}'.format(abs(points)),
                        '{:,.1f}'.format(fee['rate']),
                        '{:,.1f}'.format(fee['prev_rate'])))

    if m['arrears']['recovered'] > 0:
        lines.append('Rs %s of older arrears was recovered this month.'
                     % money(m['arrears']['recovered']))

    cash = m['cash']
    if cash['cash_in_pct'] is not None:
        word = 'higher' if cash['cash_in'] >= cash['prev_cash_in'] else 'lower'
        lines.append('Cash In was %s%% %s than last month (Rs %s vs Rs %s).'
                     % ('{:,.1f}'.format(abs(cash['cash_in_pct'])), word,
                        money(cash['cash_in']), money(cash['prev_cash_in'])))
    if cash['net_change'] >= 0:
        lines.append('Net Position improved by Rs %s (cash basis).'
                     % money(cash['net_change']))
    else:
        lines.append('Net Position fell by Rs %s (cash basis).'
                     % money(-cash['net_change']))

    biggest = None
    for trend in m['expense_trends']:
        if trend['pct'] is not None and trend['pct'] > 0 and \
                (biggest is None or trend['pct'] > biggest['pct']):
            biggest = trend
    if biggest:
        lines.append('%s expenses rose %s%% vs last month (+Rs %s).'
                     % (biggest['name'], '{:,.1f}'.format(biggest['pct']),
                        money(biggest['change'])))

    if m['sales'] is not None:
        sales = m['sales']
        if sales['revenue'] > 0 or sales['prev_revenue'] > 0:
            lines.append('Inventory sales were Rs %s with cost of goods sold '
                         'Rs %s (gross profit Rs %s).'
                         % (money(sales['revenue']),
                            money(sales['cogs'] - sales['package_cogs']),
                            money(sales['gross_profit'])))
        if sales.get('package_cogs'):
            lines.append('Books and uniform worth Rs %s (at cost) were given '
                         'inside admission packages - their price is already '
                         'part of the admission fees.'
                         % money(sales['package_cogs']))
        if sales['purchases'] > 0:
            lines.append('Stock purchases of Rs %s are part of Cash Out but '
                         'not expenses; their cost enters Cost of Goods Sold '
                         'when the items sell.' % money(sales['purchases']))
        lines.append('Estimated Net Operating Position was Rs %s '
                     '(Revenue minus Salaries, Operating Expenses and Cost of '
                     'Goods Sold — an operating estimate, not money movement).'
                     % money(m['operating_position']))

    left_total = sum(entry['monthly'] for entry in m['left_impact'].values())
    if left_total > 0:
        lines.append('Students who left reduce estimated monthly revenue by '
                     'Rs %s (estimate).' % money(left_total))
    return {'enough_history': True, 'lines': lines}


def recommendations(month_year):
    """Actionable, rule-based follow-ups; empty when there is nothing to act on."""
    m = period_metrics(month_year)
    money = lambda v: '{:,.2f}'.format(v)
    items = []

    if m['arrears']['recoverable'] > 0:
        items.append('Recover older arrears: Rs %s from earlier months is '
                     'still unpaid — see the dues list.'
                     % money(m['arrears']['recoverable']))
    fee = m['fees']
    if fee['expected'] > 0 and fee['rate'] is not None and fee['rate'] < 80:
        items.append('This month\'s fee collection is at %s%% — follow up '
                     'with pending payers.'
                     % '{:,.1f}'.format(fee['rate']))
    if m['arrears']['total_outstanding'] > 0:
        items.append('Rs %s in fees is outstanding in total — send reminders '
                     'to the largest dues first.'
                     % money(m['arrears']['total_outstanding']))

    from flask import current_app
    rise_pct_threshold = current_app.config.get('ALERT_EXPENSE_RISE_PCT', 20)
    min_change = current_app.config.get('ALERT_MIN_CHANGE_RUPEES', 1000)
    for trend in m['expense_trends']:
        if (trend['pct'] or 0) >= rise_pct_threshold and \
                trend['change'] >= min_change:
            items.append('%s expenses rose %s%% vs last month — check for '
                         'unusual usage or one-off purchases.'
                         % (trend['name'], '{:,.1f}'.format(trend['pct'])))

    if m['sales'] is not None and m['sales']['low_stock']:
        names = ', '.join('%s (%d left)' % (p.name, p.stock_qty)
                          for p in m['sales']['low_stock'][:3])
        more = (' and %d more' % (len(m['sales']['low_stock']) - 3)
                if len(m['sales']['low_stock']) > 3 else '')
        items.append('Restock soon: %s%s %s below minimum stock.'
                     % (names, more,
                        'is' if len(m['sales']['low_stock']) == 1 else 'are'))

    if m['cash']['net'] < 0:
        line = 'Net Position is negative this month.'
        if m['sales'] is not None and m['purchases'] > 0:
            line = ('Net Position is negative this month. Stock purchases of '
                    'Rs %s are held as inventory, not lost.'
                    % money(m['purchases']))
        items.append(line)
    return items

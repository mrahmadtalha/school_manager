"""Financial overview: fee revenue vs payroll + expenses, net position and trends."""
import csv
import io
from datetime import date, datetime

from app.database import db
from app.models import Expense, ExpenseCategory, FeeTransaction, StaffPayroll, TeacherModel
from app.services.payroll_service import (month_bounds, month_label, parse_month,
                                          recent_month_keys)


def short_label(month_year):
    parsed = parse_month(month_year)
    return date(parsed[0], parsed[1], 1).strftime('%b %Y') if parsed else ''


def _money(value):
    return round(float(value or 0), 2)


# --------------------------------------------------------------------------- #
# Core numbers
# --------------------------------------------------------------------------- #

def fee_collections(start, end):
    """Fee payments received within the window (voided transactions excluded)."""
    if not start or not end:
        return 0.0
    rows = FeeTransaction.query.filter(
        FeeTransaction.txn_type == 'payment',
        FeeTransaction.is_void.is_(False),
        FeeTransaction.created_at >= datetime.combine(start, datetime.min.time()),
        FeeTransaction.created_at <= datetime.combine(end, datetime.max.time()),
    ).all()
    return _money(sum(r.amount or 0 for r in rows))


def expenses_total(start, end):
    if not start or not end:
        return 0.0
    total = (Expense.query
             .filter(Expense.date >= start, Expense.date <= end)
             .with_entities(db.func.coalesce(db.func.sum(Expense.amount), 0.0))
             .scalar())
    return _money(total)


def payroll_snapshot(month_year):
    records = StaffPayroll.query.filter_by(month_year=month_year).all()
    total = _money(sum(r.net_salary or 0 for r in records))
    paid = _money(sum(r.net_salary or 0 for r in records
                      if r.payment_status == 'Paid'))
    return {'total': total, 'paid': paid, 'pending': _money(total - paid),
            'count': len(records)}


def month_snapshot(month_year):
    start, end = month_bounds(month_year)
    revenue = fee_collections(start, end)
    expenses = expenses_total(start, end)
    payroll = payroll_snapshot(month_year)
    return {
        'month': month_year,
        'label': month_label(month_year),
        'start': start,
        'end': end,
        'revenue': revenue,
        'expenses': expenses,
        'payroll': payroll['total'],
        'payroll_paid': payroll['paid'],
        'payroll_pending': payroll['pending'],
        'payroll_count': payroll['count'],
        'costs': _money(expenses + payroll['total']),
        'net': _money(revenue - expenses - payroll['total']),
    }


def expense_breakdown(start, end):
    if not start or not end:
        return []
    rows = (db.session.query(
                ExpenseCategory.name,
                db.func.coalesce(db.func.sum(Expense.amount), 0.0),
                db.func.count(Expense.id))
            .join(Expense, Expense.category_id == ExpenseCategory.id)
            .filter(Expense.date >= start, Expense.date <= end)
            .group_by(ExpenseCategory.id)
            .order_by(db.func.sum(Expense.amount).desc())
            .all())
    return [{'name': name, 'total': _money(total), 'count': count}
            for name, total, count in rows]


def payroll_rows(month_year):
    return (StaffPayroll.query
            .join(TeacherModel)
            .filter(StaffPayroll.month_year == month_year)
            .order_by(TeacherModel.teacher_name).all())


def trend_series(end_month, count=6):
    series = []
    for month in recent_month_keys(end_month, count):
        snapshot = month_snapshot(month)
        series.append({
            'month': month,
            'label': short_label(month),
            'revenue': snapshot['revenue'],
            'payroll': snapshot['payroll'],
            'expenses': snapshot['expenses'],
            'net': snapshot['net'],
        })
    return series


# --------------------------------------------------------------------------- #
# Period comparison
#
# A "period" is either one month ('2026-09') or a whole year / academic
# session ('year:2026', 'session:2026-2027').  Comparing periods is done from
# a single window aggregation rather than one snapshot per period, so showing
# twelve months costs three grouped queries instead of thirty-six.
# --------------------------------------------------------------------------- #

def session_bounds(start_year):
    """April-to-March academic session starting in ``start_year``."""
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def current_session_start_year(today=None):
    """Academic sessions run April-March, matching the rest of the app."""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def months_in_range(start, end):
    """Every 'YYYY-MM' key touched by the inclusive date range."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append('%04d-%02d' % (year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def all_months_in_period(period):
    """Every calendar month a period spans (a month period spans exactly one)."""
    return months_in_range(period['start'], period['end'])


def period_descriptor(key):
    """Parse one period key into a descriptor, or None when it is invalid.

    Accepted forms:
      '2026-09'            -> a single month
      'year:2026'          -> the calendar year (Jan-Dec)
      'session:2026-2027'  -> the academic session (Apr 2026 - Mar 2027)
    """
    key = (key or '').strip()
    if not key:
        return None

    if key.startswith('session:'):
        raw = key.split(':', 1)[1].strip()
        try:
            start_year = int(raw.split('-')[0])
        except (ValueError, IndexError):
            return None
        if not 2000 <= start_year <= 2100:
            return None
        start, end = session_bounds(start_year)
        return {'key': key, 'kind': 'session', 'start': start, 'end': end,
                'label': 'Session %d-%d' % (start_year, start_year + 1),
                'short_label': 'Session %d-%02d' % (start_year, (start_year + 1) % 100)}

    if key.startswith('year:'):
        raw = key.split(':', 1)[1].strip()
        try:
            year = int(raw)
        except ValueError:
            return None
        if not 2000 <= year <= 2100:
            return None
        return {'key': key, 'kind': 'year', 'start': date(year, 1, 1),
                'end': date(year, 12, 31), 'label': str(year),
                'short_label': str(year)}

    if parse_month(key):
        start, end = month_bounds(key)
        return {'key': key, 'kind': 'month', 'start': start, 'end': end,
                'label': month_label(key), 'short_label': short_label(key)}

    return None


def _window_totals(start, end):
    """Per-month revenue / payroll / expenses across a window (3 queries).

    Mirrors ``dashboard_service.account_book``: aggregate in SQL grouped by
    month, then read the periods out of the result.
    """
    revenue_rows = (db.session.query(
            db.func.strftime('%Y-%m', FeeTransaction.created_at),
            db.func.coalesce(db.func.sum(FeeTransaction.amount), 0.0))
        .filter(FeeTransaction.txn_type == 'payment',
                FeeTransaction.is_void.is_(False),
                FeeTransaction.created_at >= datetime.combine(start, datetime.min.time()),
                FeeTransaction.created_at <= datetime.combine(end, datetime.max.time()))
        .group_by(db.func.strftime('%Y-%m', FeeTransaction.created_at)).all())
    revenue = {key: _money(value) for key, value in revenue_rows}

    expense_rows = (db.session.query(
            db.func.strftime('%Y-%m', Expense.date),
            db.func.coalesce(db.func.sum(Expense.amount), 0.0))
        .filter(Expense.date >= start, Expense.date <= end)
        .group_by(db.func.strftime('%Y-%m', Expense.date)).all())
    expenses = {key: _money(value) for key, value in expense_rows}

    payroll_rows_ = (db.session.query(
            StaffPayroll.month_year,
            db.func.coalesce(db.func.sum(StaffPayroll.net_salary), 0.0),
            db.func.coalesce(db.func.sum(
                db.case((StaffPayroll.payment_status == 'Paid',
                         StaffPayroll.net_salary), else_=0.0)), 0.0),
            db.func.count(StaffPayroll.id))
        .filter(StaffPayroll.month_year >= start.strftime('%Y-%m'),
                StaffPayroll.month_year <= end.strftime('%Y-%m'))
        .group_by(StaffPayroll.month_year).all())
    payroll = {key: {'total': _money(total), 'paid': _money(paid), 'count': count}
               for key, total, paid, count in payroll_rows_}
    return revenue, expenses, payroll


def period_snapshot(period, revenue, expenses, payroll):
    """Turn pre-aggregated month buckets into one period's figures."""
    months = all_months_in_period(period)
    revenue_total = _money(sum(revenue.get(m, 0.0) for m in months))
    expenses_sum = _money(sum(expenses.get(m, 0.0) for m in months))
    payroll_total = _money(sum(payroll.get(m, {}).get('total', 0.0) for m in months))
    payroll_paid = _money(sum(payroll.get(m, {}).get('paid', 0.0) for m in months))
    payroll_count = sum(payroll.get(m, {}).get('count', 0) for m in months)

    monthly = []
    if period['kind'] in ('year', 'session'):
        for month in months:
            month_payroll = payroll.get(month, {})
            month_revenue = revenue.get(month, 0.0)
            month_expenses = expenses.get(month, 0.0)
            month_payroll_total = month_payroll.get('total', 0.0)
            monthly.append({
                'month': month,
                'label': short_label(month),
                'revenue': month_revenue,
                'payroll': month_payroll_total,
                'expenses': month_expenses,
                'net': _money(month_revenue - month_expenses - month_payroll_total),
            })

    return {
        'key': period['key'],
        'label': period['label'],
        'short_label': period['short_label'],
        'kind': period['kind'],
        'start': period['start'],
        'end': period['end'],
        'months': months,
        'month_count': len(months),
        'revenue': revenue_total,
        'expenses': expenses_sum,
        'payroll': payroll_total,
        'payroll_paid': payroll_paid,
        'payroll_pending': _money(payroll_total - payroll_paid),
        'payroll_count': payroll_count,
        'costs': _money(expenses_sum + payroll_total),
        'net': _money(revenue_total - expenses_sum - payroll_total),
        'monthly': monthly,
    }


def period_snapshots(period_keys):
    """Snapshot every requested period using one aggregation over their span."""
    periods = [p for p in (period_descriptor(key) for key in period_keys or []) if p]
    if not periods:
        return []
    start = min(p['start'] for p in periods)
    end = max(p['end'] for p in periods)
    revenue, expenses, payroll = _window_totals(start, end)
    return [period_snapshot(period, revenue, expenses, payroll) for period in periods]


#: Metrics shown in the comparison grid: (key, label, help text).
COMPARISON_METRICS = (
    ('revenue', 'Fee Collections', 'Fee payments received in the period'),
    ('payroll', 'Staff Payroll (Net)', 'Net salaries recorded for the period'),
    ('expenses', 'Operational Expenses', 'Expenses logged in the period'),
    ('costs', 'Total Costs', 'Payroll plus operational expenses'),
    ('net', 'Net Surplus / (Deficit)', 'Fee collections minus all costs'),
)


def comparison_rows(snapshots):
    """Metric rows for the comparison grid.

    Each row carries one value per period plus, when exactly two periods are
    selected, how much the second differs from the first.
    """
    show_difference = len(snapshots) == 2
    rows = []
    for key, label, help_text in COMPARISON_METRICS:
        values = [snapshot.get(key, 0.0) for snapshot in snapshots]
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
        'costs': _money(sum(s['costs'] for s in snapshots)),
        'net': _money(sum(s['net'] for s in snapshots)),
    }


def comparison_csv(snapshots, rows, totals=None):
    """CSV with one column per period (plus a difference column for two)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Financial Summary — Period Comparison'])
    writer.writerow(['Period'] + [s['label'] for s in snapshots] +
                    (['Difference'] if len(snapshots) == 2 else []) +
                    (['Total'] if totals else []))
    writer.writerow(['Period length (months)'] +
                    [s['month_count'] for s in snapshots] +
                    ([''] if len(snapshots) == 2 else []) +
                    ([''] if totals else []))
    writer.writerow([])
    for row in rows:
        line = [row['label']] + ['%.2f' % v for v in row['amounts']]
        if len(snapshots) == 2:
            line.append('%.2f' % row['difference'])
        if totals:
            line.append('%.2f' % totals.get(row['key'], 0.0))
        writer.writerow(line)
    writer.writerow([])
    writer.writerow(['Monthly detail'])
    writer.writerow(['Period', 'Month', 'Fee Collections', 'Staff Payroll',
                     'Operational Expenses', 'Net'])
    for snapshot in snapshots:
        if snapshot['monthly']:
            for month in snapshot['monthly']:
                writer.writerow([snapshot['label'], month['label'],
                                 '%.2f' % month['revenue'],
                                 '%.2f' % month['payroll'],
                                 '%.2f' % month['expenses'],
                                 '%.2f' % month['net']])
        else:
            writer.writerow([snapshot['label'], snapshot['label'],
                             '%.2f' % snapshot['revenue'],
                             '%.2f' % snapshot['payroll'],
                             '%.2f' % snapshot['expenses'],
                             '%.2f' % snapshot['net']])
    return buffer.getvalue()


def comparison_pdf(snapshots, rows, totals=None, root_path=None):
    """Branded landscape PDF of the period comparison."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CTitle', parent=styles['Heading1'], fontSize=15,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('CSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=6)

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('FINANCIAL COMPARISON — %s'
                  % escape(', '.join(s['label'] for s in snapshots)).upper(), sub_style),
    ]
    story.append(Spacer(1, 8))

    show_difference = len(snapshots) == 2
    header = ['Metric'] + [s['label'] for s in snapshots]
    if show_difference:
        header.append('Difference')
    if totals:
        header.append('Total')
    data = [header]
    for row in rows:
        line = [row['label']] + ['{:,.0f}'.format(v) for v in row['amounts']]
        if show_difference:
            line.append('{:,.0f}'.format(row['difference']))
        if totals:
            line.append('{:,.0f}'.format(totals.get(row['key'], 0.0)))
        data.append(line)

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#f8fafc')]),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Net position = Fee Collections - Staff Payroll - Operational Expenses.',
        styles['Normal']))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=28,
                            leftMargin=28, topMargin=26, bottomMargin=26)
    doc.build(story)
    output.seek(0)
    return output


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

def report_csv(snapshot, breakdown, payroll_list):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Financial Summary', snapshot['label']])
    writer.writerow(['Fee Collections (Revenue)', '%.2f' % snapshot['revenue']])
    writer.writerow(['Staff Payroll (Net)', '%.2f' % snapshot['payroll']])
    writer.writerow(['Operational Expenses', '%.2f' % snapshot['expenses']])
    writer.writerow(['Net Surplus / (Deficit)', '%.2f' % snapshot['net']])
    writer.writerow([])
    writer.writerow(['Expense Breakdown'])
    writer.writerow(['Category', 'Entries', 'Total (Rs)'])
    for row in breakdown:
        writer.writerow([row['name'], row['count'], '%.2f' % row['total']])
    writer.writerow([])
    writer.writerow(['Payroll'])
    writer.writerow(['Teacher', 'Net Salary (Rs)', 'Status', 'Payment Date'])
    for record in payroll_list:
        teacher_name = record.teacher.teacher_name if record.teacher else ''
        writer.writerow([
            teacher_name,
            '%.2f' % (record.net_salary or 0),
            record.payment_status or '',
            record.payment_date.isoformat() if record.payment_date else '',
        ])
    return buffer.getvalue()


def report_pdf(snapshot, breakdown, payroll_list, root_path=None):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('FTitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('FSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=6)
    section_style = ParagraphStyle('FSection', parent=styles['Normal'], fontSize=11,
                                   fontName='Helvetica-Bold',
                                   textColor=colors.HexColor('#0f172a'),
                                   spaceBefore=10, spaceAfter=4)

    def money(value):
        return '{:,.2f}'.format(value or 0)

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('MONTHLY FINANCIAL SUMMARY — %s'
                  % escape(snapshot['label']).upper(), sub_style),
    ]
    tail = ' | '.join([p for p in (school.get('address') or '',
                                   school.get('phone') or '') if p])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))
    story.append(Spacer(1, 8))

    summary_rows = [
        ['Fee Collections (Revenue)', money(snapshot['revenue'])],
        ['Staff Payroll (Net)', money(snapshot['payroll'])],
        ['  — Paid', money(snapshot['payroll_paid'])],
        ['  — Pending', money(snapshot['payroll_pending'])],
        ['Operational Expenses', money(snapshot['expenses'])],
        ['Net Surplus / (Deficit)', money(snapshot['net'])],
    ]
    summary_table = Table(summary_rows, colWidths=[360, 192])
    summary_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(summary_table)

    story.append(Paragraph('Expense Breakdown', section_style))
    breakdown_rows = [['Category', 'Entries', 'Total (Rs.)']]
    for row in breakdown:
        breakdown_rows.append([row['name'], str(row['count']), money(row['total'])])
    if len(breakdown_rows) == 1:
        breakdown_rows.append(['No expenses recorded', '', ''])
    breakdown_table = Table(breakdown_rows, colWidths=[280, 80, 192])
    breakdown_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(breakdown_table)

    story.append(Paragraph('Payroll', section_style))
    payroll_table_rows = [['Teacher', 'Net Salary (Rs.)', 'Status', 'Payment Date']]
    for record in payroll_list:
        teacher_name = record.teacher.teacher_name if record.teacher else '—'
        payroll_table_rows.append([
            teacher_name,
            money(record.net_salary),
            record.payment_status or '',
            record.payment_date.strftime('%d %b %Y') if record.payment_date else '—',
        ])
    if len(payroll_table_rows) == 1:
        payroll_table_rows.append(['No payroll records for this month', '', '', ''])
    payroll_table = Table(payroll_table_rows, colWidths=[200, 112, 90, 150])
    payroll_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(payroll_table)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        'Net position = Fee Collections − Staff Payroll − Operational Expenses.',
        styles['Normal']))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output

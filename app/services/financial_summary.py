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

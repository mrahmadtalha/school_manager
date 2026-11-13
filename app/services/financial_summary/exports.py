"""CSV and PDF exports of the financial summary and of the comparison."""

import csv
import io
from datetime import date


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
        'Net Position (cash basis) = Cash In (fee collections) - Cash Out (expenses, salaries included).',
        styles['Normal']))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=28,
                            leftMargin=28, topMargin=26, bottomMargin=26)
    doc.build(story)
    output.seek(0)
    return output


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
        'Net Position (cash basis) = Cash In (fee collections) − Cash Out (expenses, salaries included).',
        styles['Normal']))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output

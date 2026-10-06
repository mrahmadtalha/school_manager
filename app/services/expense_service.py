"""Helpers for the operational expense tracker."""
import csv
import io
from datetime import date

from app.database import db
from app.models import Expense, ExpenseCategory, DEFAULT_EXPENSE_CATEGORIES


def seed_default_categories():
    """Create the default categories when the table has none. Returns count created."""
    if ExpenseCategory.query.count() > 0:
        return 0
    created = 0
    for name in DEFAULT_EXPENSE_CATEGORIES:
        if not ExpenseCategory.query.filter_by(name=name).first():
            db.session.add(ExpenseCategory(name=name))
            created += 1
    if created:
        db.session.commit()
    return created


def active_categories():
    return (ExpenseCategory.query.filter_by(is_active=True)
            .order_by(ExpenseCategory.name).all())


def categories_with_usage():
    """Every category plus entry count / total (for the management table)."""
    rows = []
    for category in ExpenseCategory.query.order_by(ExpenseCategory.name).all():
        query = Expense.query.filter_by(category_id=category.id)
        count = query.count()
        total = query.with_entities(
            db.func.coalesce(db.func.sum(Expense.amount), 0.0)).scalar() or 0.0
        rows.append({'category': category, 'count': count,
                     'total': round(float(total), 2)})
    return rows


def filter_expenses(date_from=None, date_to=None, category_id=None, search=None):
    query = Expense.query.join(ExpenseCategory)
    if date_from:
        query = query.filter(Expense.date >= date_from)
    if date_to:
        query = query.filter(Expense.date <= date_to)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if search:
        like = '%' + search + '%'
        query = query.filter(db.or_(
            Expense.description.ilike(like),
            Expense.receipt_no.ilike(like),
            ExpenseCategory.name.ilike(like),
        ))
    return query.order_by(Expense.date.desc(), Expense.id.desc()).all()


# --------------------------------------------------------------------------- #
# Recurring expenses (continue a previous month's entry)
# --------------------------------------------------------------------------- #

def month_expenses(month_year):
    """Every expense recorded inside the given 'YYYY-MM' month, newest first."""
    from app.services.payroll_service import month_bounds

    start, end = month_bounds(month_year)
    if start is None:
        return []
    return filter_expenses(date_from=start, date_to=end)


def previous_month_expenses(month_year=None):
    """Expenses from the month before ``month_year`` (default: this month).

    Used by the "Continue previous month's expense" shortcut: the school picks
    one of last month's entries and the Add form is pre-filled from it.
    """
    from app.services.payroll_service import current_month_key, shift_month

    base = month_year or current_month_key()
    previous = shift_month(base, -1)
    return month_expenses(previous) if previous else []


def continue_payload(expense):
    """Form field values to pre-fill the Add form from an existing expense.

    Deliberately excludes the date: a continued expense is a *new* record for
    today, so the user re-dates it (or keeps today's date) before saving.
    """
    if expense is None:
        return None
    return {
        'source_id': expense.id,
        'category_id': expense.category_id,
        'category_name': expense.category.name if expense.category else '',
        'amount': round(float(expense.amount or 0), 2),
        'payment_method': expense.payment_method or 'Cash',
        'receipt_no': expense.receipt_no or '',
        'description': expense.description or '',
        'source_date': expense.date.isoformat() if expense.date else '',
    }


def summary(expenses):
    total = round(sum(e.amount or 0 for e in expenses), 2)
    by_category = {}
    for expense in expenses:
        name = expense.category.name if expense.category else '—'
        bucket = by_category.setdefault(name, {'count': 0, 'total': 0.0})
        bucket['count'] += 1
        bucket['total'] = round(bucket['total'] + (expense.amount or 0), 2)
    top = None
    if by_category:
        top_name = max(by_category, key=lambda k: by_category[k]['total'])
        top = {'name': top_name, 'total': by_category[top_name]['total']}
    return {'total': total, 'count': len(expenses),
            'by_category': by_category, 'top': top}


def ledger_csv(expenses):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Date', 'Category', 'Amount (Rs)', 'Payment Method',
                     'Receipt No', 'Description', 'Logged By'])
    total = 0.0
    for expense in expenses:
        writer.writerow([
            expense.date.strftime('%Y-%m-%d') if expense.date else '',
            expense.category.name if expense.category else '',
            '%.2f' % (expense.amount or 0),
            expense.payment_method or '',
            expense.receipt_no or '',
            expense.description or '',
            expense.logged_by_name or '',
        ])
        total += expense.amount or 0
    writer.writerow(['', 'TOTAL', '%.2f' % total, '', '', '', ''])
    return buffer.getvalue()


def ledger_pdf(expenses, root_path=None, range_label=''):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ETitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('ESub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=6)

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('EXPENSE LEDGER', sub_style),
    ]
    tail = ' | '.join([p for p in (school.get('address') or '',
                                   school.get('phone') or '') if p])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))
    if range_label:
        story.append(Paragraph(escape(range_label), sub_style))
    story.append(Spacer(1, 8))

    header = ['Date', 'Category', 'Amount (Rs.)', 'Method', 'Receipt No',
              'Description', 'Logged By']
    data = [header]
    total = 0.0
    for expense in expenses:
        data.append([
            expense.date.strftime('%d %b %Y') if expense.date else '—',
            expense.category.name if expense.category else '—',
            '{:,.0f}'.format(expense.amount or 0),
            expense.payment_method or '—',
            expense.receipt_no or '—',
            expense.description or '—',
            expense.logged_by_name or '—',
        ])
        total += expense.amount or 0
    data.append(['TOTAL', '', '{:,.0f}'.format(total), '', '', '', ''])

    table = Table(data, colWidths=[66, 92, 64, 48, 62, 148, 72], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(table)

    if not expenses:
        story.append(Spacer(1, 8))
        story.append(Paragraph('No expenses recorded for the selected filters.',
                               styles['Normal']))

    story.append(Spacer(1, 14))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'),
                           styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output

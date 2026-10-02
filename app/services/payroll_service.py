"""Monthly payroll: attendance-aware suggestions, generation and payslip PDFs."""
import io
from calendar import monthrange
from datetime import date, datetime

from app.database import db
from app.models import AttendanceModel, SchoolSettings, StaffPayroll, TeacherModel
from app.services.teacher_payroll import get_school_working_days


# --------------------------------------------------------------------------- #
# Month helpers
# --------------------------------------------------------------------------- #

def parse_month(month_year):
    """'2026-09' -> (2026, 9); returns None when invalid."""
    try:
        year_s, month_s = (month_year or '').split('-')
        year, month = int(year_s), int(month_s)
        if 2000 <= year <= 2100 and 1 <= month <= 12:
            return year, month
    except (ValueError, AttributeError):
        pass
    return None


def month_label(month_year):
    parsed = parse_month(month_year)
    if not parsed:
        return ''
    return date(parsed[0], parsed[1], 1).strftime('%B %Y')


def month_bounds(month_year):
    parsed = parse_month(month_year)
    if not parsed:
        return None, None
    year, month = parsed
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def current_month_key():
    today = date.today()
    return '%04d-%02d' % (today.year, today.month)


def shift_month(month_year, delta):
    parsed = parse_month(month_year)
    if not parsed:
        return None
    index = parsed[0] * 12 + (parsed[1] - 1) + delta
    return '%04d-%02d' % (index // 12, index % 12 + 1)


def recent_month_keys(end_month, count=6):
    return [shift_month(end_month, -offset) for offset in range(count - 1, -1, -1)]


def parse_iso_date(value):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Calculations
# --------------------------------------------------------------------------- #

def base_salary_for(teacher):
    """Base monthly salary pulled from the teacher profile."""
    return float(getattr(teacher, 'monthly_salary', 0)
                 or getattr(teacher, 'salary', 0) or 0)


def teacher_month_stats(teacher, month_year):
    """Attendance counts for one teacher within a payroll month."""
    start, end = month_bounds(month_year)
    if start is None:
        return None
    settings = SchoolSettings.query.first()
    working_days = len(get_school_working_days(start, end, settings))
    records = AttendanceModel.query.filter(
        AttendanceModel.target_type == 'teacher',
        AttendanceModel.target_id == teacher.id,
        AttendanceModel.date >= start,
        AttendanceModel.date <= end,
    ).all()
    counts = {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0}
    for record in records:
        if record.status in counts:
            counts[record.status] += 1
    return {
        'working_days': working_days,
        'marked_days': len(records),
        'present': counts['Present'],
        'absent': counts['Absent'],
        'late': counts['Late'],
        'leave': counts['Leave'],
    }


def suggested_row(teacher, month_year, per_late_amount=0.0, leave_as_absent=False):
    """Suggested payroll numbers based on attendance for the month."""
    stats = teacher_month_stats(teacher, month_year) or {
        'working_days': 0, 'marked_days': 0, 'present': 0,
        'absent': 0, 'late': 0, 'leave': 0}
    base = base_salary_for(teacher)
    working_days = stats['working_days']
    daily_rate = round(base / working_days, 2) if working_days else 0.0
    deduction_days = stats['absent'] + (stats['leave'] if leave_as_absent else 0)
    auto_deduction = round(
        daily_rate * deduction_days + float(per_late_amount or 0) * stats['late'], 2)
    return {'base': base, 'stats': stats, 'daily_rate': daily_rate,
            'auto_deduction': auto_deduction}


def preview_rows(month_year, per_late_amount=0.0, leave_as_absent=False):
    """One wizard row per active teacher, merged with any saved record."""
    teachers = (TeacherModel.query.filter_by(is_active=True)
                .order_by(TeacherModel.teacher_name).all())
    existing = {p.teacher_id: p for p in
                StaffPayroll.query.filter_by(month_year=month_year).all()}
    rows = []
    for teacher in teachers:
        calc = suggested_row(teacher, month_year, per_late_amount, leave_as_absent)
        record = existing.get(teacher.id)
        locked = bool(record and record.payment_status == 'Paid')
        base = record.base_salary if record else calc['base']
        bonus = record.bonus if record else 0.0
        deductions = record.deductions if record else calc['auto_deduction']
        rows.append({
            'teacher': teacher,
            'stats': calc['stats'],
            'daily_rate': calc['daily_rate'],
            'auto_deduction': calc['auto_deduction'],
            'record': record,
            'locked': locked,
            'base': base,
            'bonus': bonus,
            'deductions': deductions,
            'net': record.net_salary if record else round(base + bonus - deductions, 2),
            'notes': (record.notes or '') if record else '',
        })
    return rows


def _form_float(form, key, fallback=0.0):
    raw = (form.get(key) or '').strip()
    if not raw:
        return float(fallback or 0)
    try:
        return float(raw)
    except ValueError:
        return float(fallback or 0)


def generate(month_year, form, generated_by):
    """Create/update payroll rows from the wizard form. Returns counts."""
    rows = preview_rows(month_year)
    created = updated = skipped = 0
    for row in rows:
        teacher = row['teacher']
        if not form.get('include_%d' % teacher.id):
            skipped += 1
            continue
        if row['locked']:
            skipped += 1
            continue

        record = row['record']
        is_new = record is None
        if is_new:
            record = StaffPayroll(teacher_id=teacher.id, month_year=month_year)
            db.session.add(record)
            created += 1
        else:
            updated += 1

        base = _form_float(form, 'base_%d' % teacher.id, fallback=row['base'])
        bonus = _form_float(form, 'bonus_%d' % teacher.id, fallback=row['bonus'])
        deductions = _form_float(form, 'deductions_%d' % teacher.id,
                                 fallback=row['deductions'])
        stats = row['stats'] or {}

        record.base_salary = round(base, 2)
        record.bonus = round(bonus, 2)
        record.deductions = round(deductions, 2)
        record.net_salary = round(base + bonus - deductions, 2)
        record.notes = ((form.get('notes_%d' % teacher.id) or '').strip()[:255]
                        or None)
        record.generated_by = (generated_by or 'system')[:80]
        record.working_days = stats.get('working_days')
        record.present_days = stats.get('present')
        record.absent_days = stats.get('absent')
        record.late_days = stats.get('late')
        record.leave_days = stats.get('leave')

    db.session.commit()
    return {'created': created, 'updated': updated, 'skipped': skipped}


def month_totals(month_year):
    records = StaffPayroll.query.filter_by(month_year=month_year).all()
    total = round(sum(r.net_salary or 0 for r in records), 2)
    paid = round(sum(r.net_salary or 0 for r in records
                     if r.payment_status == 'Paid'), 2)
    return {'count': len(records), 'total': total, 'paid': paid,
            'pending': round(total - paid, 2)}


# --------------------------------------------------------------------------- #
# Amount in words
# --------------------------------------------------------------------------- #

_ONES = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight',
         'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen',
         'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
_TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy',
         'Eighty', 'Ninety']


def _under_100(value):
    if value < 20:
        return _ONES[value]
    return _TENS[value // 10] + ('-' + _ONES[value % 10] if value % 10 else '')


def _under_1000(value):
    if value < 100:
        return _under_100(value)
    tail = _under_100(value % 100)
    return _ONES[value // 100] + ' Hundred' + (' and ' + tail if tail else '')


def _number_words(value):
    if value == 0:
        return 'Zero'
    parts = []
    for divisor, label in ((1000000000, 'Billion'), (1000000, 'Million'),
                           (1000, 'Thousand')):
        if value >= divisor:
            parts.append(_under_1000(value // divisor) + ' ' + label)
            value %= divisor
    if value:
        parts.append(_under_1000(value))
    return ' '.join(parts)


def amount_in_words(amount):
    """'Twenty-Eight Thousand Five Hundred Rupees Only' for 28500."""
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    rupees = int(value)
    paisa = int(round((value - rupees) * 100))
    if paisa == 100:
        rupees += 1
        paisa = 0
    words = _number_words(rupees) if rupees else 'Zero'
    if paisa:
        return '%s Rupees and %s Paisa Only' % (words, _number_words(paisa))
    return '%s Rupees Only' % words


# --------------------------------------------------------------------------- #
# Payslip PDF
# --------------------------------------------------------------------------- #

def build_payslip_pdf(record, teacher, root_path=None):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('PTitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('PSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=4)
    label_style = ParagraphStyle('PLabel', parent=styles['Normal'], fontSize=9,
                                 textColor=colors.HexColor('#64748b'),
                                 fontName='Helvetica-Bold')

    def money(value):
        return 'Rs. {:,.2f}'.format(value or 0)

    def fmt_date(value):
        return value.strftime('%d %b %Y') if value else '—'

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('SALARY PAYSLIP', sub_style),
    ]
    tail = ' | '.join([p for p in (school.get('address') or '',
                                   school.get('phone') or '') if p])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))

    ref_no = 'PS-%s-%s' % (record.month_year,
                           getattr(teacher, 'teacher_id_str', None) or teacher.id)
    story.append(Paragraph(
        'Pay Period: <b>%s</b> &nbsp;&nbsp;|&nbsp;&nbsp; Payslip Ref: <b>%s</b>'
        % (escape(month_label(record.month_year)), escape(str(ref_no))), sub_style))
    story.append(Spacer(1, 8))

    info_rows = [
        ['Teacher Name', teacher.teacher_name, 'Pay Period',
         month_label(record.month_year)],
        ['Teacher ID', getattr(teacher, 'teacher_id_str', '') or '—', 'Status',
         record.payment_status or 'Pending'],
        ['Joining Date', fmt_date(teacher.joining_date), 'Payment Date',
         fmt_date(record.payment_date)],
        ['Salary Type', (teacher.salary_type or 'monthly').title(), 'Payment Method',
         record.payment_method or '—'],
    ]
    info_table = Table(info_rows, colWidths=[95, 181, 95, 181])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#64748b')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#64748b')),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f8fafc')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    money_rows = [
        ['Base Salary', money(record.base_salary)],
        ['Bonus', money(record.bonus)],
        ['Deductions', '- ' + money(record.deductions)],
        ['Net Salary', money(record.net_salary)],
    ]
    money_table = Table(money_rows, colWidths=[380, 172])
    money_table.setStyle(TableStyle([
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
    story.append(money_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        'Net salary in words: <b>%s</b>' % escape(amount_in_words(record.net_salary)),
        styles['Normal']))
    story.append(Spacer(1, 10))

    att_header = ['Working Days', 'Present', 'Absent', 'Late', 'Leave']
    att_values = [str(record.working_days if record.working_days is not None else '—'),
                  str(record.present_days if record.present_days is not None else '—'),
                  str(record.absent_days if record.absent_days is not None else '—'),
                  str(record.late_days if record.late_days is not None else '—'),
                  str(record.leave_days if record.leave_days is not None else '—')]
    att_table = Table([att_header, att_values],
                      colWidths=[110.4, 110.4, 110.4, 110.4, 110.4])
    att_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(Paragraph('Attendance Summary (this month)', label_style))
    story.append(Spacer(1, 3))
    story.append(att_table)

    if record.notes:
        story.append(Spacer(1, 8))
        story.append(Paragraph('Notes: %s' % escape(record.notes), styles['Normal']))

    story.append(Spacer(1, 24))
    sign_table = Table(
        [['_________________________', '_________________________'],
         ['Prepared By', 'Principal / Authorized Signature']],
        colWidths=[276, 276])
    sign_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#475569')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(sign_table)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        'Generated on %s%s' % (
            date.today().strftime('%d %b %Y'),
            ' by %s' % escape(record.generated_by) if record.generated_by else ''),
        styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output

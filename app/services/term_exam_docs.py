"""Printable documents for term examinations (date sheets; results come later)."""
import io
from datetime import date
from xml.sax.saxutils import escape


def _fmt_date(value):
    return value.strftime('%d %b %Y') if value else '—'


def build_date_sheet_pdf(exam, tests, root_path=None):
    """Official date-sheet PDF for one term exam (subjects sorted by date)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DSTitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('DSSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=4)
    meta_style = ParagraphStyle('DSMeta', parent=styles['Normal'], fontSize=10,
                                alignment=1, textColor=colors.HexColor('#1f2937'),
                                spaceAfter=6)

    story = [
        Paragraph(escape(str(school['name'])), title_style),
        Paragraph('DATE SHEET', sub_style),
    ]
    tail = ' | '.join([p for p in (school.get('address') or '',
                                   school.get('phone') or '') if p])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))

    class_name = exam.class_info.name if exam.class_info else '—'
    meta = '%s &mdash; %s &nbsp;|&nbsp; Class: %s &nbsp;|&nbsp; Session: %s' % (
        escape(exam.exam_type), escape(exam.name), escape(class_name),
        escape(exam.session_label or '—'))
    story.append(Paragraph(meta, meta_style))
    if exam.start_date or exam.end_date:
        story.append(Paragraph(
            'Exam Dates: <b>%s &ndash; %s</b>' % (_fmt_date(exam.start_date),
                                                  _fmt_date(exam.end_date)),
            meta_style))
    story.append(Spacer(1, 8))

    header = ['#', 'Subject', 'Day', 'Date', 'Time', 'Room', 'Max Marks']
    data = [header]
    total_max = 0.0
    for index, test in enumerate(tests, 1):
        subject_name = (test.subject_info.name if test.subject_info else '—')
        data.append([
            str(index),
            subject_name,
            test.test_date.strftime('%A') if test.test_date else '—',
            test.test_date.strftime('%d %b %Y') if test.test_date else '—',
            test.start_time or '—',
            test.room or '—',
            '{:,.0f}'.format(test.total_marks or 0),
        ])
        total_max += test.total_marks or 0
    data.append(['', 'Total', '', '', '', '', '{:,.0f}'.format(total_max)])

    table = Table(data, colWidths=[30, 122, 70, 85, 55, 90, 100], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (6, 0), (6, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white,
                                              colors.HexColor('#f8fafc')]),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(table)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'Candidates must reach the examination hall at least 15 minutes before the '
        'start time. Mobile phones and smart devices are not allowed.', sub_style))

    story.append(Spacer(1, 30))
    sign_table = Table(
        [['_________________________', '_________________________'],
         ['Controller of Examinations', 'Principal']],
        colWidths=[276, 276])
    sign_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#475569')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        'Generated on %s' % date.today().strftime('%d %b %Y'), styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output


def build_result_cards_pdf(exam, cards, root_path=None):
    """Official result card PDF (one card per entry, page break between)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('RCTitle', parent=styles['Heading1'], fontSize=15,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('RCSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=2)
    exam_style = ParagraphStyle('RCExam', parent=styles['Normal'], fontSize=10.5,
                                alignment=1, fontName='Helvetica-Bold',
                                textColor=colors.HexColor('#1f2937'), spaceAfter=4)
    warn_style = ParagraphStyle('RCWarn', parent=styles['Normal'], fontSize=8.5,
                                alignment=1, textColor=colors.HexColor('#b45309'),
                                spaceBefore=4)

    def money(value):
        return '{:,.0f}'.format(value or 0)

    def fmt(value):
        return value.strftime('%d %b %Y') if value else '—'

    class_name = exam.class_info.name if exam.class_info else '—'
    story = []
    for index, card in enumerate(cards):
        if index:
            story.append(PageBreak())
        student = card['student']
        story.append(Paragraph(escape(str(school['name'])), title_style))
        story.append(Paragraph('OFFICIAL RESULT CARD', sub_style))
        tail = ' | '.join([p for p in (school.get('address') or '',
                                       school.get('phone') or '') if p])
        if tail:
            story.append(Paragraph(escape(tail), sub_style))
        story.append(Paragraph(
            '%s — %s &nbsp;|&nbsp; Session: %s'
            % (escape(exam.exam_type), escape(exam.name),
               escape(exam.session_label or '—')), exam_style))
        story.append(Paragraph(
            'Exam Dates: %s – %s &nbsp;|&nbsp; Result announced: %s'
            % (fmt(exam.start_date), fmt(exam.end_date), fmt(exam.announce_date)),
            sub_style))
        story.append(Spacer(1, 8))

        info_rows = [
            ['Student Name', student.student_name, 'Roll No', str(student.roll_number)],
            ['Father Name', student.father_name, 'Class', class_name],
            ['Session', exam.session_label or '—', 'Position', card['position'] or '—'],
        ]
        info_table = Table(info_rows, colWidths=[92, 184, 92, 184])
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

        header = ['Subject', 'Max Marks', 'Marks Obtained', 'Percentage', 'Grade']
        data = [header]
        for label, subject_max, obtained, pct, grade in card['subject_rows']:
            data.append([label, money(subject_max),
                         ('—' if obtained is None else
                          obtained if isinstance(obtained, str) else money(obtained)),
                         ('—' if pct is None else '%.1f%%' % pct),
                         grade or '—'])
        if card.get('all_absent'):
            data.append(['Total', '—', '—', '—', card['grade'] or '—'])
        else:
            data.append(['Total', money(card['total_max']), money(card['total_obt']),
                         '%.1f%%' % card['pct'], card['grade'] or '—'])
        table = Table(data, colWidths=[190, 82, 110, 90, 80], repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white,
                                                  colors.HexColor('#f8fafc')]),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
        ]))
        story.append(table)
        if card.get('absent_count') and not card.get('all_absent'):
            story.append(Paragraph(
                'Absent in %d subject(s) &mdash; those papers are not included in the '
                'total, percentage, grade or position.' % card['absent_count'],
                warn_style))

        if card.get('remark'):
            story.append(Spacer(1, 8))
            story.append(Paragraph(
                'Class Teacher&apos;s Remarks: %s' % escape(card['remark']),
                styles['Normal']))
        if not card.get('complete', True):
            story.append(Paragraph(
                'Note: this result is provisional - some subject marks are not yet '
                'entered.', warn_style))

        story.append(Spacer(1, 30))
        sign_table = Table(
            [['_________________________', '_________________________'],
             ['Class Teacher', 'Principal']],
            colWidths=[276, 276])
        sign_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#475569')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(sign_table)
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            'Generated on %s' % date.today().strftime('%d %b %Y'), styles['Normal']))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output

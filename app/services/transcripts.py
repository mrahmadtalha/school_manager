"""Cumulative multi-year academic transcript (PDF) builder."""
import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import AttendanceModel, StudentMarkModel
from app.models.settings import calculate_grade
from app.services.id_documents import school_branding

STATUS_LABELS = {
    'enrolled': 'Enrolled',
    'slc_issued': 'SLC Issued',
    'graduated': 'Graduated',
    'struck_off': 'Struck Off',
}


def _fmt_date(value):
    return value.strftime('%d %b %Y') if value else '—'


def _claim_groups(enrollments, marks):
    """Assign each mark to an enrollment bucket (date-aware, earliest match wins)."""
    buckets = {e.id: [] for e in enrollments}
    leftovers = []
    for m in marks:
        test = m.test_info
        if test is None:
            leftovers.append(m)
            continue
        claimed = None
        for e in enrollments:
            if e.class_id != test.class_id:
                continue
            if e.start_date and test.test_date < e.start_date:
                continue
            if e.end_date and test.test_date > e.end_date:
                continue
            claimed = e
            break
        if claimed is None:
            for e in enrollments:
                if e.class_id == test.class_id:
                    claimed = e
                    break
        if claimed is not None:
            buckets[claimed.id].append(m)
        else:
            leftovers.append(m)
    return buckets, leftovers


def _attendance_line(student_id, enrollment):
    query = AttendanceModel.query.filter_by(target_type='student', target_id=student_id)
    if enrollment.class_id:
        query = query.filter(AttendanceModel.class_id == enrollment.class_id)
    if enrollment.start_date:
        query = query.filter(AttendanceModel.date >= enrollment.start_date)
    if enrollment.end_date:
        query = query.filter(AttendanceModel.date <= enrollment.end_date)
    records = query.all()
    if not records:
        return None
    present = sum(1 for r in records if r.status in ('Present', 'Late'))
    pct = round(present / len(records) * 100, 1)
    return 'Attendance: %d/%d days present (incl. late) — %.1f%%' % (present, len(records), pct)


def build_transcript_pdf(student, enrollments, marks, root_path=None):
    school = school_branding(root_path)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TTitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('TSub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'), spaceAfter=4)
    info_style = ParagraphStyle('TInfo', parent=styles['Normal'], fontSize=10,
                                textColor=colors.HexColor('#1f2937'), spaceAfter=4)
    head_style = ParagraphStyle('THead', parent=styles['Normal'], fontSize=10,
                                fontName='Helvetica-Bold', textColor=colors.HexColor('#0f172a'),
                                spaceBefore=2)
    small_style = ParagraphStyle('TSmall', parent=styles['Normal'], fontSize=8.5,
                                 textColor=colors.HexColor('#475569'))

    story = []
    story.append(Paragraph(escape(str(school['name'])), title_style))
    story.append(Paragraph('CUMULATIVE ACADEMIC TRANSCRIPT', sub_style))
    tail = ' | '.join([p for p in (school.get('address') or '', school.get('phone') or '') if p])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))

    status_label = STATUS_LABELS.get(student.status or 'enrolled', 'Enrolled')
    info = ('%s — s/o %s | Current Class: %s | Roll No: %s | Status: %s'
            % (student.student_name, student.father_name,
               student.class_info.name if student.class_info else '—',
               student.roll_number, status_label))
    story.append(Paragraph(escape(info), info_style))
    story.append(Spacer(1, 8))

    table_header = ['Subject', 'Test', 'Type', 'Date', 'Max', 'Obtained', '%', 'Grade']
    col_widths = [118, 108, 62, 68, 42, 58, 48, 48]

    def render_section(title_line, section_marks, attendance_text):
        data = [table_header]
        obt = 0.0
        mx = 0.0
        for m in sorted(section_marks, key=lambda x: (x.test_info.test_date, x.test_info.test_title)):
            t = m.test_info
            data.append([
                t.subject_info.name if t.subject_info else '—',
                t.test_title or '—',
                t.test_type or '—',
                t.test_date.strftime('%d %b %Y') if t.test_date else '—',
                '%g' % (t.total_marks or 0),
                '%g' % (m.marks_obtained or 0),
                ('%.1f%%' % m.percentage) if m.percentage is not None else '—',
                m.grade or '—',
            ])
            obt += m.marks_obtained or 0.0
            mx += t.total_marks or 0.0
        total_row = None
        if len(data) > 1 and mx > 0:
            pct = obt / mx * 100
            total_row = len(data)
            data.append(['TOTAL', '', '', '', '%g' % mx, '%g' % obt, '%.1f%%' % pct,
                         calculate_grade(pct)])
        table = Table(data, colWidths=col_widths)
        style_commands = [
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
        ]
        if total_row is not None:
            style_commands.append(('FONTNAME', (0, total_row), (-1, total_row), 'Helvetica-Bold'))
            style_commands.append(('BACKGROUND', (0, total_row), (-1, total_row), colors.HexColor('#eef2f7')))
        table.setStyle(TableStyle(style_commands))
        block = [Paragraph(escape(title_line), head_style), Spacer(1, 3), table]
        if not section_marks:
            block.append(Spacer(1, 3))
            block.append(Paragraph('No marks recorded for this period.', small_style))
        if attendance_text:
            block.append(Spacer(1, 3))
            block.append(Paragraph(escape(attendance_text), small_style))
        return block

    buckets, leftovers = _claim_groups(enrollments, marks)

    if not enrollments and not marks:
        story.append(Paragraph('No academic records are available for this student yet.', info_style))

    for e in enrollments:
        rows = buckets.get(e.id, [])
        period = '%s – %s' % (_fmt_date(e.start_date),
                              _fmt_date(e.end_date) if e.end_date else 'Present')
        title_line = ('%s — Session %s | Roll No %s | %s'
                      % (e.class_name or 'Class', e.session_label or '—',
                         e.roll_number if e.roll_number is not None else '—', period))
        story.extend(render_section(title_line, rows, _attendance_line(student.id, e)))
        story.append(Spacer(1, 10))

    if leftovers:
        story.extend(render_section('Other records (not linked to an enrollment)', leftovers, None))
        story.append(Spacer(1, 10))

    if marks:
        obt = sum((m.marks_obtained or 0.0) for m in marks)
        mx = sum((m.test_info.total_marks or 0.0) for m in marks if m.test_info)
        if mx > 0:
            pct = obt / mx * 100
            overall = 'Overall: %g / %g (%.1f%%) — Grade %s' % (obt, mx, pct, calculate_grade(pct))
            story.append(Paragraph(escape(overall), info_style))

    story.append(Spacer(1, 16))
    story.append(Paragraph('Generated on %s' % date.today().strftime('%d %b %Y'), small_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph('_________________________<br/>Principal / School Stamp', small_style))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=28, bottomMargin=28)
    doc.build(story)
    output.seek(0)
    return output

"""Class timetable helpers: templates, period timings, auto-fill and PDF export."""

import io
import json
import re
from xml.sax.saxutils import escape

DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
DEFAULT_START = '08:30'

_TIME_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')



# ---------------------------------------------------------------- time helpers
def clean_time(raw):
    """'' for empty, 'HH:MM' for valid input, None for invalid input."""
    raw = (raw or '').strip()
    if not raw:
        return ''
    match = _TIME_RE.match(raw)
    if not match:
        return None
    return '%02d:%02d' % (int(match.group(1)), int(match.group(2)))


def _to_minutes(value):
    hours, minutes = value.split(':')
    return int(hours) * 60 + int(minutes)


def _fmt_minutes(total):
    total %= 24 * 60
    return '%02d:%02d' % (total // 60, total % 60)


def pretty_time(value):
    """'14:10' -> '2:10 PM' (empty stays empty)."""
    if not value:
        return ''
    hours, minutes = value.split(':')
    hours = int(hours)
    suffix = 'AM' if hours < 12 else 'PM'
    return '%d:%s %s' % (hours % 12 or 12, minutes, suffix)


# ------------------------------------------------------------------- row setup


def number_rows(rows):
    """Add a 1-based ``no`` to lesson rows (breaks get None)."""
    counter = 0
    for row in rows:
        if row.get('kind') == 'break':
            row['no'] = None
        else:
            counter += 1
            row['no'] = counter
    return rows


def school_period_structure():
    """Period/break structure configured on the School Settings page.

    Falls back to the built-in default structure (8 x 40-minute periods with a
    break after the 4th) when nothing was saved yet, so the Timetables page
    always has a usable axis.
    """
    from app.models.settings import get_timetable_structure
    structure = get_timetable_structure()
    structure['start'] = school_start_time()
    return structure


def build_school_rows():
    """The school's period/break rows, built from School Settings.

    Returns ``[{'kind', 'start', 'end', 'label'}, ...]`` with the first period
    starting at the configured school start time (after the optional assembly
    slot, like the reference chart).  Every class shares this structure, which
    is what the timetable generator schedules into.
    """
    structure = school_period_structure()
    periods = structure['periods_per_day']
    length = structure['period_minutes']
    break_after = structure['break_after']
    break_minutes = structure['break_minutes']
    break_label = structure['break_label']

    current = _to_minutes(structure['start'])
    rows = []
    if structure.get('assembly_minutes'):
        rows.append({'kind': 'break', 'start': _fmt_minutes(current),
                     'end': _fmt_minutes(current + structure['assembly_minutes']),
                     'label': structure.get('assembly_label') or 'Assembly'})
        current += structure['assembly_minutes']
    for number in range(1, periods + 1):
        rows.append({'kind': 'period', 'start': _fmt_minutes(current),
                     'end': _fmt_minutes(current + length), 'label': ''})
        current += length
        if break_after and number == break_after and break_minutes:
            rows.append({'kind': 'break', 'start': _fmt_minutes(current),
                         'end': _fmt_minutes(current + break_minutes),
                         'label': break_label})
            current += break_minutes
    return rows


def load_rows(class_id):
    """Saved rows for the class, or the school structure when none were saved.

    The per-class ``rows_json`` is no longer edited from a dedicated page; the
    fallback is therefore the School Settings structure rather than a preset.
    """
    from app.models.class_ import TimetableConfig
    cfg = TimetableConfig.query.filter_by(class_id=class_id).first()
    rows = None
    if cfg and cfg.rows_json:
        try:
            rows = json.loads(cfg.rows_json)
        except (TypeError, ValueError):
            rows = None
    if not rows:
        rows = build_school_rows()
    return number_rows(rows)


def school_start_time():
    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    return clean_time(school.school_start_time if school else '') or DEFAULT_START


def school_days(settings=None):
    """The school's teaching days as [(index, name)], honouring School Settings.

    Index is the stored ``day_of_week`` (0=Mon .. 5=Sat); Sunday is never part
    of the weekly grid.  The separate Saturday/Sunday toggles and the custom
    off-day list from the settings page decide what is included.
    """
    from app.models import SchoolSettings
    from app.services.teacher_payroll import get_school_off_days
    if settings is None:
        settings = SchoolSettings.query.first()
    off = get_school_off_days(settings) if settings else {'Saturday', 'Sunday'}
    return [(idx, name) for idx, name in enumerate(DAYS) if name not in off]


# --------------------------------------------------------------------- PDF


def build_teacher_timetable_pdf(teacher, period_rows, days, grid, root_path=None):
    """A4 landscape teacher timetable PDF.

    ``period_rows`` is the period axis: [{'no': 1, 'start': '08:30', 'end': '09:10'}, ...]
    (times optional — mixed period timings across classes leave them empty).
    ``days`` is the teaching-day axis as (index, name) pairs.  ``grid`` maps
    (day_index, period_no) to {'class': ClassModel, 'subject': SubjectModel};
    empty cells are printed as Free.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.models import SchoolSettings
    from app.services.id_documents import school_branding
    from app.services.transcripts import _logo_flowable

    school = school_branding(root_path)
    settings = SchoolSettings.query.first()
    session_label = (settings.academic_session if settings else '') or ''
    styles = getSampleStyleSheet()
    dark = colors.HexColor('#0f172a')
    muted = colors.HexColor('#475569')
    free_bg = colors.HexColor('#f1f5f9')

    title = ParagraphStyle('TTTTitle', parent=styles['Heading1'], fontSize=17, alignment=1,
                           fontName='Helvetica-Bold', textColor=dark, spaceAfter=2)
    sub = ParagraphStyle('TTTSub', parent=styles['Normal'], fontSize=9, alignment=1,
                         textColor=muted, spaceAfter=3)
    meta = ParagraphStyle('TTTMeta', parent=styles['Normal'], fontSize=10.5, alignment=1,
                          textColor=colors.HexColor('#1f2937'), spaceAfter=4)
    cell = ParagraphStyle('TTTCell', parent=styles['Normal'], fontSize=9.5, leading=11.5,
                          alignment=1, textColor=dark)
    time_style = ParagraphStyle('TTTTime', parent=styles['Normal'], fontSize=8, leading=10,
                                alignment=1, textColor=muted)
    head = ParagraphStyle('TTTHead', parent=styles['Normal'], fontSize=9.5, alignment=1,
                          fontName='Helvetica-Bold', textColor=colors.white)

    heading = [Paragraph(escape(str(school['name'])), title),
               Paragraph('TEACHER TIMETABLE', sub)]
    tail = ' | '.join(p for p in (school.get('address') or '', school.get('phone') or '') if p)
    if tail:
        heading.append(Paragraph(escape(tail), sub))

    page = landscape(A4)
    margin = 28
    usable = page[0] - 2 * margin
    story = []
    logo = _logo_flowable(school.get('logo_path'), 62)
    if logo is not None:
        header = Table([[logo, heading, '']], colWidths=[72, usable - 144, 72])
        header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                    ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        story.append(header)
    else:
        story.extend(heading)

    info = ['Teacher: <b>%s</b>' % escape(teacher.teacher_name)]
    if teacher.designation:
        info.append(escape(teacher.designation))
    if session_label:
        info.append('Session: <b>%s</b>' % escape(session_label))
    story.append(Paragraph(' &nbsp;|&nbsp; '.join(info), meta))
    story.append(Spacer(1, 6))

    data = [[Paragraph('Period / Time', head)]
            + [Paragraph(name, head) for _idx, name in days]]
    for row in period_rows:
        label = '<b>Period %d</b>' % row['no']
        start, end = pretty_time(row.get('start')), pretty_time(row.get('end'))
        if start and end:
            label += '<br/>%s - %s' % (start, end)
        line = [Paragraph(label, time_style)]
        for day, _name in days:
            entry = grid.get((day, row['no']))
            if entry is None:
                line.append(Paragraph('<font color="#94a3b8">Free</font>', cell))
                continue
            text = '<b>%s</b><br/><font size="8" color="#475569">%s</font>' % (
                escape(entry['class'].name), escape(entry['subject'].name))
            line.append(Paragraph(text, cell))
        data.append(line)

    first = 92
    day_width = (usable - first) / float(len(days))
    table = Table(data, colWidths=[first] + [day_width] * len(days), repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), dark),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    story.append(Spacer(1, 26))
    sign = Table([['_______________________'],
                  ['Principal']], colWidths=[usable / 2.0])
    sign.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                              ('FONTSIZE', (0, 0), (-1, -1), 9),
                              ('TEXTCOLOR', (0, 1), (-1, 1), muted)]))
    story.append(sign)

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=page, leftMargin=margin, rightMargin=margin,
                      topMargin=margin, bottomMargin=margin,
                      title='Timetable - %s' % teacher.teacher_name).build(story)
    buffer.seek(0)
    return buffer


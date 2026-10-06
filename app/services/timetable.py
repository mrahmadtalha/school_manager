"""Class timetable helpers: templates, period timings, auto-fill and PDF export."""

import io
import json
import re
from xml.sax.saxutils import escape

DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
MAX_PERIODS = 10          # lesson rows per day
MAX_ROWS = 16             # lessons + breaks
DEFAULT_START = '08:30'

_TIME_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')

# Ready-made layouts so a non-technical user does not start from a blank grid.
TEMPLATES = {
    'standard': {'label': 'Standard day - 8 periods + 1 break',
                 'periods': 8, 'minutes': 40, 'breaks': {4: ('Break', 20)}},
    'two_breaks': {'label': '8 periods + short break + lunch',
                   'periods': 8, 'minutes': 40,
                   'breaks': {3: ('Short Break', 15), 6: ('Lunch', 30)}},
    'primary': {'label': 'Primary - 6 periods + 1 break',
                'periods': 6, 'minutes': 35, 'breaks': {3: ('Break', 20)}},
    'half_day': {'label': 'Half day - 5 periods, no break',
                 'periods': 5, 'minutes': 40, 'breaks': {}},
}


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
def build_rows(template_key, start=DEFAULT_START, minutes=None):
    """Period/break rows (with timings) for a template."""
    tpl = TEMPLATES.get(template_key) or TEMPLATES['standard']
    start = clean_time(start) or DEFAULT_START
    try:
        minutes = int(minutes) if minutes else tpl['minutes']
    except (TypeError, ValueError):
        minutes = tpl['minutes']
    minutes = max(10, min(minutes, 120))
    current = _to_minutes(start)
    rows = []
    for number in range(1, tpl['periods'] + 1):
        rows.append({'kind': 'period', 'start': _fmt_minutes(current),
                     'end': _fmt_minutes(current + minutes), 'label': ''})
        current += minutes
        if number in tpl['breaks']:
            label, length = tpl['breaks'][number]
            rows.append({'kind': 'break', 'start': _fmt_minutes(current),
                         'end': _fmt_minutes(current + length), 'label': label})
            current += length
    return rows


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


def school_start_time():
    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    return clean_time(school.school_start_time if school else '') or DEFAULT_START


def get_config(class_id):
    from app.models.class_ import TimetableConfig
    return TimetableConfig.query.filter_by(class_id=class_id).first()


def load_rows(class_id):
    """Saved rows for the class, or a sensible default when none were saved yet."""
    cfg = get_config(class_id)
    rows = None
    if cfg and cfg.rows_json:
        try:
            rows = json.loads(cfg.rows_json)
        except (TypeError, ValueError):
            rows = None
    if not rows:
        rows = build_rows('standard', school_start_time())
    return number_rows(rows)


def save_config(class_id, rows, incharge_id=None, template_key=None, keep_incharge=False):
    from app.database import db
    from app.models.class_ import TimetableConfig
    cfg = get_config(class_id)
    if cfg is None:
        cfg = TimetableConfig(class_id=class_id)
        db.session.add(cfg)
    cfg.rows_json = json.dumps([{k: r.get(k, '') for k in ('kind', 'start', 'end', 'label')}
                                for r in rows])
    if template_key is not None:
        cfg.template_key = template_key
    if not keep_incharge:
        cfg.incharge_teacher_id = incharge_id
    return cfg


# ------------------------------------------------------------------- auto-fill
def autofill_pairs(subject_ids, lesson_count, day_count=len(DAYS)):
    """{(day, period_no): subject_id}, spreading subjects evenly across the week.

    Consecutive periods get different subjects, and the starting subject shifts
    each day so one subject is not always taught in the same period.
    """
    pairs = {}
    if not subject_ids:
        return pairs
    count = len(subject_ids)
    for day in range(day_count):
        for period in range(1, lesson_count + 1):
            pairs[(day, period)] = subject_ids[(day * (lesson_count + 1) + period - 1) % count]
    return pairs


# ------------------------------------------------------------------ class in-charge
def _assigned_class_names(teacher):
    names = []
    if teacher.assigned_classes:
        try:
            data = json.loads(teacher.assigned_classes)
            if isinstance(data, list):
                names = [str(x).strip() for x in data if str(x).strip()]
        except (TypeError, ValueError):
            names = []
    if not names and teacher.assigned_class:
        names = [p.strip() for p in str(teacher.assigned_class).split(',') if p.strip()]
    return names


def resolve_incharge(class_obj, cfg):
    """(teacher, is_auto). Explicit choice wins; otherwise a lone teacher assigned to the class."""
    if cfg is not None and cfg.incharge_teacher_id:
        teacher = cfg.incharge
        if teacher is not None and teacher.is_active:
            return teacher, False
    from app.models import TeacherModel
    matches = [t for t in TeacherModel.query.filter_by(is_active=True).all()
               if class_obj.name in _assigned_class_names(t)]
    if len(matches) == 1:
        return matches[0], True
    return None, False


# --------------------------------------------------------------------- PDF
def build_timetable_pdf(class_obj, rows, grid, subject_lookup, incharge,
                        include_teachers=True, root_path=None):
    """A4 landscape timetable PDF: logo, class, in-charge, periods with timings."""
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

    title = ParagraphStyle('TTTitle', parent=styles['Heading1'], fontSize=17, alignment=1,
                           fontName='Helvetica-Bold', textColor=dark, spaceAfter=2)
    sub = ParagraphStyle('TTSub', parent=styles['Normal'], fontSize=9, alignment=1,
                         textColor=muted, spaceAfter=3)
    meta = ParagraphStyle('TTMeta', parent=styles['Normal'], fontSize=10.5, alignment=1,
                          textColor=colors.HexColor('#1f2937'), spaceAfter=4)
    cell = ParagraphStyle('TTCell', parent=styles['Normal'], fontSize=9.5, leading=11.5,
                          alignment=1, textColor=dark)
    time_style = ParagraphStyle('TTTime', parent=styles['Normal'], fontSize=8, leading=10,
                                alignment=1, textColor=muted)
    head = ParagraphStyle('TTHead', parent=styles['Normal'], fontSize=9.5, alignment=1,
                          fontName='Helvetica-Bold', textColor=colors.white)

    # Drop an entirely empty Saturday column so a Mon-Fri school gets a clean sheet.
    lesson_numbers = [r['no'] for r in rows if r.get('kind') != 'break']
    day_indices = [d for d in range(len(DAYS))
                   if d < 5 or any(grid.get((d, n)) for n in lesson_numbers)]

    heading = [Paragraph(escape(str(school['name'])), title),
               Paragraph('CLASS TIMETABLE', sub)]
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

    info = ['Class: <b>%s</b>' % escape(class_obj.name)]
    if include_teachers:
        info.append('Class In-charge: <b>%s</b>' % (escape(incharge.teacher_name) if incharge else '&mdash;'))
    if session_label:
        info.append('Session: <b>%s</b>' % escape(session_label))
    story.append(Paragraph(' &nbsp;|&nbsp; '.join(info), meta))
    story.append(Spacer(1, 6))

    data = [[Paragraph('Period / Time', head)] + [Paragraph(DAYS[d], head) for d in day_indices]]
    break_rows = []
    for row in rows:
        start, end = pretty_time(row.get('start')), pretty_time(row.get('end'))
        times = '%s - %s' % (start, end) if start and end else (start or end or '')
        if row.get('kind') == 'break':
            label = escape(row.get('label') or 'Break')
            line = ['<b>%s</b>' % label]
            if times:
                line.append('(%s)' % times)
            data.append([Paragraph('', time_style), Paragraph(' &nbsp; '.join(line), cell)]
                        + [''] * (len(day_indices) - 1))
            break_rows.append(len(data) - 1)
            continue
        label = '<b>Period %d</b>' % row['no']
        if times:
            label += '<br/>' + times
        line = [Paragraph(label, time_style)]
        for d in day_indices:
            subject = subject_lookup.get(grid.get((d, row['no'])))
            if subject is None:
                line.append(Paragraph('&mdash;', cell))
                continue
            text = '<b>%s</b>' % escape(subject.name)
            if include_teachers and subject.teacher:
                text += '<br/><font size="7.5" color="#475569">%s</font>' % escape(subject.teacher.teacher_name)
            line.append(Paragraph(text, cell))
        data.append(line)

    first = 92
    day_width = (usable - first) / float(len(day_indices))
    table = Table(data, colWidths=[first] + [day_width] * len(day_indices), repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), dark),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    for r in break_rows:
        style.append(('SPAN', (1, r), (-1, r)))
        style.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor('#fef3c7')))
    table.setStyle(TableStyle(style))
    story.append(table)

    if include_teachers:
        used = []
        for subject in subject_lookup.values():
            if subject.id in {sid for sid in grid.values() if sid} and subject.teacher:
                used.append('%s: %s' % (escape(subject.name), escape(subject.teacher.teacher_name)))
        if used:
            story.append(Spacer(1, 8))
            story.append(Paragraph('<b>Subject Teachers</b> &nbsp;&mdash;&nbsp; ' + ' &nbsp;|&nbsp; '.join(sorted(used)),
                                   ParagraphStyle('TTLegend', parent=styles['Normal'],
                                                  fontSize=8.5, textColor=muted)))

    story.append(Spacer(1, 26))
    sign = Table([['_______________________', '_______________________'],
                  ['Class In-charge', 'Principal']], colWidths=[usable / 2.0] * 2)
    sign.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                              ('FONTSIZE', (0, 0), (-1, -1), 9),
                              ('TEXTCOLOR', (0, 1), (-1, 1), muted)]))
    story.append(sign)

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=page, leftMargin=margin, rightMargin=margin,
                      topMargin=margin, bottomMargin=margin,
                      title='Timetable - %s' % class_obj.name).build(story)
    buffer.seek(0)
    return buffer
"""Data + PDF helpers for the one-page timetable sheet.

Column layout comes from the School Settings period structure
(``get_timetable_structure``); the only extra value stored here is the time the
school day starts, which is kept as a plain system setting.
"""
import io
import json
import math
import re

from app.database import db
from app.models import ClassModel, SchoolSettings, TeacherModel
from app.models.settings import (get_system_value, get_timetable_structure,
                                 set_system_value)
from app.models.timetable import TimetableCell, TimetableRow

START_KEY = 'timetable_start_time'
DEFAULT_START = '08:00'
MAX_ROWS = 100
_TIME_RE = re.compile(r'^(\d{1,2}):(\d{2})$')


# --------------------------------------------------------------- time helpers
def to_minutes(value):
    """'07:45' -> 465, or None when it is not a valid HH:MM time."""
    match = _TIME_RE.match((value or '').strip())
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        return None
    return hours * 60 + minutes


def fmt(minutes):
    """Compact 12-hour form without AM/PM: 465 -> '7:45', 13:00 -> '1:00'."""
    minutes %= 24 * 60
    return '%d:%02d' % ((minutes // 60) % 12 or 12, minutes % 60)


def get_start_time():
    value = get_system_value(START_KEY, DEFAULT_START)
    return value if to_minutes(value) is not None else DEFAULT_START


# -------------------------------------------------------------------- columns
def build_columns(structure=None):
    """Ordered list of timetable columns (assembly, periods, break).

    Assembly appears only when its length is above 0; the break only when it
    has a position and a length.  ``minutes`` is each column's duration.
    """
    structure = structure or get_timetable_structure()
    columns = []
    if structure['assembly_minutes'] > 0:
        columns.append({'kind': 'assembly', 'key': 'assembly',
                        'label': structure['assembly_label'],
                        'minutes': structure['assembly_minutes']})
    periods = structure['periods_per_day']
    break_after = structure['break_after']
    has_break = 1 <= break_after <= periods and structure['break_minutes'] > 0
    for number in range(1, periods + 1):
        columns.append({'kind': 'period', 'key': 'p%d' % number, 'no': number,
                        'label': 'P%d' % number,
                        'minutes': structure['period_minutes']})
        if has_break and number == break_after:
            columns.append({'kind': 'break', 'key': 'break',
                            'label': structure['break_label'],
                            'minutes': structure['break_minutes']})
    return columns


def with_times(columns, start_value):
    """Add a 'time' string ('7:45 to 8:30') to every column."""
    cursor = to_minutes(start_value)
    if cursor is None:
        cursor = to_minutes(DEFAULT_START)
    result = []
    for column in columns:
        end = cursor + column['minutes']
        result.append(dict(column, time='%s to %s' % (fmt(cursor), fmt(end))))
        cursor = end
    return result


# ----------------------------------------------------------------------- data
def load_sheet():
    """Saved rows as plain dicts, skipping classes that no longer exist."""
    names = {c.id: c.name for c in ClassModel.query.all()}
    rows = []
    for row in TimetableRow.query.order_by(TimetableRow.sort_order, TimetableRow.id).all():
        try:
            ids = [int(i) for i in json.loads(row.class_ids or '[]')]
        except (ValueError, TypeError):
            ids = []
        ids = [i for i in ids if i in names]
        if not ids:
            continue
        rows.append({
            'class_ids': ids,
            'label': ' + '.join(names[i] for i in ids),
            'cells': {str(c.period_no): c.teacher_id for c in row.cells if c.teacher_id},
        })
    return rows


def save_sheet(payload):
    """Validate and replace the whole sheet.  Returns (ok, error_message)."""
    if not isinstance(payload, dict):
        return False, 'Invalid data.'
    start = str(payload.get('start_time') or DEFAULT_START).strip()
    if to_minutes(start) is None:
        return False, 'Start time is not valid.'
    rows = payload.get('rows')
    if not isinstance(rows, list):
        return False, 'Invalid data.'
    if len(rows) > MAX_ROWS:
        return False, 'Too many rows (maximum %d).' % MAX_ROWS

    structure = get_timetable_structure()
    periods = structure['periods_per_day']
    class_names = {c.id: c.name for c in ClassModel.query.all()}
    teacher_ids = {t.id for t in TeacherModel.query.all()}
    used = {}
    clean = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            return False, 'Row %d is not valid.' % index
        ids = []
        for raw in row.get('class_ids') or []:
            try:
                class_id = int(raw)
            except (ValueError, TypeError):
                return False, 'Row %d has an invalid class.' % index
            if class_id not in class_names:
                return False, 'Row %d has a class that no longer exists.' % index
            if class_id in used:
                return False, '%s is added in more than one row (rows %d and %d).' % (
                    class_names[class_id], used[class_id], index)
            used[class_id] = index
            if class_id not in ids:
                ids.append(class_id)
        if not ids:
            return False, 'Row %d has no class selected.' % index
        cells = {}
        raw_cells = row.get('cells') or {}
        if not isinstance(raw_cells, dict):
            return False, 'Row %d is not valid.' % index
        for key, value in raw_cells.items():
            if value in (None, '', 0, '0'):
                continue
            try:
                number, teacher_id = int(key), int(value)
            except (ValueError, TypeError):
                return False, 'Row %d has an invalid cell.' % index
            if not 1 <= number <= periods:
                continue            # period no longer exists in settings
            if teacher_id not in teacher_ids:
                return False, 'Row %d has a teacher that no longer exists.' % index
            cells[number] = teacher_id
        clean.append((ids, cells))

    try:
        TimetableCell.query.delete()
        TimetableRow.query.delete()
        for order, (ids, cells) in enumerate(clean):
            row = TimetableRow(sort_order=order, class_ids=json.dumps(ids))
            db.session.add(row)
            db.session.flush()
            for number, teacher_id in sorted(cells.items()):
                db.session.add(TimetableCell(row_id=row.id, period_no=number,
                                             teacher_id=teacher_id))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    set_system_value(START_KEY, start)
    return True, None


def teacher_options():
    """Active teachers, plus inactive ones that still hold a cell."""
    assigned = {c.teacher_id for c in TimetableCell.query.all() if c.teacher_id}
    teachers = [t for t in TeacherModel.query.order_by(TeacherModel.teacher_name).all()
                if t.is_active or t.id in assigned]
    return [{'id': t.id, 'name': t.teacher_name + ('' if t.is_active else ' (inactive)')}
            for t in teachers]


def class_options():
    return [{'id': c.id, 'name': c.name}
            for c in ClassModel.query.order_by(ClassModel.id).all()]


# ------------------------------------------------------------------------ PDF
def build_pdf(orientation='landscape'):
    """Render the saved sheet as a single-page A4 PDF (BytesIO)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import (Flowable, Paragraph, SimpleDocTemplate,
                                    Table, TableStyle)

    class VerticalText(Flowable):
        """Label rotated to read bottom-to-top, centred in its (spanned) cell."""

        def __init__(self, text, size):
            super().__init__()
            self.text, self.size = text, size
            self.width = self.height = 0

        def wrap(self, avail_w, avail_h):
            self.width, self.height = avail_w, avail_h
            return avail_w, avail_h

        def draw(self):
            canvas = self.canv
            canvas.saveState()
            canvas.setFont('Helvetica-Bold', self.size)
            canvas.translate(self.width / 2.0 + self.size * 0.35, self.height / 2.0)
            canvas.rotate(90)
            canvas.drawCentredString(0, 0, self.text)
            canvas.restoreState()

    structure = get_timetable_structure()
    columns = with_times(build_columns(structure), get_start_time())
    rows = load_sheet()
    teachers = {t.id: t.teacher_name for t in TeacherModel.query.all()}
    settings = SchoolSettings.query.first()
    school_name = (getattr(settings, 'school_name', None) or 'School').strip()

    portrait = orientation == 'portrait'
    page = A4 if portrait else landscape(A4)
    margin = 20
    page_w, page_h = page
    avail_w = page_w - 2 * margin

    sr_w, class_w, side_w = 24, (78 if portrait else 96), 30
    fixed = sr_w + class_w + side_w * sum(1 for c in columns if c['kind'] != 'period')
    period_cols = [c for c in columns if c['kind'] == 'period']
    period_w = (avail_w - fixed) / float(max(1, len(period_cols)))
    col_widths = [sr_w, class_w] + [side_w if c['kind'] != 'period' else period_w
                                    for c in columns]

    title_h, header_h = 46, 34
    body_h = page_h - 2 * margin - title_h - header_h - 6
    count = max(1, len(rows))
    row_h = min(body_h / float(count), 44.0)

    # shrink the font until the longest names fit their cell without overflow
    font = min(9.0, max(5.0, row_h * 0.42))
    while font > 5.0:
        lines_ok = True
        for row in rows:
            for tid in row['cells'].values():
                name = teachers.get(tid, '')
                lines = math.ceil(stringWidth(name, 'Helvetica', font) / max(1.0, period_w - 6))
                if lines * font * 1.2 > row_h - 3:
                    lines_ok = False
                    break
            label_lines = math.ceil(stringWidth(row['label'], 'Helvetica-Bold', font)
                                    / max(1.0, class_w - 6))
            if lines_ok and label_lines * font * 1.2 > row_h - 3:
                lines_ok = False
            if not lines_ok:
                break
        if lines_ok:
            break
        font -= 0.5

    cell_style = ParagraphStyle('ttcell', fontName='Helvetica', fontSize=font,
                                leading=font * 1.2, alignment=1)
    class_style = ParagraphStyle('ttclass', parent=cell_style, fontName='Helvetica-Bold')
    head_style = ParagraphStyle('tthead', parent=cell_style, fontName='Helvetica-Bold',
                                fontSize=min(font, 7.5), leading=min(font, 7.5) * 1.2)
    title_style = ParagraphStyle('tttitle', fontName='Helvetica-Bold', fontSize=15,
                                 leading=18, alignment=1)
    sub_style = ParagraphStyle('ttsub', fontName='Helvetica', fontSize=9,
                               leading=11, alignment=1, textColor=colors.HexColor('#444444'))

    def esc(text):
        return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    header = [Paragraph('Sr', head_style), Paragraph('Class', head_style)]
    side_head = ParagraphStyle('ttside', parent=head_style, fontSize=6.5, leading=7.8)
    for column in columns:
        start, end = column['time'].split(' to ')
        header.append(Paragraph('%s<br/>to<br/>%s' % (start, end),
                                head_style if column['kind'] == 'period' else side_head))
    data = [header]
    side_font = min(10.0, max(6.0, row_h * 0.3))
    for number, row in enumerate(rows, start=1):
        line = [Paragraph(str(number), cell_style), Paragraph(esc(row['label']), class_style)]
        for column in columns:
            if column['kind'] == 'period':
                name = teachers.get(row['cells'].get(str(column['no'])), '')
                line.append(Paragraph(esc(name), cell_style) if name else '')
            elif number == 1:
                line.append(VerticalText(column['label'], side_font))
            else:
                line.append('')
        data.append(line)

    story = [Paragraph(esc(school_name), title_style),
             Paragraph('Class Timetable', sub_style)]
    style = [
        ('GRID', (0, 0), (-1, -1), 0.6, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]
    if rows:
        for index, column in enumerate(columns, start=2):
            if column['kind'] != 'period':
                style.append(('SPAN', (index, 1), (index, len(rows))))
                style.append(('BACKGROUND', (index, 1), (index, len(rows)),
                              colors.HexColor('#d1d5db')))
        table = Table(data, colWidths=col_widths,
                      rowHeights=[header_h] + [row_h] * len(rows))
        table.setStyle(TableStyle(style))
        story.append(Paragraph('&nbsp;', sub_style))
        story.append(table)
    else:
        story.append(Paragraph('<br/><br/>No timetable rows have been added yet.', sub_style))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=page, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin,
                            title='Class Timetable')
    doc.build(story)
    output.seek(0)
    return output

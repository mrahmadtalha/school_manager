"""Attendance export builders: PDF, XLSX and CSV.

Every export carries school branding (logo, name, tagline, contact details),
the class / "Whole School" context, the reporting period and the attendance
figures — including late-arrival minutes for both students and teachers.
"""

import csv
import io
import os
from datetime import date, datetime
from xml.sax.saxutils import escape as _xml_escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)

try:  # Pillow is required by reportlab; guard so a missing install never breaks exports.
    from openpyxl.drawing.image import Image as XLImage
except Exception:  # pragma: no cover - defensive
    XLImage = None


# ==========================================
# SHARED HELPERS
# ==========================================

HEADER_FILL = PatternFill('solid', fgColor='2D3748')
HEADER_FONT = Font(bold=True, color='FFFFFF', size=10)
TITLE_FONT = Font(bold=True, size=14, color='1A202C')
SUBTITLE_FONT = Font(bold=True, size=11, color='2D3748')
META_FONT = Font(size=10, color='4A5568')
_THIN = Side(style='thin', color='CBD5E0')
CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
CENTER = Alignment(horizontal='center', vertical='center')
LEFT = Alignment(horizontal='left', vertical='center')


def _esc(value):
    return _xml_escape(str('' if value is None else value))


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return date.today()


def school_branding(app_root=None):
    """Collect the school identity used in every export header."""
    if app_root is None:
        try:
            from flask import current_app
            app_root = current_app.root_path
        except Exception:
            app_root = None

    school = None
    try:
        from app.models import SchoolSettings
        school = SchoolSettings.query.first()
    except Exception:
        school = None

    logo_filename = (getattr(school, 'logo_filename', '') or '').strip()
    logo_path = ''
    if logo_filename and app_root:
        # Data folder first (installed products keep the install dir
        # read-only), then the legacy static copy.
        try:
            from flask import current_app
            candidate = os.path.join(current_app.config['DATA_DIR'],
                                     'uploads', logo_filename)
            if os.path.isfile(candidate):
                logo_path = candidate
        except Exception:  # no app context (scripts)
            pass
        if not logo_path:
            candidate = os.path.join(app_root, 'static', logo_filename)
            if os.path.isfile(candidate):
                logo_path = candidate

    return {
        'name': (getattr(school, 'school_name', '') or 'School Manager').strip(),
        'tagline': (getattr(school, 'tagline', '') or '').strip(),
        'address': (getattr(school, 'address', '') or '').strip(),
        'phone': (getattr(school, 'phone', '') or '').strip(),
        'email': (getattr(school, 'email', '') or '').strip(),
        'logo_path': logo_path,
    }


def _logo_flowable(logo_path, max_w=95, max_h=60):
    """Build a size-preserving reportlab Image for the school logo."""
    if not logo_path:
        return None
    try:
        width, height = ImageReader(logo_path).getSize()
        if not width or not height:
            return None
        scale = min(max_w / float(width), max_h / float(height))
        return Image(logo_path, width=width * scale, height=height * scale)
    except Exception:
        return None


def _pdf_styles():
    styles = getSampleStyleSheet()
    return {
        'school': ParagraphStyle('SchoolName', parent=styles['Heading1'], fontSize=15,
                                 textColor=colors.HexColor('#1a202c'), spaceAfter=2,
                                 alignment=1),
        'contact': ParagraphStyle('Contact', parent=styles['Normal'], fontSize=8.5,
                                  textColor=colors.HexColor('#4a5568'), spaceAfter=4,
                                  alignment=1),
        'title': ParagraphStyle('ReportTitle', parent=styles['Heading2'], fontSize=13,
                                textColor=colors.HexColor('#2d3748'), spaceAfter=3,
                                alignment=1),
        'meta': ParagraphStyle('Meta', parent=styles['Normal'], fontSize=9,
                               textColor=colors.HexColor('#4a5568'), spaceAfter=10,
                               alignment=1),
        'normal': styles['Normal'],
    }


def _pdf_header(story, branding, title, meta_line):
    """Append the branded header (logo, school name, title, meta) to a story."""
    styles = _pdf_styles()
    logo = _logo_flowable(branding['logo_path'])
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    story.append(Paragraph(_esc(branding['name']), styles['school']))
    contact_bits = [b for b in (branding['tagline'], branding['address'],
                                branding['phone'], branding['email']) if b]
    if contact_bits:
        story.append(Paragraph(_esc(' | '.join(contact_bits)), styles['contact']))
    story.append(Paragraph(_esc(title), styles['title']))
    if meta_line:
        story.append(Paragraph(meta_line, styles['meta']))
    story.append(Spacer(1, 4))


def _pdf_table(table_data, font_size=8, extra_style=None):
    table = Table(table_data)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), font_size),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    if extra_style:
        style.extend(extra_style)
    table.setStyle(TableStyle(style))
    return table


def _safe_filename(*parts):
    raw = '_'.join(str(p) for p in parts if p not in (None, ''))
    cleaned = ''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in raw)
    return cleaned or 'attendance'


def _late_text(status, late_time, late_minutes):
    """Render a status plus any late-arrival detail."""
    text = status or '—'
    if text == 'Late':
        detail = []
        if late_time:
            detail.append(str(late_time))
        if late_minutes is not None:
            detail.append(f'{late_minutes} min')
        if detail:
            text = f"Late ({' / '.join(detail)})"
    return text


# ==========================================
# XLSX HELPERS
# ==========================================

def _xlsx_metadata(ws, branding, title, meta_lines, trailing_cols):
    """Write the branded title block; return the next free row number."""
    row = 1
    ws.cell(row=row, column=1, value=branding['name']).font = TITLE_FONT
    row += 1
    contact_bits = [b for b in (branding['tagline'], branding['address'],
                                branding['phone'], branding['email']) if b]
    if contact_bits:
        ws.cell(row=row, column=1, value=' | '.join(contact_bits)).font = META_FONT
        row += 1
    ws.cell(row=row, column=1, value=title).font = SUBTITLE_FONT
    row += 1
    for line in meta_lines:
        if line:
            ws.cell(row=row, column=1, value=line).font = META_FONT
            row += 1

    if branding['logo_path'] and XLImage is not None:
        try:
            img = XLImage(branding['logo_path'])
            width, height = img.width or 0, img.height or 0
            if width and height:
                scale = min(90.0 / width, 60.0 / height, 1.0)
                img.width, img.height = width * scale, height * scale
            anchor_col = get_column_letter(max(int(trailing_cols) + 2, 5))
            ws.add_image(img, f'{anchor_col}1')
        except Exception:
            pass

    return row + 1


def _xlsx_write_table(ws, start_row, header, rows, bold_last_cols=()):
    for col, value in enumerate(header, 1):
        cell = ws.cell(row=start_row, column=col, value=value)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = CELL_BORDER
    for offset, row_values in enumerate(rows, 1):
        for col, value in enumerate(row_values, 1):
            cell = ws.cell(row=start_row + offset, column=col, value=value)
            cell.border = CELL_BORDER
            cell.alignment = LEFT if col <= 3 else CENTER
            if col in bold_last_cols:
                cell.font = Font(bold=True)
    last_row = start_row + len(rows)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = (
            f'A{start_row}:{get_column_letter(len(header))}{last_row}')
    return last_row


def _xlsx_autosize(ws, header, rows):
    for col in range(1, len(header) + 1):
        longest = len(str(header[col - 1]))
        for row_values in rows:
            if col <= len(row_values):
                longest = max(longest, len(str(row_values[col - 1])))
        ws.column_dimensions[get_column_letter(col)].width = min(max(longest + 2, 6), 26)


def _csv_metadata(writer, branding, title, meta_lines):
    writer.writerow(['School', branding['name']])
    if branding['tagline']:
        writer.writerow(['Tagline', branding['tagline']])
    if branding['address']:
        writer.writerow(['Address', branding['address']])
    if branding['phone']:
        writer.writerow(['Phone', branding['phone']])
    writer.writerow(['Report', title])
    for line in meta_lines:
        if line and ':' in line:
            label, _, value = line.partition(':')
            writer.writerow([label.strip(), value.strip()])
    writer.writerow([])


# ==========================================
# CLASS (DAILY) ATTENDANCE SHEET EXPORTS
# ==========================================

def generate_class_attendance_pdf(class_obj, students, selected_date,
                                  attendance_map=None, late_time_map=None,
                                  late_minutes_map=None):
    """Printable PDF sheet for one class on one date, with branding and late minutes."""
    attendance_map = attendance_map or {}
    late_time_map = late_time_map or {}
    late_minutes_map = late_minutes_map or {}
    branding = school_branding()
    day = _as_date(selected_date)
    is_recorded = bool(attendance_map)

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=30, bottomMargin=30)
    story = []
    styles = _pdf_styles()

    if is_recorded:
        total = len(students)
        p_count = sum(1 for s in students if attendance_map.get(s.id) == 'Present')
        a_count = sum(1 for s in students if attendance_map.get(s.id) == 'Absent')
        l_count = sum(1 for s in students if attendance_map.get(s.id) == 'Late')
        late_total = sum(int(late_minutes_map.get(s.id) or 0) for s in students)
        title = 'Student Attendance Report'
        meta = (f"<b>Class:</b> {_esc(class_obj.name)} &nbsp;|&nbsp; "
                f"<b>Date:</b> {day.strftime('%d %b %Y')} &nbsp;|&nbsp; "
                f"<b>Total:</b> {total} &nbsp; <b>Present:</b> {p_count} &nbsp; "
                f"<b>Absent:</b> {a_count} &nbsp; <b>Late:</b> {l_count} &nbsp; "
                f"<b>Late minutes:</b> {late_total}")
    else:
        title = 'Student Attendance Sheet'
        meta = (f"<b>Class:</b> {_esc(class_obj.name)} &nbsp;|&nbsp; "
                f"<b>Date:</b> {day.strftime('%d %b %Y')}")

    _pdf_header(story, branding, title, meta)

    status_header = 'Status' if is_recorded else 'Status (P / A / L / LV)'
    late_header = 'Late minutes' if is_recorded else ''
    table_data = [['Roll No', 'Student Name', 'Father Name', status_header, late_header, 'Remarks']]
    for s in students:
        if is_recorded:
            status_cell = _late_text(attendance_map.get(s.id, '—'),
                                     late_time_map.get(s.id),
                                     late_minutes_map.get(s.id))
            late_cell = str(late_minutes_map.get(s.id) or '') \
                if attendance_map.get(s.id) == 'Late' else ''
        else:
            status_cell = '___________________'
            late_cell = ''
        table_data.append([str(s.roll_number), str(s.student_name),
                           str(s.father_name), status_cell, late_cell, ''])

    story.append(_pdf_table(table_data, font_size=9))
    doc.build(story)
    output.seek(0)
    return output


def generate_class_attendance_excel(class_obj, students, attendance_map=None,
                                    late_time_map=None, late_minutes_map=None,
                                    selected_date=None):
    """Branded XLSX sheet for one class on one date."""
    attendance_map = attendance_map or {}
    late_time_map = late_time_map or {}
    late_minutes_map = late_minutes_map or {}
    branding = school_branding()
    is_recorded = bool(attendance_map)

    header = ['Roll Number', 'Student Name', 'Father Name', 'Status',
              'Late Time', 'Late Minutes', 'Remarks']
    rows = []
    for s in students:
        if is_recorded:
            status = attendance_map.get(s.id, '—')
            late_time = late_time_map.get(s.id) or ''
            late_minutes = late_minutes_map.get(s.id)
            if status != 'Late':
                late_time, late_minutes = '', ''
            elif late_minutes is None:
                late_minutes = ''
        else:
            status, late_time, late_minutes = '—', '', ''
        rows.append([s.roll_number, s.student_name, s.father_name, status,
                     late_time, late_minutes, ''])

    wb = Workbook()
    ws = wb.active
    ws.title = f'Class {class_obj.name}'[:31]
    meta_lines = [f'Class: {class_obj.name}']
    if selected_date:
        meta_lines.append(f'Date: {_as_date(selected_date).strftime("%d %b %Y")}')
    if is_recorded:
        meta_lines.append(
            f'Present: {sum(1 for s in students if attendance_map.get(s.id) == "Present")} | '
            f'Absent: {sum(1 for s in students if attendance_map.get(s.id) == "Absent")} | '
            f'Late: {sum(1 for s in students if attendance_map.get(s.id) == "Late")} | '
            f'Late minutes: {sum(int(late_minutes_map.get(s.id) or 0) for s in students)}')
    start_row = _xlsx_metadata(ws, branding, 'Student Attendance Report',
                               meta_lines, len(header))
    _xlsx_write_table(ws, start_row, header, rows)
    _xlsx_autosize(ws, header, rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_class_attendance_csv(class_obj, students, attendance_map=None,
                                  late_time_map=None, late_minutes_map=None,
                                  selected_date=None):
    """Branded CSV sheet for one class on one date."""
    attendance_map = attendance_map or {}
    late_time_map = late_time_map or {}
    late_minutes_map = late_minutes_map or {}
    branding = school_branding()
    is_recorded = bool(attendance_map)

    output = io.StringIO()
    writer = csv.writer(output)
    meta_lines = [f'Class: {class_obj.name}']
    if selected_date:
        meta_lines.append(f'Date: {_as_date(selected_date).strftime("%d %b %Y")}')
    if is_recorded:
        meta_lines.append(
            f'Present: {sum(1 for s in students if attendance_map.get(s.id) == "Present")}')
        meta_lines.append(
            f'Absent: {sum(1 for s in students if attendance_map.get(s.id) == "Absent")}')
        meta_lines.append(
            f'Late: {sum(1 for s in students if attendance_map.get(s.id) == "Late")}')
        meta_lines.append(
            f'Late minutes: {sum(int(late_minutes_map.get(s.id) or 0) for s in students)}')
    _csv_metadata(writer, branding, 'Student Attendance Report', meta_lines)

    writer.writerow(['Roll Number', 'Student Name', 'Father Name', 'Status',
                     'Late Time', 'Late Minutes', 'Remarks'])
    for s in students:
        if is_recorded:
            status = attendance_map.get(s.id, '—')
            late_time = late_time_map.get(s.id) or ''
            late_minutes = late_minutes_map.get(s.id)
            if status != 'Late':
                late_time, late_minutes = '', ''
            elif late_minutes is None:
                late_minutes = ''
        else:
            status, late_time, late_minutes = '', '', ''
        writer.writerow([s.roll_number, s.student_name, s.father_name, status,
                         late_time, late_minutes, ''])
    return output.getvalue()


# ==========================================
# TEACHER (DAILY) ATTENDANCE SHEET EXPORTS
# ==========================================

def generate_teacher_attendance_pdf(teachers, selected_date, attendance_map=None,
                                    late_time_map=None, late_minutes_map=None):
    """Branded teacher attendance sheet/report for one date, including late minutes."""
    attendance_map = attendance_map or {}
    late_time_map = late_time_map or {}
    late_minutes_map = late_minutes_map or {}
    branding = school_branding()
    day = _as_date(selected_date)
    is_recorded = bool(attendance_map)

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30,
                            topMargin=30, bottomMargin=30)
    story = []
    styles = _pdf_styles()

    if is_recorded:
        p_count = sum(1 for t in teachers if attendance_map.get(t.id) == 'Present')
        a_count = sum(1 for t in teachers if attendance_map.get(t.id) == 'Absent')
        l_count = sum(1 for t in teachers if attendance_map.get(t.id) == 'Late')
        late_total = sum(int(late_minutes_map.get(t.id) or 0) for t in teachers)
        title = 'Teacher Attendance Report'
        meta = (f"<b>Date:</b> {day.strftime('%d %b %Y')} &nbsp;|&nbsp; "
                f"<b>Total:</b> {len(teachers)} &nbsp; <b>Present:</b> {p_count} &nbsp; "
                f"<b>Absent:</b> {a_count} &nbsp; <b>Late:</b> {l_count} &nbsp; "
                f"<b>Late minutes:</b> {late_total}")
    else:
        title = 'Teacher Attendance Sheet'
        meta = f"<b>Date:</b> {day.strftime('%d %b %Y')}"

    _pdf_header(story, branding, title, meta)

    status_header = 'Status' if is_recorded else 'Status (P / A / L / LV)'
    table_data = [['Teacher ID', 'Teacher Name', 'Qualification', status_header,
                   'Late minutes', 'Signature / Remarks']]
    for t in teachers:
        if is_recorded:
            status_cell = _late_text(attendance_map.get(t.id, '—'),
                                     late_time_map.get(t.id),
                                     late_minutes_map.get(t.id))
            late_cell = str(late_minutes_map.get(t.id) or '') \
                if attendance_map.get(t.id) == 'Late' else ''
        else:
            status_cell, late_cell = '___________________', ''
        table_data.append([str(t.teacher_id_str), str(t.teacher_name),
                           str(t.qualification), status_cell, late_cell, ''])

    story.append(_pdf_table(table_data, font_size=9))
    doc.build(story)
    output.seek(0)
    return output


def generate_teacher_attendance_excel(teachers, attendance_map=None,
                                      late_time_map=None, late_minutes_map=None,
                                      selected_date=None):
    """Branded XLSX teacher attendance sheet including late minutes."""
    attendance_map = attendance_map or {}
    late_time_map = late_time_map or {}
    late_minutes_map = late_minutes_map or {}
    branding = school_branding()
    is_recorded = bool(attendance_map)

    header = ['Teacher ID', 'Teacher Name', 'Qualification', 'Status',
              'Late Time', 'Late Minutes', 'Remarks']
    rows = []
    for t in teachers:
        if is_recorded:
            status = attendance_map.get(t.id, '—')
            late_time = late_time_map.get(t.id) or ''
            late_minutes = late_minutes_map.get(t.id)
            if status != 'Late':
                late_time, late_minutes = '', ''
            elif late_minutes is None:
                late_minutes = ''
        else:
            status, late_time, late_minutes = '—', '', ''
        rows.append([t.teacher_id_str, t.teacher_name, t.qualification,
                     status, late_time, late_minutes, ''])

    wb = Workbook()
    ws = wb.active
    ws.title = 'Teacher Attendance'
    meta_lines = []
    if selected_date:
        meta_lines.append(f'Date: {_as_date(selected_date).strftime("%d %b %Y")}')
    if is_recorded:
        meta_lines.append(
            f'Present: {sum(1 for t in teachers if attendance_map.get(t.id) == "Present")} | '
            f'Absent: {sum(1 for t in teachers if attendance_map.get(t.id) == "Absent")} | '
            f'Late: {sum(1 for t in teachers if attendance_map.get(t.id) == "Late")} | '
            f'Late minutes: {sum(int(late_minutes_map.get(t.id) or 0) for t in teachers)}')
    start_row = _xlsx_metadata(ws, branding, 'Teacher Attendance Report',
                               meta_lines, len(header))
    _xlsx_write_table(ws, start_row, header, rows)
    _xlsx_autosize(ws, header, rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_teacher_attendance_csv(teachers, attendance_map=None,
                                    late_time_map=None, late_minutes_map=None,
                                    selected_date=None):
    """Branded CSV teacher attendance sheet including late minutes."""
    attendance_map = attendance_map or {}
    late_time_map = late_time_map or {}
    late_minutes_map = late_minutes_map or {}
    branding = school_branding()
    is_recorded = bool(attendance_map)

    output = io.StringIO()
    writer = csv.writer(output)
    meta_lines = []
    if selected_date:
        meta_lines.append(f'Date: {_as_date(selected_date).strftime("%d %b %Y")}')
    if is_recorded:
        meta_lines.append(
            f'Present: {sum(1 for t in teachers if attendance_map.get(t.id) == "Present")}')
        meta_lines.append(
            f'Absent: {sum(1 for t in teachers if attendance_map.get(t.id) == "Absent")}')
        meta_lines.append(
            f'Late: {sum(1 for t in teachers if attendance_map.get(t.id) == "Late")}')
        meta_lines.append(
            f'Late minutes: {sum(int(late_minutes_map.get(t.id) or 0) for t in teachers)}')
    _csv_metadata(writer, branding, 'Teacher Attendance Report', meta_lines)

    writer.writerow(['Teacher ID', 'Teacher Name', 'Qualification', 'Status',
                     'Late Time', 'Late Minutes', 'Remarks'])
    for t in teachers:
        if is_recorded:
            status = attendance_map.get(t.id, '—')
            late_time = late_time_map.get(t.id) or ''
            late_minutes = late_minutes_map.get(t.id)
            if status != 'Late':
                late_time, late_minutes = '', ''
            elif late_minutes is None:
                late_minutes = ''
        else:
            status, late_time, late_minutes = '', '', ''
        writer.writerow([t.teacher_id_str, t.teacher_name, t.qualification,
                         status, late_time, late_minutes, ''])
    return output.getvalue()


# ==========================================
# SUMMARY (MATRIX) EXPORTS
# ==========================================

def _summary_scope(summary, mode):
    """Return (title_scope, report_title, meta_lines, include_class_column)."""
    if mode == 'school':
        return ('Whole School', 'School Attendance Summary Report',
                ['Scope: All school students'], True)
    if mode == 'teacher':
        return ('All Teachers', 'Teacher Attendance Summary Report',
                ['Scope: All active teachers'], False)
    class_name = getattr(summary.get('class_obj'), 'name', '') or 'Class'
    return (class_name, 'Attendance Summary Report',
            [f'Class: {class_name}'], False)


def _summary_columns(summary, mode):
    """Header row and per-row builder shared by all summary export formats."""
    include_class = mode == 'school'
    if mode == 'teacher':
        header = ['Sr', 'Teacher ID', 'Teacher Name', 'Qualification']
    else:
        header = ['Sr', 'Roll No', 'Student Name']
        if include_class:
            header.append('Class')
        header.append('Father Name')
    header += [d.strftime('%d/%m/%Y') for d in summary['dates_list']]
    header += ['Present', 'Absent', 'Late', 'Late Minutes', 'Percentage']

    rows = []
    for row in summary['matrix_data']:
        person = row.get('student') or row.get('teacher')
        if mode == 'teacher':
            line = [row['sr'], person.teacher_id_str, person.teacher_name,
                    person.qualification]
        else:
            line = [row['sr'], person.roll_number, person.student_name]
            if include_class:
                cls = summary.get('classes', {}).get(getattr(person, 'class_id', None))
                line.append(cls.name if cls else '—')
            line.append(getattr(person, 'father_name', '') or '')
        for d in summary['dates_list']:
            status = row['daily_status'].get(d, '—')
            if status == 'Late':
                minutes = row['daily_late_minutes'].get(d)
                line.append(f'L ({minutes}m)' if minutes is not None else 'L')
            else:
                line.append(status)
        line += [row['p_count'], row['a_count'], row['l_count'],
                 row['total_late_minutes'], f"{row['percentage']}%"]
        rows.append(line)
    return header, rows


def _summary_meta(summary, start_date, end_date, mode):
    stats = summary.get('kpi_stats', {})
    days = len(summary['dates_list'])
    lines = []
    if mode == 'class':
        lines.append(f"Class: {getattr(summary.get('class_obj'), 'name', '')}")
    elif mode == 'school':
        lines.append('Scope: All school students')
    else:
        lines.append('Scope: All active teachers')
    lines.append(f"Period: {_as_date(start_date).strftime('%d %b %Y')} to "
                 f"{_as_date(end_date).strftime('%d %b %Y')}")
    lines.append(f"Attendance days: {days}")
    if mode != 'teacher':
        lines.append(f"Students: {stats.get('total_students', 0)} | "
                     f"Average rate: {stats.get('avg_percentage', 0)}% | "
                     f"At risk (<75%): {stats.get('at_risk_count', 0)}")
    return lines


def generate_summary_pdf(summary, start_date, end_date, mode='class'):
    """Landscape branded PDF matrix summary for a class, the whole school or teachers."""
    scope, report_title, _, _ = _summary_scope(summary, mode)
    branding = school_branding()
    dates_list = summary['dates_list']

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=20,
                            leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    meta = ' &nbsp;&nbsp;|&nbsp;&nbsp; '.join(
        _esc(line) for line in _summary_meta(summary, start_date, end_date, mode))
    _pdf_header(story, branding, f'{report_title} — {scope}', meta)

    if not dates_list:
        story.append(Paragraph('No attendance records found for this period.',
                               _pdf_styles()['normal']))
        doc.build(story)
        output.seek(0)
        return output

    # Compact table: date columns keep only the day number.
    header, rows = _summary_columns(summary, mode)
    date_count = len(dates_list)
    fixed_cols = len(header) - date_count - 5
    compact_header = (header[:fixed_cols]
                      + [d.strftime('%d/%m') for d in dates_list]
                      + header[-5:])
    compact_rows = []
    for row in rows:
        compact_rows.append(row[:fixed_cols] + row[fixed_cols:fixed_cols + date_count]
                            + row[-5:])

    story.append(_pdf_table([compact_header] + compact_rows, font_size=7))
    doc.build(story)
    output.seek(0)
    return output


def generate_summary_excel(summary, start_date, end_date, mode='class'):
    """Branded XLSX matrix summary for a class, the whole school or teachers."""
    _, report_title, _, _ = _summary_scope(summary, mode)
    branding = school_branding()
    header, rows = _summary_columns(summary, mode)
    meta_lines = _summary_meta(summary, start_date, end_date, mode)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Attendance Summary'[:31]
    start_row = _xlsx_metadata(ws, branding, report_title, meta_lines, len(header))
    if not summary['dates_list']:
        ws.cell(row=start_row, column=1,
                value='No attendance records found for this period.')
    else:
        _xlsx_write_table(ws, start_row, header, rows,
                          bold_last_cols={len(header), len(header) - 1})
        _xlsx_autosize(ws, header, rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_summary_csv(summary, start_date, end_date, mode='class'):
    """Branded CSV matrix summary for a class, the whole school or teachers."""
    _, report_title, _, _ = _summary_scope(summary, mode)
    branding = school_branding()
    header, rows = _summary_columns(summary, mode)
    meta_lines = _summary_meta(summary, start_date, end_date, mode)

    output = io.StringIO()
    writer = csv.writer(output)
    _csv_metadata(writer, branding, report_title, meta_lines)
    if not summary['dates_list']:
        writer.writerow(['No attendance records found for this period.'])
    else:
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return output.getvalue()

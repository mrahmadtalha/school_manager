import io
import os
from datetime import date

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import SchoolSettings

NAVY = (0.09, 0.16, 0.29)
GOLD = (0.72, 0.55, 0.22)
WHITE = (1, 1, 1)
SLATE = (0.29, 0.33, 0.41)
LIGHT = (0.96, 0.97, 0.99)

CARD_W = 86 * mm
CARD_H = 54 * mm


def academic_session(today=None):
    today = today or date.today()
    if today.month >= 4:
        return f'{today.year}-{today.year + 1}'
    return f'{today.year - 1}-{today.year}'


def school_branding(app_root=None):
    school = SchoolSettings.query.first()
    name = school.school_name if school and school.school_name else 'School Manager'
    tagline = school.tagline if school and school.tagline else ''
    address = school.address if school and school.address else ''
    phone = school.phone if school and school.phone else ''
    email = school.email if school and school.email else ''
    logo_path = ''
    if school and school.logo_filename and app_root:
        candidate = os.path.join(app_root, 'static', school.logo_filename)
        if os.path.isfile(candidate):
            logo_path = candidate
    return {
        'name': name,
        'tagline': tagline,
        'address': address,
        'phone': phone,
        'email': email,
        'logo_path': logo_path,
    }


def _set_fill(c, rgb):
    c.setFillColorRGB(*rgb)


def _set_stroke(c, rgb):
    c.setStrokeColorRGB(*rgb)


def _fit_text(c, text, x, y, max_width, font='Helvetica-Bold', max_size=11, min_size=6.5, align='left'):
    text = text or ''
    size = max_size
    while size >= min_size and c.stringWidth(text, font, size) > max_width:
        size -= 0.4
    if c.stringWidth(text, font, size) > max_width:
        while text and c.stringWidth(text + '…', font, size) > max_width:
            text = text[:-1]
        text = text + '…'
    c.setFont(font, size)
    if align == 'center':
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _draw_logo(c, path, x, y, size):
    if not path:
        return False
    try:
        image = ImageReader(path)
        c.drawImage(image, x, y, width=size, height=size, preserveAspectRatio=True, mask='auto')
        return True
    except Exception:
        return False


def _draw_qr(c, payload, x, y, size):
    widget = QrCodeWidget(payload)
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _draw_initials_badge(c, name, x, y, size):
    parts = [part for part in (name or '').split() if part]
    initials = ''.join(p[0] for p in parts[:2]).upper() or '?'
    _set_fill(c, (0.91, 0.94, 0.98))
    _set_stroke(c, NAVY)
    c.setLineWidth(1)
    c.circle(x + size / 2, y + size / 2, size / 2, fill=1, stroke=1)
    _set_fill(c, NAVY)
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(x + size / 2, y + size / 2 - 4, initials)


def _draw_id_card(c, x, y, person, school, session):
    c.saveState()
    c.setLineWidth(1.4)
    _set_stroke(c, NAVY)
    _set_fill(c, WHITE)
    c.roundRect(x, y, CARD_W, CARD_H, 4, fill=1, stroke=1)

    header_h = 14 * mm
    _set_fill(c, NAVY)
    c.rect(x, y + CARD_H - header_h, CARD_W, header_h, fill=1, stroke=0)
    _set_fill(c, GOLD)
    c.rect(x, y + CARD_H - header_h - 1.6, CARD_W, 1.6, fill=1, stroke=0)

    logo_size = 10 * mm
    logo_x = x + 3 * mm
    logo_y = y + CARD_H - header_h + 2 * mm
    drew_logo = _draw_logo(c, school['logo_path'], logo_x, logo_y, logo_size)
    title_x = logo_x + (logo_size + 2 * mm if drew_logo else 0)
    _set_fill(c, WHITE)
    _fit_text(
        c, school['name'], title_x, y + CARD_H - 7 * mm,
        CARD_W - (title_x - x) - 4 * mm, font='Helvetica-Bold', max_size=9, min_size=6,
    )
    subtitle = school['tagline'] or person.get('role_label', 'IDENTITY CARD')
    _fit_text(
        c, subtitle, title_x, y + CARD_H - 11.2 * mm,
        CARD_W - (title_x - x) - 4 * mm, font='Helvetica', max_size=6.5, min_size=5,
    )

    photo_size = 18 * mm
    photo_x = x + 3.5 * mm
    photo_y = y + 16 * mm
    _set_stroke(c, (0.78, 0.82, 0.89))
    _set_fill(c, LIGHT)
    c.roundRect(photo_x, photo_y, photo_size, photo_size, 2, fill=1, stroke=1)
    _draw_initials_badge(c, person['name'], photo_x + 1.5 * mm, photo_y + 1.5 * mm, photo_size - 3 * mm)

    info_x = photo_x + photo_size + 3 * mm
    info_w = CARD_W - (info_x - x) - 18 * mm
    _set_fill(c, NAVY)
    _fit_text(c, person['name'], info_x, y + CARD_H - header_h - 8 * mm, info_w, max_size=10, min_size=7)

    rows = person.get('rows') or []
    row_y = y + CARD_H - header_h - 13 * mm
    for label, value in rows:
        _set_fill(c, SLATE)
        c.setFont('Helvetica', 6)
        c.drawString(info_x, row_y, f'{label}:')
        _set_fill(c, (0.12, 0.16, 0.23))
        _fit_text(c, str(value or '—'), info_x + 16 * mm, row_y, info_w - 16 * mm, font='Helvetica-Bold', max_size=7, min_size=5.5)
        row_y -= 4.2 * mm

    qr_size = 14 * mm
    _draw_qr(c, person['qr'], x + CARD_W - qr_size - 3 * mm, y + 16.5 * mm, qr_size)

    _set_fill(c, NAVY)
    c.rect(x, y, CARD_W, 8.5 * mm, fill=1, stroke=0)
    _set_fill(c, GOLD)
    c.rect(x, y + 8.5 * mm, CARD_W, 1.2, fill=1, stroke=0)
    _set_fill(c, WHITE)
    c.setFont('Helvetica', 6)
    c.drawString(x + 3 * mm, y + 4.6 * mm, person.get('badge', 'STUDENT ID'))
    c.drawRightString(x + CARD_W - 3 * mm, y + 4.6 * mm, f'Session {session}')
    c.setFont('Helvetica', 5)
    contact = school['phone'] or school['address'] or 'If found, return to the school office.'
    c.drawString(x + 3 * mm, y + 2 * mm, contact[:70])
    c.restoreState()


def student_card_payload(student):
    class_name = student.class_info.name if student.class_info else 'N/A'
    section = student.section_info.name if student.section_info else ''
    class_label = f'{class_name}{f" / {section}" if section else ""}'
    return {
        'name': student.student_name,
        'role_label': 'STUDENT IDENTITY CARD',
        'badge': f'ID {student.roll_number}',
        'qr': f'STUDENT|{student.roll_number}|{student.student_name}',
        'rows': [
            ('Roll No', student.roll_number),
            ('Class', class_label),
            ('Father', student.father_name),
            ('Phone', student.guardian_phone),
        ],
    }


def teacher_card_payload(teacher):
    joining = teacher.joining_date.strftime('%d %b %Y') if teacher.joining_date else '—'
    return {
        'name': teacher.teacher_name,
        'role_label': 'STAFF IDENTITY CARD',
        'badge': f'STAFF {teacher.teacher_id_str}',
        'qr': f'TEACHER|{teacher.teacher_id_str}|{teacher.teacher_name}',
        'rows': [
            ('Staff ID', teacher.teacher_id_str),
            ('Qual.', teacher.qualification),
            ('Class', teacher.assigned_class or '—'),
            ('Joined', joining),
        ],
    }


def build_id_cards_pdf(people, school, session, filename_hint='id_cards'):
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    page_w, page_h = A4
    margin_x = 12 * mm
    margin_y = 12 * mm
    gap_x = 8 * mm
    gap_y = 8 * mm
    cols = 2
    start_x = margin_x
    start_y = page_h - margin_y - CARD_H
    col = 0
    row_y = start_y

    if not people:
        c.setFont('Helvetica', 12)
        c.drawCentredString(page_w / 2, page_h / 2, 'No records to print.')
    else:
        for person in people:
            if row_y < margin_y:
                c.showPage()
                col = 0
                row_y = start_y
            x = start_x + col * (CARD_W + gap_x)
            _draw_id_card(c, x, row_y, person, school, session)
            col += 1
            if col >= cols:
                col = 0
                row_y -= CARD_H + gap_y

    c.save()
    output.seek(0)
    output.name = filename_hint
    return output


def _wrapped_lines(c, text, font, size, max_width):
    words = (text or '').split()
    if not words:
        return ['']
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f'{current} {word}'
        if c.stringWidth(trial, font, size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def certificate_title(cert_type):
    titles = {
        'bonafide': 'BONAFIDE CERTIFICATE',
        'character': 'CHARACTER CERTIFICATE',
        'leaving': 'SCHOOL LEAVING CERTIFICATE',
        'merit': 'MERIT CERTIFICATE',
    }
    return titles.get(cert_type, 'CERTIFICATE')


def certificate_body(cert_type, student, school, session, issue_date, remarks):
    class_name = student.class_info.name if student.class_info else 'N/A'
    section = student.section_info.name if student.section_info else ''
    class_label = f'{class_name}{f" ({section})" if section else ""}'
    extra = f' {remarks.strip()}' if remarks and remarks.strip() else ''
    if cert_type == 'character':
        return (
            f'This is to certify that {student.student_name}, son/daughter of {student.father_name}, '
            f'Roll No. {student.roll_number}, is/was a student of {class_label} at {school["name"]} '
            f'during the academic session {session}. During this period the student has borne a good moral character.{extra}'
        )
    if cert_type == 'leaving':
        return (
            f'This is to certify that {student.student_name}, son/daughter of {student.father_name}, '
            f'Roll No. {student.roll_number}, was a bona fide student of {class_label} at {school["name"]}. '
            f'The student left the institution on {issue_date.strftime("%d %B %Y")} with a satisfactory record.{extra}'
        )
    if cert_type == 'merit':
        achievement = remarks.strip() if remarks and remarks.strip() else 'outstanding academic performance'
        return (
            f'This is to certify that {student.student_name}, son/daughter of {student.father_name}, '
            f'Roll No. {student.roll_number}, of {class_label} at {school["name"]}, is awarded this merit certificate '
            f'in recognition of {achievement} during the academic session {session}.'
        )
    return (
        f'This is to certify that {student.student_name}, son/daughter of {student.father_name}, '
        f'Roll No. {student.roll_number}, is a bona fide student of {class_label} at {school["name"]} '
        f'during the academic session {session}.{extra}'
    )


def build_certificates_pdf(students, school, cert_type, session, issue_date, remarks):
    output = io.BytesIO()
    page = landscape(A4)
    c = canvas.Canvas(output, pagesize=page)
    page_w, page_h = page

    for index, student in enumerate(students):
        if index:
            c.showPage()
        _draw_certificate_page(c, page_w, page_h, student, school, cert_type, session, issue_date, remarks)

    if not students:
        c.setFont('Helvetica', 12)
        c.drawCentredString(page_w / 2, page_h / 2, 'No students selected.')

    c.save()
    output.seek(0)
    return output


def _draw_certificate_page(c, page_w, page_h, student, school, cert_type, session, issue_date, remarks):
    margin = 14 * mm
    c.setLineWidth(3)
    _set_stroke(c, NAVY)
    c.rect(margin, margin, page_w - 2 * margin, page_h - 2 * margin)
    c.setLineWidth(1)
    _set_stroke(c, GOLD)
    inner = margin + 4 * mm
    c.rect(inner, inner, page_w - 2 * inner, page_h - 2 * inner)

    logo_size = 22 * mm
    logo_x = page_w / 2 - logo_size / 2
    logo_y = page_h - inner - 28 * mm
    if not _draw_logo(c, school['logo_path'], logo_x, logo_y, logo_size):
        _set_fill(c, NAVY)
        c.setFont('Helvetica-Bold', 16)
        c.drawCentredString(page_w / 2, logo_y + 8 * mm, '◆')

    _set_fill(c, NAVY)
    c.setFont('Times-Bold', 22)
    c.drawCentredString(page_w / 2, logo_y - 8 * mm, school['name'])
    if school['tagline']:
        _set_fill(c, GOLD)
        c.setFont('Times-Italic', 11)
        c.drawCentredString(page_w / 2, logo_y - 14 * mm, school['tagline'])

    _set_fill(c, GOLD)
    c.setLineWidth(0.8)
    c.line(page_w / 2 - 70 * mm, logo_y - 18 * mm, page_w / 2 + 70 * mm, logo_y - 18 * mm)

    _set_fill(c, NAVY)
    c.setFont('Times-Bold', 18)
    c.drawCentredString(page_w / 2, logo_y - 28 * mm, certificate_title(cert_type))

    body = certificate_body(cert_type, student, school, session, issue_date, remarks)
    lines = _wrapped_lines(c, body, 'Times-Roman', 13, page_w - 2 * inner - 30 * mm)
    text_y = logo_y - 42 * mm
    _set_fill(c, (0.15, 0.18, 0.22))
    c.setFont('Times-Roman', 13)
    for line in lines:
        c.drawCentredString(page_w / 2, text_y, line)
        text_y -= 7 * mm

    details = [
        f'Class: {student.class_info.name if student.class_info else "N/A"}',
        f'Roll No: {student.roll_number}',
        f'Session: {session}',
        f'Issue Date: {issue_date.strftime("%d %B %Y")}',
    ]
    _set_fill(c, SLATE)
    c.setFont('Helvetica', 10)
    c.drawCentredString(page_w / 2, text_y - 4 * mm, '   |   '.join(details))

    sig_y = inner + 22 * mm
    _set_stroke(c, NAVY)
    c.setLineWidth(0.7)
    left_x = inner + 25 * mm
    right_x = page_w - inner - 70 * mm
    c.line(left_x, sig_y + 12 * mm, left_x + 45 * mm, sig_y + 12 * mm)
    c.line(right_x, sig_y + 12 * mm, right_x + 45 * mm, sig_y + 12 * mm)
    _set_fill(c, NAVY)
    c.setFont('Helvetica-Bold', 10)
    c.drawCentredString(left_x + 22.5 * mm, sig_y + 6 * mm, 'Class Teacher')
    c.drawCentredString(right_x + 22.5 * mm, sig_y + 6 * mm, 'Principal')

    serial = f'{cert_type[:3].upper()}-{student.id:04d}-{issue_date.strftime("%Y%m%d")}'
    _set_fill(c, SLATE)
    c.setFont('Helvetica', 8)
    c.drawString(inner + 4 * mm, inner + 6 * mm, f'Serial: {serial}')
    contact_bits = [bit for bit in (school['address'], school['phone'], school['email']) if bit]
    if contact_bits:
        c.drawRightString(page_w - inner - 4 * mm, inner + 6 * mm, '  ·  '.join(contact_bits)[:90])

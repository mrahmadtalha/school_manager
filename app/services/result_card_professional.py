"""Professional result-card PDF builder.

This module renders the "professional" result-card style that matches the
reference design: dark navy header, stat boxes, coloured progress bars,
attendance section, teacher remarks and signature line.

Public API
----------
build_story(student, marks, root_path, evaluation=None) -> list
    Returns a ReportLab story list (same contract as the classic builder
    in cards.py).  Pass it straight to _fit_report_on_one_page().
"""

from __future__ import annotations

import os
from datetime import date
from itertools import groupby
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from app.services.marks import ABSENT_LABEL
from app.services.pdf_logo import logo_flowable, school_logo_path

# ---------------------------------------------------------------------------
# Colour palette  (matches the reference design)
# ---------------------------------------------------------------------------
_NAVY   = colors.HexColor('#1a2744')   # header background
_GOLD   = colors.HexColor('#c8a32c')   # accent / badge
_WHITE  = colors.white
_LIGHT  = colors.HexColor('#f4f6fa')   # alternating row / section bg
_BORDER = colors.HexColor('#d0d7e8')
_TEXT   = colors.HexColor('#1a2744')
_SUBTEXT = colors.HexColor('#4a5568')
_GREEN  = colors.HexColor('#27a35e')
_BLUE   = colors.HexColor('#3b82f6')
_ORANGE = colors.HexColor('#f59e0b')
_RED    = colors.HexColor('#dc2626')

# Grade → bar colour
_GRADE_COLOR = {
    'A+': colors.HexColor('#27a35e'),
    'A':  colors.HexColor('#27a35e'),
    'B':  colors.HexColor('#3b82f6'),
    'C':  colors.HexColor('#f59e0b'),
    'D':  colors.HexColor('#f97316'),
    'F':  colors.HexColor('#dc2626'),
}


def _grade_color(grade: str):
    if not grade:
        return _SUBTEXT
    return _GRADE_COLOR.get(grade.upper().strip(), _BLUE)


def _pct_bar(pct: float, width: float = 90) -> Table:
    """Return a small Table that looks like a filled progress bar."""
    pct = max(0.0, min(100.0, float(pct)))
    filled = width * pct / 100
    empty  = width - filled

    if pct >= 85:
        bar_col = _GREEN
    elif pct >= 70:
        bar_col = _BLUE
    elif pct >= 50:
        bar_col = _ORANGE
    else:
        bar_col = _RED

    # Build the bar from two cells; handle edge cases (0 / 100 %)
    if filled < 1:
        data     = [['', '']]
        col_w    = [0.5, width - 0.5]
        bar_cols = [colors.HexColor('#e2e8f0'), colors.HexColor('#e2e8f0')]
    elif empty < 1:
        data     = [['', '']]
        col_w    = [width - 0.5, 0.5]
        bar_cols = [bar_col, bar_col]
    else:
        data     = [['', '']]
        col_w    = [filled, empty]
        bar_cols = [bar_col, colors.HexColor('#e2e8f0')]

    t = Table(data, colWidths=col_w, rowHeights=[7])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), bar_cols[0]),
        ('BACKGROUND', (1, 0), (1, 0), bar_cols[1]),
        ('ROUNDEDCORNERS', [3, 3, 3, 3]),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    return t


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_story(student, marks, root_path: str, evaluation=None) -> list:
    """Build the professional card story and return it as a list."""
    story: list = []
    styles = getSampleStyleSheet()

    from app.models import SchoolSettings
    from app.services import photos as _photos

    school      = SchoolSettings.query.first()
    school_name = (school.school_name if school else '') or 'School Manager'
    tagline     = (school.tagline     if school else '') or ''

    logo_path = school_logo_path(root_path)

    # -----------------------------------------------------------------------
    # 1.  HEADER  (navy band: logo · school name · tagline · badge)
    # -----------------------------------------------------------------------
    exam_badge = ''
    if evaluation:
        badge_parts = []
        if evaluation.get('announce_display'):
            badge_parts.append(evaluation['announce_display'].upper())
        if evaluation.get('exam_type'):
            badge_parts.append(evaluation['exam_type'].upper())
        exam_badge = '  |  '.join(badge_parts)

    name_style = ParagraphStyle(
        'HName', parent=styles['Normal'],
        fontSize=18, textColor=_WHITE, fontName='Helvetica-Bold',
        leading=22, spaceAfter=1,
    )
    sub_style = ParagraphStyle(
        'HSub', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#a0aec0'), fontName='Helvetica',
        leading=12,
    )
    card_title_style = ParagraphStyle(
        'HTitle', parent=styles['Normal'],
        fontSize=11, textColor=colors.HexColor('#cbd5e0'), fontName='Helvetica',
        leading=14, spaceBefore=4,
    )
    badge_style = ParagraphStyle(
        'Badge', parent=styles['Normal'],
        fontSize=9, textColor=_NAVY, fontName='Helvetica-Bold',
        alignment=1,
    )

    school_col = [
        Paragraph(school_name, name_style),
        Paragraph(tagline, sub_style) if tagline else Spacer(1, 2),
        Paragraph('Monthly Test Result Card', card_title_style),
    ]
    if evaluation and evaluation.get('session'):
        school_col.append(
            Paragraph('Academic session ' + escape(str(evaluation['session'])), sub_style)
        )

    badge_cell = Paragraph(exam_badge, badge_style) if exam_badge else Spacer(1, 1)

    logo_img = logo_flowable(logo_path, 52, 52)
    if logo_img is not None:
        hdr_data = [[logo_img, school_col, badge_cell]]
        hdr_col_w = [60, 350, 130]
    else:
        hdr_data = [[school_col, badge_cell]]
        hdr_col_w = [390, 150]

    hdr_table = Table(hdr_data, colWidths=hdr_col_w, rowHeights=[70])
    hdr_style = [
        ('BACKGROUND', (0, 0), (-1, -1), _NAVY),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',      (-1, 0), (-1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, 0), 12),
        ('LEFTPADDING', (1, 0), (1, 0), 10),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]
    # Wrap badge in gold box
    if exam_badge:
        hdr_style += [
            ('BOX', (-1, 0), (-1, 0), 1.5, _GOLD),
            ('BACKGROUND', (-1, 0), (-1, 0), _GOLD),
            ('ALIGN', (-1, 0), (-1, 0), 'CENTER'),
        ]
    hdr_table.setStyle(TableStyle(hdr_style))

    # Gold bottom line
    accent_table = Table([['']], colWidths=[540], rowHeights=[3])
    accent_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), _GOLD),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(hdr_table)
    story.append(accent_table)
    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 2.  STUDENT INFO BOX  (photo · name · father · class · roll · gr/adm)
    # -----------------------------------------------------------------------
    lbl_s = ParagraphStyle('L', parent=styles['Normal'],
                           fontSize=7.5, textColor=_SUBTEXT,
                           fontName='Helvetica', leading=10)
    val_s = ParagraphStyle('V', parent=styles['Normal'],
                           fontSize=11, textColor=_TEXT,
                           fontName='Helvetica-Bold', leading=14)

    def _lv(label, val):
        return [Paragraph(label.upper(), lbl_s), Paragraph(escape(str(val or '—')), val_s)]

    class_name = student.class_info.name if student.class_info else 'N/A'
    adm_no     = getattr(student, 'admission_number', '') or getattr(student, 'gr_number', '') or ''
    test_period = ''
    if evaluation and evaluation.get('announce_display'):
        test_period = evaluation['announce_display']

    # Photo
    photo_buffer = _photos.square_image_buffer(
        _photos.photo_path('student', getattr(student, 'photo_filename', None)))

    info_rows = [
        [*_lv('Student Name', student.student_name),
         *_lv('Class', class_name),
         *_lv('GR / Admission No', adm_no or 'N/A')],
        [*_lv('Father Name', student.father_name),
         *_lv('Roll No', student.roll_number),
         *_lv('Test Period', test_period or '—')],
    ]

    info_col_w = [70, 110, 60, 80, 70, 100]
    if photo_buffer:
        photo_img = Image(photo_buffer, width=56, height=56)
        for row in info_rows:
            row.append('')
        info_rows[0][-1] = photo_img
        info_col_w = [65, 100, 55, 75, 65, 90, 60]

    info_table = Table(info_rows, colWidths=info_col_w)
    info_st = [
        ('BACKGROUND', (0, 0), (-1, -1), _WHITE),
        ('BOX',        (0, 0), (-1, -1), 1,   _BORDER),
        ('INNERGRID',  (0, 0), (-1, -1), 0.3, _BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    if photo_buffer:
        info_st += [
            ('SPAN', (-1, 0), (-1, 1)),
            ('ALIGN', (-1, 0), (-1, 1), 'CENTER'),
            ('VALIGN', (-1, 0), (-1, 1), 'MIDDLE'),
        ]
    info_table.setStyle(TableStyle(info_st))
    story.append(info_table)
    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 3.  STAT BOXES  (Total Marks · Percentage · Grade · Position)
    # -----------------------------------------------------------------------
    if evaluation:
        big_s = ParagraphStyle('Big', parent=styles['Normal'],
                               fontSize=22, textColor=_TEXT,
                               fontName='Helvetica-Bold', alignment=1, leading=28)
        big_s_white = ParagraphStyle('BigW', parent=big_s, textColor=_WHITE)
        cap_s = ParagraphStyle('Cap', parent=styles['Normal'],
                               fontSize=7.5, textColor=_SUBTEXT,
                               fontName='Helvetica', alignment=1, leading=10)
        cap_s_white = ParagraphStyle('CapW', parent=cap_s, textColor=_WHITE)

        total_txt = '%g / %g' % (
            float(evaluation.get('total_obtained') or 0),
            float(evaluation.get('total_max') or 0),
        )
        pct_txt  = '%s%%' % evaluation.get('percentage', '—')
        grade_txt = str(evaluation.get('overall_grade') or '—')
        rank_txt  = str(evaluation.get('rank') or '—')
        total_stu = str(evaluation.get('total_students') or '—')

        stat_data = [[
            [Paragraph(total_txt, big_s),  Paragraph('TOTAL MARKS',  cap_s)],
            [Paragraph(pct_txt,   big_s),  Paragraph('PERCENTAGE',   cap_s)],
            [Paragraph(grade_txt, big_s),  Paragraph('GRADE',        cap_s)],
            [Paragraph(rank_txt,  big_s_white), Paragraph('POSITION OF ' + total_stu, cap_s_white)],
        ]]
        stat_table = Table(stat_data, colWidths=[135, 135, 135, 135])
        stat_table.setStyle(TableStyle([
            ('BOX',   (0, 0), (2, 0), 1, _BORDER),
            ('INNERGRID', (0, 0), (2, 0), 0.5, _BORDER),
            ('BACKGROUND', (0, 0), (2, 0), _WHITE),
            ('BACKGROUND', (3, 0), (3, 0), _NAVY),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(stat_table)
        story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 4.  SUBJECT-WISE PERFORMANCE TABLE  (with coloured progress bars)
    # -----------------------------------------------------------------------
    sec_hdr_s = ParagraphStyle('SecHdr', parent=styles['Normal'],
                               fontSize=9, textColor=_TEXT,
                               fontName='Helvetica-Bold', leading=12)
    th_s = ParagraphStyle('TH', parent=styles['Normal'],
                          fontSize=8.5, textColor=_WHITE,
                          fontName='Helvetica-Bold', alignment=1, leading=11)
    td_s = ParagraphStyle('TD', parent=styles['Normal'],
                          fontSize=9, textColor=_TEXT,
                          fontName='Helvetica', alignment=1, leading=12)
    td_bold = ParagraphStyle('TDB', parent=td_s, fontName='Helvetica-Bold')
    td_left = ParagraphStyle('TDL', parent=td_s, alignment=0)
    td_bold_left = ParagraphStyle('TDBL', parent=td_bold, alignment=0)

    story.append(Paragraph('SUBJECT-WISE PERFORMANCE', sec_hdr_s))
    story.append(Spacer(1, 4))

    tbl_data = [[
        Paragraph('SUBJECT', th_s),
        Paragraph('TOTAL', th_s),
        Paragraph('OBTAINED', th_s),
        Paragraph('PERFORMANCE', th_s),
        Paragraph('%', th_s),
        Paragraph('GRADE', th_s),
        Paragraph('CLASS AVG', th_s),
    ]]
    tbl_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), _NAVY),
        ('GRID', (0, 0), (-1, -1), 0.4, _BORDER),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (0, -1), 8),
    ]

    sorted_marks = sorted(
        marks,
        key=lambda m: (m.test_info.test_date or date.min, m.test_info.test_title),
    )

    # Collect per-subject totals for class-average column
    # (we show avg from evaluation if available; otherwise '—')
    total_ob = 0.0
    total_mx = 0.0
    absent_papers = 0
    row_i = 1

    for (date_val, title), grp in groupby(
        sorted_marks,
        key=lambda m: (m.test_info.test_date, m.test_info.test_title),
    ):
        group_marks = list(grp)
        date_str = date_val.strftime('%d %b %Y') if date_val else ''
        batch_lbl = '%s   (%s)' % (title, date_str) if date_str else title
        # Group header spanning all columns
        tbl_data.append([
            Paragraph(batch_lbl, ParagraphStyle(
                'BH', parent=td_bold_left, textColor=_TEXT,
            )),
            '', '', '', '', '', '',
        ])
        tbl_cmds += [
            ('SPAN', (0, row_i), (-1, row_i)),
            ('BACKGROUND', (0, row_i), (-1, row_i), _LIGHT),
            ('LEFTPADDING', (0, row_i), (-1, row_i), 10),
        ]
        row_i += 1

        for m in group_marks:
            t   = m.test_info
            sbj = t.subject_info.name if t.subject_info else 'N/A'
            if m.is_absent:
                pct_val = 0.0
                tbl_data.append([
                    Paragraph(sbj, td_left),
                    Paragraph(str(t.total_marks), td_s),
                    Paragraph(ABSENT_LABEL, td_bold),
                    _pct_bar(0),
                    Paragraph('—', td_s),
                    Paragraph(ABSENT_LABEL, td_bold),
                    Paragraph('—', td_s),
                ])
                absent_papers += 1
            else:
                pct_val = float(m.percentage or 0)
                grade   = str(m.grade or '—')
                gc      = _grade_color(grade)
                # grade badge style (coloured text)
                grade_s = ParagraphStyle(
                    'GS', parent=td_bold, textColor=gc,
                )
                tbl_data.append([
                    Paragraph(sbj, td_bold_left),
                    Paragraph(str(t.total_marks), td_s),
                    Paragraph(str(m.marks_obtained), td_bold),
                    _pct_bar(pct_val),
                    Paragraph('%s%%' % int(pct_val), td_s),
                    Paragraph(grade, grade_s),
                    Paragraph('—', td_s),   # class avg placeholder
                ])
                total_ob += m.marks_obtained
                total_mx += t.total_marks

            bg = _WHITE if row_i % 2 == 0 else _LIGHT
            tbl_cmds.append(('BACKGROUND', (0, row_i), (-1, row_i), bg))
            row_i += 1

    # Totals row
    if total_mx > 0 or len(tbl_data) > 1:
        overall_pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        tbl_data.append([
            Paragraph('TOTAL', td_bold),
            Paragraph(str(int(total_mx)), td_bold),
            Paragraph(str(int(total_ob)), td_bold),
            _pct_bar(overall_pct),
            Paragraph('%d%%' % int(overall_pct), td_bold),
            Paragraph('', td_s),
            Paragraph('', td_s),
        ])
        tbl_cmds += [
            ('BACKGROUND', (0, row_i), (-1, row_i), colors.HexColor('#e8ecf3')),
            ('FONTNAME', (0, row_i), (-1, row_i), 'Helvetica-Bold'),
        ]
    else:
        tbl_data.append([Paragraph('No marks entered yet', td_left), '', '', '', '', '', ''])
        tbl_cmds.append(('SPAN', (0, row_i), (-1, row_i)))

    subj_table = Table(
        tbl_data,
        colWidths=[110, 45, 55, 100, 40, 50, 55],
    )
    subj_table.setStyle(TableStyle(tbl_cmds))
    story.append(subj_table)

    if absent_papers:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            'ABS = absent.  %d paper(s) marked absent excluded from totals, '
            'percentage, grade and rank.' % absent_papers,
            ParagraphStyle('AN', parent=styles['Normal'], fontSize=7.5,
                           textColor=colors.HexColor('#92400e')),
        ))

    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 5.  ATTENDANCE THIS MONTH  (from evaluation extras or skip)
    # -----------------------------------------------------------------------
    # Attendance data may come later via evaluation extras; for now a compact
    # placeholder row is shown when evaluation exists.
    if evaluation:
        attn = evaluation.get('attendance') or {}
        present = attn.get('present', '—')
        absent  = attn.get('absent',  '—')
        late    = attn.get('late',    '—')
        pct_a   = attn.get('percentage', '—')

        story.append(Paragraph('ATTENDANCE THIS MONTH', sec_hdr_s))
        story.append(Spacer(1, 4))

        a_lbl = ParagraphStyle('AL', parent=styles['Normal'], fontSize=7.5,
                               textColor=_SUBTEXT, fontName='Helvetica', leading=10)
        a_val_green  = ParagraphStyle('AVG', parent=styles['Normal'], fontSize=12,
                                      textColor=_GREEN, fontName='Helvetica-Bold', leading=16)
        a_val_red    = ParagraphStyle('AVR', parent=a_val_green, textColor=_RED)
        a_val_orange = ParagraphStyle('AVO', parent=a_val_green, textColor=_ORANGE)
        a_val_navy   = ParagraphStyle('AVN', parent=a_val_green, textColor=_NAVY)

        attn_data = [[
            [Paragraph('PRESENT', a_lbl), Paragraph(str(present), a_val_green)],
            [Paragraph('ABSENT',  a_lbl), Paragraph(str(absent),  a_val_red)],
            [Paragraph('LATE',    a_lbl), Paragraph(str(late),    a_val_orange)],
            [Paragraph('ATTENDANCE', a_lbl), Paragraph(str(pct_a),  a_val_navy)],
        ]]
        attn_table = Table(attn_data, colWidths=[135, 135, 135, 135])
        attn_table.setStyle(TableStyle([
            ('BOX',       (0, 0), (-1, -1), 1,   _BORDER),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, _BORDER),
            ('BACKGROUND',(0, 0), (-1, -1), _WHITE),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ]))
        story.append(attn_table)
        story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 6.  TEACHER REMARKS
    # -----------------------------------------------------------------------
    if evaluation and evaluation.get('remarks'):
        story.append(Paragraph('TEACHER REMARKS', sec_hdr_s))
        story.append(Spacer(1, 4))
        remarks_s = ParagraphStyle('REM', parent=styles['Normal'],
                                   fontSize=9.5, textColor=_TEXT,
                                   fontName='Helvetica-Oblique',
                                   leading=14, leftIndent=10,
                                   rightIndent=10, spaceBefore=6, spaceAfter=6)
        remark_box = Table(
            [[Paragraph(escape(str(evaluation['remarks'])), remarks_s)]],
            colWidths=[540],
        )
        remark_box.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, _BORDER),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffdf0')),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ]))
        story.append(remark_box)
        story.append(Spacer(1, 14))

    # -----------------------------------------------------------------------
    # 7.  SIGNATURE LINE
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 20))
    sig_s = ParagraphStyle('Sig', parent=styles['Normal'],
                           alignment=1, fontSize=9,
                           textColor=_SUBTEXT, leading=14)
    sig_table = Table(
        [[
            Paragraph('_______________________<br/>Class Teacher', sig_s),
            Paragraph('_______________________<br/>Parent / Guardian', sig_s),
            Paragraph('_______________________<br/>Principal', sig_s),
        ]],
        colWidths=[180, 180, 180],
    )
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sig_table)

    # -----------------------------------------------------------------------
    # 8.  FOOTER
    # -----------------------------------------------------------------------
    footer_s = ParagraphStyle('Ftr', parent=styles['Normal'],
                              alignment=1, fontSize=7.5,
                              textColor=_SUBTEXT, spaceBefore=10)
    issued = ''
    if evaluation and evaluation.get('announce_display'):
        issued = ' | Issued on %s' % evaluation['announce_display']
    story.append(Paragraph(
        'Computer generated result card%s | Sample data for design preview' % issued,
        footer_s,
    ))

    return story

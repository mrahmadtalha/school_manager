"""Term exam tabulation, result cards, publish/unpublish and result alerts."""

import io
from datetime import date, datetime
from flask import current_app, flash, redirect, request, send_file, url_for
from app.database import db
from app.models import MessageQueue, StudentRemark, TermExam
from app.routes import main
from app.services.audit import log_action
from app.services.marks import ABSENT_LABEL
from app.services.term_exam_docs import build_result_cards_pdf
from app.services.test_result_alerts import result_alerts_off_reason
from app.services.whatsapp_automation import normalize_whatsapp_number, queue_automation_message

from app.routes.term_exams.exams import build_tabulation


@main.route('/examinations/<int:id>/tabulation/export.xlsx')
def examinations_tabulation_xlsx(id):
    import pandas as pd

    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests, rows, summary = build_tabulation(exam)

    data = []
    for row in rows:
        line = {'Position': row['position'], 'Roll No': row['student'].roll_number,
                'Student Name': row['student'].student_name}
        for test in tests:
            column = '%s (%s)' % ((test.subject_info.name if test.subject_info
                                   else 'Subject'),
                                  '{:,.0f}'.format(test.total_marks or 0))
            line[column] = (ABSENT_LABEL if row['absent'].get(test.id)
                            else row['scores'].get(test.id))
        line['Total Obtained'] = row['total_obt']
        line['Total Max'] = row['max_marks']
        line['Percentage'] = row['pct']
        line['Grade'] = row['grade']
        data.append(line)

    frame = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        frame.to_excel(writer, index=False, sheet_name='Tabulation')
    output.seek(0)

    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='Tabulation Excel exported: %s' % exam.name)
    db.session.commit()
    class_name = (exam.class_info.name if exam.class_info else 'class').replace(' ', '_')
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='tabulation_%s_%s.xlsx' % (class_name, exam.id))


def _build_tabulation_pdf(exam, tests, rows, summary, root_path=None):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TT', parent=styles['Heading1'], fontSize=15,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    meta_style = ParagraphStyle('TS', parent=styles['Normal'], fontSize=8.5,
                                alignment=1, textColor=colors.HexColor('#475569'),
                                spaceAfter=4)
    doc_style = ParagraphStyle('TD', parent=styles['Heading2'], fontSize=11.5,
                               alignment=1, textColor=colors.HexColor('#1f2a44'),
                               spaceBefore=3, spaceAfter=1)
    head_style = ParagraphStyle('TH', parent=styles['Normal'], fontSize=7,
                                leading=8.5, alignment=1, textColor=colors.white)
    name_style = ParagraphStyle('TN', parent=styles['Normal'], fontSize=7, leading=8.5)

    def fmt_num(value):
        if value is None:
            return '—'
        number = float(value)
        return str(int(number)) if number.is_integer() else str(round(number, 1))

    story = [Paragraph(escape(str(school['name'])), title_style)]
    tail = ' | '.join([part for part in (school.get('address') or '',
                                         school.get('phone') or '') if part])
    if tail:
        story.append(Paragraph(escape(tail), meta_style))
    story.append(Paragraph('TERM EXAMINATION TABULATION SHEET', doc_style))
    bits = ['Class %s' % (exam.class_info.name if exam.class_info else '—'),
            'Exam: %s' % (exam.name or '—')]
    if exam.session_label:
        bits.append('Session %s' % exam.session_label)
    story.append(Paragraph(escape(' · '.join(bits)), meta_style))
    story.append(Spacer(1, 7))

    headers = ['Pos.', 'Roll', 'Student']
    for test in tests:
        label = test.subject_info.name if test.subject_info else 'Subject'
        headers.append('%s (%s)' % (label, fmt_num(test.total_marks or 0)))
    headers += ['Total', 'Max', 'Pct', 'Grade']

    body = [[Paragraph('<b>%s</b>' % escape(str(header)), head_style)
             for header in headers]]
    for row in rows:
        student = row['student']
        cells = [row['position'],
                 str(student.roll_number if student.roll_number is not None else '—'),
                 Paragraph(escape(student.student_name or ''), name_style)]
        for test in tests:
            cells.append(ABSENT_LABEL if row['absent'].get(test.id)
                         else fmt_num(row['scores'].get(test.id)))
        if row['all_absent']:
            cells += ['—', '—', '—', ABSENT_LABEL]
        else:
            cells += [fmt_num(row['total_obt']), fmt_num(row['max_marks']),
                      '%g%%' % row['pct'], row['grade']]
        body.append(cells)
    if len(body) == 1:
        body.append(['No students for this exam.'] + [''] * (len(headers) - 1))

    page = landscape(letter)
    content_width = page[0] - 52.0
    fixed_widths = [30.0, 34.0, 132.0]
    tail_widths = [46.0, 40.0, 34.0, 38.0]
    subject_space = content_width - sum(fixed_widths) - sum(tail_widths)
    subject_width = (subject_space / len(tests)) if tests else 0.0
    col_widths = fixed_widths + [subject_width] * len(tests) + tail_widths
    scale = content_width / float(sum(col_widths))
    col_widths = [width * scale for width in col_widths]

    table = Table(body, colWidths=col_widths, repeatRows=1)
    commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2a44')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
        ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]
    for row_index in range(1, len(body)):
        if row_index % 2 == 0:
            commands.append(('BACKGROUND', (0, row_index), (-1, row_index),
                             colors.HexColor('#f2f6fc')))
    table.setStyle(TableStyle(commands))
    story.append(table)

    story.append(Spacer(1, 7))
    story.append(Paragraph(
        'Class Average: <b>%g%%</b> &nbsp;&middot;&nbsp; Passed: <b>%d / %d (%g%%)</b> '
        '&nbsp;&middot;&nbsp; Marks filled: <b>%d / %d</b>'
        % (summary['average'], summary['pass_count'], summary['sat'],
           summary['pass_rate'], summary['filled'], summary['expected']),
        ParagraphStyle('TF', parent=styles['Normal'], fontSize=9, alignment=1,
                       textColor=colors.HexColor('#2d3748'))))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        'Generated on %s' % datetime.now().strftime('%d %b %Y, %I:%M %p'),
        ParagraphStyle('TG', parent=styles['Normal'], fontSize=7.5,
                       alignment=1, textColor=colors.HexColor('#94a3b8'))))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=page, rightMargin=26, leftMargin=26,
                            topMargin=22, bottomMargin=22)
    doc.build(story)
    output.seek(0)
    return output


@main.route('/examinations/<int:id>/tabulation/export.pdf')
def examinations_tabulation_pdf(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests, rows, summary = build_tabulation(exam)
    output = _build_tabulation_pdf(exam, tests, rows, summary,
                                   current_app.root_path)
    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='Tabulation PDF exported: %s' % exam.name)
    db.session.commit()
    class_name = (exam.class_info.name if exam.class_info else 'class').replace(' ', '_')
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name='tabulation_%s_%s.pdf' % (class_name, exam.id))


def _result_cards(exam):
    """Result-card payloads (per student) built on top of the tabulation."""
    from app.models.settings import calculate_grade as _grade

    tests, rows, summary = build_tabulation(exam)
    remarks = {}
    for remark in (StudentRemark.query
                   .filter_by(class_id=exam.class_id, test_type=exam.exam_type)
                   .all()):
        if remark.remarks:
            remarks[remark.student_id] = remark.remarks

    cards = []
    for row in rows:
        subject_rows = []
        for test in tests:
            subject_name = (test.subject_info.name if test.subject_info else '—')
            score = row['scores'].get(test.id)
            if row['absent'].get(test.id):
                subject_rows.append((subject_name, test.total_marks or 0,
                                     ABSENT_LABEL, None, ABSENT_LABEL))
            elif score is None:
                subject_rows.append((subject_name, test.total_marks or 0,
                                     None, None, None))
            else:
                pct = (score / test.total_marks * 100) if test.total_marks else 0.0
                subject_rows.append((subject_name, test.total_marks or 0, score,
                                     round(pct, 1), _grade(pct)))
        cards.append({
            'student': row['student'],
            'position': row['position'],
            'subject_rows': subject_rows,
            'absent_count': row['absent_count'],
            'all_absent': row['all_absent'],
            'total_obt': row['total_obt'],
            'total_max': row['max_marks'],
            'pct': row['pct'],
            'grade': row['grade'],
            'remark': remarks.get(row['student'].id, ''),
            'complete': summary['complete'],
        })
    return tests, cards, summary


@main.route('/examinations/<int:id>/results/<int:student_id>.pdf')
def examinations_result_card(id, student_id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests, cards, summary = _result_cards(exam)
    card = next((c for c in cards if c['student'].id == student_id), None)
    if card is None:
        flash('Student not found in this exam.', 'warning')
        return redirect(url_for('main.examinations_tabulation', id=id))

    output = build_result_cards_pdf(exam, [card], current_app.root_path)
    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='Result card PDF: %s - %s'
                       % (exam.name, card['student'].student_name))
    db.session.commit()
    filename = 'result_card_%s_%s.pdf' % (card['student'].roll_number,
                                          card['student'].student_name.replace(' ', '_'))
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=filename)


@main.route('/examinations/<int:id>/results/pdf-all')
def examinations_result_cards_all(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests, cards, summary = _result_cards(exam)
    if not cards:
        flash('No students to generate result cards for.', 'warning')
        return redirect(url_for('main.examinations_tabulation', id=id))

    output = build_result_cards_pdf(exam, cards, current_app.root_path)
    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='All result cards PDF: %s (%d students)'
                       % (exam.name, len(cards)))
    db.session.commit()
    class_name = (exam.class_info.name if exam.class_info else 'class').replace(' ', '_')
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name='result_cards_%s_%s.pdf' % (class_name, exam.id))


@main.route('/examinations/<int:id>/publish', methods=['POST'])
def examinations_publish(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    if exam.status == 'Published':
        flash('Results for "%s" are already published.' % exam.name, 'warning')
        return redirect(url_for('main.examinations_detail', id=id))

    exam.status = 'Published'
    if exam.announce_date is None:
        exam.announce_date = date.today()

    queued = 0
    skipped = 0
    off_reason = None
    if request.form.get('queue_whatsapp') == '1':
        # Same rules as absent/late alerts: master switch, "Results" switch,
        # license and the chosen mode (auto / approval / delayed one-by-one).
        off_reason = result_alerts_off_reason()
        tests, cards, summary = _result_cards(exam)
        for card in (cards if off_reason is None else ()):
            student = card['student']
            phone = normalize_whatsapp_number(student.guardian_phone or '')
            if not phone:
                skipped += 1
                continue
            existing = (MessageQueue.query
                        .filter_by(student_id=student.id, trigger='result',
                                   ref_date=exam.announce_date)
                        .filter(MessageQueue.status.in_((
                            'pending', 'approved', 'sending', 'sending_auto',
                            'sent')))
                        .first())
            if existing:
                skipped += 1
                continue
            if card['all_absent']:
                skipped += 1
                continue
            if queue_automation_message(student, 'result', {
                'student_name': student.student_name,
                'test_type': exam.exam_type,
                'date': exam.announce_date,
                'obtained': '%g' % card['total_obt'],
                'total': '%g' % card['total_max'],
                'percentage': card['pct'],
                'grade': card['grade'],
            }):
                queued += 1
            else:
                skipped += 1

    log_action('update', entity_type='TermExam', entity_id=exam.id,
               summary='Results published: %s (announce %s, %d message(s) queued)'
                       % (exam.name, exam.announce_date, queued))
    db.session.commit()
    extra = ''
    if off_reason:
        extra = ' No WhatsApp messages queued: %s' % off_reason
    elif request.form.get('queue_whatsapp') == '1':
        extra = ' %d WhatsApp result message(s) queued; %d skipped.' % (queued, skipped)
    flash('Results published for "%s".%s' % (exam.name, extra), 'success')
    return redirect(url_for('main.examinations_detail', id=id))


@main.route('/examinations/<int:id>/unpublish', methods=['POST'])
def examinations_unpublish(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    exam.status = 'Scheduled'
    log_action('update', entity_type='TermExam', entity_id=exam.id,
               summary='Results reverted to Scheduled: %s' % exam.name)
    db.session.commit()
    flash('Results for "%s" reverted to Scheduled.' % exam.name, 'warning')
    return redirect(url_for('main.examinations_detail', id=id))

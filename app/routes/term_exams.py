"""Term Examination hub: schedule creation, hub list and exam detail pages."""
import io
from datetime import date, datetime, timedelta

from flask import (Response, current_app, flash, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user
from sqlalchemy import func

from app.database import db
from app.models import (ClassModel, MessageQueue, SchoolSettings,
                        StudentMarkModel, StudentModel, StudentRemark,
                        SubjectModel, TermExam, TestModel, TestTypeModel)
from app.routes import main
from app.routes.examinations import test_type_color
from app.services.audit import log_action
from app.services.term_exam_docs import (build_date_sheet_pdf,
                                         build_result_cards_pdf)
from app.services.whatsapp_automation import (build_whatsapp_message,
                                              normalize_whatsapp_number)

STATUS_COLORS = {'Scheduled': 'secondary', 'Ongoing': 'warning',
                 'Published': 'success'}


def _parse_date(value):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _current_session_label():
    school = SchoolSettings.query.first()
    label = (getattr(school, 'academic_session', '') or '').strip()
    if label:
        return label
    from app.services.id_documents import academic_session
    return academic_session()


def _term_exam_types():
    """Categories scoped to term exams (fallback: all categories)."""
    scoped = (TestTypeModel.query
              .filter(TestTypeModel.scope == 'term_exam')
              .order_by(TestTypeModel.name).all())
    if scoped:
        return scoped
    return TestTypeModel.query.order_by(TestTypeModel.name).all()


def _marks_filled_for(test_ids):
    if not test_ids:
        return 0
    return int(db.session.query(func.count(StudentMarkModel.id))
               .filter(StudentMarkModel.test_id.in_(test_ids)).scalar() or 0)


def _progress_state(filled, total):
    if total == 0:
        return 'empty', 'No students'
    if filled >= total:
        return 'done', 'Marks complete'
    if filled == 0:
        return 'none', 'No marks yet'
    pct = round(filled * 100.0 / total)
    return 'partial', 'Marks %d/%d (%d%%)' % (filled, total, pct)


def _exam_rows(exams):
    student_counts = {class_id: int(count) for class_id, count in
                      db.session.query(StudentModel.class_id,
                                       func.count(StudentModel.id))
                      .filter(StudentModel.is_active.is_(True))
                      .group_by(StudentModel.class_id).all()}
    rows = []
    for exam in exams:
        tests = list(exam.tests)
        tests.sort(key=lambda t: (t.test_date or date.min, t.id))
        filled = _marks_filled_for([t.id for t in tests])
        students = student_counts.get(exam.class_id, 0)
        expected = students * len(tests)
        state, label = _progress_state(filled, expected)
        rows.append({
            'exam': exam,
            'subject_count': len(tests),
            'students': students,
            'total_marks': sum(t.total_marks or 0 for t in tests),
            'filled': filled,
            'expected': expected,
            'progress_state': state,
            'progress_label': label,
            'color': test_type_color(exam.exam_type),
            'status_color': STATUS_COLORS.get(exam.status, 'secondary'),
        })
    return rows


@main.route('/examinations')
def examinations_page():
    class_id = request.args.get('class_id', type=int)
    status = (request.args.get('status') or '').strip()
    session = (request.args.get('session') or '').strip()

    query = TermExam.query.order_by(TermExam.id.desc())
    if class_id:
        query = query.filter(TermExam.class_id == class_id)
    if status:
        query = query.filter(TermExam.status == status)
    if session:
        query = query.filter(TermExam.session_label == session)
    exams = query.all()

    sessions = [row[0] for row in
                db.session.query(TermExam.session_label).distinct().all()
                if row[0]]

    return render_template(
        'examinations.html',
        exam_rows=_exam_rows(exams),
        classes=ClassModel.query.all(),
        subjects=SubjectModel.query.filter_by(is_active=True).all(),
        create_types=_term_exam_types(),
        statuses=('Scheduled', 'Ongoing', 'Published'),
        sessions=sorted(set(sessions), reverse=True),
        filters={'class_id': class_id, 'status': status, 'session': session},
        current_session=_current_session_label(),
        today=date.today(),
    )


@main.route('/examinations/create', methods=['POST'])
def examinations_create():
    try:
        class_id = request.form.get('class_id', type=int) or 0
        class_obj = db.session.get(ClassModel, class_id)
        if class_obj is None:
            flash('Please choose a valid class.', 'danger')
            return redirect(url_for('main.examinations_page'))

        exam_type = (request.form.get('exam_type') or '').strip()
        if not exam_type:
            flash('Please choose an exam type.', 'danger')
            return redirect(url_for('main.examinations_page'))

        name = (request.form.get('name') or '').strip()
        if not name:
            name = '%s Examination — %s' % (exam_type, class_obj.name)
        name = name[:120]

        session_label = ((request.form.get('session_label') or '').strip()
                         or _current_session_label())[:50]
        start_date = _parse_date(request.form.get('start_date'))
        end_date = _parse_date(request.form.get('end_date'))
        announce_date = _parse_date(request.form.get('announce_date'))

        type_obj = TestTypeModel.query.filter_by(name=exam_type).first()
        fallback_marks = (float(type_obj.default_marks)
                          if type_obj is not None and type_obj.default_marks
                          else 100.0)

        exam = TermExam(name=name, class_id=class_id, exam_type=exam_type,
                        session_label=session_label, start_date=start_date,
                        end_date=end_date, announce_date=announce_date,
                        status='Scheduled',
                        created_by=(getattr(current_user, 'username', None)
                                    or 'system')[:80])
        db.session.add(exam)
        db.session.flush()

        added = 0
        exam_dates = []
        for subject in SubjectModel.query.filter_by(class_id=class_id, is_active=True).all():
            if not request.form.get('include_subject_%d' % subject.id):
                continue
            exam_date = (_parse_date(request.form.get('exam_date_%d' % subject.id))
                         or start_date or date.today())
            start_time = ((request.form.get('exam_time_%d' % subject.id) or '')
                          .strip()[:10] or None)
            room = ((request.form.get('exam_room_%d' % subject.id) or '')
                    .strip()[:60] or None)
            marks_str = (request.form.get('marks_%d' % subject.id) or '').strip()
            if marks_str:
                try:
                    total_marks = float(marks_str)
                except ValueError:
                    db.session.rollback()
                    flash('Total marks must be a number.', 'danger')
                    return redirect(url_for('main.examinations_page'))
                if total_marks <= 0:
                    db.session.rollback()
                    flash('Total marks must be a positive number.', 'danger')
                    return redirect(url_for('main.examinations_page'))
            else:
                total_marks = fallback_marks

            db.session.add(TestModel(
                test_title=name, test_type=exam_type, class_id=class_id,
                subject_id=subject.id, total_marks=total_marks,
                test_date=exam_date, start_time=start_time, room=room,
                term_exam_id=exam.id))
            exam_dates.append(exam_date)
            added += 1

        if added == 0:
            db.session.rollback()
            flash('Select at least one subject for the term exam.', 'danger')
            return redirect(url_for('main.examinations_page'))

        if exam.start_date is None and exam_dates:
            exam.start_date = min(exam_dates)
        if exam.end_date is None and exam_dates:
            exam.end_date = max(exam_dates)

        log_action('create', entity_type='TermExam', entity_id=exam.id,
                   summary='Term exam created: %s (%s, %d subject(s))'
                           % (name, class_obj.name, added))
        db.session.commit()
        flash('Term exam "%s" created with %d subject(s).' % (name, added),
              'success')
        return redirect(url_for('main.examinations_detail', id=exam.id))
    except Exception as error:
        db.session.rollback()
        flash('Error creating term exam: %s' % error, 'danger')
        return redirect(url_for('main.examinations_page'))


@main.route('/examinations/<int:id>')
def examinations_detail(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))

    tests = list(exam.tests)
    tests.sort(key=lambda t: (t.test_date or date.min, t.id))
    marks_counts = {}
    if tests:
        for test_id, count in (db.session.query(StudentMarkModel.test_id,
                                                func.count(StudentMarkModel.id))
                               .filter(StudentMarkModel.test_id.in_(
                                   [t.id for t in tests]))
                               .group_by(StudentMarkModel.test_id).all()):
            marks_counts[test_id] = int(count)

    student_count = StudentModel.query.filter_by(
        is_active=True, class_id=exam.class_id).count()
    filled = sum(marks_counts.values())
    expected = student_count * len(tests)
    state, label = _progress_state(filled, expected)

    return render_template(
        'examination_detail.html',
        exam=exam,
        tests=tests,
        marks_counts=marks_counts,
        student_count=student_count,
        total_max=sum(t.total_marks or 0 for t in tests),
        filled=filled,
        expected=expected,
        progress_state=state,
        progress_label=label,
        color=test_type_color(exam.exam_type),
        status_color=STATUS_COLORS.get(exam.status, 'secondary'),
    )


@main.route('/examinations/<int:id>/schedule', methods=['POST'])
def examinations_schedule(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))

    tests = list(exam.tests)
    try:
        shift_raw = (request.form.get('shift_days') or '').strip()
        if shift_raw:
            try:
                shift = int(shift_raw)
            except ValueError:
                flash('Shift days must be a whole number.', 'danger')
                return redirect(url_for('main.examinations_detail', id=id))
            if shift == 0:
                flash('Nothing to shift (0 days).', 'warning')
                return redirect(url_for('main.examinations_detail', id=id))
            delta = timedelta(days=shift)
            for test in tests:
                if test.test_date:
                    test.test_date = test.test_date + delta
            if exam.start_date:
                exam.start_date = exam.start_date + delta
            if exam.end_date:
                exam.end_date = exam.end_date + delta
            if exam.announce_date:
                exam.announce_date = exam.announce_date + delta
            log_action('update', entity_type='TermExam', entity_id=exam.id,
                       summary='Date sheet shifted by %+d day(s): %s'
                               % (shift, exam.name))
            db.session.commit()
            flash('All exam dates shifted by %+d day(s).' % shift, 'success')
            return redirect(url_for('main.examinations_detail', id=id))

        exam.start_date = _parse_date(request.form.get('start_date'))
        exam.end_date = _parse_date(request.form.get('end_date'))
        exam.announce_date = _parse_date(request.form.get('announce_date'))

        changed = 0
        for test in tests:
            date_value = _parse_date(request.form.get('exam_date_%d' % test.id))
            if date_value is None:
                db.session.rollback()
                flash('Date sheet not saved - every subject needs a valid exam date.',
                      'danger')
                return redirect(url_for('main.examinations_detail', id=id))
            time_value = ((request.form.get('exam_time_%d' % test.id) or '')
                          .strip()[:10] or None)
            room_value = ((request.form.get('exam_room_%d' % test.id) or '')
                          .strip()[:60] or None)
            if (test.test_date != date_value or test.start_time != time_value
                    or test.room != room_value):
                changed += 1
            test.test_date = date_value
            test.start_time = time_value
            test.room = room_value

        test_dates = [t.test_date for t in tests if t.test_date]
        if exam.start_date is None and test_dates:
            exam.start_date = min(test_dates)
        if exam.end_date is None and test_dates:
            exam.end_date = max(test_dates)

        log_action('update', entity_type='TermExam', entity_id=exam.id,
                   summary='Date sheet updated: %s (%d change(s))'
                           % (exam.name, changed))
        db.session.commit()
        flash('Date sheet updated (%d change(s)).' % changed, 'success')
    except Exception as error:
        db.session.rollback()
        flash('Error updating date sheet: %s' % error, 'danger')
    return redirect(url_for('main.examinations_detail', id=id))


@main.route('/examinations/<int:id>/date-sheet')
def examinations_date_sheet(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests = list(exam.tests)
    tests.sort(key=lambda t: (t.test_date or date.min, t.id))
    return render_template(
        'examination_date_sheet.html',
        exam=exam,
        tests=tests,
        total_max=sum(t.total_marks or 0 for t in tests),
        generated_on=date.today())


@main.route('/examinations/<int:id>/date-sheet.pdf')
def examinations_date_sheet_pdf(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests = list(exam.tests)
    tests.sort(key=lambda t: (t.test_date or date.min, t.id))
    output = build_date_sheet_pdf(exam, tests, current_app.root_path)
    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='Date sheet PDF exported: %s' % exam.name)
    db.session.commit()
    class_name = (exam.class_info.name if exam.class_info else 'class').replace(' ', '_')
    filename = 'date_sheet_%s_%s.pdf' % (class_name, exam.id)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=filename)


def _ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return '%d%s' % (number, suffix)


def build_tabulation(exam):
    """Full class tabulation: per-subject scores, totals, grade and position.

    Positions use competition ranking - students with equal totals share a
    position (e.g. 1, 2, 2, 4).
    """
    from app.models.settings import calculate_grade

    tests = list(exam.tests)
    tests.sort(key=lambda t: (t.test_date or date.min, t.id))
    students = (StudentModel.query
                .filter_by(is_active=True, class_id=exam.class_id)
                .order_by(StudentModel.roll_number).all())
    test_ids = [t.id for t in tests]
    marks_map = {}
    if test_ids:
        for mark in (StudentMarkModel.query
                     .filter(StudentMarkModel.test_id.in_(test_ids)).all()):
            marks_map[(mark.student_id, mark.test_id)] = mark

    total_max = sum(t.total_marks or 0 for t in tests)
    filled = 0
    rows = []
    for student in students:
        row = {'student': student, 'scores': {}, 'total_obt': 0.0}
        for test in tests:
            mark = marks_map.get((student.id, test.id))
            row['scores'][test.id] = mark.marks_obtained if mark else None
            if mark is not None:
                row['total_obt'] += mark.marks_obtained or 0
                filled += 1
        row['total_obt'] = round(row['total_obt'], 2)
        row['pct'] = (round(row['total_obt'] / total_max * 100, 1)
                      if total_max else 0.0)
        row['grade'] = calculate_grade(row['pct']) if total_max else 'N/A'
        row['is_pass'] = bool(total_max > 0 and row['grade'] != 'F')
        rows.append(row)

    rows.sort(key=lambda r: r['total_obt'], reverse=True)
    rank = 0
    previous = None
    for index, row in enumerate(rows, 1):
        if previous is None or row['total_obt'] != previous:
            rank = index
            previous = row['total_obt']
        row['rank'] = rank
        row['position'] = _ordinal(rank)

    expected = len(students) * len(tests)
    pass_count = sum(1 for r in rows if r['is_pass'])
    summary = {
        'students': len(students),
        'total_max': total_max,
        'average': (round(sum(r['pct'] for r in rows) / len(rows), 1)
                    if rows else 0.0),
        'highest': rows[0]['pct'] if rows else 0.0,
        'pass_count': pass_count,
        'pass_rate': (round(pass_count * 100.0 / len(rows), 1) if rows else 0.0),
        'filled': filled,
        'expected': expected,
        'missing': max(0, expected - filled),
        'complete': bool(expected > 0 and filled >= expected),
    }
    return tests, rows, summary


def _tabulation_header(tests):
    header = ['Position', 'Roll No', 'Student Name']
    header += ['%s (%s)' % ((t.subject_info.name if t.subject_info else 'Subject'),
                            '{:,.0f}'.format(t.total_marks or 0)) for t in tests]
    header += ['Total Obtained', 'Total Max', 'Percentage', 'Grade']
    return header


@main.route('/examinations/<int:id>/tabulation')
def examinations_tabulation(id):
    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests, rows, summary = build_tabulation(exam)
    return render_template(
        'examination_tabulation.html',
        exam=exam, tests=tests, rows=rows, summary=summary,
        color=test_type_color(exam.exam_type),
        status_color=STATUS_COLORS.get(exam.status, 'secondary'))


@main.route('/examinations/<int:id>/tabulation/export.csv')
def examinations_tabulation_csv(id):
    import csv as csv_module

    exam = db.session.get(TermExam, id)
    if exam is None:
        flash('Term exam not found.', 'warning')
        return redirect(url_for('main.examinations_page'))
    tests, rows, summary = build_tabulation(exam)

    buffer = io.StringIO()
    writer = csv_module.writer(buffer)
    writer.writerow(_tabulation_header(tests))
    for row in rows:
        line = [row['position'], row['student'].roll_number,
                row['student'].student_name]
        for test in tests:
            value = row['scores'].get(test.id)
            line.append('' if value is None else value)
        line += [row['total_obt'], summary['total_max'], row['pct'], row['grade']]
        writer.writerow(line)

    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='Tabulation CSV exported: %s' % exam.name)
    db.session.commit()
    class_name = (exam.class_info.name if exam.class_info else 'class').replace(' ', '_')
    filename = 'tabulation_%s_%s.csv' % (class_name, exam.id)
    return Response(buffer.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=%s'
                                                     % filename})


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
            line[column] = row['scores'].get(test.id)
        line['Total Obtained'] = row['total_obt']
        line['Total Max'] = summary['total_max']
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
            cells.append(fmt_num(row['scores'].get(test.id)))
        cells += [fmt_num(row['total_obt']), fmt_num(summary['total_max']),
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
        % (summary['average'], summary['pass_count'], summary['students'],
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
            if score is None:
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
            'total_obt': row['total_obt'],
            'total_max': summary['total_max'],
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
    if request.form.get('queue_whatsapp') == '1':
        tests, cards, summary = _result_cards(exam)
        for card in cards:
            student = card['student']
            phone = normalize_whatsapp_number(student.guardian_phone or '')
            if not phone:
                skipped += 1
                continue
            existing = (MessageQueue.query
                        .filter_by(student_id=student.id, trigger='result',
                                   ref_date=exam.announce_date)
                        .filter(MessageQueue.status.in_(('pending', 'approved',
                                                         'sent')))
                        .first())
            if existing:
                skipped += 1
                continue
            message = build_whatsapp_message('result', {
                'student_name': student.student_name,
                'test_type': exam.exam_type,
                'date': exam.announce_date,
                'obtained': '%g' % card['total_obt'],
                'total': '%g' % card['total_max'],
                'percentage': card['pct'],
                'grade': card['grade'],
            })
            db.session.add(MessageQueue(
                phone=phone, message=message, status='pending',
                trigger='result', student_id=student.id,
                ref_date=exam.announce_date))
            queued += 1

    log_action('update', entity_type='TermExam', entity_id=exam.id,
               summary='Results published: %s (announce %s, %d message(s) queued)'
                       % (exam.name, exam.announce_date, queued))
    db.session.commit()
    extra = ''
    if request.form.get('queue_whatsapp') == '1':
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

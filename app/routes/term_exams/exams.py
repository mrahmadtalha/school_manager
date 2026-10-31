"""Term examinations: list, create, detail, schedule and date sheet."""

import io
from datetime import date, datetime, timedelta
from flask import (
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func
from app.database import db
from app.models import (
    ClassModel,
    SchoolSettings,
    StudentMarkModel,
    StudentModel,
    SubjectModel,
    TermExam,
    TestModel,
    TestTypeModel,
)
from app.routes import main
from app.routes.examinations import test_type_color
from app.services.audit import log_action
from app.services.marks import ABSENT_LABEL, mark_is_absent
from app.services.term_exam_docs import build_date_sheet_pdf


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

    Positions use competition ranking - students with equal results share a
    position (e.g. 1, 2, 2, 4).

    A paper marked Absent is left out of the student's total, maximum,
    percentage, grade and position: they are judged only on the papers they
    sat.  A student absent from every paper has no grade or position.
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
        row = {'student': student, 'scores': {}, 'absent': {}, 'absent_count': 0,
               'total_obt': 0.0, 'max_marks': 0.0}
        for test in tests:
            mark = marks_map.get((student.id, test.id))
            if mark_is_absent(mark):
                # Recorded as absent: counts as entered, but is not scored and
                # its maximum is not held against the student.
                row['scores'][test.id] = None
                row['absent'][test.id] = True
                row['absent_count'] += 1
                filled += 1
                continue
            row['scores'][test.id] = mark.marks_obtained if mark else None
            row['max_marks'] += test.total_marks or 0
            if mark is not None:
                row['total_obt'] += mark.marks_obtained or 0
                filled += 1
        row['total_obt'] = round(row['total_obt'], 2)
        row['all_absent'] = bool(row['absent_count'] and not row['max_marks'])
        max_marks = row['max_marks']
        row['pct'] = (round(row['total_obt'] / max_marks * 100, 1)
                      if max_marks else 0.0)
        if row['all_absent']:
            row['grade'] = ABSENT_LABEL
        else:
            row['grade'] = calculate_grade(row['pct']) if max_marks else 'N/A'
        row['is_pass'] = bool(max_marks > 0 and row['grade'] != 'F')
        rows.append(row)

    # Positions compare percentage on the papers actually sat, so a student who
    # missed a paper is not pushed down for the marks they could not earn.
    # (With no absences every student has the same maximum, so this orders
    # exactly as ranking by total marks did.)  All-absent students come last
    # and have no position.
    ranked = [r for r in rows if not r['all_absent']]
    unranked = [r for r in rows if r['all_absent']]

    def _standing(r):
        return (r['total_obt'] / r['max_marks']) if r['max_marks'] else 0.0

    ranked.sort(key=_standing, reverse=True)
    rank = 0
    previous = None
    for index, row in enumerate(ranked, 1):
        key = _standing(row)
        if previous is None or key != previous:
            rank = index
            previous = key
        row['rank'] = rank
        row['position'] = _ordinal(rank)
    for row in unranked:
        row['rank'] = None
        row['position'] = '—'
    rows = ranked + unranked

    expected = len(students) * len(tests)
    sat = [r for r in rows if not r['all_absent']]
    pass_count = sum(1 for r in rows if r['is_pass'])
    summary = {
        'students': len(students),
        'sat': len(sat),
        'total_max': total_max,
        'absences': sum(r['absent_count'] for r in rows),
        'average': (round(sum(r['pct'] for r in sat) / len(sat), 1)
                    if sat else 0.0),
        'highest': rows[0]['pct'] if rows else 0.0,
        'pass_count': pass_count,
        'pass_rate': (round(pass_count * 100.0 / len(sat), 1) if sat else 0.0),
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
            if row['absent'].get(test.id):
                line.append(ABSENT_LABEL)
                continue
            value = row['scores'].get(test.id)
            line.append('' if value is None else value)
        line += [row['total_obt'], row['max_marks'], row['pct'], row['grade']]
        writer.writerow(line)

    log_action('export', entity_type='TermExam', entity_id=exam.id,
               summary='Tabulation CSV exported: %s' % exam.name)
    db.session.commit()
    class_name = (exam.class_info.name if exam.class_info else 'class').replace(' ', '_')
    filename = 'tabulation_%s_%s.csv' % (class_name, exam.id)
    return Response(buffer.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=%s'
                                                     % filename})

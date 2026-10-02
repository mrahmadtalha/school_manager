"""Tests, marks and test-category management (with batch workflow upgrades)."""
from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import func

from app.database import db
from app.models import (ClassModel, StudentMarkModel, StudentModel, SubjectModel,
                        TermExam, TestModel, TestTypeModel)
from app.routes import main
from app.services.audit import log_action
from app.services.whatsapp_automation import queue_automation_message  # noqa: F401

#: Card accent colours per test category (case-insensitive, with safe fallback).
TEST_TYPE_COLORS = {
    'daily': 'info',
    'weekly': 'primary',
    'monthly': 'success',
    'mid term': 'warning',
    'mid-term': 'warning',
    'midterm': 'warning',
    'final': 'danger',
    'annual': 'danger',
}


def test_type_color(name):
    return TEST_TYPE_COLORS.get((name or '').strip().lower(), 'secondary')


def _active_student_counts():
    rows = (db.session.query(StudentModel.class_id, func.count(StudentModel.id))
            .filter(StudentModel.is_active.is_(True))
            .group_by(StudentModel.class_id).all())
    return {class_id: int(count) for class_id, count in rows}


def _recent_titles(limit=10):
    titles = []
    for (title,) in (db.session.query(TestModel.test_title)
                     .filter(TestModel.term_exam_id.is_(None))
                     .order_by(TestModel.id.desc()).limit(80).all()):
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


# ==========================================
# TESTING, MARKS & TEST TYPES MANAGEMENT
# ==========================================
@main.route('/tests')
def tests_list():
    tests = (TestModel.query
             .filter(TestModel.term_exam_id.is_(None))
             .order_by(TestModel.test_date.desc(), TestModel.id.desc()).all())
    classes = ClassModel.query.all()
    subjects = SubjectModel.query.filter_by(is_active=True).all()
    test_types = TestTypeModel.query.all()
    create_types = [t for t in test_types
                    if not getattr(t, 'scope', None) or t.scope == 'class_test']
    term_exams_count = TermExam.query.count()

    student_counts = _active_student_counts()

    test_ids = [t.id for t in tests]
    filled_by_test = {}
    if test_ids:
        for test_id, count in (db.session.query(StudentMarkModel.test_id,
                                                func.count(StudentMarkModel.id))
                               .filter(StudentMarkModel.test_id.in_(test_ids))
                               .group_by(StudentMarkModel.test_id).all()):
            filled_by_test[test_id] = int(count)

    exams = []
    seen = {}
    for test in tests:
        key = f'{test.test_title}_{test.test_date}_{test.class_id}'
        if key not in seen:
            seen[key] = {
                'title': test.test_title,
                'date': test.test_date,
                'class_info': test.class_info,
                'test_type': test.test_type,
                'color': test_type_color(test.test_type),
                'subjects_count': 0,
                'total_marks_sum': 0.0,
                'first_test_id': test.id,
                'class_id': test.class_id,
                'students_count': student_counts.get(test.class_id, 0),
                'marks_filled': 0,
                'test_ids': [],
            }
            exams.append(seen[key])
        bucket = seen[key]
        bucket['subjects_count'] += 1
        bucket['total_marks_sum'] += test.total_marks or 0
        bucket['test_ids'].append(test.id)

    for bucket in exams:
        bucket['marks_filled'] = sum(filled_by_test.get(tid, 0)
                                     for tid in bucket['test_ids'])
        bucket['marks_total'] = bucket['students_count'] * bucket['subjects_count']
        if bucket['marks_total'] == 0:
            bucket['progress_state'] = 'empty'
            bucket['progress_label'] = 'No students'
        elif bucket['marks_filled'] >= bucket['marks_total']:
            bucket['progress_state'] = 'done'
            bucket['progress_label'] = 'Marks complete'
        elif bucket['marks_filled'] == 0:
            bucket['progress_state'] = 'none'
            bucket['progress_label'] = 'No marks yet'
        else:
            pct = round(bucket['marks_filled'] * 100.0 / bucket['marks_total'])
            bucket['progress_state'] = 'partial'
            bucket['progress_label'] = ('Marks %d/%d (%d%%)'
                                        % (bucket['marks_filled'],
                                           bucket['marks_total'], pct))
        bucket.pop('test_ids', None)

    return render_template(
        'tests.html',
        exams=exams,
        classes=classes,
        subjects=subjects,
        test_types=test_types,
        create_types=create_types,
        term_exams_count=term_exams_count,
        recent_titles=_recent_titles(),
        type_defaults={tt.name: (tt.default_marks if tt.default_marks else 100)
                       for tt in test_types},
        today=date.today(),
    )


@main.route('/tests/add', methods=['POST'])
def add_test():
    try:
        class_id = request.form.get('class_id', type=int) or 0
        class_obj = db.session.get(ClassModel, class_id)
        if class_obj is None:
            flash('Please choose a valid class.', 'danger')
            return redirect(url_for('main.tests_list'))

        test_type = (request.form.get('test_type') or '').strip()
        if not test_type:
            flash('Please choose a test category.', 'danger')
            return redirect(url_for('main.tests_list'))

        test_date_str = (request.form.get('test_date') or '').strip()
        if test_date_str:
            try:
                test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Please choose a valid test date.', 'danger')
                return redirect(url_for('main.tests_list'))
        else:
            test_date = date.today()

        test_title = (request.form.get('test_title') or '').strip()
        if not test_title:
            test_title = '%s Test — %s' % (test_type, test_date.strftime('%b %Y'))
        test_title = test_title[:100]

        existing = TestModel.query.filter_by(test_title=test_title,
                                             test_date=test_date,
                                             class_id=class_id).first()
        if existing:
            flash('A batch titled "%s" already exists for %s on %s — nothing was '
                  'created; open it from the list to enter marks.'
                  % (test_title, class_obj.name, test_date.strftime('%d %b %Y')),
                  'warning')
            return redirect(url_for('main.tests_list'))

        type_obj = TestTypeModel.query.filter_by(name=test_type).first()
        fallback_marks = float(type_obj.default_marks) \
            if type_obj is not None and type_obj.default_marks else 100.0

        subjects = SubjectModel.query.filter_by(class_id=class_id, is_active=True).all()
        added_count = 0
        for subject in subjects:
            if not request.form.get('include_subject_%d' % subject.id):
                continue
            marks_str = (request.form.get('total_marks_%d' % subject.id) or '').strip()
            if marks_str:
                try:
                    total_marks = float(marks_str)
                except ValueError:
                    flash('Total marks must be a number.', 'danger')
                    return redirect(url_for('main.tests_list'))
                if total_marks <= 0:
                    flash('Total marks must be a positive number.', 'danger')
                    return redirect(url_for('main.tests_list'))
            else:
                total_marks = fallback_marks

            db.session.add(TestModel(
                test_title=test_title, test_type=test_type,
                class_id=class_id, subject_id=subject.id,
                total_marks=total_marks, test_date=test_date))
            added_count += 1

        if added_count == 0:
            flash('You must select at least one subject to create a test batch.',
                  'danger')
            return redirect(url_for('main.tests_list'))

        log_action('create', entity_type='TestModel',
                   summary='Test batch created: %s (%s, %s) — %d subject(s)'
                           % (test_title, class_obj.name,
                              test_date.strftime('%d %b %Y'), added_count))
        db.session.commit()
        flash('Test batch created successfully with %d subjects! '
              'You can now enter student marks.' % added_count, 'success')

        if request.form.get('redirect_to_marks') == '1':
            return redirect(url_for('main.enter_batch_marks',
                                    title=test_title,
                                    date=test_date.isoformat(),
                                    class_id=class_id))
    except Exception as error:
        db.session.rollback()
        flash('Error creating test batch: %s' % error, 'danger')

    return redirect(url_for('main.tests_list'))


@main.route('/tests/batch_delete', methods=['POST'])
def delete_test_batch():
    test_title = (request.form.get('test_title') or '').strip()
    test_date_str = (request.form.get('test_date') or '').strip()
    class_id = request.form.get('class_id', type=int) or 0
    try:
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid batch selected.', 'danger')
        return redirect(url_for('main.tests_list'))

    tests = TestModel.query.filter_by(test_title=test_title, test_date=test_date,
                                      class_id=class_id).all()
    if not tests:
        flash('That test batch was not found.', 'warning')
        return redirect(url_for('main.tests_list'))

    subject_count = len(tests)
    marks_count = sum(len(test.marks) for test in tests)
    for test in tests:
        db.session.delete(test)
    log_action('delete', entity_type='TestModel',
               summary='Test batch deleted: %s (%s) — %d subject(s), %d mark(s) removed'
                       % (test_title, test_date.strftime('%d %b %Y'),
                          subject_count, marks_count))
    db.session.commit()
    flash('Test batch "%s" deleted (%d subject(s), %d mark(s) removed).'
          % (test_title, subject_count, marks_count), 'warning')
    return redirect(url_for('main.tests_list'))


@main.route('/tests/batch_marks', methods=['GET', 'POST'])
def enter_batch_marks():
    term_exam_id = (request.args.get('term_exam_id', type=int)
                    or request.form.get('term_exam_id', type=int))
    term_exam = None
    if term_exam_id:
        term_exam = db.session.get(TermExam, term_exam_id)
        if term_exam is None:
            flash("Term exam not found.", "danger")
            return redirect(url_for('main.examinations_page'))
        tests = (TestModel.query.filter_by(term_exam_id=term_exam_id)
                 .order_by(TestModel.test_date, TestModel.id).all())
        if not tests:
            flash("This term exam has no subjects yet.", "danger")
            return redirect(url_for('main.examinations_detail', id=term_exam_id))
        class_info = term_exam.class_info
        students = StudentModel.query.filter_by(
            is_active=True, class_id=term_exam.class_id).all()
        test_title = term_exam.name
        test_date = term_exam.start_date or date.today()
        test_date_str = test_date.isoformat()
        class_id = term_exam.class_id
        back_url = url_for('main.examinations_detail', id=term_exam.id)
    else:
        test_title = request.args.get('title')
        test_date_str = request.args.get('date')
        class_id = request.args.get('class_id')

        if not all([test_title, test_date_str, class_id]):
            flash("Invalid exam batch specified.", "danger")
            return redirect(url_for('main.tests_list'))

        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date()

        # Get all tests in this batch
        tests = TestModel.query.filter_by(
            test_title=test_title,
            test_date=test_date,
            class_id=class_id
        ).all()

        if not tests:
            flash("Exam batch not found.", "danger")
            return redirect(url_for('main.tests_list'))

        class_info = ClassModel.query.get_or_404(class_id)
        students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
        back_url = url_for('main.tests_list')

    if request.method == 'POST':
        try:
            saved_count = 0
            for test in tests:
                for student in students:
                    marks_str = request.form.get(f'marks_{student.id}_{test.id}')
                    if marks_str is not None and marks_str.strip() != '':
                        marks_obtained = float(marks_str)
                        if marks_obtained > test.total_marks:
                            flash(f'Error: Marks obtained cannot exceed total marks ({test.total_marks}) for {student.student_name} in {test.subject_info.name}.', 'danger')
                            return redirect(request.url)

                        percentage = (marks_obtained / test.total_marks) * 100 if test.total_marks > 0 else 0
                        from app.models.settings import calculate_grade
                        grade = calculate_grade(percentage)

                        mark_record = StudentMarkModel.query.filter_by(
                            test_id=test.id, student_id=student.id).first()
                        if mark_record:
                            mark_record.marks_obtained = marks_obtained
                            mark_record.percentage = round(percentage, 1)
                            mark_record.grade = grade
                        else:
                            new_mark = StudentMarkModel(
                                test_id=test.id, student_id=student.id,
                                marks_obtained=marks_obtained,
                                percentage=round(percentage, 1), grade=grade
                            )
                            db.session.add(new_mark)
                        saved_count += 1

            db.session.commit()

            flash(f'Marks saved successfully ({saved_count} entries)!', 'success')
            if term_exam is not None:
                canonical = url_for('main.enter_batch_marks',
                                    term_exam_id=term_exam.id)
                done_url = url_for('main.examinations_detail', id=term_exam.id)
            else:
                canonical = url_for('main.enter_batch_marks',
                                    title=test_title, date=test_date_str,
                                    class_id=class_id)
                done_url = url_for('main.tests_list')
            if request.form.get('stay') == '1':
                return redirect(canonical)
            return redirect(done_url)
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving marks: {str(e)}', 'danger')

    # Load existing marks
    existing_marks = {}
    for student in students:
        existing_marks[student.id] = {}

    all_marks = StudentMarkModel.query.filter(StudentMarkModel.test_id.in_([t.id for t in tests])).all()
    for m in all_marks:
        if m.student_id in existing_marks:
            existing_marks[m.student_id][m.test_id] = m.marks_obtained

    return render_template(
        'enter_batch_marks.html',
        tests=tests,
        students=students,
        class_info=class_info,
        batch_title=test_title,
        batch_date=test_date,
        batch_type=tests[0].test_type,
        term_exam_id=term_exam_id,
        back_url=back_url,
        existing_marks=existing_marks
    )


@main.route('/test-types')
def test_types_list():
    types = TestTypeModel.query.all()
    return render_template('test_types.html', test_types=types)


@main.route('/test-types/add', methods=['POST'])
def add_test_type():
    try:
        name = request.form.get('name').strip()
        default_marks = request.form.get('default_marks', type=float)
        scope = (request.form.get('scope') or '').strip()
        if scope not in ('class_test', 'term_exam'):
            scope = None
        if default_marks is not None and default_marks <= 0:
            flash('Default marks must be a positive number.', 'danger')
            return redirect(url_for('main.test_types_list'))

        existing = TestTypeModel.query.filter_by(name=name).first()
        if existing:
            flash(f'Test type "{name}" already exists.', 'danger')
            return redirect(url_for('main.test_types_list'))

        new_type = TestTypeModel(name=name, default_marks=default_marks, scope=scope)
        db.session.add(new_type)
        db.session.commit()
        flash('Test type added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding test type: {str(e)}', 'danger')
    return redirect(url_for('main.test_types_list'))


@main.route('/test-types/edit/<int:id>', methods=['POST'])
def edit_test_type(id):
    try:
        t_type = TestTypeModel.query.get_or_404(id)
        new_name = request.form.get('name').strip()
        default_marks = request.form.get('default_marks', type=float)
        scope = (request.form.get('scope') or '').strip()
        if scope not in ('class_test', 'term_exam'):
            scope = None
        if default_marks is not None and default_marks <= 0:
            flash('Default marks must be a positive number.', 'danger')
            return redirect(url_for('main.test_types_list'))

        existing = TestTypeModel.query.filter_by(name=new_name).first()
        if existing and existing.id != id:
            flash(f'Test type name "{new_name}" already exists.', 'danger')
            return redirect(url_for('main.test_types_list'))

        t_type.name = new_name
        t_type.default_marks = default_marks
        t_type.scope = scope
        db.session.commit()
        flash('Test type updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating test type: {str(e)}', 'danger')
    return redirect(url_for('main.test_types_list'))


@main.route('/test-types/delete/<int:id>', methods=['POST'])
def delete_test_type(id):
    try:
        t_type = TestTypeModel.query.get_or_404(id)
        db.session.delete(t_type)
        db.session.commit()
        flash('Test type deleted successfully!', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting test type: {str(e)}', 'danger')
    return redirect(url_for('main.test_types_list'))

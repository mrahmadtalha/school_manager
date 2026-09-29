from datetime import datetime, date
from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash
)

from app.database import db
from app.models import (
    ClassModel, SectionModel, SubjectModel, StudentModel, 
    TestModel, StudentMarkModel, TestTypeModel
)
from app.routes import main
from app.services.whatsapp_automation import queue_automation_message

# ==========================================
# TESTING, MARKS & TEST TYPES MANAGEMENT
# ==========================================
@main.route('/tests')
def tests_list():
    tests = TestModel.query.all()
    classes = ClassModel.query.all()
    subjects = SubjectModel.query.all()
    test_types = TestTypeModel.query.all()
    
    # Group tests into batches
    exams = {}
    for t in tests:
        key = f"{t.test_title}_{t.test_date}_{t.class_id}"
        if key not in exams:
            exams[key] = {
                'title': t.test_title,
                'date': t.test_date,
                'class_info': t.class_info,
                'test_type': t.test_type,
                'subjects_count': 0,
                'total_marks_sum': 0,
                'first_test_id': t.id,
                'class_id': t.class_id,
            }
        exams[key]['subjects_count'] += 1
        exams[key]['total_marks_sum'] += t.total_marks

    return render_template(
        'tests.html', 
        exams=exams.values(), 
        classes=classes, 
        subjects=subjects, 
        test_types=test_types
    )
@main.route('/tests/add', methods=['POST'])
def add_test():
    try:
        test_title = request.form.get('test_title').strip()
        test_type = request.form.get('test_type')
        class_id = int(request.form.get('class_id'))
        test_date_str = request.form.get('test_date')
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date() if test_date_str else datetime.utcnow().date()

        # Find all selected subjects for this class
        subjects = SubjectModel.query.filter_by(class_id=class_id).all()
        added_count = 0
        for subject in subjects:
            include_subject = request.form.get(f'include_subject_{subject.id}')
            if include_subject:
                marks_str = request.form.get(f'total_marks_{subject.id}')
                total_marks = float(marks_str) if marks_str and marks_str.strip() else 100.0
                
                new_test = TestModel(
                    test_title=test_title, test_type=test_type,
                    class_id=class_id, subject_id=subject.id,
                    total_marks=total_marks, test_date=test_date
                )
                db.session.add(new_test)
                added_count += 1
                
        if added_count == 0:
            flash('You must select at least one subject to create a test batch.', 'danger')
            return redirect(url_for('main.tests_list'))

        db.session.commit()
        flash(f'Test batch created successfully with {added_count} subjects! You can now enter student marks.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating test batch: {str(e)}', 'danger')
        
    return redirect(url_for('main.tests_list'))

@main.route('/tests/batch_marks', methods=['GET', 'POST'])
def enter_batch_marks():
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
                            
                        mark_record = StudentMarkModel.query.filter_by(test_id=test.id, student_id=student.id).first()
                        if mark_record:
                            mark_record.marks_obtained = marks_obtained
                            mark_record.percentage = round(percentage, 1)
                            mark_record.grade = grade
                        else:
                            new_mark = StudentMarkModel(
                                test_id=test.id, student_id=student.id,
                                marks_obtained=marks_obtained, percentage=round(percentage, 1), grade=grade
                            )
                            db.session.add(new_mark)
                        saved_count += 1

            db.session.commit()
            
            flash(f'Marks saved successfully ({saved_count} entries)!', 'success')
            return redirect(url_for('main.tests_list'))
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
        existing = TestTypeModel.query.filter_by(name=name).first()
        if existing:
            flash(f'Test type "{name}" already exists.', 'danger')
            return redirect(url_for('main.test_types_list'))
            
        new_type = TestTypeModel(name=name)
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
        existing = TestTypeModel.query.filter_by(name=new_name).first()
        if existing and existing.id != id:
            flash(f'Test type name "{new_name}" already exists.', 'danger')
            return redirect(url_for('main.test_types_list'))
            
        t_type.name = new_name
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


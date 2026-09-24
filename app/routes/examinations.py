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
    return render_template(
        'tests.html', 
        tests=tests, 
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
        subject_id = int(request.form.get('subject_id'))
        total_marks = float(request.form.get('total_marks'))
        test_date_str = request.form.get('test_date')
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date() if test_date_str else datetime.utcnow().date()

        new_test = TestModel(
            test_title=test_title, test_type=test_type,
            class_id=class_id, subject_id=subject_id,
            total_marks=total_marks, test_date=test_date
        )
        db.session.add(new_test)
        db.session.commit()
        flash('Test created successfully! You can now enter student marks.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating test: {str(e)}', 'danger')
        
    return redirect(url_for('main.tests_list'))

@main.route('/tests/marks/<int:test_id>', methods=['GET', 'POST'])
def enter_marks(test_id):
    test = TestModel.query.get_or_404(test_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=test.class_id).all()
    
    if request.method == 'POST':
        try:
            for student in students:
                marks_str = request.form.get(f'marks_{student.id}')
                if marks_str is not None and marks_str.strip() != '':
                    marks_obtained = float(marks_str)
                    if marks_obtained > test.total_marks:
                        flash(f'Error: Marks obtained cannot exceed total marks ({test.total_marks}) for {student.student_name}.', 'danger')
                        return redirect(url_for('main.enter_marks', test_id=test_id))
                        
                    percentage = (marks_obtained / test.total_marks) * 100 if test.total_marks > 0 else 0
                    if percentage >= 85: grade = 'A+'
                    elif percentage >= 70: grade = 'A'
                    elif percentage >= 60: grade = 'B'
                    elif percentage >= 50: grade = 'C'
                    elif percentage >= 40: grade = 'D'
                    else: grade = 'F'
                        
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
                        
            saved_students = []
            db.session.commit()
            for student in students:
                marks_str = request.form.get(f'marks_{student.id}')
                if marks_str is not None and marks_str.strip() != '':
                    mark_record = StudentMarkModel.query.filter_by(test_id=test.id, student_id=student.id).first()
                    if mark_record:
                        saved_students.append((student, float(mark_record.marks_obtained), float(mark_record.percentage), mark_record.grade))

            for student, obtained, percentage, grade in saved_students:
                queue_automation_message(
                    student,
                    'result',
                    {
                        'student_name': student.student_name,
                        'date': test.test_date.isoformat(),
                        'test_type': test.test_type,
                        'grade': grade,
                        'obtained': str(obtained),
                        'total': str(test.total_marks),
                        'percentage': str(percentage),
                    },
                )

            flash('Student marks saved and grades computed successfully!', 'success')
            return redirect(url_for('main.tests_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving marks: {str(e)}', 'danger')
            
    existing_marks = {m.student_id: m.marks_obtained for m in StudentMarkModel.query.filter_by(test_id=test.id).all()}
    return render_template('enter_marks.html', test=test, students=students, existing_marks=existing_marks)

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


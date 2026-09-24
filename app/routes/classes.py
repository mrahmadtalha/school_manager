from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash
)

from app.database import db
from app.models import ClassModel, SectionModel, SubjectModel, TeacherModel, StudentModel
from app.routes import main

# ==========================================
# CLASS, SECTION, & SUBJECT MANAGEMENT
# ==========================================
@main.route('/classes')
def classes_list():
    classes = ClassModel.query.all()
    active_student_count = StudentModel.query.filter_by(is_active=True).count()
    return render_template('classes.html', classes=classes, active_student_count=active_student_count)

@main.route('/classes/add', methods=['POST'])
def add_class():
    try:
        class_name = request.form.get('class_name').strip()
        existing = ClassModel.query.filter_by(name=class_name).first()
        if existing:
            flash(f'Class "{class_name}" already exists.', 'danger')
            return redirect(url_for('main.classes_list'))
            
        new_class = ClassModel(name=class_name)
        db.session.add(new_class)
        db.session.commit()
        
        db.session.add(SectionModel(name="A", class_id=new_class.id))
        db.session.add(SectionModel(name="B", class_id=new_class.id))
        
        default_subs = ["English", "Urdu", "Mathematics", "Islamiyat"]
        for sub in default_subs:
            db.session.add(SubjectModel(name=sub, class_id=new_class.id))
            
        db.session.commit()
        flash(f'Class "{class_name}" created successfully with default sections and subjects!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding class: {str(e)}', 'danger')
        
    return redirect(url_for('main.classes_list'))

@main.route('/classes/edit/<int:id>', methods=['POST'])
def edit_class(id):
    try:
        class_obj = ClassModel.query.get_or_404(id)
        new_name = request.form.get('class_name').strip()
        existing = ClassModel.query.filter_by(name=new_name).first()
        if existing and existing.id != id:
            flash(f'Class name "{new_name}" already exists.', 'danger')
            return redirect(url_for('main.classes_list'))
            
        class_obj.name = new_name
        db.session.commit()
        flash('Class updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating class: {str(e)}', 'danger')
        
    return redirect(url_for('main.classes_list'))

@main.route('/sections/add', methods=['POST'])
def add_section():
    try:
        section_name = request.form.get('section_name').strip().upper()
        class_id = int(request.form.get('class_id'))
        new_sec = SectionModel(name=section_name, class_id=class_id)
        db.session.add(new_sec)
        db.session.commit()
        flash(f'Section "{section_name}" added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding section: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/sections/edit/<int:id>', methods=['POST'])
def edit_section(id):
    try:
        sec = SectionModel.query.get_or_404(id)
        sec.name = request.form.get('section_name').strip().upper()
        db.session.commit()
        flash('Section updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating section: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/sections/delete/<int:id>', methods=['POST'])
def delete_section(id):
    try:
        sec = SectionModel.query.get_or_404(id)
        db.session.delete(sec)
        db.session.commit()
        flash('Section deleted successfully!', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting section: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/subjects/add', methods=['POST'])
def add_subject():
    try:
        subject_name = request.form.get('subject_name').strip()
        class_id = int(request.form.get('class_id'))
        new_sub = SubjectModel(name=subject_name, class_id=class_id)
        db.session.add(new_sub)
        db.session.commit()
        flash(f'Subject "{subject_name}" added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding subject: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/subjects/edit/<int:id>', methods=['POST'])
def edit_subject(id):
    try:
        sub = SubjectModel.query.get_or_404(id)
        sub.name = request.form.get('subject_name').strip()
        db.session.commit()
        flash('Subject updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating subject: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/subjects/delete/<int:id>', methods=['POST'])
def delete_subject(id):
    try:
        sub = SubjectModel.query.get_or_404(id)
        db.session.delete(sub)
        db.session.commit()
        flash('Subject deleted successfully!', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting subject: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))


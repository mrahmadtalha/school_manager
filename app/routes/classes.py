from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    current_app,
    abort,
)

from flask_login import current_user
from app.database import db
from app.models import (ClassModel, SectionModel, SubjectModel, SubjectLibrary, TeacherModel,
                       StudentModel, TestModel)
from app.routes import main

# ==========================================
# CLASS, SECTION, & SUBJECT MANAGEMENT
# ==========================================


def _parse_class_fee(form):
    """Read the optional standard monthly fee from a class form."""
    raw = (form.get('monthly_fee') or '').strip().replace(',', '')
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError('Please enter a valid class fee.')
    if value < 0:
        raise ValueError('Class fee cannot be negative.')
    return round(value, 2)


@main.route('/classes')
def classes_list():
    classes = ClassModel.query.all()
    active_student_count = StudentModel.query.filter_by(is_active=True).count()
    section_count = SectionModel.query.count()
    active_subject_count = SubjectModel.query.filter_by(is_active=True).count()
    fee_unset_count = sum(1 for class_obj in classes if not class_obj.monthly_fee)
    subject_test_counts = dict(
        db.session.query(TestModel.subject_id, db.func.count(TestModel.id))
        .group_by(TestModel.subject_id).all())
    teachers = (TeacherModel.query.filter_by(is_active=True)
                .order_by(TeacherModel.teacher_name).all())
    library_subjects = (SubjectLibrary.query.filter_by(is_active=True)
                        .order_by(SubjectLibrary.name).all())
    return render_template('classes.html', classes=classes,
                           active_student_count=active_student_count,
                           section_count=section_count,
                           active_subject_count=active_subject_count,
                           fee_unset_count=fee_unset_count,
                           teachers=teachers,
                           subject_test_counts=subject_test_counts,
                           library_subjects=library_subjects)

@main.route('/classes/add', methods=['POST'])
def add_class():
    try:
        class_name = request.form.get('class_name').strip()
        if not class_name:
            flash('Please enter a class name.', 'danger')
            return redirect(url_for('main.classes_list'))
        existing = ClassModel.query.filter_by(name=class_name).first()
        if existing:
            flash(f'Class "{class_name}" already exists.', 'danger')
            return redirect(url_for('main.classes_list'))

        fee_value = _parse_class_fee(request.form)

        # Subjects come from the global Subject Library: the checked entries
        # become this class's subjects (pre-ticked defaults live on the
        # library rows themselves, editable on the Subject Library page).
        selected_ids = []
        for raw in request.form.getlist('library_subject'):
            try:
                selected_ids.append(int(raw))
            except ValueError:
                continue
        library_subjects = []
        if selected_ids:
            library_subjects = (SubjectLibrary.query
                                .filter(SubjectLibrary.id.in_(selected_ids),
                                        SubjectLibrary.is_active.is_(True))
                                .order_by(SubjectLibrary.name).all())

        new_class = ClassModel(name=class_name, monthly_fee=fee_value)
        db.session.add(new_class)
        db.session.flush()

        db.session.add(SectionModel(name="A", class_id=new_class.id))
        db.session.add(SectionModel(name="B", class_id=new_class.id))

        for lib in library_subjects:
            db.session.add(SubjectModel(name=lib.name, class_id=new_class.id,
                                        library_id=lib.id))

        db.session.commit()
        subject_note = f' and {len(library_subjects)} subject(s)' if library_subjects else ''
        flash(f'Class "{class_name}" created successfully with sections A & B{subject_note}!',
              'success')
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

@main.route('/classes/<int:id>/fee', methods=['POST'])
def update_class_fee(id):
    from app.services.audit import log_action
    try:
        class_obj = ClassModel.query.get_or_404(id)
        if (request.form.get('confirm_fee') or '') != '1':
            flash('Please tick the confirmation box to update the default admission fee.', 'warning')
            return redirect(url_for('main.classes_list'))
        fee_value = _parse_class_fee(request.form)
        previous = class_obj.monthly_fee
        class_obj.monthly_fee = fee_value
        if previous != fee_value:
            log_action('settings_change', entity_type='ClassModel', entity_id=class_obj.id,
                       summary=f'Class standard fee for {class_obj.name} set to '
                               f'{fee_value if fee_value is not None else "none"}',
                       before={'monthly_fee': previous}, after={'monthly_fee': fee_value})
        db.session.commit()
        if fee_value is None:
            flash(f'Standard fee cleared for {class_obj.name}.', 'warning')
        else:
            flash(f'Standard fee for {class_obj.name} set to Rs {fee_value:,.0f} / month.',
                  'success')
    except ValueError as err:
        flash(str(err), 'danger')
    except Exception as err:
        db.session.rollback()
        flash(f'Error updating class fee: {str(err)}', 'danger')
    return redirect(url_for('main.classes_list'))






@main.route('/sections/add', methods=['POST'])
def add_section():
    try:
        section_name = (request.form.get('section_name') or '').strip().upper()
        class_id = int(request.form.get('class_id'))
        if not section_name:
            flash('Please enter a section name.', 'danger')
            return redirect(url_for('main.classes_list'))
        existing = SectionModel.query.filter_by(class_id=class_id, name=section_name).first()
        if existing:
            flash(f'Section "{section_name}" already exists in this class.', 'danger')
            return redirect(url_for('main.classes_list'))
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
        new_name = (request.form.get('section_name') or '').strip().upper()
        if not new_name:
            flash('Please enter a section name.', 'danger')
            return redirect(url_for('main.classes_list'))
        duplicate = SectionModel.query.filter(SectionModel.class_id == sec.class_id,
                                              SectionModel.name == new_name,
                                              SectionModel.id != sec.id).first()
        if duplicate:
            flash(f'Section "{new_name}" already exists in this class.', 'danger')
            return redirect(url_for('main.classes_list'))
        sec.name = new_name
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
        students = StudentModel.query.filter_by(section_id=sec.id).all()

        target = None
        target_raw = (request.form.get('target_section_id') or '').strip()
        if target_raw:
            try:
                target_id = int(target_raw)
            except ValueError:
                target_id = None
            if target_id:
                target = db.session.get(SectionModel, target_id)
                if target is None or target.class_id != sec.class_id or target.id == sec.id:
                    flash('Please choose a valid section of the same class for the move.', 'danger')
                    return redirect(url_for('main.classes_list'))

        # Bulk move first so the ORM has no attached children left when the
        # section delete is processed (otherwise SQLAlchemy re-nulls their FK).
        new_section_id = target.id if target else None
        StudentModel.query.filter_by(section_id=sec.id).update(
            {'section_id': new_section_id}, synchronize_session=False)
        db.session.delete(sec)
        db.session.commit()

        if students:
            destination = target.name if target else 'unassigned'
            flash(f'Section "{sec.name}" deleted — {len(students)} student(s) moved to {destination}.', 'warning')
        else:
            flash('Section deleted successfully!', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting section: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/subjects/add', methods=['POST'])
def add_subject():
    try:
        subject_name = (request.form.get('subject_name') or '').strip()
        if not subject_name:
            flash('Please enter a subject name.', 'danger')
            return redirect(url_for('main.classes_list'))
        class_id = int(request.form.get('class_id'))
        duplicate = (SubjectModel.query
                     .filter(SubjectModel.class_id == class_id,
                             db.func.lower(SubjectModel.name) == subject_name.lower())
                     .first())
        if duplicate:
            if duplicate.is_active:
                flash(f'Subject "{subject_name}" already exists in this class.', 'danger')
            else:
                flash(f'Subject "{subject_name}" already exists (archived) — restore it instead.', 'danger')
            return redirect(url_for('main.classes_list'))
        new_lib = None
        library = (SubjectLibrary.query
                   .filter(db.func.lower(SubjectLibrary.name) == subject_name.lower())
                   .first())
        if library is None:
            # A subject typed here but not yet in the catalog joins the library
            # automatically, so the two stay in sync going forward.
            new_lib = SubjectLibrary(name=subject_name, is_active=True, is_default=False)
            db.session.add(new_lib)
            db.session.flush()
            library = new_lib
        new_sub = SubjectModel(name=subject_name, class_id=class_id, library_id=library.id)
        db.session.add(new_sub)
        db.session.flush()
        from app.services import teaching_assignments
        teaching_assignments.sync_for_class_subject(new_sub)
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
        new_name = (request.form.get('subject_name') or '').strip()
        if not new_name:
            flash('Please enter a subject name.', 'danger')
            return redirect(url_for('main.classes_list'))
        duplicate = (SubjectModel.query
                     .filter(SubjectModel.class_id == sub.class_id,
                             SubjectModel.id != sub.id,
                             db.func.lower(SubjectModel.name) == new_name.lower())
                     .first())
        if duplicate:
            flash(f'Subject "{new_name}" already exists in this class.', 'danger')
            return redirect(url_for('main.classes_list'))
        sub.name = new_name
        # Re-link when the new name matches a library subject; otherwise the
        # row keeps its current link and stays managed by the library.
        match = (SubjectLibrary.query
                 .filter(db.func.lower(SubjectLibrary.name) == new_name.lower())
                 .first())
        if match is not None:
            sub.library_id = match.id
        if 'teacher_id' in request.form:
            raw_teacher = (request.form.get('teacher_id') or '').strip()
            try:
                teacher_id = int(raw_teacher) if raw_teacher else None
            except ValueError:
                teacher_id = None
            if teacher_id is not None and db.session.get(TeacherModel, teacher_id) is None:
                teacher_id = None
            sub.teacher_id = teacher_id
        from app.services import teaching_assignments
        teaching_assignments.sync_for_class_subject(sub)
        db.session.commit()
        flash('Subject updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating subject: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))

@main.route('/subjects/archive/<int:id>', methods=['POST'])
def archive_subject(id):
    try:
        sub = SubjectModel.query.get_or_404(id)
        sub.is_active = False
        from app.services import teaching_assignments
        teaching_assignments.sync_for_class_subject(sub)
        db.session.commit()
        flash(f'Subject "{sub.name}" archived — hidden from new tests/exams; past marks stay intact.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error archiving subject: {str(e)}', 'danger')
    return redirect(url_for('main.classes_list'))


@main.route('/subjects/archived')
def archived_subjects_list():
    """All archived subjects, with how many tests still reference each one."""
    subjects = (SubjectModel.query.filter_by(is_active=False)
                .join(ClassModel, SubjectModel.class_id == ClassModel.id)
                .order_by(ClassModel.name, SubjectModel.name).all())
    test_counts = dict(
        db.session.query(TestModel.subject_id, db.func.count(TestModel.id))
        .group_by(TestModel.subject_id).all())
    return render_template('archived_subjects.html', subjects=subjects,
                           subject_test_counts=test_counts)


@main.route('/subjects/restore/<int:id>', methods=['POST'])
def restore_subject(id):
    try:
        sub = SubjectModel.query.get_or_404(id)
        sub.is_active = True
        from app.services import teaching_assignments
        teaching_assignments.sync_for_class_subject(sub)
        db.session.commit()
        flash(f'Subject "{sub.name}" restored in {sub.class_info.name if sub.class_info else "its class"} '
              '— it is available for new tests/exams again.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring subject: {str(e)}', 'danger')
    if request.form.get('next') == 'archived':
        return redirect(url_for('main.archived_subjects_list'))
    return redirect(url_for('main.classes_list'))


# ==========================================
# SUBJECT LIBRARY (global subject catalog)
# ==========================================

@main.route('/subjects/library')
def subject_library():
    """Global subject catalog with how much each entry is actually used."""
    library_subjects = SubjectLibrary.query.order_by(SubjectLibrary.name).all()
    class_counts = dict(
        db.session.query(SubjectModel.library_id, db.func.count(SubjectModel.id))
        .filter(SubjectModel.library_id.isnot(None), SubjectModel.is_active.is_(True))
        .group_by(SubjectModel.library_id).all())
    archived_counts = dict(
        db.session.query(SubjectModel.library_id, db.func.count(SubjectModel.id))
        .filter(SubjectModel.library_id.isnot(None), SubjectModel.is_active.is_(False))
        .group_by(SubjectModel.library_id).all())
    test_counts = dict(
        db.session.query(SubjectModel.library_id, db.func.count(TestModel.id))
        .join(SubjectModel, TestModel.subject_id == SubjectModel.id)
        .filter(SubjectModel.library_id.isnot(None))
        .group_by(SubjectModel.library_id).all())
    return render_template('subject_library.html', library_subjects=library_subjects,
                           class_counts=class_counts, archived_counts=archived_counts,
                           test_counts=test_counts)


@main.route('/subjects/library/add', methods=['POST'])
def library_add_subject():
    try:
        name = (request.form.get('subject_name') or '').strip()
        if not name:
            flash('Please enter a subject name.', 'danger')
            return redirect(url_for('main.subject_library'))
        code = (request.form.get('subject_code') or '').strip() or None
        existing = (SubjectLibrary.query
                    .filter(db.func.lower(SubjectLibrary.name) == name.lower())
                    .first())
        if existing:
            if existing.is_active:
                flash(f'Subject "{name}" already exists in the library.', 'danger')
            else:
                flash(f'Subject "{name}" is archived in the library — restore it instead.', 'danger')
            return redirect(url_for('main.subject_library'))
        entry = SubjectLibrary(name=name, code=code, is_active=True,
                               is_default=request.form.get('is_default') == '1')
        db.session.add(entry)
        db.session.commit()
        flash(f'Subject "{name}" added to the library.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding library subject: {str(e)}', 'danger')
    return redirect(url_for('main.subject_library'))


@main.route('/subjects/library/rename/<int:id>', methods=['POST'])
def library_rename_subject(id):
    try:
        from app.services.audit import log_action
        entry = SubjectLibrary.query.get_or_404(id)
        new_name = (request.form.get('subject_name') or '').strip()
        if not new_name:
            flash('Please enter a subject name.', 'danger')
            return redirect(url_for('main.subject_library'))
        duplicate = (SubjectLibrary.query
                     .filter(SubjectLibrary.id != entry.id,
                             db.func.lower(SubjectLibrary.name) == new_name.lower())
                     .first())
        if duplicate:
            flash(f'Subject "{new_name}" already exists in the library.', 'danger')
            return redirect(url_for('main.subject_library'))
        previous = entry.name
        entry.name = new_name
        linked = SubjectModel.query.filter_by(library_id=entry.id).all()
        for subject in linked:
            subject.name = new_name
        log_action('update', entity_type='SubjectLibrary', entity_id=entry.id,
                   summary=f'Library subject renamed: {previous} → {new_name} '
                           f'({len(linked)} class row(s) updated)',
                   before={'name': previous}, after={'name': new_name})
        db.session.commit()
        flash(f'Subject renamed to "{new_name}" — {len(linked)} class row(s) updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error renaming library subject: {str(e)}', 'danger')
    return redirect(url_for('main.subject_library'))


@main.route('/subjects/library/archive/<int:id>', methods=['POST'])
def library_archive_subject(id):
    try:
        entry = SubjectLibrary.query.get_or_404(id)
        entry.is_active = False
        db.session.commit()
        flash(f'Library subject "{entry.name}" archived — hidden from subject pickers; '
              'existing class subjects and their marks are unchanged.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error archiving library subject: {str(e)}', 'danger')
    return redirect(url_for('main.subject_library'))


@main.route('/subjects/library/restore/<int:id>', methods=['POST'])
def library_restore_subject(id):
    try:
        entry = SubjectLibrary.query.get_or_404(id)
        entry.is_active = True
        db.session.commit()
        flash(f'Library subject "{entry.name}" restored — it can be assigned to classes again.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring library subject: {str(e)}', 'danger')
    return redirect(url_for('main.subject_library'))


@main.route('/subjects/library/default/<int:id>', methods=['POST'])
def library_toggle_default(id):
    try:
        entry = SubjectLibrary.query.get_or_404(id)
        if not entry.is_active:
            flash('Restore this subject before marking it as a default for new classes.', 'warning')
            return redirect(url_for('main.subject_library'))
        entry.is_default = not entry.is_default
        db.session.commit()
        if entry.is_default:
            flash(f'"{entry.name}" is now pre-selected when creating a new class.', 'success')
        else:
            flash(f'"{entry.name}" is no longer pre-selected when creating a new class.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating library subject: {str(e)}', 'danger')
    return redirect(url_for('main.subject_library'))

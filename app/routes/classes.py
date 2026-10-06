from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash,
    send_file,
    current_app
)

from flask_login import current_user
from app.database import db
from app.models import (ClassModel, SectionModel, SubjectModel, TeacherModel,
                       StudentModel, TestModel, TimetableSlot)
from app.routes import main

# ==========================================
# CLASS, SECTION, & SUBJECT MANAGEMENT
# ==========================================
TIMETABLE_DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')


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
    return render_template('classes.html', classes=classes,
                           active_student_count=active_student_count,
                           section_count=section_count,
                           active_subject_count=active_subject_count,
                           fee_unset_count=fee_unset_count,
                           teachers=teachers,
                           subject_test_counts=subject_test_counts)

@main.route('/classes/add', methods=['POST'])
def add_class():
    try:
        class_name = request.form.get('class_name').strip()
        existing = ClassModel.query.filter_by(name=class_name).first()
        if existing:
            flash(f'Class "{class_name}" already exists.', 'danger')
            return redirect(url_for('main.classes_list'))
            
        fee_value = _parse_class_fee(request.form)
        new_class = ClassModel(name=class_name, monthly_fee=fee_value)
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


@main.route('/classes/<int:id>/timetable', methods=['GET', 'POST'])
def class_timetable(id):
    """Template-based, fully editable Mon-Sat timetable with period timings and PDF export."""
    from app.services import timetable as tt
    from app.services.audit import log_action

    class_obj = ClassModel.query.get_or_404(id)
    subjects = [s for s in class_obj.subjects if s.is_active]
    subject_lookup = {s.id: s for s in class_obj.subjects}
    day_count = len(TIMETABLE_DAYS)

    if request.method == 'POST':
        if not current_user.is_admin:
            flash('Only administrators can edit the timetable.', 'danger')
            return redirect(url_for('main.class_timetable', id=id))

        action = request.form.get('action') or 'save'

        # ---- Quick setup from a ready-made template (everything stays editable) ----
        if action == 'generate':
            template_key = request.form.get('template') or 'standard'
            if template_key not in tt.TEMPLATES:
                template_key = 'standard'
            start = tt.clean_time(request.form.get('start_time'))
            if not start:
                flash('Please enter a valid school start time.', 'danger')
                return redirect(url_for('main.class_timetable', id=id))
            rows = tt.number_rows(tt.build_rows(template_key, start, request.form.get('minutes')))
            TimetableSlot.query.filter_by(class_id=id).delete()
            filled = 0
            if request.form.get('autofill') == '1':
                lessons = sum(1 for r in rows if r['kind'] == 'period')
                for (day, period), subject_id in tt.autofill_pairs(
                        [s.id for s in subjects], lessons, day_count).items():
                    db.session.add(TimetableSlot(class_id=id, day_of_week=day,
                                                 period_no=period, subject_id=subject_id))
                    filled += 1
            tt.save_config(id, rows, template_key=template_key, keep_incharge=True)
            log_action('timetable_update', entity_type='ClassModel', entity_id=id,
                       summary=f'Timetable generated from template "{template_key}" for {class_obj.name}')
            db.session.commit()
            flash('Timetable generated from the template. Review it below and change anything you like, '
                  'then press Save.' if filled else
                  'Period timings generated. Choose subjects for each cell below, then press Save.',
                  'success')
            return redirect(url_for('main.class_timetable', id=id))

        # ---- Save manual edits: timings, breaks, subjects, in-charge ----
        try:
            row_count = int(request.form.get('row_count') or 0)
        except ValueError:
            row_count = 0
        row_count = max(0, min(row_count, tt.MAX_ROWS))

        rows = []
        for i in range(row_count):
            kind = 'break' if request.form.get('row_kind_%d' % i) == 'break' else 'period'
            start = tt.clean_time(request.form.get('row_start_%d' % i))
            end = tt.clean_time(request.form.get('row_end_%d' % i))
            if start is None or end is None:
                flash('Please enter times in a valid format (e.g. 08:30).', 'danger')
                return redirect(url_for('main.class_timetable', id=id))
            if start and end and tt._to_minutes(end) <= tt._to_minutes(start):
                flash('A period/break ends before it starts - please check the times.', 'danger')
                return redirect(url_for('main.class_timetable', id=id))
            rows.append({'kind': kind, 'start': start, 'end': end,
                         'label': (request.form.get('row_label_%d' % i) or '').strip()[:30]})
        tt.number_rows(rows)
        if sum(1 for r in rows if r['kind'] == 'period') > tt.MAX_PERIODS:
            flash('A day can have at most %d lesson periods.' % tt.MAX_PERIODS, 'danger')
            return redirect(url_for('main.class_timetable', id=id))

        existing = TimetableSlot.query.filter_by(class_id=id).all()
        valid_ids = {s.id for s in subjects} | {slot.subject_id for slot in existing if slot.subject_id}
        new_slots = []
        for i, row in enumerate(rows):
            if row['kind'] == 'break':
                continue
            for day in range(day_count):
                raw = (request.form.get('slot_%d_%d' % (day, i)) or '').strip()
                try:
                    subject_id = int(raw) if raw else None
                except ValueError:
                    subject_id = None
                if subject_id in valid_ids:
                    new_slots.append((day, row['no'], subject_id))

        TimetableSlot.query.filter_by(class_id=id).delete()
        db.session.flush()
        for day, period, subject_id in new_slots:
            db.session.add(TimetableSlot(class_id=id, day_of_week=day,
                                         period_no=period, subject_id=subject_id))

        raw_incharge = (request.form.get('incharge_teacher_id') or '').strip()
        try:
            incharge_id = int(raw_incharge) if raw_incharge else None
        except ValueError:
            incharge_id = None
        if incharge_id is not None and db.session.get(TeacherModel, incharge_id) is None:
            incharge_id = None
        tt.save_config(id, rows, incharge_id=incharge_id)

        log_action('timetable_update', entity_type='ClassModel', entity_id=id,
                   summary=f'Timetable updated for {class_obj.name}')
        db.session.commit()
        flash('Timetable saved.', 'success')
        return redirect(url_for('main.class_timetable', id=id))

    rows = tt.load_rows(id)
    slots = TimetableSlot.query.filter_by(class_id=id).all()
    grid = {(slot.day_of_week, slot.period_no): slot.subject_id for slot in slots}
    cfg = tt.get_config(id)
    incharge, incharge_auto = tt.resolve_incharge(class_obj, cfg)

    if request.args.get('pdf'):
        include_teachers = request.args.get('teachers') == '1'
        output = tt.build_timetable_pdf(class_obj, rows, grid, subject_lookup, incharge,
                                        include_teachers=include_teachers,
                                        root_path=current_app.root_path)
        log_action('export', entity_type='ClassModel', entity_id=id,
                   summary=f'Timetable PDF exported: {class_obj.name}')
        db.session.commit()
        safe_name = ''.join(ch if ch.isalnum() else '_' for ch in class_obj.name)
        return send_file(output, mimetype='application/pdf', as_attachment=True,
                         download_name='timetable_%s.pdf' % safe_name)

    teachers = (TeacherModel.query.filter_by(is_active=True)
                .order_by(TeacherModel.teacher_name).all())
    return render_template('class_timetable.html',
                           class_obj=class_obj,
                           subjects=subjects,
                           subject_lookup=subject_lookup,
                           days=TIMETABLE_DAYS,
                           rows=rows,
                           grid=grid,
                           teachers=teachers,
                           incharge=incharge,
                           incharge_auto=incharge_auto,
                           explicit_incharge_id=(cfg.incharge_teacher_id if cfg else None),
                           templates=tt.TEMPLATES,
                           default_start=tt.school_start_time(),
                           has_slots=bool(slots),
                           max_rows=tt.MAX_ROWS,
                           max_periods=tt.MAX_PERIODS)


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
        if 'teacher_id' in request.form:
            raw_teacher = (request.form.get('teacher_id') or '').strip()
            try:
                teacher_id = int(raw_teacher) if raw_teacher else None
            except ValueError:
                teacher_id = None
            if teacher_id is not None and db.session.get(TeacherModel, teacher_id) is None:
                teacher_id = None
            sub.teacher_id = teacher_id
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
        db.session.commit()
        flash(f'Subject "{sub.name}" restored in {sub.class_info.name if sub.class_info else "its class"} '
              '— it is available for new tests/exams again.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring subject: {str(e)}', 'danger')
    if request.form.get('next') == 'archived':
        return redirect(url_for('main.archived_subjects_list'))
    return redirect(url_for('main.classes_list'))
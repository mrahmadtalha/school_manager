"""Student list, add, edit, transfer, archive/restore and photo routes."""

from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash, send_file, abort, session
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from app.database import db
from app.models import StudentModel, ClassModel, SectionModel
from app.models.student import STUDENT_STATUSES, STUDENT_STATUS_LABELS
from app.routes import main
from app.services import record_view
from app.services import admission_fee, student_stock
from app.services import admission_numbers
from app.services.photos import photo_path, save_photo, stash_upload, delete_photo, PhotoError
from app.models.settings import get_custom_fields
from app.services.custom_fields import (
    collect_custom_field_values,
    has_custom_field_input,
    missing_required_custom_fields,
    prefixed_custom_values,
    serialize_custom_field_values,
)
from app.services.id_documents import default_academic_session
from app.services.enrollments import close_open_enrollment, start_enrollment, sync_open_enrollment
from app.services.roll_numbers import apply_shift_plan, cascade_shift_plan, parse_roll_number

from app.routes.students.helpers import (
    _apply_student_filters,
    _dues_balances,
    _parse_gender,
    _parse_optional_date,
    _render_students_page,
    _student_edit_map,
    _student_fee_values,
    _student_filters,
    _student_form_context,
    _student_sponsor_values,
)


@main.route('/students')
@main.route('/students/')
def students_list():
    filters = _student_filters()
    dues_ids = None
    if filters['has_dues']:
        dues_ids = [sid for sid, bal in _dues_balances().items() if bal > 0]
    query = _apply_student_filters(StudentModel.query, filters, dues_ids=dues_ids)
    students = query.order_by(StudentModel.student_name).all()
    dues_map = _dues_balances([s.id for s in students]) if students else {}
    sections = (SectionModel.query.filter_by(class_id=filters['class_id']).all()
                if filters['class_id'] else [])
    specs = record_view.field_specs('student')
    row_extras = {'dues_map': dues_map,
                  'admission_map': admission_fee.student_map(
                      [s.id for s in students])}
    display_map = {
        student.id: {spec.key: record_view.display_value(spec, student, row_extras)
                     for spec in specs}
        for student in students
    }
    return render_template(
        'students.html', students=students, sections=sections,
        dues_map=dues_map,
        selected_class=filters['class_id'], selected_section=filters['section_id'],
        search=filters['search'], selected_gender=filters['gender'],
        selected_status=filters['status'], has_dues=filters['has_dues'],
        student_field_specs=specs,
        display_map=display_map,
        edit_map=_student_edit_map(students),
        column_picker=record_view.picker_payload('student'),
        row_extras=row_extras,
        **_student_form_context())


@main.route('/students/add', methods=['POST'])
def add_student():
    payload = {field: (request.form.get(field) or '') for field in (
        'roll_number', 'student_name', 'father_name', 'guardian_phone',
        'address', 'class_id', 'section_id', 'monthly_fee',
        'discount_type', 'discount_value', 'date_of_birth',
        'gender', 'admission_number', 'admission_date', 'sponsor_type', 'sponsor_cnic', 'photo_token',
        'admission_fee', 'admission_discount_type', 'admission_discount_value',
        'admission_note', 'admission_received_now', 'admission_received_amount',
        'admission_method', 'books_taken', 'books_qty', 'uniform_qty')}
    custom_field_definitions = get_custom_fields('student')
    missing_fields = missing_required_custom_fields(request.form, custom_field_definitions)
    if missing_fields:
        flash('Complete required custom fields: ' + ', '.join(missing_fields), 'danger')
        return redirect(url_for('main.students_list'))
    custom_values = collect_custom_field_values(request.form, custom_field_definitions)
    payload.update(prefixed_custom_values(custom_values))
    try:
        roll_number = parse_roll_number(payload['roll_number'])
        class_id = int(payload['class_id'])
        class_obj = db.session.get(ClassModel, class_id)
        if class_obj is None:
            raise ValueError('Please choose a valid class.')

        class_fee, monthly_fee, discount_type, discount_value = _student_fee_values(payload)
        sponsor_type, sponsor_cnic = _student_sponsor_values(request.form)
        section_id = int(payload['section_id']) if payload['section_id'] else None
        if section_id:
            with db.session.no_autoflush:
                section_obj = db.session.get(SectionModel, section_id)
            if section_obj is None or section_obj.class_id != class_id:
                raise ValueError('The selected section does not belong to the chosen class.')

        conflict = StudentModel.query.filter_by(class_id=class_id,
                                                roll_number=roll_number).first()
        
        photo_stash_id = payload.get('photo_token')
        if not photo_stash_id:
            try:
                photo_stash_id = stash_upload(request.files.get('photo'))
            except PhotoError as e:
                flash(f'Photo ignored: {e}', 'warning')
                photo_stash_id = ''
        payload['photo_token'] = photo_stash_id

        if conflict and request.form.get('confirm_cascade') != '1':
            return _render_students_page(cascade_preview={
                'mode': 'add',
                'target': roll_number,
                'class_name': class_obj.name,
                'conflict_name': conflict.student_name,
                'plan': cascade_shift_plan(class_id, roll_number),
                'payload': payload,
            })

        if conflict:
            apply_shift_plan(cascade_shift_plan(class_id, roll_number))
            flash(f'Roll Number {roll_number} made free — existing students shifted up by one.', 'info')

        new_student = StudentModel(
            roll_number=roll_number,
            student_name=payload['student_name'],
            father_name=payload['father_name'],
            sponsor_type=sponsor_type,
            sponsor_cnic=sponsor_cnic,
            guardian_phone=payload['guardian_phone'],
            address=payload['address'],
            date_of_birth=_parse_optional_date(payload['date_of_birth']),
            gender=_parse_gender(payload['gender']),
            admission_number=None,                 # never typed: given below from the pattern
            admission_date=_parse_optional_date(payload['admission_date']),
            monthly_fee=monthly_fee,
            class_id=class_id,
            section_id=section_id,
            class_fee=class_fee,
            discount_type=discount_type,
            discount_value=discount_value,
            custom_fields_data=serialize_custom_field_values(custom_values),
        )
        
        try:
            photo_filename = save_photo('student', token=payload.get('photo_token'))
            new_student.photo_filename = photo_filename
        except PhotoError as e:
            flash(f'Photo ignored: {e}', 'warning')

        if admission_numbers.is_auto():          # automatic: given by the app, never typed
            new_student.admission_number = admission_numbers.next_number()
        db.session.add(new_student)
        start_enrollment(new_student, reason='enrolled', start_date=date.today(),
                         end_previous=False)
        # One-time admission fee (no-op until the school has set one). Only an
        # administrator can change the amount, give a concession or take the
        # money; for anyone else the standard fee is recorded as pending.
        admission = admission_fee.apply_on_admission(
            new_student, request.form, current_user,
            can_manage=admission_fee.is_admin(current_user))
        notice = None
        if admission:
            receipt = admission['receipt']
            if receipt is not None:
                notice = {'receipt_id': receipt.id, 'receipt_no': receipt.receipt_no,
                          'amount': admission_fee.money(receipt.amount_paisa),
                          'student': new_student.student_name}
            else:
                pending = admission_fee.summary(new_student)['balance']
        # Inventory (Phase 3): books / uniform taken at admission come out of
        # stock by themselves (price 0 - the money is in the admission fee).
        stock_messages = student_stock.sync_student_stock(
            new_student, actor=current_user, new_admission=True,
            issue_date=new_student.admission_date or date.today())
        db.session.commit()
        flash('Student added successfully!', 'success')
        for category, text in stock_messages:
            flash(text, category)
        if notice:
            session['admission_notice'] = notice
        elif admission and pending:
            flash('Admission fee / books / uniform %s is pending for this student. '
                  'It can be received from Admission Fees.' % admission_fee.money(pending), 'info')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    except IntegrityError:
        db.session.rollback()
        flash('That roll number was just taken by another save. Please reload and try again.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding student: {str(e)}', 'danger')

    return redirect(url_for('main.students_list'))


@main.route('/students/edit/<int:id>', methods=['POST'])
def edit_student(id):
    student = StudentModel.query.get_or_404(id)
    previous_class_id = student.class_id
    payload = {field: (request.form.get(field) or '') for field in (
        'roll_number', 'student_name', 'father_name', 'guardian_phone',
        'address', 'class_id', 'section_id', 'monthly_fee',
        'discount_type', 'discount_value', 'date_of_birth',
        'gender', 'admission_number', 'admission_date', 'sponsor_type', 'sponsor_cnic', 'photo_token')}
    custom_field_definitions = get_custom_fields('student')
    missing_fields = missing_required_custom_fields(request.form, custom_field_definitions)
    if missing_fields:
        flash('Complete required custom fields: ' + ', '.join(missing_fields), 'danger')
        return redirect(url_for('main.students_list'))
    custom_values = collect_custom_field_values(request.form, custom_field_definitions)
    payload.update(prefixed_custom_values(custom_values))
    try:
        roll_number = parse_roll_number(payload['roll_number'])
        class_id = int(payload['class_id'])
        class_obj = db.session.get(ClassModel, class_id)
        if class_obj is None:
            raise ValueError('Please choose a valid class.')

        conflict = StudentModel.query.filter(
            StudentModel.class_id == class_id,
            StudentModel.roll_number == roll_number,
            StudentModel.id != student.id,
        ).first()
        
        photo_stash_id = payload.get('photo_token')
        if not photo_stash_id:
            try:
                photo_stash_id = stash_upload(request.files.get('photo'))
            except PhotoError as e:
                flash(f'Photo ignored: {e}', 'warning')
                photo_stash_id = ''
        payload['photo_token'] = photo_stash_id
        
        if conflict and request.form.get('confirm_cascade') != '1':
            return _render_students_page(cascade_preview={
                'mode': 'edit',
                'student_id': student.id,
                'target': roll_number,
                'class_name': class_obj.name,
                'conflict_name': conflict.student_name,
                'plan': cascade_shift_plan(class_id, roll_number,
                                           exclude_student_id=student.id),
                'payload': payload,
            })

        if conflict:
            plan = cascade_shift_plan(class_id, roll_number, exclude_student_id=student.id)
            student.roll_number = -student.id  # vacate temporarily; keeps the constraint satisfied
            db.session.flush()
            apply_shift_plan(plan)
            flash(f'Roll Number {roll_number} made free — existing students shifted up by one.', 'info')

        student.roll_number = roll_number
        student.student_name = payload['student_name']
        student.father_name = payload['father_name']
        student.guardian_phone = payload['guardian_phone']
        student.address = payload['address']
        student.date_of_birth = _parse_optional_date(payload['date_of_birth'])
        student.gender = _parse_gender(payload['gender'])
        with db.session.no_autoflush:            # (a query here must not flush half an edit)
            # Never typed: a number on record stays; a blank one gets the next (auto ON).
            student.admission_number = admission_numbers.resolve_on_edit(
                student.admission_number, payload['admission_number'])
        student.admission_date = _parse_optional_date(payload['admission_date'])
        student.class_id = class_id
        section_id = int(payload['section_id']) if payload['section_id'] else None
        if section_id:
            with db.session.no_autoflush:
                section_obj = db.session.get(SectionModel, section_id)
            if section_obj is None or section_obj.class_id != class_id:
                raise ValueError('The selected section does not belong to the chosen class.')
        student.section_id = section_id

        fee_input = payload['monthly_fee']
        sponsor_type, sponsor_cnic = _student_sponsor_values(request.form, existing=student)
        student.sponsor_type = sponsor_type
        student.sponsor_cnic = sponsor_cnic
        if 'discount_type' in request.form or 'discount_value' in request.form:
            class_fee, monthly_fee, discount_type, discount_value = _student_fee_values(payload)
            student.class_fee = class_fee
            student.discount_type = discount_type
            student.discount_value = discount_value
            student.monthly_fee = monthly_fee
        else:
            # Legacy submission without discount inputs: keep the stored discount
            # data and treat the posted fee as the net monthly fee (previous behavior).
            student.monthly_fee = float(fee_input) if fee_input.strip() else None

        if has_custom_field_input(request.form):
            student.custom_fields_data = serialize_custom_field_values(custom_values)

        if previous_class_id != student.class_id:
            start_enrollment(student, reason='class_change', start_date=date.today())
        else:
            sync_open_enrollment(student)

        if request.form.get('remove_photo') == '1':
            if student.photo_filename:
                delete_photo('student', student.photo_filename)
                student.photo_filename = None
        else:
            try:
                photo_filename = save_photo('student', token=payload.get('photo_token'))
                if photo_filename:
                    if student.photo_filename:
                        delete_photo('student', student.photo_filename)
                    student.photo_filename = photo_filename
            except PhotoError as e:
                flash(f'Photo ignored: {e}', 'warning')

        db.session.commit()
        flash('Student record updated successfully!', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    except IntegrityError:
        db.session.rollback()
        flash('That roll number conflicts with another student. Please reload and try again.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating student: {str(e)}', 'danger')

    return redirect(url_for('main.students_list'))


@main.route('/students/<int:id>/transfer-section', methods=['POST'])
def transfer_student_section(id):
    student = StudentModel.query.get_or_404(id)
    raw = (request.form.get('to_section_id') or '').strip()
    try:
        target_id = int(raw) if raw else None
    except ValueError:
        target_id = None

    target = None
    if target_id:
        with db.session.no_autoflush:
            target = db.session.get(SectionModel, target_id)
        if target is None or target.class_id != student.class_id:
            flash('That section is not available for this student\'s class.', 'danger')
            return redirect(url_for('main.classes_list'))

    new_section_id = target.id if target else None
    if student.section_id == new_section_id:
        flash('Student is already in that section.', 'info')
        return redirect(url_for('main.classes_list'))

    student.section_id = new_section_id
    db.session.commit()
    destination = target.name if target else 'unassigned'
    flash(f'{student.student_name} moved to section {destination}.', 'success')
    return redirect(url_for('main.classes_list'))


@main.route('/students/delete/<int:id>', methods=['POST'])
def delete_student(id):
    try:
        student = StudentModel.query.get_or_404(id)
        status = (request.form.get('status') or 'slc_issued').strip().lower()
        if status not in STUDENT_STATUSES or status == 'enrolled':
            status = 'slc_issued'
        reason = (request.form.get('leaving_reason') or '').strip() or None
        date_str = (request.form.get('leaving_date') or '').strip()
        leaving_date = None
        if date_str:
            try:
                leaving_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                leaving_date = None

        # When a student formally leaves (SLC Issued / Struck Off) the school
        # must record when and why — both are mandatory for those statuses.
        if status in ('slc_issued', 'struck_off') and (not reason or leaving_date is None):
            label = STUDENT_STATUS_LABELS.get(status, status)
            missing = []
            if leaving_date is None:
                missing.append('the leaving date')
            if not reason:
                missing.append('a leaving reason')
            flash(f'Cannot mark "{student.student_name}" as {label}: please provide '
                  + ' and '.join(missing) + '.', 'danger')
            return redirect(url_for('main.students_list'))

        student.is_active = False
        student.status = status
        student.leaving_reason = reason
        student.leaving_date = leaving_date or date.today()
        close_open_enrollment(student, end_date=student.leaving_date)
        db.session.commit()
        label = STUDENT_STATUS_LABELS.get(status, status)
        flash(f'"{student.student_name}" archived with status: {label}.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error archiving student: {str(e)}', 'danger')

    return redirect(url_for('main.students_list'))


@main.route('/students/archived')
def archived_students_list():
    archived = (StudentModel.query.filter_by(is_active=False)
                .order_by(StudentModel.leaving_date.desc(),
                          StudentModel.student_name).all())
    return render_template('archived_students.html', students=archived,
                           status_labels=STUDENT_STATUS_LABELS,
                           default_session=default_academic_session(),
                           today=date.today().isoformat())


@main.route('/students/restore/<int:id>', methods=['POST'])
def restore_student(id):
    try:
        student = StudentModel.query.get_or_404(id)
        student.is_active = True
        student.status = 'enrolled'
        start_enrollment(student, reason='restored', start_date=date.today())
        db.session.commit()
        flash(f'Student "{student.student_name}" has been restored to Enrolled status.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash(f'Cannot restore: Roll No {student.roll_number} is used by another student '
              'in this class. Edit one of the two roll numbers first.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring student: {str(e)}', 'danger')

    return redirect(url_for('main.archived_students_list'))


@main.route('/students/restore-all', methods=['POST'])
def restore_all_students():
    count = StudentModel.query.filter_by(is_active=False).update({'is_active': True})
    db.session.commit()
    flash(f'{count} student(s) restored successfully.', 'success')
    return redirect(url_for('main.archived_students_list'))


@main.route('/students/<int:id>/photo')
def student_photo(id):
    student = StudentModel.query.get_or_404(id)
    if not student.photo_filename:
        abort(404)
    path = photo_path('student', student.photo_filename)
    if not path:
        abort(404)
    return send_file(path, mimetype='image/jpeg')

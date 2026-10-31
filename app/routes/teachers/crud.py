"""Teacher list, profile, add, edit and delete."""

import json
import re
from datetime import datetime, date
from app.timeutil import utcnow
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.database import db
from app.models import TeacherModel, SubjectModel, ClassModel
from app.models.attendance import AttendanceModel
from app.routes import main
from app.services.photos import save_photo, delete_photo, PhotoError
from app.models.settings import get_custom_fields
from app.services import record_view
from app.services.custom_fields import (
    collect_custom_field_values,
    has_custom_field_input,
    missing_required_custom_fields,
    parse_custom_fields_json,
    serialize_custom_field_values,
)


def _optional_str(value):
    value = (value or '').strip()
    return value or None


def _optional_float(value, label):
    raw = (value or '').strip().replace(',', '')
    if not raw:
        return None
    try:
        return round(float(raw), 2)
    except ValueError:
        raise ValueError(f'{label} must be a number.')


def _optional_date(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _multi_values(form, field):
    """Selected values for a multi-select, de-duplicated and order-preserving."""
    seen = set()
    values = []
    for raw in form.getlist(field):
        value = (raw or '').strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _assigned_classes_from_form(form):
    """Return (list, joined) for the assigned classes.

    Multi-select posts ``assigned_classes`` (with a hidden companion field so
    the key is always present); the legacy single ``assigned_class`` field is
    still honoured so cached pages keep working.
    """
    if 'assigned_classes' in form:
        values = _multi_values(form, 'assigned_classes')
    else:
        single = (form.get('assigned_class') or '').strip()
        values = [single] if single else []
    return values, (', '.join(values) if values else None)


def _teacher_assignment_views(teachers):
    """Robust per-teacher class/subject assignment view (JSON + legacy fallback)."""
    views = {}
    for teacher in teachers:
        classes = []
        if teacher.assigned_classes:
            try:
                data = json.loads(teacher.assigned_classes)
                if isinstance(data, list):
                    classes = [str(item).strip() for item in data if str(item).strip()]
            except (TypeError, ValueError):
                classes = []
        if not classes and teacher.assigned_class:
            classes = [part.strip() for part in str(teacher.assigned_class).split(',')
                       if part.strip()]
        subjects = []
        if teacher.assigned_subjects:
            try:
                data = json.loads(teacher.assigned_subjects)
                if isinstance(data, list):
                    subjects = [str(item).strip() for item in data if str(item).strip()]
            except (TypeError, ValueError):
                subjects = []
        views[teacher.id] = {'classes': classes, 'subjects': subjects}
    return views


# Teacher page: designation -> colour group (drives the card edge colour and the mix bar).
_DESIGNATION_GROUPS = (
    ('lead', 'Leadership', ('Principal', 'Vice Principal')),
    ('senior', 'Senior staff', ('Head Teacher', 'Senior Teacher')),
    ('teach', 'Teachers', ('Teacher',)),
    ('admin', 'Admin staff', ('Admin Staff',)),
    ('other', 'Other / not set', ()),
)


_TODAY_STATES = ('Present', 'Late', 'Leave', 'Absent')


def _designation_group(designation):
    for key, _label, names in _DESIGNATION_GROUPS:
        if designation in names:
            return key
    return 'other'


def _staff_overview(teachers, classes):
    """Numbers for the summary band and the per-teacher card state.

    * group mix of the teachers on screen,
    * today's staff attendance of the active teachers on screen,
    * how many classes have at least one active teacher (school-wide, so the
      figure does not change when the list is filtered).
    """
    group_of = {teacher.id: _designation_group(teacher.designation) for teacher in teachers}
    mix = []
    for key, label, _names in _DESIGNATION_GROUPS:
        count = sum(1 for value in group_of.values() if value == key)
        if count:
            mix.append({'key': key, 'label': label, 'count': count})

    active_ids = [teacher.id for teacher in teachers if teacher.is_active]
    today_of = {}
    if active_ids:
        rows = (AttendanceModel.query
                .filter(AttendanceModel.target_type == 'teacher',
                        AttendanceModel.date == date.today(),
                        AttendanceModel.target_id.in_(active_ids))
                .all())
        today_of = {row.target_id: row.status for row in rows if row.status in _TODAY_STATES}
    today = {state: sum(1 for value in today_of.values() if value == state)
             for state in _TODAY_STATES}
    today['marked'] = sum(today.values())
    today['expected'] = len(active_ids)
    today['not_marked'] = max(0, len(active_ids) - today['marked'])
    today['here'] = today['Present'] + today['Late']

    everyone = TeacherModel.query.filter_by(is_active=True).all()
    covered = set()
    for view in _teacher_assignment_views(everyone).values():
        covered.update(view['classes'])
    class_names = [item.name for item in classes]
    missing = [name for name in class_names if name not in covered]
    coverage = {'total': len(class_names), 'covered': len(class_names) - len(missing),
                'missing': missing}
    return {'group_of': group_of, 'mix': mix, 'today': today, 'today_of': today_of,
            'coverage': coverage}


def next_teacher_id():
    """Next free sequential teacher ID (T001, T002, ...) — always editable."""
    max_num = 0
    for (value,) in db.session.query(TeacherModel.teacher_id_str).all():
        match = re.fullmatch(r'[Tt](\d+)', (value or '').strip())
        if match:
            max_num = max(max_num, int(match.group(1)))
    return 'T%03d' % (max_num + 1)


# ==========================================
# TEACHER MANAGEMENT & EXPORTS
# ==========================================
@main.route('/teachers')
def teachers_list():
    search = request.args.get('search', '').strip()
    f_designation = request.args.get('designation', '').strip()
    f_gender = request.args.get('gender', '').strip()
    f_class = request.args.get('class_name', '').strip()
    f_status = (request.args.get('status', '') or 'active').strip().lower()
    if f_status not in ('active', 'archived', 'all'):
        f_status = 'active'

    query = TeacherModel.query
    if f_status == 'active':
        query = query.filter_by(is_active=True)
    elif f_status == 'archived':
        query = query.filter_by(is_active=False)

    if f_designation:
        query = query.filter(TeacherModel.designation == f_designation)
    if f_gender:
        query = query.filter(TeacherModel.gender == f_gender)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                TeacherModel.teacher_name.ilike(like),
                TeacherModel.teacher_id_str.ilike(like),
                TeacherModel.qualification.ilike(like),
                TeacherModel.assigned_class.ilike(like),
                TeacherModel.cnic.ilike(like),
            )
        )
    teachers = query.order_by(TeacherModel.teacher_name).all()

    assignment_map = _teacher_assignment_views(teachers)
    if f_class:
        teachers = [t for t in teachers
                    if f_class in assignment_map.get(t.id, {}).get('classes', [])]

    classes = ClassModel.query.all()
    subjects = [row[0] for row in db.session.query(SubjectModel.name)
                .distinct().order_by(SubjectModel.name).all()]
    designation_options = sorted(
        {row[0] for row in db.session.query(TeacherModel.designation).all() if row[0]}
        | {'Principal', 'Vice Principal', 'Head Teacher', 'Senior Teacher',
           'Teacher', 'Admin Staff', 'Other'})
    specs = record_view.field_specs('teacher')
    row_extras = {'assignment_map': assignment_map}
    teacher_display_map = {
        teacher.id: {spec.key: record_view.display_value(spec, teacher, row_extras)
                     for spec in specs}
        for teacher in teachers
    }
    overview = _staff_overview(teachers, classes)
    return render_template('teachers.html', teachers=teachers, classes=classes, search=search,
                           subjects=subjects, overview=overview,
                           filters={'designation': f_designation, 'gender': f_gender,
                                    'class_name': f_class, 'status': f_status},
                           assignment_map=assignment_map,
                           designation_options=designation_options,
                           teacher_custom_fields=get_custom_fields('teacher'),
                           teacher_field_specs=specs,
                           teacher_display_map=teacher_display_map,
                           column_picker=record_view.picker_payload('teacher'),
                           row_extras=row_extras,
                           next_teacher_id=next_teacher_id())


@main.route('/teachers/<int:id>')
def teacher_profile(id):
    teacher = TeacherModel.query.get_or_404(id)

    from app.services.payroll_service import (current_month_key, month_bounds,
                                              month_label, shift_month, teacher_month_stats)
    from app.services.whatsapp_automation import normalize_whatsapp_number
    from app.models.attendance import AttendanceModel
    from app.models.payroll import StaffPayroll

    month_key = (request.args.get('month') or '').strip() or current_month_key()
    start, end = month_bounds(month_key)
    current_key = current_month_key()
    if start is None or month_key > current_key:
        month_key = current_key
        start, end = month_bounds(month_key)

    stats = teacher_month_stats(teacher, month_key) or {
        'working_days': 0, 'marked_days': 0, 'present': 0,
        'absent': 0, 'late': 0, 'leave': 0}
    taken = stats['present'] + stats['absent'] + stats['late'] + stats['leave']
    stats['taken'] = taken
    stats['rate'] = round((stats['present'] / taken) * 100, 1) if taken else None

    att_records = (AttendanceModel.query
                   .filter(AttendanceModel.target_type == 'teacher',
                           AttendanceModel.target_id == teacher.id,
                           AttendanceModel.date >= start,
                           AttendanceModel.date <= end)
                   .order_by(AttendanceModel.date.desc())
                   .all())

    prev_month = shift_month(month_key, -1)
    next_month = shift_month(month_key, 1)
    can_next = bool(next_month) and next_month <= current_key

    tab = (request.args.get('tab') or 'overview').strip().lower()
    if tab not in ('overview', 'assignments', 'attendance', 'payroll', 'documents'):
        tab = 'overview'
    if tab == 'payroll' and not current_user.is_admin:
        tab = 'overview'

    payroll_rows = []
    if current_user.is_admin:
        rows = (StaffPayroll.query.filter_by(teacher_id=teacher.id)
                .order_by(StaffPayroll.month_year.desc()).all())
        payroll_rows = [{'record': row, 'label': month_label(row.month_year)} for row in rows]

    cur_stats = stats if month_key == current_key else (teacher_month_stats(teacher, current_key) or {})
    cur_taken = (cur_stats.get('present', 0) + cur_stats.get('absent', 0)
                 + cur_stats.get('late', 0) + cur_stats.get('leave', 0))
    hero_rate = round((cur_stats.get('present', 0) / cur_taken) * 100, 1) if cur_taken else None

    assignments = _teacher_assignment_views([teacher])[teacher.id]

    teacher_custom_fields = get_custom_fields('teacher')
    custom_values = parse_custom_fields_json(teacher.custom_fields_data) or {}
    custom_display = []
    for field in teacher_custom_fields:
        value = custom_values.get(field.get('name'))
        if value not in (None, ''):
            custom_display.append((field.get('name'), value))

    wa_digits = normalize_whatsapp_number(teacher.contact_number or '')
    wa_link = ('https://wa.me/%s' % wa_digits) if wa_digits else None

    return render_template('teacher_profile.html',
                           teacher=teacher,
                           assignments=assignments,
                           month_key=month_key,
                           month_label=month_label(month_key),
                           prev_month=prev_month,
                           next_month=next_month,
                           can_next=can_next,
                           stats=stats,
                           att_records=att_records,
                           payroll_rows=payroll_rows,
                           teacher_custom_fields=teacher_custom_fields,
                           custom_display=custom_display,
                           wa_link=wa_link,
                           hero_rate=hero_rate,
                           tab=tab)


@main.route('/teachers/add', methods=['POST'])
def add_teacher():
    try:
        teacher_id_str = (request.form.get('teacher_id_str') or '').strip() or next_teacher_id()
        teacher_name = request.form.get('teacher_name')
        joining_date_str = request.form.get('joining_date')
        joining_date = datetime.strptime(joining_date_str, '%Y-%m-%d') if joining_date_str else utcnow()
        qualification = request.form.get('qualification')
        salary_type = request.form.get('salary_type', 'monthly').strip().lower()
        monthly_salary = float(request.form.get('monthly_salary') or 0)
        hourly_rate = float(request.form.get('hourly_rate') or 0)
        salary = float(request.form.get('salary') or 0)
        if salary_type == 'hourly':
            hourly_rate = float(request.form.get('hourly_rate') or salary or 0)
            monthly_salary = 0.0
            salary = hourly_rate
        else:
            monthly_salary = float(request.form.get('monthly_salary') or salary or 0)
            hourly_rate = 0.0
            salary = monthly_salary
        assigned_classes, assigned_class_joined = _assigned_classes_from_form(request.form)
        assigned_subjects = _multi_values(request.form, 'assigned_subjects')
        custom_field_definitions = get_custom_fields('teacher')
        missing_fields = missing_required_custom_fields(request.form, custom_field_definitions)
        if missing_fields:
            raise ValueError('Complete required custom fields: ' + ', '.join(missing_fields))
        custom_values = collect_custom_field_values(request.form, custom_field_definitions)

        existing_teacher = TeacherModel.query.filter_by(teacher_id_str=teacher_id_str).first()
        if existing_teacher:
            flash(f'Error: Teacher ID "{teacher_id_str}" already exists.', 'danger')
            return redirect(url_for('main.teachers_list'))

        new_teacher = TeacherModel(
            teacher_id_str=teacher_id_str,
            teacher_name=teacher_name,
            joining_date=joining_date,
            qualification=qualification,
            salary=salary,
            salary_type=salary_type,
            monthly_salary=monthly_salary,
            hourly_rate=hourly_rate,
            assigned_class=assigned_class_joined,
            assigned_classes=json.dumps(assigned_classes) if assigned_classes else None,
            assigned_subjects=json.dumps(assigned_subjects) if assigned_subjects else None,
            cnic=_optional_str(request.form.get('cnic')),
            designation=_optional_str(request.form.get('designation')),
            gender=_optional_str(request.form.get('gender')),
            address=_optional_str(request.form.get('address')),
            contact_number=_optional_str(request.form.get('contact_number')),
            emergency_contact_number=_optional_str(request.form.get('emergency_contact_number')),
            previous_experience_years=_optional_float(request.form.get('previous_experience_years'), 'Previous experience'),
            previous_salary=_optional_float(request.form.get('previous_salary'), 'Previous salary'),
            date_of_birth=_optional_date(request.form.get('date_of_birth')),
            custom_fields_data=serialize_custom_field_values(custom_values),
        )
        try:
            photo_filename = save_photo('teacher', request.files.get('photo'))
            new_teacher.photo_filename = photo_filename
        except PhotoError as e:
            flash(f'Photo ignored: {e}', 'warning')
        db.session.add(new_teacher)
        db.session.commit()
        flash('Teacher added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding teacher: {str(e)}', 'danger')

    return redirect(url_for('main.teachers_list'))


@main.route('/teachers/edit/<int:id>', methods=['POST'])
def edit_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        custom_field_definitions = get_custom_fields('teacher')
        missing_fields = missing_required_custom_fields(request.form, custom_field_definitions)
        if missing_fields:
            raise ValueError('Complete required custom fields: ' + ', '.join(missing_fields))
        teacher.teacher_id_str = request.form.get('teacher_id_str').strip()
        teacher.teacher_name = request.form.get('teacher_name')
        
        joining_date_str = request.form.get('joining_date')
        if joining_date_str:
            teacher.joining_date = datetime.strptime(joining_date_str, '%Y-%m-%d')
            
        teacher.qualification = request.form.get('qualification')
        teacher.salary_type = request.form.get('salary_type', teacher.salary_type or 'monthly').strip().lower()
        teacher.monthly_salary = float(request.form.get('monthly_salary') or 0)
        teacher.hourly_rate = float(request.form.get('hourly_rate') or 0)
        salary = float(request.form.get('salary') or 0)
        if teacher.salary_type == 'hourly':
            teacher.hourly_rate = float(request.form.get('hourly_rate') or salary or 0)
            teacher.monthly_salary = 0.0
            teacher.salary = teacher.hourly_rate
        else:
            teacher.monthly_salary = float(request.form.get('monthly_salary') or salary or 0)
            teacher.hourly_rate = 0.0
            teacher.salary = teacher.monthly_salary
        assigned_classes, assigned_class_joined = _assigned_classes_from_form(request.form)
        teacher.assigned_class = assigned_class_joined
        teacher.assigned_classes = json.dumps(assigned_classes) if assigned_classes else None
        if 'assigned_subjects' in request.form:
            assigned_subjects = _multi_values(request.form, 'assigned_subjects')
            teacher.assigned_subjects = json.dumps(assigned_subjects) if assigned_subjects else None
        if any(key in request.form for key in ('cnic', 'contact_number', 'previous_experience_years', 'date_of_birth', 'designation', 'gender')):
            teacher.cnic = _optional_str(request.form.get('cnic'))
            if 'designation' in request.form:
                teacher.designation = _optional_str(request.form.get('designation'))
            if 'gender' in request.form:
                teacher.gender = _optional_str(request.form.get('gender'))
            teacher.address = _optional_str(request.form.get('address'))
            teacher.contact_number = _optional_str(request.form.get('contact_number'))
            teacher.emergency_contact_number = _optional_str(request.form.get('emergency_contact_number'))
            teacher.previous_experience_years = _optional_float(request.form.get('previous_experience_years'), 'Previous experience')
            teacher.previous_salary = _optional_float(request.form.get('previous_salary'), 'Previous salary')
            teacher.date_of_birth = _optional_date(request.form.get('date_of_birth'))

        if has_custom_field_input(request.form):
            teacher.custom_fields_data = serialize_custom_field_values(
                collect_custom_field_values(request.form, custom_field_definitions))

        if request.form.get('remove_photo') == '1':
            if teacher.photo_filename:
                delete_photo('teacher', teacher.photo_filename)
                teacher.photo_filename = None
        else:
            try:
                photo_filename = save_photo('teacher', request.files.get('photo'))
                if photo_filename:
                    if teacher.photo_filename:
                        delete_photo('teacher', teacher.photo_filename)
                    teacher.photo_filename = photo_filename
            except PhotoError as e:
                flash(f'Photo ignored: {e}', 'warning')

        db.session.commit()
        flash('Teacher record updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating teacher: {str(e)}', 'danger')

    return redirect(url_for('main.teachers_list'))


@main.route('/teachers/delete/<int:id>', methods=['POST'])
def delete_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        teacher.is_active = False
        db.session.commit()
        flash(f'Teacher "{teacher.teacher_name}" moved to archive safely.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting teacher: {str(e)}', 'danger')

    return redirect(url_for('main.teachers_list'))


@main.route('/teachers/archived')
def archived_teachers_list():
    archived = TeacherModel.query.filter_by(is_active=False).all()
    return render_template('archived_teachers.html', teachers=archived)


@main.route('/teachers/restore/<int:id>', methods=['POST'])
def restore_teacher(id):
    try:
        teacher = TeacherModel.query.get_or_404(id)
        teacher.is_active = True
        db.session.commit()
        flash(f'Teacher "{teacher.teacher_name}" has been restored successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring teacher: {str(e)}', 'danger')

    return redirect(url_for('main.archived_teachers_list'))


def _teacher_export_context():
    """Active teachers to export for the chosen columns (see the Students page)."""
    teachers = TeacherModel.query.filter_by(is_active=True).all()
    assignment_map = _teacher_assignment_views(teachers)
    specs = record_view.export_specs('teacher', request.args.get('cols'))
    return teachers, specs, {'assignment_map': assignment_map}

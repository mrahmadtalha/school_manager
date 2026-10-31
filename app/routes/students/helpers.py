"""Student list filters, form helpers and shared student-page helpers."""

import re
from datetime import datetime, date
from flask import render_template, request, url_for, session
from flask_login import current_user
from markupsafe import Markup
from app.database import db
from app.models import StudentModel, ClassModel, FeeRecordModel
from app.routes import main
from sqlalchemy import func
from app.services import record_view
from app.services import admission_fee
from app.services import admission_numbers
from app.models.settings import get_custom_fields
from app.services.custom_fields import parse_custom_fields_json
from app.services.roll_numbers import FIRST_ROLL_NUMBER, next_roll_map


# STUDENT MANAGEMENT & EXPORTS
# ==========================================
def _student_filters():
    """Read the students list filters from the request."""
    gender = (request.args.get('gender') or '').strip()
    if gender not in ('Male', 'Female', 'Other'):
        gender = ''
    status = (request.args.get('status') or '').strip()
    if status not in ('all', 'enrolled', 'slc_issued', 'graduated', 'struck_off'):
        status = ''
    return {
        'class_id': request.args.get('class_id', type=int),
        'section_id': request.args.get('section_id', type=int),
        'search': (request.args.get('search') or '').strip(),
        'gender': gender,
        'status': status,
        'has_dues': request.args.get('has_dues') == '1',
    }


def _apply_student_filters(query, filters, dues_ids=None):
    if filters['class_id']:
        query = query.filter(StudentModel.class_id == filters['class_id'])
    if filters['section_id']:
        query = query.filter(StudentModel.section_id == filters['section_id'])
    if filters['gender']:
        query = query.filter(StudentModel.gender == filters['gender'])
    status = filters['status']
    if status in ('slc_issued', 'graduated', 'struck_off'):
        query = query.filter(StudentModel.status == status)
    elif status == 'enrolled':
        query = query.filter(StudentModel.is_active.is_(True),
                             StudentModel.status == 'enrolled')
    elif status == 'all':
        pass
    else:
        query = query.filter(StudentModel.is_active.is_(True))
    if filters['search']:
        like = '%' + filters['search'] + '%'
        query = query.filter(db.or_(
            StudentModel.student_name.ilike(like),
            db.cast(StudentModel.roll_number, db.String).ilike(like),
            StudentModel.father_name.ilike(like),
            StudentModel.guardian_phone.ilike(like),
            StudentModel.admission_number.ilike(like),
        ))
    if filters['has_dues'] and dues_ids is not None:
        query = query.filter(StudentModel.id.in_(dues_ids or [-1]))
    return query


def _dues_balances(student_ids=None):
    """Live pending dues per student from the fee records (max(0, due - paid))."""
    query = db.session.query(
        FeeRecordModel.student_id,
        func.coalesce(func.sum(func.max(
            FeeRecordModel.amount_due_paisa - FeeRecordModel.amount_paid_paisa, 0)), 0.0))
    if student_ids is not None:
        if not student_ids:
            return {}
        query = query.filter(FeeRecordModel.student_id.in_(student_ids))
    query = query.group_by(FeeRecordModel.student_id)
    return {sid: round(float(value or 0) / 100.0, 2) for sid, value in query.all()}


def _parse_gender(value):
    value = (value or '').strip()
    return value if value in ('Male', 'Female', 'Other') else None


def _parse_optional_date(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _student_sponsor_values(form, existing=None):
    sponsor_type = (form.get('sponsor_type') or
                    (existing.sponsor_type if existing else 'Father') or 'Father').strip()
    if sponsor_type not in {'Father', 'Guardian'}:
        raise ValueError('Choose Father or Guardian as the sponsor type.')

    raw_cnic = form.get('sponsor_cnic')
    sponsor_cnic = (raw_cnic if raw_cnic is not None else
                    ((existing.sponsor_cnic if existing else '') or '')).strip()
    if sponsor_cnic and not re.fullmatch(r'\d{5}-\d{7}-\d', sponsor_cnic):
        raise ValueError('CNIC must use the format 12345-1234567-1.')
    return sponsor_type, sponsor_cnic or None


def _student_form_context():
    """Render context shared by the students page and the cascade preview."""
    classes = ClassModel.query.all()
    sections_by_class = {
        str(class_obj.id): [
            {'id': section.id, 'name': section.name}
            for section in sorted(class_obj.sections, key=lambda s: s.name)
        ]
        for class_obj in classes
    }
    return {
        'classes': classes,
        'sections_by_class': sections_by_class,
        'next_roll_by_class': next_roll_map(),
        'first_roll_number': FIRST_ROLL_NUMBER,
        'student_custom_fields': get_custom_fields('student'),
        'class_fee_by_class': {str(class_obj.id): class_obj.monthly_fee
                               for class_obj in classes
                               if class_obj.monthly_fee is not None},
        'today': date.today().isoformat(),
        # Admission fee (opt-in: nothing shows until the school sets one).
        'admission_enabled': admission_fee.is_enabled(),
        'admission_manage': admission_fee.is_admin(current_user),
        'admission_fee_by_class': admission_fee.fee_by_class(),
        'admission_items_by_class': admission_fee.items_by_class(),
        'auto_admission_number': admission_numbers.is_auto(),
        'next_admission_number': admission_numbers.next_number(),
        # Administrator only: students with no Admission No can be numbered in one click.
        'missing_admission_count': (admission_numbers.count_missing()
                                    if getattr(current_user, 'role', '') == 'admin' else 0),
        'admission_notice': session.pop('admission_notice', None),
    }


_NEWLINE_WS = re.compile(r'\s*\n\s*')


@main.app_template_filter('collapse_ws')
def collapse_ws(html):
    """Squeeze template indentation/newlines to single spaces.

    HTML already renders any whitespace run containing a newline as one space,
    so the page looks identical; the table rows are just ~60% smaller on the
    wire (indentation was most of each row).  Used by students.html.
    """
    return Markup(_NEWLINE_WS.sub(' ', str(html)))


def _num_text(value):
    """Number as the form field text, e.g. 3500.0 (same text the old modals showed)."""
    return '' if value is None or value == '' else str(value)


def _student_edit_map(students):
    """Per-student values for the shared Edit / Archive modals on the list page.

    The page used to render a full Edit modal and an Archive modal for EVERY
    student (about 27 KB of HTML each, thousands of hidden forms for a large
    school).  It now renders one Edit modal and one Archive modal and fills
    them from this small JSON map when a row's button is clicked, so the page
    size no longer depends on the number of modals.  Values mirror exactly what
    the old per-student modals pre-filled.
    """
    result = {}
    for student in students:
        if student.class_fee is not None:
            fee = student.class_fee
        else:
            fee = student.monthly_fee if student.monthly_fee else ''
        result[str(student.id)] = {
            'name': student.student_name,
            'roll': student.roll_number,
            'class_id': student.class_id,
            'section_id': student.section_id,
            'sponsor_type': student.sponsor_type or 'Father',
            'father_name': student.father_name,
            'cnic': student.sponsor_cnic or '',
            'fee': _num_text(fee),
            'discount_type': student.discount_type or 'percentage',
            'discount_value': _num_text(student.discount_value
                                        if student.discount_value is not None else 0),
            'phone': student.guardian_phone,
            'address': student.address,
            'dob': student.date_of_birth.isoformat() if student.date_of_birth else '',
            'gender': student.gender or '',
            'admission_number': student.admission_number or '',
            'admission_date': (student.admission_date.isoformat()
                               if student.admission_date else ''),
            'custom': parse_custom_fields_json(student.custom_fields_data),
            'photo': (url_for('main.student_photo', id=student.id,
                              v=student.photo_filename)
                      if student.photo_filename else ''),
            'edit_url': url_for('main.edit_student', id=student.id),
            'archive_url': url_for('main.delete_student', id=student.id),
        }
    return result


def _render_students_page(**extra):
    """Render the students page with default filters plus ``extra`` context.

    Used to answer a conflicting add/edit with a confirmation preview instead
    of a redirect.
    """
    context = _student_form_context()
    listed = (StudentModel.query.filter_by(is_active=True)
              .order_by(StudentModel.student_name).all())
    dues_map = _dues_balances([s.id for s in listed])
    specs = record_view.field_specs('student')
    row_extras = {'dues_map': dues_map,
                  'admission_map': admission_fee.student_map(
                      [s.id for s in listed])}
    context.update({
        'students': listed,
        'sections': [],
        'selected_class': None,
        'selected_section': None,
        'search': '',
        'dues_map': dues_map,
        'selected_gender': '',
        'selected_status': '',
        'has_dues': False,
        'student_field_specs': specs,
        'display_map': {
            student.id: {spec.key: record_view.display_value(spec, student, row_extras)
                         for spec in specs}
            for student in listed
        },
        'column_picker': record_view.picker_payload('student'),
        'edit_map': _student_edit_map(listed),
        'row_extras': row_extras,
    })
    context.update(extra)
    return render_template('students.html', **context)


def _student_fee_values(payload):
    """Return (class_fee, net_fee, discount_type, discount_value) for a student form.

    The posted fee is the class/base fee (auto-filled, editable); the discount
    is applied server-side to compute the persisted net monthly fee.
    """
    fee_input = (payload.get('monthly_fee') or '').strip()
    class_fee = float(fee_input) if fee_input else None
    if class_fee is not None and class_fee < 0:
        raise ValueError('Fee cannot be negative.')

    discount_type = (payload.get('discount_type') or '').strip().lower()
    if discount_type not in ('percentage', 'fixed'):
        discount_type = None

    raw_value = (payload.get('discount_value') or '').strip()
    try:
        discount_value = float(raw_value) if raw_value else 0.0
    except ValueError:
        raise ValueError('Please enter a valid discount value.')
    if discount_value < 0:
        discount_value = 0.0

    if class_fee is None or discount_value <= 0 or discount_type is None:
        return class_fee, class_fee, None, None

    if discount_type == 'percentage':
        net_fee = class_fee * (1.0 - discount_value / 100.0)
    else:
        net_fee = class_fee - discount_value
    return class_fee, round(max(0.0, net_fee), 2), discount_type, round(discount_value, 2)


def _import_admission_enabled():
    """Admission columns are offered to an administrator once a fee is set."""
    return admission_fee.is_enabled() and admission_fee.is_admin(current_user)

import io
import csv
import re
import pandas as pd
from datetime import datetime, date
from flask import (
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash, 
    send_file, 
    Response
)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.models import (
    StudentModel,
    ClassModel,
    SectionModel,
    AttendanceModel,
    TestModel,
    StudentMarkModel,
    FeeRecordModel,
    FeeTransaction,
    MessageQueue,
    GuardianStudentLink,
    StudentRemark,
    StudentEnrollment,
)
from app.models.student import STUDENT_STATUSES, STUDENT_STATUS_LABELS
from app.routes import main
from sqlalchemy import func
from app.services.audit import log_action, serialize
from app.models.settings import calculate_grade, get_custom_fields
from app.services.custom_fields import (
    collect_custom_field_values,
    has_custom_field_input,
    missing_required_custom_fields,
    prefixed_custom_values,
    serialize_custom_field_values,
)
from app.services.id_documents import default_academic_session
from app.services.enrollments import (
    close_open_enrollment,
    start_enrollment,
    sync_open_enrollment,
)
from app.services.roll_numbers import (
    FIRST_ROLL_NUMBER,
    apply_shift_plan,
    cascade_shift_plan,
    next_roll_map,
    parse_roll_number,
)


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
        ))
    if filters['has_dues'] and dues_ids is not None:
        query = query.filter(StudentModel.id.in_(dues_ids or [-1]))
    return query


def _dues_balances(student_ids=None):
    """Live pending dues per student from the fee records (max(0, due - paid))."""
    query = db.session.query(
        FeeRecordModel.student_id,
        func.coalesce(func.sum(func.max(
            FeeRecordModel.amount_due - FeeRecordModel.amount_paid, 0)), 0.0))
    if student_ids is not None:
        if not student_ids:
            return {}
        query = query.filter(FeeRecordModel.student_id.in_(student_ids))
    query = query.group_by(FeeRecordModel.student_id)
    return {sid: round(float(value or 0), 2) for sid, value in query.all()}


def _parse_gender(value):
    value = (value or '').strip()
    return value if value in ('Male', 'Female', 'Other') else None


def _parse_optional_date(value):
    value = (value or '').strip()
    if not value:
        return None


def _student_sponsor_values(form, existing=None):
    sponsor_type = (form.get('sponsor_type') or
                    (existing.sponsor_type if existing else 'Father') or 'Father').strip()
    if sponsor_type not in {'Father', 'Guardian'}:
        raise ValueError('Choose Father or Guardian as the sponsor type.')

    raw_cnic = form.get('sponsor_cnic')
    sponsor_cnic = (raw_cnic if raw_cnic is not None else
                    (existing.sponsor_cnic if existing else '')).strip()
    if sponsor_cnic and not re.fullmatch(r'\d{5}-\d{7}-\d', sponsor_cnic):
        raise ValueError('CNIC must use the format 12345-1234567-1.')
    return sponsor_type, sponsor_cnic or None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


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
    }


def _render_students_page(**extra):
    """Render the students page with default filters plus ``extra`` context.

    Used to answer a conflicting add/edit with a confirmation preview instead
    of a redirect.
    """
    context = _student_form_context()
    listed = (StudentModel.query.filter_by(is_active=True)
              .order_by(StudentModel.student_name).all())
    context.update({
        'students': listed,
        'sections': [],
        'selected_class': None,
        'selected_section': None,
        'search': '',
        'dues_map': _dues_balances([s.id for s in listed]),
        'selected_gender': '',
        'selected_status': '',
        'has_dues': False,
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
    return render_template(
        'students.html', students=students, sections=sections,
        dues_map=dues_map,
        selected_class=filters['class_id'], selected_section=filters['section_id'],
        search=filters['search'], selected_gender=filters['gender'],
        selected_status=filters['status'], has_dues=filters['has_dues'],
        **_student_form_context())

@main.route('/students/add', methods=['POST'])
def add_student():
    payload = {field: (request.form.get(field) or '') for field in (
        'roll_number', 'student_name', 'father_name', 'guardian_phone',
        'address', 'class_id', 'section_id', 'monthly_fee',
        'discount_type', 'discount_value', 'date_of_birth',
        'gender', 'admission_number', 'admission_date', 'sponsor_type', 'sponsor_cnic')}
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
            admission_number=(payload['admission_number'].strip()[:40] or None),
            admission_date=_parse_optional_date(payload['admission_date']),
            monthly_fee=monthly_fee,
            class_id=class_id,
            section_id=section_id,
            class_fee=class_fee,
            discount_type=discount_type,
            discount_value=discount_value,
            custom_fields_data=serialize_custom_field_values(custom_values),
        )
        db.session.add(new_student)
        start_enrollment(new_student, reason='enrolled', start_date=date.today(),
                         end_previous=False)
        db.session.commit()
        flash('Student added successfully!', 'success')
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
        'gender', 'admission_number', 'admission_date', 'sponsor_type', 'sponsor_cnic')}
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
        student.admission_number = payload['admission_number'].strip()[:40] or None
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

@main.route('/students/<int:id>/report')
def student_detailed_report(id):
    from app.models import TermExam
    from app.routes.term_exams import build_tabulation
    from app.services.fee_ledger import _month_sort_key
    from app.services.whatsapp_automation import normalize_whatsapp_number

    student = StudentModel.query.get_or_404(id)
    attendance_records = AttendanceModel.query.filter_by(target_type='student', target_id=student.id).order_by(AttendanceModel.date.desc()).all()
    marks = StudentMarkModel.query.filter_by(student_id=student.id).join(TestModel).order_by(TestModel.test_date.desc()).all()

    total_records = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == 'Present')
    absent_count = sum(1 for r in attendance_records if r.status == 'Absent')
    late_count = sum(1 for r in attendance_records if r.status == 'Late')
    leave_count = sum(1 for r in attendance_records if r.status == 'Leave')
    attendance_pct = round(present_count * 100.0 / total_records, 1) if total_records else 0.0

    overall_percentage = 0.0
    if marks:
        percentages = [m.percentage for m in marks if m.percentage is not None]
        overall_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
    overall_grade = calculate_grade(overall_percentage)

    summary = {
        'attendance_total': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'leave_count': leave_count,
        'attendance_pct': attendance_pct,
        'overall_percentage': overall_percentage,
        'overall_grade': overall_grade,
        'best_test': max(marks, key=lambda m: (m.percentage or 0)).test_info.test_title if marks else 'N/A',
    }

    enrollments = (StudentEnrollment.query.filter_by(student_id=student.id)
                   .order_by(StudentEnrollment.id).all())

    # Live dues + recent fee ledger (newest first)
    dues = _dues_balances([student.id]).get(student.id, 0.0)
    fee_rows = FeeRecordModel.query.filter_by(student_id=student.id).all()
    fee_rows.sort(key=lambda record: _month_sort_key(record.month_year), reverse=True)
    fee_recent = fee_rows[:12]

    # Recent term-exam results with positions (latest 4 exams of the class)
    term_results = []
    exams = (TermExam.query.filter_by(class_id=student.class_id)
             .order_by(TermExam.id.desc()).limit(4).all())
    for exam in exams:
        tests, rows, exam_summary = build_tabulation(exam)
        row = next((r for r in rows if r['student'].id == student.id), None)
        if row:
            term_results.append({'exam': exam, 'row': row,
                                 'total_max': exam_summary['total_max'],
                                 'complete': exam_summary['complete']})

    wa_digits = normalize_whatsapp_number(student.guardian_phone or '')
    wa_link = ('https://wa.me/%s' % wa_digits) if wa_digits else None

    return render_template('student_report.html',
                           student=student,
                           attendance_records=attendance_records,
                           marks=marks,
                           enrollments=enrollments,
                           summary=summary,
                           dues=dues,
                           fee_recent=fee_recent,
                           term_results=term_results,
                           wa_link=wa_link)

@main.route('/students/<int:id>/report/pdf')
def student_report_pdf(id):
    student = StudentModel.query.get_or_404(id)
    marks = StudentMarkModel.query.filter_by(student_id=student.id).join(TestModel).order_by(TestModel.test_date.asc()).all()
    attendance_records = AttendanceModel.query.filter_by(target_type='student', target_id=student.id).order_by(AttendanceModel.date.asc()).all()

    total_records = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == 'Present')
    absent_count = sum(1 for r in attendance_records if r.status == 'Absent')
    late_count = sum(1 for r in attendance_records if r.status == 'Late')
    leave_count = sum(1 for r in attendance_records if r.status == 'Leave')

    percentages = [m.percentage for m in marks if m.percentage is not None]
    overall_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0.0

    if overall_percentage >= 85:
        overall_grade = 'A+'
    elif overall_percentage >= 70:
        overall_grade = 'A'
    elif overall_percentage >= 60:
        overall_grade = 'B'
    elif overall_percentage >= 50:
        overall_grade = 'C'
    elif overall_percentage >= 40:
        overall_grade = 'D'
    else:
        overall_grade = 'F'

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=8, alignment=1, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#475569'), spaceAfter=12, alignment=1)
    label_style = ParagraphStyle('LabelStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), leading=12)

    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    school_name = school.school_name if school else 'School Management System'

    story.append(Paragraph(f"{school_name}", title_style))
    story.append(Paragraph('Student Performance Report Card', subtitle_style))
    story.append(Paragraph(f"<b>Student:</b> {student.student_name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Roll No:</b> {student.roll_number} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Class:</b> {student.class_info.name if student.class_info else 'N/A'} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Father:</b> {student.father_name}", label_style))

    metric_data = [
        ['Overall %', f'{overall_percentage}%'],
        ['Grade', overall_grade],
        ['Present', str(present_count)],
        ['Absent', str(absent_count)],
        ['Late', str(late_count)],
        ['Leave', str(leave_count)],
    ]
    metric_table = Table(metric_data, colWidths=[75, 65], rowHeights=28)
    metric_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('BACKGROUND', (0, 0), (0, 5), colors.HexColor('#dbeafe')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#dcfce7')),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#fef3c7')),
    ]))
    story.append(Spacer(1, 8))
    story.append(metric_table)
    story.append(Spacer(1, 12))

    table_data = [['Test', 'Type', 'Subject', 'Date', 'Obtained', '%', 'Grade']]
    for mark in marks:
        test = mark.test_info
        table_data.append([
            test.test_title if test else 'N/A',
            test.test_type if test else 'N/A',
            test.subject_info.name if test and test.subject_info else 'N/A',
            str(test.test_date) if test else 'N/A',
            str(mark.marks_obtained),
            f"{mark.percentage}%" if mark.percentage is not None else '—',
            mark.grade or '—'
        ])

    table = Table(table_data, colWidths=[110, 55, 80, 70, 55, 45, 45])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ]))
    story.append(table)
    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f'{student.roll_number}_{student.student_name}_result_card.pdf')

@main.route('/students/<int:id>/transcript.pdf')
def student_transcript_pdf(id):
    student = StudentModel.query.get_or_404(id)
    enrollments = (StudentEnrollment.query.filter_by(student_id=student.id)
                   .order_by(StudentEnrollment.id).all())
    marks = (StudentMarkModel.query.filter_by(student_id=student.id)
             .join(TestModel).order_by(TestModel.test_date.asc()).all())

    from flask import current_app
    from app.services.transcripts import build_transcript_pdf

    output = build_transcript_pdf(student, enrollments, marks, current_app.root_path)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'transcript_{student.roll_number}_{student.student_name}.pdf')

@main.route('/students/export/csv')
def export_students_csv():
    filters = _student_filters()
    dues_ids = ([sid for sid, bal in _dues_balances().items() if bal > 0]
                if filters['has_dues'] else None)
    students = (_apply_student_filters(StudentModel.query, filters,
                                       dues_ids=dues_ids)
                .order_by(StudentModel.student_name).all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll Number', 'Student Name', 'Father Name', 'Class', 'Section',
                     'Gender', 'Date of Birth', 'Admission No', 'Admission Date',
                     'Guardian Phone', 'Address', 'Status'])
    
    for s in students:
        class_name = s.class_info.name if s.class_info else 'N/A'
        section_name = s.section_info.name if s.section_info else 'N/A'
        writer.writerow([
            s.roll_number, s.student_name, s.father_name, class_name, section_name,
            s.gender or '', s.date_of_birth.isoformat() if s.date_of_birth else '',
            s.admission_number or '',
            s.admission_date.isoformat() if s.admission_date else '',
            s.guardian_phone, s.address, s.status])
    
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=students_report.csv"})

@main.route('/students/template/excel')
def students_template_excel():
    template_data = [{
        'Roll Number': '1001',
        'Student Name': 'Ali Khan',
        'Father Name': 'Ahmad Khan',
        'Class': 'Class 1',
        'Section': 'A',
        'Guardian Phone': '+923001234567',
        'Address': 'Main Bazaar, City'
    }]
    df = pd.DataFrame(template_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students Template')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='students_import_template.xlsx')


@main.route('/students/export/excel')
def export_students_excel():
    filters = _student_filters()
    dues_ids = ([sid for sid, bal in _dues_balances().items() if bal > 0]
                if filters['has_dues'] else None)
    students = (_apply_student_filters(StudentModel.query, filters,
                                       dues_ids=dues_ids)
                .order_by(StudentModel.student_name).all())
    data = [{
        'Roll Number': s.roll_number,
        'Student Name': s.student_name,
        'Father Name': s.father_name,
        'Class': s.class_info.name if s.class_info else 'N/A',
        'Section': s.section_info.name if s.section_info else 'N/A',
        'Gender': s.gender or '',
        'Date of Birth': s.date_of_birth.isoformat() if s.date_of_birth else '',
        'Admission No': s.admission_number or '',
        'Admission Date': s.admission_date.isoformat() if s.admission_date else '',
        'Guardian Phone': s.guardian_phone,
        'Address': s.address,
        'Status': s.status
    } for s in students]
    
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')
    output.seek(0)
    
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='students_report.xlsx')

@main.route('/students/export/pdf')
def export_students_pdf():
    filters = _student_filters()
    dues_ids = ([sid for sid, bal in _dues_balances().items() if bal > 0]
                if filters['has_dues'] else None)
    students = (_apply_student_filters(StudentModel.query, filters,
                                       dues_ids=dues_ids)
                .order_by(StudentModel.student_name).all())
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1a202c'), spaceAfter=15, alignment=1)
    
    story.append(Paragraph("School Management System — Student Report", title_style))
    story.append(Spacer(1, 10))
    
    table_data = [['Roll No', 'Student Name', 'Father Name', 'Class', 'Phone']]
    for s in students:
        table_data.append([str(s.roll_number), str(s.student_name), str(s.father_name), str(s.class_info.name if s.class_info else 'N/A'), str(s.guardian_phone)])
        
    t = Table(table_data, colWidths=[70, 130, 130, 80, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(t)
    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name='students_report.pdf')


@main.route('/students/import', methods=['POST'])
def import_students():
    import io
    file = request.files.get('import_file')
    if not file or not file.filename:
        flash('No file selected.', 'warning')
        return redirect(url_for('main.students_list'))

    ext = file.filename.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'csv':
            import csv as csv_module
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv_module.DictReader(stream)
            rows = list(reader)
        elif ext in ('xlsx', 'xls'):
            df = pd.read_excel(file)
            df.columns = df.columns.str.strip()
            rows = df.to_dict(orient='records')
        else:
            flash('Only .xlsx or .csv files are supported.', 'danger')
            return redirect(url_for('main.students_list'))
    except Exception as e:
        flash(f'Could not read file: {str(e)}', 'danger')
        return redirect(url_for('main.students_list'))

    class_map = {c.name.strip().lower(): c for c in ClassModel.query.all()}
    section_map = {}
    for sec in SectionModel.query.all():
        section_map[(sec.class_id, sec.name.strip().lower())] = sec

    added = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            roll     = str(row.get('Roll Number', '') or '').strip()
            name     = str(row.get('Student Name', '') or '').strip()
            father   = str(row.get('Father Name', '') or '').strip()
            cls_name = str(row.get('Class', '') or '').strip()
            sec_name = str(row.get('Section', '') or '').strip()
            phone    = str(row.get('Guardian Phone', '') or '').strip()
            address  = str(row.get('Address', '') or '').strip()

            if not roll or not name:
                errors.append(f'Row {i}: Roll Number or Student Name is empty — skipped.')
                skipped += 1
                continue

            try:
                roll_number = int(float(roll))
            except (TypeError, ValueError):
                errors.append(f'Row {i}: Roll No "{roll}" must be a whole number — {name} skipped.')
                skipped += 1
                continue
            if roll_number < FIRST_ROLL_NUMBER:
                errors.append(f'Row {i}: Roll No {roll_number} is below {FIRST_ROLL_NUMBER} — {name} skipped.')
                skipped += 1
                continue

            cls_obj = class_map.get(cls_name.lower())
            if not cls_obj:
                errors.append(f'Row {i}: Class "{cls_name}" not found — {name} skipped.')
                skipped += 1
                continue

            if StudentModel.query.filter_by(class_id=cls_obj.id, roll_number=roll_number).first():
                errors.append(f'Row {i}: Roll No {roll_number} ({name}) already exists in '
                              f'{cls_obj.name} — skipped.')
                skipped += 1
                continue

            sec_obj = section_map.get((cls_obj.id, sec_name.lower())) if sec_name else None

            student = StudentModel(
                roll_number    = roll_number,
                student_name   = name,
                father_name    = father,
                class_id       = cls_obj.id,
                section_id     = sec_obj.id if sec_obj else None,
                guardian_phone = phone,
                address        = address,
                is_active      = True
            )
            db.session.add(student)
            added += 1

        except Exception as e:
            errors.append(f'Row {i}: Error — {str(e)}')
            skipped += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Database error while saving: {str(e)}', 'danger')
        return redirect(url_for('main.students_list'))

    flash(f'Import complete — {added} student(s) added, {skipped} skipped.',
          'success' if added > 0 else 'warning')
    for err in errors[:10]:
        flash(err, 'warning')
    if len(errors) > 10:
        flash(f'...and {len(errors) - 10} more warnings not shown.', 'secondary')

    return redirect(url_for('main.students_list'))


@main.route('/students/restore-all', methods=['POST'])
def restore_all_students():
    count = StudentModel.query.filter_by(is_active=False).update({'is_active': True})
    db.session.commit()
    flash(f'{count} student(s) restored successfully.', 'success')
    return redirect(url_for('main.archived_students_list'))



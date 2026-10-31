"""Bulk student import from Excel/CSV."""

from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from app.database import db
from app.models import StudentModel, ClassModel, SectionModel
from app.routes import main
from app.services import admission_fee
from app.models.settings import get_custom_fields
from app.services.custom_fields import serialize_custom_field_values
from app.services.enrollments import start_enrollment
from app.services.roll_numbers import FIRST_ROLL_NUMBER
from app.services.data_import import (
    ImportFileError,
    ImportResult,
    RowChecker,
    collect_custom_values,
    is_example_row,
    norm_name,
    parse_whole_number,
    read_import_file,
    student_import_fields,
)

from app.routes.students.helpers import _import_admission_enabled, _student_fee_values


STUDENT_EXAMPLE_KEYS = ('student_name', 'father_name', 'guardian_phone')


def _roll_conflict_text(roll, class_name, source):
    if isinstance(source, int):
        return f'Roll Number {roll} is repeated in this file (already used in row {source})'
    return f'Roll Number {roll} is already registered in {class_name}'


@main.route('/students/import', methods=['POST'])
def import_students():
    """Bulk-import students.

    Rules: mandatory fields must be present; nothing already registered is ever
    overwritten (duplicate roll number in the class, duplicate admission number,
    or an existing student with the same name + father name + class are skipped);
    a blank Roll Number is assigned automatically (highest in class + 1).  Every
    skipped row is listed with its reason on the result page.
    """
    file = request.files.get('import_file')
    if not file or not file.filename:
        flash('No file selected.', 'warning')
        return redirect(url_for('main.students_list'))

    use_admission = _import_admission_enabled()
    specs = student_import_fields(get_custom_fields('student'), admission=use_admission)
    paid_as_income = use_admission and request.form.get('admission_paid_as_income') == '1'
    income_date = date.today()
    if paid_as_income:
        raw_date = (request.form.get('admission_income_date') or '').strip()
        if raw_date:
            try:
                income_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Please enter a valid income date.', 'danger')
                return redirect(url_for('main.students_list'))
        if income_date > date.today():
            flash('The income date cannot be in the future.', 'danger')
            return redirect(url_for('main.students_list'))
    try:
        parsed = read_import_file(file, specs)

    except ImportFileError as error:
        flash(str(error), 'danger')
        return redirect(url_for('main.students_list'))

    result = ImportResult('student')
    result.total_rows = len(parsed.rows)
    result.ignored_columns = parsed.ignored_columns

    class_map = {c.name.strip().lower(): c for c in ClassModel.query.all()}
    class_names = sorted(c.name for c in class_map.values())
    sections_by_class = {}
    for sec in SectionModel.query.all():
        sections_by_class.setdefault(sec.class_id, {})[sec.name.strip().lower()] = sec

    # What is already registered (archived students count too - they still own
    # their roll number and would otherwise be re-created as duplicates).
    used_rolls = {}      # class_id -> {roll: 'registered' | file row number}
    used_admission = {}  # lower admission no -> 'registered' | file row number
    people = {}          # (name, father, class_id) -> [(dob, source, is_active)]
    for row in StudentModel.query.with_entities(
            StudentModel.class_id, StudentModel.roll_number, StudentModel.student_name,
            StudentModel.father_name, StudentModel.admission_number,
            StudentModel.date_of_birth, StudentModel.is_active).all():
        used_rolls.setdefault(row.class_id, {})[int(row.roll_number)] = 'registered'
        if row.admission_number:
            used_admission[row.admission_number.strip().lower()] = 'registered'
        people.setdefault((norm_name(row.student_name), norm_name(row.father_name), row.class_id),
                          []).append((row.date_of_birth, 'registered', bool(row.is_active)))

    example = {spec.key: spec.example for spec in specs}
    pending = []

    # ---- pass 1: validate every row, detect duplicates ----------------------
    for row_no, record in parsed.rows:
        if is_example_row(record, example, STUDENT_EXAMPLE_KEYS):
            result.example_rows += 1
            continue

        chk = RowChecker(record, specs)
        name = chk.text('student_name', required=True, max_len=100)
        father = chk.text('father_name', required=True, max_len=100)
        class_text = chk.text('class_name', required=True)
        phone = chk.phone('guardian_phone', required=True)
        address = chk.long_text('address', required=True)
        gender = chk.choice('gender', ('Male', 'Female', 'Other'),
                            aliases={'m': 'Male', 'f': 'Female'})
        dob = chk.date('date_of_birth')
        admission_date = chk.date('admission_date')
        admission_no = chk.text('admission_number', max_len=40)
        sponsor_type = chk.choice('sponsor_type', ('Father', 'Guardian'), default='Father')
        sponsor_cnic = chk.cnic('sponsor_cnic')
        fee = chk.number('monthly_fee')
        discount_type = chk.choice('discount_type', ('percentage', 'fixed'))
        discount_value = chk.number('discount_value')
        if discount_value and discount_type is None:
            chk.add_problem('Discount Type (percentage or fixed) is required when a Discount Value is given')
        if discount_value and discount_type == 'percentage' and discount_value > 100:
            chk.add_problem('Discount Value cannot be more than 100 percent')
        custom_values = collect_custom_values(chk, specs)

        admission = None
        if use_admission:
            adm_fee = chk.number('admission_fee')
            adm_type = chk.choice('admission_discount_type',
                                  ('percentage', 'fixed', 'waived'))
            adm_value = chk.number('admission_discount_value')
            adm_paid = chk.number('admission_fee_paid')
            if adm_fee:
                try:
                    adm_net, _ = admission_fee.compute_net(
                        admission_fee.to_paisa(adm_fee), adm_type, adm_value)
                    if adm_paid and admission_fee.to_paisa(adm_paid) > adm_net:
                        chk.add_problem('Admission Fee Paid is more than the agreed '
                                        'admission fee after the concession')
                except ValueError as error:
                    chk.add_problem('Admission concession: %s' % error)
                admission = {'fee': adm_fee, 'type': adm_type, 'value': adm_value,
                             'paid': adm_paid}
            elif adm_type or adm_value or adm_paid:
                chk.add_problem('Admission Fee is required when an admission concession '
                                'or an amount paid is given')

        roll = None
        roll_raw = chk.raw('roll_number')

        if roll_raw:
            try:
                roll = parse_whole_number(roll_raw)
            except ValueError:
                chk.add_problem(f'Roll Number "{roll_raw}" must be a whole number such as {FIRST_ROLL_NUMBER} '
                                '(or leave it blank to assign one automatically)')
            else:
                if roll < FIRST_ROLL_NUMBER:
                    chk.add_problem(f'Roll Numbers start at {FIRST_ROLL_NUMBER}; {roll} is too small')
                    roll = None

        class_obj = section_obj = None
        if class_text:
            class_obj = class_map.get(class_text.lower())
            if class_obj is None:
                shown = ', '.join(class_names[:8]) + (' ...' if len(class_names) > 8 else '')
                chk.add_problem(f'Class "{class_text}" does not exist (your classes: {shown or "none yet"})')
        section_text = chk.text('section')
        if section_text.lower() in ('n/a', 'na', '-'):
            section_text = ''
        if section_text and class_obj is not None:
            section_obj = sections_by_class.get(class_obj.id, {}).get(section_text.lower())
            if section_obj is None:
                available = ', '.join(sorted(sec.name for sec in class_obj.sections)) or 'none'
                chk.add_problem(f'Section "{section_text}" does not exist in {class_obj.name} '
                                f'(available: {available})')

        reason = chk.reason()
        if reason:
            result.skip(row_no, name, reason, 'missing' if chk.missing else 'invalid')
            continue

        # duplicates -------------------------------------------------------
        duplicates = []
        class_rolls = used_rolls.setdefault(class_obj.id, {})
        if roll is not None and roll in class_rolls:
            duplicates.append(_roll_conflict_text(roll, class_obj.name, class_rolls[roll]))
        if admission_no and admission_no.lower() in used_admission:
            source = used_admission[admission_no.lower()]
            duplicates.append(
                f'Admission No "{admission_no}" is repeated in this file (row {source})'
                if isinstance(source, int) else
                f'Admission No "{admission_no}" is already registered')
        person_key = (norm_name(name), norm_name(father), class_obj.id)
        for known_dob, source, is_active in people.get(person_key, []):
            if known_dob is None or dob is None or known_dob == dob:
                if isinstance(source, int):
                    duplicates.append(f'Looks like a duplicate of row {source} in this file '
                                      f'(same name, father name and class)')
                else:
                    duplicates.append(
                        f'A student named {name} (father: {father}) is already registered in '
                        f'{class_obj.name}' + ('' if is_active else ' (archived - restore them instead)'))
                break
        if duplicates:
            result.skip(row_no, name, '; '.join(duplicates), 'duplicate')
            continue

        # reserve what this row uses so later rows in the file cannot clash
        if roll is not None:
            class_rolls[roll] = row_no
        if admission_no:
            used_admission[admission_no.lower()] = row_no
        people.setdefault(person_key, []).append((dob, row_no, True))
        pending.append({
            'row': row_no, 'name': name, 'father': father, 'class': class_obj,
            'section': section_obj, 'phone': phone, 'address': address, 'roll': roll,
            'gender': gender, 'dob': dob, 'admission_no': admission_no or None,
            'admission_date': admission_date, 'sponsor_type': sponsor_type,
            'sponsor_cnic': sponsor_cnic, 'fee': fee, 'discount_type': discount_type,
            'discount_value': discount_value, 'custom': custom_values,
            'admission': admission,
        })

    # ---- pass 2: assign automatic roll numbers and save ---------------------
    try:
        for item in pending:
            class_obj = item['class']
            class_rolls = used_rolls[class_obj.id]
            auto_assigned = item['roll'] is None
            if auto_assigned:
                item['roll'] = max(class_rolls, default=FIRST_ROLL_NUMBER - 1) + 1
                class_rolls[item['roll']] = item['row']

            base_fee = item['fee'] if item['fee'] is not None else class_obj.monthly_fee
            class_fee, monthly_fee, discount_type, discount_value = _student_fee_values({
                'monthly_fee': '' if base_fee is None else str(base_fee),
                'discount_type': item['discount_type'] or '',
                'discount_value': '' if item['discount_value'] is None else str(item['discount_value']),
            })

            student = StudentModel(
                roll_number=item['roll'],
                student_name=item['name'],
                father_name=item['father'],
                sponsor_type=item['sponsor_type'],
                sponsor_cnic=item['sponsor_cnic'],
                guardian_phone=item['phone'],
                address=item['address'],
                date_of_birth=item['dob'],
                gender=item['gender'],
                admission_number=item['admission_no'],
                admission_date=item['admission_date'],
                monthly_fee=monthly_fee,
                class_fee=class_fee,
                discount_type=discount_type,
                discount_value=discount_value,
                class_id=class_obj.id,
                section_id=item['section'].id if item['section'] else None,
                custom_fields_data=serialize_custom_field_values(item['custom']),
                is_active=True,
            )
            db.session.add(student)
            start_enrollment(student, reason='enrolled', start_date=date.today(),
                             end_previous=False)
            admission_note = ''
            if item.get('admission'):
                adm = item['admission']
                admission_fee.apply_on_import(
                    student, adm['fee'], adm['type'], adm['value'], adm['paid'],
                    paid_as_income, income_date, current_user)
                admission_note = ' - admission fee %s' % admission_fee.STATUS_LABELS[
                    admission_fee.status_for(student)].lower()
            label = f"{item['name']} (Roll No {item['roll']}, {class_obj.name})"
            result.added.append((item['row'], label + (' - roll number assigned automatically'
                                                       if auto_assigned else '') + admission_note))

        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Import cancelled and nothing was saved: another user changed the student list '
              'while the file was being imported. Please try again.', 'danger')
        return redirect(url_for('main.students_list'))
    except Exception as error:
        db.session.rollback()
        flash(f'Import cancelled and nothing was saved: {error}', 'danger')
        return redirect(url_for('main.students_list'))

    result.skipped.sort(key=lambda item: item['row'])
    return render_template('import_result.html', result=result, entity_label='Student',
                           entity_plural='Students',
                           back_url=url_for('main.students_list'),
                           template_url=url_for('main.students_template_excel'))

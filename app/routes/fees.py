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
    ClassModel, StudentModel, FeeRecordModel, SchoolSettings
)
from app.routes import main

@main.route('/fees', methods=['GET'])
def fees_list():
    selected_class_id = request.args.get('class_id', type=int)
    month_year = request.args.get('month_year', datetime.now().strftime('%B %Y'))
    show_unpaid = request.args.get('show_unpaid', '0') == '1'

    classes = ClassModel.query.all()
    if not show_unpaid and not selected_class_id and classes:
        selected_class_id = classes[0].id

    fee_data = []
    summary = {'total_due': 0.0, 'total_paid': 0.0, 'count_paid': 0, 'count_partial': 0, 'count_pending': 0}

    if show_unpaid:
        # All active students across ALL classes for this month
        all_students = StudentModel.query.filter_by(is_active=True).order_by(
            StudentModel.class_id, StudentModel.student_name).all()
        existing = {fr.student_id: fr for fr in
                    FeeRecordModel.query.filter_by(month_year=month_year).all()}
        for s in all_students:
            record = existing.get(s.id)
            due = s.monthly_fee if s.monthly_fee else 0.0
            status = record.status if record else 'Pending'
            # Only include Pending or Partial
            if status in ('Pending', 'Partial'):
                fee_data.append({'student': s, 'record': record, 'due': due,
                                 'class_name': s.class_info.name if s.class_info else '—'})
    else:
        if selected_class_id:
            students = StudentModel.query.filter_by(
                is_active=True, class_id=selected_class_id).all()
            fee_records_map = {
                fr.student_id: fr for fr in FeeRecordModel.query.join(StudentModel).filter(
                    StudentModel.class_id == selected_class_id,
                    FeeRecordModel.month_year == month_year
                ).all()
            }
            for s in students:
                record = fee_records_map.get(s.id)
                due = s.monthly_fee if s.monthly_fee else 0.0
                if not record and due > 0:
                    record = FeeRecordModel(
                        student_id=s.id, month_year=month_year,
                        amount_due=due, amount_paid=0.0, status='Pending'
                    )
                    db.session.add(record)
                    db.session.commit()
                fee_data.append({'student': s, 'record': record, 'due': due,
                                 'class_name': s.class_info.name if s.class_info else '—'})

    # Build summary
    for row in fee_data:
        due = row['due']
        status = row['record'].status if row['record'] else 'Pending'
        paid = row['record'].amount_paid if row['record'] else 0.0
        summary['total_due'] += due
        summary['total_paid'] += paid
        if status == 'Paid':
            summary['count_paid'] += 1
        elif status == 'Partial':
            summary['count_partial'] += 1
        else:
            summary['count_pending'] += 1

    return render_template('fees.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           month_year=month_year,
                           fee_data=fee_data,
                           show_unpaid=show_unpaid,
                           summary=summary)

@main.route('/fees/class-bulk-update', methods=['POST'])
def bulk_update_class_fees():
    class_id = request.form.get('class_id', type=int)
    fee_input = request.form.get('monthly_fee', '').strip()

    if not class_id:
        flash('Please select a class.', 'danger')
        return redirect(url_for('main.fees_list'))

    try:
        fee_value = float(fee_input) if fee_input else None
    except ValueError:
        flash('Please enter a valid fee amount.', 'danger')
        return redirect(url_for('main.fees_list', class_id=class_id))

    class_obj = ClassModel.query.get(class_id)
    if not class_obj:
        flash('Class not found.', 'danger')
        return redirect(url_for('main.fees_list'))

    students = StudentModel.query.filter_by(class_id=class_id, is_active=True).all()
    if fee_value is None:
        for student in students:
            student.monthly_fee = None
    else:
        for student in students:
            student.monthly_fee = fee_value

    db.session.commit()
    flash(f'Class fee updated for {len(students)} student(s) in {class_obj.name}.', 'success')
    return redirect(url_for('main.fees_list', class_id=class_id))


@main.route('/fees/pay/<int:student_id>', methods=['POST'])
def pay_fee(student_id):
    try:
        month_year = request.form.get('month_year', datetime.now().strftime('%B %Y'))
        amount_paid = float(request.form.get('amount_paid', 0))
        remarks = request.form.get('remarks', '')

        student = StudentModel.query.get_or_404(student_id)

        # If a due override was submitted (e.g. student had no monthly_fee set),
        # save it back to the student record so future months pick it up automatically.
        due_override_str = request.form.get('amount_due_override', '').strip()
        if due_override_str:
            try:
                due_override = float(due_override_str)
                if due_override > 0 and (not student.monthly_fee or student.monthly_fee != due_override):
                    student.monthly_fee = due_override
            except ValueError:
                pass

        due = student.monthly_fee if student.monthly_fee else 0.0

        # Check if record already exists for this student & month
        record = FeeRecordModel.query.filter_by(student_id=student.id, month_year=month_year).first()

        if record:
            record.amount_paid = amount_paid
            record.amount_due = due
            record.payment_date = datetime.utcnow().date()
            record.remarks = remarks
        else:
            record = FeeRecordModel(
                student_id=student.id,
                month_year=month_year,
                amount_due=due,
                amount_paid=amount_paid,
                payment_date=datetime.utcnow().date(),
                remarks=remarks
            )
            db.session.add(record)

        if amount_paid >= due > 0:
            record.status = 'Paid'
        elif amount_paid > 0:
            record.status = 'Partial'
        else:
            record.status = 'Pending'

        db.session.commit()
        flash(f'Fee updated successfully for {student.student_name}!', 'success')
        return redirect(url_for('main.fee_receipt',
                                student_id=student.id,
                                month_year=month_year))
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating fee: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('main.fees_list'))


@main.route('/fees/receipt/<int:student_id>/<month_year>')
def fee_receipt(student_id, month_year):
    student = StudentModel.query.get_or_404(student_id)
    record = FeeRecordModel.query.filter_by(
        student_id=student_id, month_year=month_year).first_or_404()
    school = None
    try:
        from app.models import SchoolSettings
        school = SchoolSettings.query.first()
    except Exception:
        pass
    return render_template('fee_receipt.html',
                           student=student,
                           record=record,
                           school=school,
                           month_year=month_year)


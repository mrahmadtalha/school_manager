from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.models import (
    AutomationSettings, ClassModel, FeeRecordModel, FeeTransaction, StudentModel,
    TXN_CHARGE, TXN_PAYMENT,
)
from app.routes import main
from app.security import role_required
from app.services.audit import log_action
from app.services import fee_reminders as fee_reminders_service
from app.services.fee_ledger import (
    current_month, ensure_charge, ledger_totals, reconcile, recompute_fee_record,
    record_payment, set_month_charge, student_summary, transactions_for,
)

PAYMENT_METHODS = ('cash', 'bank', 'online', 'other')


@main.route('/fees', methods=['GET'])
def fees_list():
    selected_class_id = request.args.get('class_id', type=int)
    month_year = (request.args.get('month_year') or '').strip() or current_month()
    show_unpaid = request.args.get('show_unpaid', '0') == '1'

    classes = ClassModel.query.all()
    if not show_unpaid and not selected_class_id and classes:
        selected_class_id = classes[0].id

    fee_data = []
    summary = {'total_due': 0.0, 'total_paid': 0.0, 'count_paid': 0,
               'count_partial': 0, 'count_pending': 0}

    if show_unpaid:
        students = (StudentModel.query.filter_by(is_active=True)
                    .order_by(StudentModel.class_id, StudentModel.student_name).all())
    elif selected_class_id:
        students = (StudentModel.query.filter_by(is_active=True, class_id=selected_class_id)
                    .order_by(StudentModel.student_name).all())
    else:
        students = []

    records = {r.student_id: r for r in
               FeeRecordModel.query.filter_by(month_year=month_year).all()}

    touched = False
    for student in students:
        record = records.get(student.id)
        if record is None:
            charged, paid = ledger_totals(student.id, month_year)
            if charged == 0 and (student.monthly_fee or 0) > 0:
                ensure_charge(student, month_year)
                touched = True
            record = recompute_fee_record(student.id, month_year)
            touched = True

        row = {
            'student': student,
            'record': record,
            'due': record.amount_due if record else 0.0,
            'paid': record.amount_paid if record else 0.0,
            'balance': record.balance if record else 0.0,
            'class_name': student.class_info.name if student.class_info else '—',
        }
        if show_unpaid and record and record.amount_due > 0 and record.amount_paid + 0.001 >= record.amount_due:
            continue
        fee_data.append(row)

    if touched:
        db.session.commit()

    for row in fee_data:
        record = row['record']
        summary['total_due'] += row['due']
        summary['total_paid'] += row['paid']
        status = record.status if record else 'Pending'
        if status == 'Paid':
            summary['count_paid'] += 1
        elif status == 'Partial':
            summary['count_partial'] += 1
        else:
            summary['count_pending'] += 1

    summary['total_due'] = round(summary['total_due'], 2)
    summary['total_paid'] = round(summary['total_paid'], 2)
    summary['total_balance'] = round(summary['total_due'] - summary['total_paid'], 2)

    return render_template('fees.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           month_year=month_year,
                           fee_data=fee_data,
                           show_unpaid=show_unpaid,
                           summary=summary,
                           payment_methods=PAYMENT_METHODS)


@main.route('/fees/class-bulk-update', methods=['POST'])
def bulk_update_class_fees():
    class_id = request.form.get('class_id', type=int)
    fee_input = (request.form.get('monthly_fee') or '').strip()

    if not class_id:
        flash('Please select a class.', 'danger')
        return redirect(url_for('main.fees_list'))

    try:
        fee_value = float(fee_input) if fee_input else None
        if fee_value is not None and fee_value < 0:
            raise ValueError
    except ValueError:
        flash('Please enter a valid, non-negative fee amount.', 'danger')
        return redirect(url_for('main.fees_list', class_id=class_id))

    class_obj = db.session.get(ClassModel, class_id)
    if not class_obj:
        flash('Class not found.', 'danger')
        return redirect(url_for('main.fees_list'))

    students = StudentModel.query.filter_by(class_id=class_id, is_active=True).all()
    month_year = (request.form.get('month_year') or '').strip() or current_month()

    for student in students:
        before = student.monthly_fee
        student.monthly_fee = fee_value
        log_action('charge', entity_type='StudentModel', entity_id=student.id,
                   summary=f'Monthly fee for {student.student_name} set to '
                           f'{fee_value if fee_value is not None else "none"}',
                   before={'monthly_fee': before}, after={'monthly_fee': fee_value})
        if fee_value is not None:
            set_month_charge(student, month_year, fee_value)
        recompute_fee_record(student.id, month_year)

    db.session.commit()
    flash(f'Class fee updated for {len(students)} student(s) in {class_obj.name}.', 'success')
    return redirect(url_for('main.fees_list', class_id=class_id, month_year=month_year))


@main.route('/fees/pay/<int:student_id>', methods=['POST'])
def pay_fee(student_id):
    student = StudentModel.query.get_or_404(student_id)
    month_year = (request.form.get('month_year') or '').strip() or current_month()
    remarks = (request.form.get('remarks') or '').strip()

    try:
        amount_paid = float(request.form.get('amount_paid') or 0)
    except ValueError:
        flash('Please enter a valid payment amount.', 'danger')
        return redirect(request.referrer or url_for('main.fees_list'))

    if amount_paid < 0:
        flash('Payment amount cannot be negative.', 'danger')
        return redirect(request.referrer or url_for('main.fees_list'))

    due_override_str = (request.form.get('amount_due_override') or '').strip()
    if due_override_str:
        try:
            due_override = float(due_override_str)
        except ValueError:
            due_override = None
        if due_override is not None and due_override > 0:
            student.monthly_fee = due_override
            set_month_charge(student, month_year, due_override)

    ensure_charge(student, month_year)

    if amount_paid > 0:
        record_payment(
            student, month_year, amount_paid,
            method=request.form.get('method') or 'cash',
            reference=(request.form.get('reference') or '').strip() or None,
            note=remarks or None,
            created_by=getattr(current_user, 'id', None),
        )

    record = recompute_fee_record(student.id, month_year, remarks=remarks or None)

    log_action('payment' if amount_paid > 0 else 'settings',
               entity_type='FeeTransaction', entity_id=student.id,
               summary=(f'Payment of {amount_paid:.2f} recorded for {student.student_name} '
                        f'({month_year})' if amount_paid > 0
                        else f'Fee record refreshed for {student.student_name} ({month_year})'),
               after={'student_id': student.id, 'month_year': month_year,
                      'amount': round(amount_paid, 2), 'status': record.status,
                      'method': request.form.get('method') or 'cash'})
    db.session.commit()

    flash(f'Fee updated for {student.student_name}: status {record.status}.', 'success')
    return redirect(url_for('main.fee_receipt', student_id=student.id, month_year=month_year))


@main.route('/fees/receipt/<int:student_id>/<month_year>')
def fee_receipt(student_id, month_year):
    student = StudentModel.query.get_or_404(student_id)
    record = FeeRecordModel.query.filter_by(
        student_id=student_id, month_year=month_year).first()
    if record is None:
        record = recompute_fee_record(student_id, month_year)
        db.session.commit()

    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    transactions = transactions_for(student_id, month_year)

    return render_template('fee_receipt.html',
                           student=student,
                           record=record,
                           school=school,
                           month_year=month_year,
                           transactions=transactions)


@main.route('/fees/reconciliation', methods=['GET'])
@role_required('admin')
def fees_reconciliation():
    month_year = (request.args.get('month_year') or '').strip() or None
    rows, totals, discrepancies = reconcile(month_year)
    months = sorted({t.month_year for t in FeeTransaction.query.all()})
    return render_template('fees_reconciliation.html',
                           rows=rows,
                           totals=totals,
                           discrepancies=discrepancies,
                           month_year=month_year,
                           months=months)


@main.route('/fees/reminders', methods=['GET'])
@role_required('admin')
def fee_reminders():
    month_year = (request.args.get('month_year') or '').strip() or current_month()
    if fee_reminders_service.month_start(month_year) is None:
        flash(f'Unknown month "{month_year}" - showing {current_month()} instead.', 'warning')
        month_year = current_month()

    class_id = request.args.get('class_id', type=int)
    classes = ClassModel.query.all()
    awaiting, already = fee_reminders_service.fee_reminder_status(month_year, class_id=class_id)
    settings = AutomationSettings.get()
    return render_template('fee_reminders.html',
                           month_year=month_year,
                           classes=classes,
                           selected_class_id=class_id,
                           awaiting=awaiting,
                           already=already,
                           count_no_phone=fee_reminders_service.count_without_phone(awaiting),
                           automation_enabled=bool(settings.enabled))


@main.route('/fees/reminders/queue', methods=['POST'])
@role_required('admin')
def fee_reminders_queue():
    month_year = (request.form.get('month_year') or '').strip() or current_month()
    class_id = request.form.get('class_id', type=int)
    try:
        summary = fee_reminders_service.queue_fee_reminders(month_year, class_id=class_id or None)
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('main.fee_reminders'))

    if summary['queued']:
        flash(f'Fee reminders for {month_year}: {summary["queued"]} queued, '
              f'{summary["skipped_existing"]} already queued, '
              f'{summary["skipped_no_phone"]} without a phone number.', 'success')
    else:
        flash(f'No new reminders queued for {month_year} '
              f'({summary["skipped_existing"]} already queued, '
              f'{summary["skipped_no_phone"]} without a phone number).', 'info')
    return redirect(url_for('main.fee_reminders', month_year=month_year))


@main.route('/fees/student/<int:student_id>', methods=['GET'])
def fee_student_ledger(student_id):
    student = StudentModel.query.get_or_404(student_id)
    summary_rows = student_summary(student_id)
    totals = {
        'charged': round(sum(r['charged'] for r in summary_rows), 2),
        'paid': round(sum(r['paid'] for r in summary_rows), 2),
        'balance': round(sum(r['balance'] for r in summary_rows), 2),
    }
    return render_template('fee_ledger.html', student=student, rows=summary_rows, totals=totals)

"""Staff payroll routes: wizard, generation, payment status and payslips (admin only)."""
from datetime import date

from flask import (abort, current_app, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user

from app.database import db
from app.models import ROLE_ACCOUNTANT, ROLE_ADMIN, SalaryPayment, StaffPayroll
from app.routes import main
from app.security import role_required
from app.services import payroll_service
from app.services.audit import log_action


def _valid_month_or_none(value):
    value = (value or '').strip()
    return value if payroll_service.parse_month(value) else None


@main.route('/payroll')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_page():
    month = _valid_month_or_none(request.args.get('month')) \
        or payroll_service.current_month_key()
    per_late = request.args.get('per_late', type=float) or 0.0
    leave_as_absent = request.args.get('leave_as_absent') == '1'
    rows = payroll_service.preview_rows(month, per_late, leave_as_absent)
    return render_template(
        'payroll.html',
        month=month,
        month_label=payroll_service.month_label(month),
        prev_month=payroll_service.shift_month(month, -1),
        next_month=payroll_service.shift_month(month, 1),
        rows=rows,
        totals=payroll_service.month_totals(month),
        per_late=per_late,
        leave_as_absent=leave_as_absent,
        today=date.today(),
    )


@main.route('/payroll/generate', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_generate():
    month = _valid_month_or_none(request.form.get('month'))
    if not month:
        flash('Please choose a valid month.', 'danger')
        return redirect(url_for('main.payroll_page'))

    result = payroll_service.generate(
        month, request.form,
        generated_by=getattr(current_user, 'username', 'system') or 'system')

    if result['created'] or result['updated']:
        log_action('create', entity_type='StaffPayroll',
                   summary='Payroll saved for %s (%d new, %d updated)'
                           % (month, result['created'], result['updated']))
        db.session.commit()
        flash('Payroll saved for %s — %d created, %d updated, %d skipped.'
              % (payroll_service.month_label(month), result['created'],
                 result['updated'], result['skipped']), 'success')
    else:
        flash('Nothing to save — %d row(s) were skipped (unchecked or locked).'
              % result['skipped'], 'warning')
    return redirect(url_for('main.payroll_page', month=month))


@main.route('/payroll/<int:id>/pay', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_pay(id):
    """Pay part of (or all of) a month's salary; mirrors into Salaries expense."""
    record = db.session.get(StaffPayroll, id)
    if record is None:
        abort(404)

    try:
        amount = float(request.form.get('amount') or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        amount = record.remaining_amount  # "pay full remaining" default

    method = (request.form.get('payment_method') or 'Cash').strip()
    if method not in ('Cash', 'Bank', 'Cheque'):
        method = 'Cash'
    payment_date = (payroll_service.parse_iso_date(request.form.get('payment_date'))
                    or date.today())
    note = (request.form.get('note') or '').strip() or None

    try:
        payment = payroll_service.record_salary_payment(
            record, amount, payment_date, method=method, note=note,
            actor=current_user)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
        return redirect(url_for('main.payroll_page', month=record.month_year))

    teacher_name = record.teacher.teacher_name if record.teacher else str(record.teacher_id)
    month_name = payroll_service.month_label(record.month_year)
    log_action('payment', entity_type='SalaryPayment', entity_id=payment.id,
               summary='Salary paid %s: %s (%s) — Rs. %s (%s remaining)'
                       % (month_name, teacher_name,
                          '{:,.0f}'.format(payment.amount),
                          '{:,.0f}'.format(payment.amount),
                          '{:,.0f}'.format(record.remaining_amount)))
    db.session.commit()
    flash('Salary payment recorded: %s — Rs. %s (%s). Remaining: Rs. %s.'
          % (teacher_name, '{:,.2f}'.format(payment.amount),
             month_name,
             '{:,.2f}'.format(record.remaining_amount)), 'success')
    return redirect(url_for('main.payroll_page', month=record.month_year))


@main.route('/payroll/payment/<int:payment_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_payment_void(payment_id):
    """Void a salary payment (mandatory reason) and the expense it created."""
    payment = db.session.get(SalaryPayment, payment_id)
    if payment is None:
        abort(404)
    record = payment.payroll

    reason = (request.form.get('void_reason') or '').strip()
    if not reason:
        flash('A reason is required to void a salary payment.', 'danger')
        return redirect(url_for('main.payroll_page',
                                month=record.month_year if record else payroll_service.current_month_key()))

    payroll_service.void_salary_payment(payment, reason, actor=current_user)
    teacher_name = record.teacher.teacher_name if record and record.teacher else payment.teacher_id
    log_action('void', entity_type='SalaryPayment', entity_id=payment.id,
               before={'amount': payment.amount},
               summary='Salary payment voided: %s (%s) — %s'
                       % (teacher_name, payment.amount, reason))
    db.session.commit()
    flash('Salary payment voided — Rs. %s returned to pending for %s.'
          % ('{:,.2f}'.format(payment.amount),
             payroll_service.month_label(record.month_year) if record else ''), 'warning')
    return redirect(url_for('main.payroll_page',
                            month=record.month_year if record else payroll_service.current_month_key()))


@main.route('/payroll/mark-all-paid', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_mark_all_paid():
    """Pay the full remaining balance of every pending/partial row for the month."""
    month = _valid_month_or_none(request.form.get('month'))
    if not month:
        flash('Please choose a valid month.', 'danger')
        return redirect(url_for('main.payroll_page'))

    records = StaffPayroll.query.filter_by(month_year=month).all()
    paid_count = 0
    for record in records:
        remaining = record.remaining_amount
        if remaining <= 0:
            continue
        payroll_service.record_salary_payment(
            record, remaining, date.today(),
            method=(record.payment_method or 'Cash'), note='Bulk payment',
            actor=current_user)
        paid_count += 1

    if paid_count:
        log_action('payment', entity_type='SalaryPayment',
                   summary='Bulk salary payment: %d record(s) for %s' % (paid_count, month))
        db.session.commit()
        flash('%d salary record(s) fully paid for %s.' % (paid_count,
              payroll_service.month_label(month)), 'success')
    else:
        flash('No pending salary records for %s.' % payroll_service.month_label(month),
              'warning')
    return redirect(url_for('main.payroll_page', month=month))


@main.route('/payroll/<int:id>/payslip.pdf')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_payslip_pdf(id):
    record = db.session.get(StaffPayroll, id)
    if record is None or record.teacher is None:
        abort(404)

    output = payroll_service.build_payslip_pdf(record, record.teacher,
                                               current_app.root_path)
    filename = 'payslip_%s_%s.pdf' % (
        record.month_year,
        getattr(record.teacher, 'teacher_id_str', None) or record.teacher.id)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=filename)

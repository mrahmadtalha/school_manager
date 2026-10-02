"""Staff payroll routes: wizard, generation, payment status and payslips (admin only)."""
from datetime import date

from flask import (abort, current_app, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user

from app.database import db
from app.models import ROLE_ACCOUNTANT, ROLE_ADMIN, StaffPayroll
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


@main.route('/payroll/<int:id>/mark-paid', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_mark_paid(id):
    record = db.session.get(StaffPayroll, id)
    if record is None:
        abort(404)

    method = (request.form.get('payment_method') or 'Cash').strip()
    if method not in ('Cash', 'Bank', 'Cheque'):
        method = 'Cash'
    payment_date = (payroll_service.parse_iso_date(request.form.get('payment_date'))
                    or date.today())

    record.payment_status = 'Paid'
    record.payment_method = method
    record.payment_date = payment_date
    teacher_name = record.teacher.teacher_name if record.teacher else str(record.teacher_id)
    log_action('payment', entity_type='StaffPayroll', entity_id=record.id,
               summary='Salary paid: %s (%s)' % (teacher_name,
                                                 payroll_service.month_label(record.month_year)))
    db.session.commit()
    flash('Salary marked paid: %s — %s.' % (teacher_name, payroll_service.month_label(record.month_year)),
          'success')
    return redirect(url_for('main.payroll_page', month=record.month_year))


@main.route('/payroll/<int:id>/mark-pending', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_mark_pending(id):
    record = db.session.get(StaffPayroll, id)
    if record is None:
        abort(404)

    record.payment_status = 'Pending'
    record.payment_date = None
    record.payment_method = None
    teacher_name = record.teacher.teacher_name if record.teacher else str(record.teacher_id)
    log_action('update', entity_type='StaffPayroll', entity_id=record.id,
               summary='Salary reverted to pending: %s (%s)'
                       % (teacher_name, payroll_service.month_label(record.month_year)))
    db.session.commit()
    flash('Salary reverted to Pending: %s.' % teacher_name, 'success')
    return redirect(url_for('main.payroll_page', month=record.month_year))


@main.route('/payroll/mark-all-paid', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def payroll_mark_all_paid():
    month = _valid_month_or_none(request.form.get('month'))
    if not month:
        flash('Please choose a valid month.', 'danger')
        return redirect(url_for('main.payroll_page'))

    records = StaffPayroll.query.filter_by(month_year=month,
                                           payment_status='Pending').all()
    for record in records:
        record.payment_status = 'Paid'
        record.payment_method = record.payment_method or 'Cash'
        record.payment_date = record.payment_date or date.today()

    if records:
        log_action('payment', entity_type='StaffPayroll',
                   summary='Bulk salary payment: %d record(s) for %s'
                           % (len(records), month))
        db.session.commit()
        flash('%d salary record(s) marked paid for %s.'
              % (len(records), payroll_service.month_label(month)), 'success')
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

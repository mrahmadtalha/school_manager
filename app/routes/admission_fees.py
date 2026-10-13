"""Admission fee pages (see app/services/admission_fee.py for the rules).

* Fees page settings (universal + per-class fee) ... administrator only
* Register, student page, receipt ................. administrator, accountant
                                                     (owner: read-only views)
* Receiving money, voiding a receipt ............. administrator, accountant
* Changing a student's terms / concessions ....... administrator only

The money itself is recorded as Other Income, so these pages only add the
per-student view, receipts and the register.
"""
from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.models import (ClassModel, OtherIncome, ROLE_ACCOUNTANT, ROLE_ADMIN,
                        ROLE_OWNER, SchoolSettings, StudentModel)
from app.routes import main
from app.security import role_required
from app.services import admission_fee
from app.services.audit import log_action
from app.services.payroll_service import amount_in_words


def _parse_date(value, default=None):
    value = (value or '').strip()
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _student_url(student_id):
    return url_for('main.admission_student', student_id=student_id)


# --------------------------------------------------------------------------- #
# Settings (Fees page)
# --------------------------------------------------------------------------- #

@main.route('/fees/admission-settings', methods=['POST'])
@role_required(ROLE_ADMIN)
def admission_settings_save():
    class_values = {}
    for class_obj in ClassModel.query.all():
        key = 'class_%d' % class_obj.id
        if key in request.form:
            class_values[class_obj.id] = request.form.get(key)
    try:
        default, parsed = admission_fee.save_settings(
            request.form.get('default_admission_fee'), class_values)
        log_action('update', entity_type='AdmissionFeeSettings', entity_id=None,
                   summary='Admission fee settings saved: school fee %s, %d class '
                           'override(s)' % (
                               'none' if default is None else 'Rs. %s' % default,
                               sum(1 for v in parsed.values() if v is not None)))
        db.session.commit()
        flash('Admission fee settings saved. They apply to students admitted '
              'from now on; existing students are not changed.', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(request.referrer or url_for('main.fees_list'))


# --------------------------------------------------------------------------- #
# Register and student page
# --------------------------------------------------------------------------- #

def _register_filters():
    """Filters shared by the register page and its exports."""
    status = (request.args.get('status') or '').strip()
    if status not in admission_fee.STATUSES:
        status = ''
    return {
        'class_id': request.args.get('class_id', type=int),
        'status': status,
        'search': (request.args.get('search') or '').strip()[:80],
        'date_from': _parse_date(request.args.get('date_from')),
        'date_to': _parse_date(request.args.get('date_to')),
    }


@main.route('/admission-fees')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_OWNER)
def admission_register():
    filters = _register_filters()
    class_id, status, search = filters['class_id'], filters['status'], filters['search']
    rows, totals = admission_fee.register(
        class_id=class_id, status=status or None, search=search or None,
        date_from=filters['date_from'], date_to=filters['date_to'])
    return render_template(
        'admission_fees.html', rows=rows, totals=totals,
        classes=ClassModel.query.order_by(ClassModel.id).all(),
        selected_class=class_id, selected_status=status, search=search,
        date_from=request.args.get('date_from') or '',
        date_to=request.args.get('date_to') or '',
        statuses=admission_fee.STATUSES, status_labels=admission_fee.STATUS_LABELS,
        enabled=admission_fee.is_enabled(), money=admission_fee.money,
        is_admin=admission_fee.is_admin(current_user))


@main.route('/admission-fees/export/<fmt>')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_OWNER)
def admission_export(fmt):
    """The register (with the page's filters) as PDF, Excel or CSV."""
    from app.routes import reports as hub     # shared, school-branded export engine
    hub._hub_export_guard(fmt)
    filters = _register_filters()
    rows, totals = admission_fee.register(
        class_id=filters['class_id'], status=filters['status'] or None,
        search=filters['search'] or None, date_from=filters['date_from'],
        date_to=filters['date_to'])
    rupees = admission_fee.to_rupees
    headers = ['Date', 'Student', 'Father', 'Class', 'Roll No', 'Standard (Rs)',
               'Concession (Rs)', 'Net (Rs)', 'Received (Rs)', 'Pending (Rs)',
               'Status', 'Reason']
    data = []
    for row in rows:
        student = row['student']
        data.append([
            student.admission_fee_date.strftime('%Y-%m-%d') if student.admission_fee_date else '',
            student.student_name, student.father_name,
            student.class_info.name if student.class_info else '',
            student.roll_number, rupees(row['standard']), rupees(row['concession']),
            rupees(row['net']), rupees(row['received']), rupees(row['balance']),
            admission_fee.STATUS_LABELS[row['status']], student.admission_note or ''])
    parts = []
    if filters['class_id']:
        class_obj = db.session.get(ClassModel, filters['class_id'])
        parts.append(class_obj.name if class_obj else 'Class')
    else:
        parts.append('All classes')
    if filters['status']:
        parts.append(admission_fee.STATUS_LABELS[filters['status']])
    if filters['date_from'] or filters['date_to']:
        parts.append('%s to %s' % (filters['date_from'] or '...', filters['date_to'] or '...'))
    if filters['search']:
        parts.append('"%s"' % filters['search'])
    footer = ('Students: <b>%d</b> &nbsp;&middot;&nbsp; Agreed: <b>%s</b> &nbsp;&middot;&nbsp; '
              'Received: <b>%s</b> &nbsp;&middot;&nbsp; Pending: <b>%s</b> &nbsp;&middot;&nbsp; '
              'Concessions given: <b>%s</b>' % (
                  totals['count'], admission_fee.money(totals['net']),
                  admission_fee.money(totals['received']),
                  admission_fee.money(totals['balance']),
                  admission_fee.money(totals['concession'])))
    if totals['prior']:
        footer += (' &nbsp;&middot;&nbsp; Opening amounts (not income): <b>%s</b>'
                   % admission_fee.money(totals['prior']))
    return hub._hub_export_file(
        fmt, 'admission_fees_%s' % date.today().strftime('%Y%m%d'),
        'Admission Fees Register', ' - '.join(parts), headers, data,
        col_align=['CENTER', 'LEFT', 'LEFT', 'LEFT', 'CENTER', 'RIGHT', 'RIGHT',
                   'RIGHT', 'RIGHT', 'RIGHT', 'CENTER', 'LEFT'],
        col_weights=[2.2, 3.6, 3.2, 2.2, 1.5, 2.2, 2.2, 2.2, 2.2, 2.2, 1.8, 3.0],
        cell_formats=[None, None, None, None, None, 'money', 'money', 'money',
                      'money', 'money', None, None],
        landscape_mode=True, footer_note=footer)


@main.route('/admission-fees/student/<int:student_id>')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_OWNER)
def admission_student(student_id):
    student = StudentModel.query.get_or_404(student_id)
    return render_template(
        'admission_student.html', student=student,
        info=admission_fee.summary(student),
        payments=admission_fee.all_payments(student.id),
        status_labels=admission_fee.STATUS_LABELS,
        methods=admission_fee.PAYMENT_METHODS,
        default_standard=admission_fee.to_rupees(
            admission_fee.effective_paisa(student.class_id)),
        money=admission_fee.money, today=date.today(),
        can_receive=current_user.role in (ROLE_ADMIN, ROLE_ACCOUNTANT),
        is_admin=admission_fee.is_admin(current_user))


# --------------------------------------------------------------------------- #
# Receiving money, terms, receipts
# --------------------------------------------------------------------------- #

@main.route('/admission-fees/student/<int:student_id>/receive', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def admission_receive(student_id):
    student = StudentModel.query.get_or_404(student_id)
    pay_date = _parse_date(request.form.get('payment_date'), date.today())
    if pay_date is None:
        flash('Please enter a valid payment date.', 'danger')
        return redirect(_student_url(student.id))
    try:
        row = admission_fee.receive_payment(
            student, (request.form.get('amount') or '').strip().replace(',', ''),
            pay_date, request.form.get('method'), actor=current_user,
            note=request.form.get('note'))
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
        return redirect(_student_url(student.id))
    flash('Admission fee of %s received (receipt %s).' % (
        admission_fee.money(row.amount_paisa), row.receipt_no), 'success')
    return redirect(url_for('main.admission_receipt', row_id=row.id))


@main.route('/admission-fees/student/<int:student_id>/terms', methods=['POST'])
@role_required(ROLE_ADMIN)
def admission_terms(student_id):
    student = StudentModel.query.get_or_404(student_id)
    raw = (request.form.get('admission_fee') or '').strip().replace(',', '')
    try:
        standard = float(raw)
    except ValueError:
        flash('Please enter the admission fee amount (0 removes it).', 'danger')
        return redirect(_student_url(student.id))
    try:
        admission_fee.adjust_terms(
            student, standard, request.form.get('admission_discount_type'),
            request.form.get('admission_discount_value'),
            request.form.get('admission_note'))
        db.session.commit()
        flash('Admission fee terms updated.', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(_student_url(student.id))


@main.route('/admission-fees/receipt/<int:row_id>')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_OWNER)
def admission_receipt(row_id):
    row = OtherIncome.query.get_or_404(row_id)
    if row.student_id is None:
        abort(404)
    student = row.student
    info = admission_fee.summary(student)
    # Paid so far *as of this receipt*: earlier or same receipts only, so a
    # reprinted old receipt still shows what was true when it was issued.
    earlier = info['prior_paid'] + sum(p.amount_paisa for p in admission_fee.active_payments(student.id)
                                       if (p.income_date, p.id) <= (row.income_date, row.id))
    return render_template(
        'admission_receipt.html', row=row, student=student, info=info,
        paid_to_date=earlier,
        balance_after=max(0, info['net'] - earlier),
        school=SchoolSettings.query.first(), money=admission_fee.money,
        words=amount_in_words(row.amount), status_labels=admission_fee.STATUS_LABELS)


@main.route('/admission-fees/receipt/<int:row_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def admission_payment_void(row_id):
    row = OtherIncome.query.get_or_404(row_id)
    if row.student_id is None:
        abort(404)
    student_id = row.student_id
    try:
        admission_fee.void_payment(row, request.form.get('reason'), actor=current_user)
        db.session.commit()
        flash('Receipt %s voided. The balance is open again.' % row.receipt_no,
              'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(_student_url(student_id))

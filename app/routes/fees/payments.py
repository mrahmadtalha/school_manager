"""Fee payments, receipts, reconciliation, allocation repair and fee reminders."""

from datetime import date, datetime
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from app.database import db
from app.models import (
    AutomationSettings,
    ClassModel,
    FeeRecordModel,
    FeeTransaction,
    MessageQueue,
    StudentModel,
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    TXN_CHARGE,
    TXN_PAYMENT,
)
from app.routes import main
from app.security import role_required
from app.services.audit import current_actor, log_action
from app.services import fee_reminders as fee_reminders_service
from app.services.fee_ledger import (
    DuplicateReferenceError,
    advance_credit_enabled,
    current_month,
    ensure_charge,
    ledger_totals,
    next_reference,
    payment_allocation_lines,
    payment_allocation_summary,
    reconcile,
    recompute_fee_record,
    record_payment,
    orphaned_settlements,
    repair_allocations,
    reference_in_use,
    set_month_charge,
    student_credit_paisa,
    student_dues_months,
    student_outstanding_paisa,
    student_summary,
    transactions_for,
)
from app.services.fee_ledger import _month_sort_key
from app.services.whatsapp_automation import normalize_whatsapp_number

from app.routes.fees.core import back_to_fees_url, receipt_return_args


@main.route('/fees/pay/<int:student_id>', methods=['POST'])
def pay_fee(student_id):
    student = StudentModel.query.get_or_404(student_id)
    month_year = (request.form.get('month_year') or '').strip() or current_month()
    remarks = (request.form.get('remarks') or '').strip()

    try:
        amount_paid = float(request.form.get('amount_paid') or 0)
    except ValueError:
        flash('Please enter a valid payment amount.', 'danger')
        return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))

    if amount_paid < 0:
        flash('Payment amount cannot be negative.', 'danger')
        return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))

    # Explicit cash date (back-dating is normal); defaults to today.
    payment_date = None
    date_raw = (request.form.get('payment_date') or '').strip()
    if date_raw:
        try:
            payment_date = datetime.strptime(date_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Please enter a valid payment date (YYYY-MM-DD).', 'danger')
            return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))

    # A slip / reference number may only be used once.  Check it before anything
    # is changed so a rejected form leaves the student's fee data untouched.
    typed_reference = (request.form.get('reference') or '').strip()
    if amount_paid > 0 and typed_reference and reference_in_use(typed_reference):
        flash(f'Slip / Reference No "{typed_reference}" has already been used. '
              f'Please enter a different number (next free: {next_reference()}).', 'danger')
        return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))

    due_override_str = (request.form.get('amount_due_override') or '').strip()
    if due_override_str:
        try:
            due_override = float(due_override_str)
        except ValueError:
            due_override = None
        if due_override is not None and due_override > 0:
            # The form always posts the month's current due in this field (it
            # is readonly when set).  Only a value that DIFFERS from the
            # existing charge is a real override — recording a payment must
            # never be blocked just because the month already has payments.
            existing_charge = (FeeTransaction.query
                               .filter_by(student_id=student.id, month_year=month_year,
                                          txn_type=TXN_CHARGE, is_void=False)
                               .order_by(FeeTransaction.id.asc()).first())
            existing_amount = existing_charge.amount if existing_charge else 0.0
            # The form shows the month's WHOLE due: the monthly charge plus any
            # extra charge / adjustment (event, trip, fine).  Compare against that
            # whole figure, otherwise a month with an extra charge would look like
            # a changed fee on every payment.
            month_total, _paid_so_far, _written_off = ledger_totals(student.id, month_year)
            extras = round(month_total - existing_amount, 2)
            if existing_charge is None or abs(due_override - month_total) > 0.005:
                # Explicit charge change: a month with payments must be
                # corrected by voiding the payment, never by rewriting the charge.
                has_payments = FeeTransaction.query.filter_by(
                    student_id=student.id, month_year=month_year,
                    txn_type=TXN_PAYMENT, is_void=False).first() is not None
                if has_payments:
                    flash(f'{month_year} already has payments, so its charged amount can no '
                          'longer be overwritten. Void the payment first if the charge is wrong.', 'danger')
                    return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))
                # The change belongs to THIS month only.  The student's standing
                # monthly fee is touched only when none was ever set (the first
                # fee typed into an empty field), so a one-off amount can no
                # longer change every future month.
                # The typed figure is the month's whole due, so the monthly
                # charge itself is that figure minus the extras already in it.
                new_charge = round(due_override - (extras if existing_charge else 0.0), 2)
                if new_charge <= 0:
                    flash('The month due cannot be lower than its extra charges '
                          f'(Rs. {extras:,.0f}). Void the extra charge first.', 'danger')
                    return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))
                if not (student.monthly_fee or 0) > 0:
                    student.monthly_fee = new_charge
                else:
                    flash(f'{month_year} charge changed to Rs. {new_charge:,.0f}. '
                          f'The monthly fee on the student record '
                          f'(Rs. {student.monthly_fee:,.0f}) was not changed.', 'info')
                set_month_charge(student, month_year, new_charge)

    ensure_charge(student, month_year)
    # Overpayment is allowed on purpose: whatever the charges of this month do
    # not absorb stays as advance credit and settles older/future arrears
    # automatically (oldest first).

    payment_transaction = None
    if amount_paid > 0:
        if not advance_credit_enabled() and student_outstanding_paisa(student.id) <= 0:
            flash('This student has no dues.', 'info')
            return redirect(request.referrer
                            or url_for('main.fees_list', month_year=month_year))
        # "Apply to" choice: oldest dues first (default) or a specific month
        # settled before everything else (remainder still oldest-first).  The
        # dropdown posts the month label and only offers months where the
        # student actually has dues.
        apply_to = (request.form.get('apply_to') or 'oldest').strip()
        apply_month = None
        # "Advance" is only meaningful when nothing is owed.  The service
        # re-allocates oldest-first regardless, so a crafted POST cannot park
        # money as credit while dues remain; this just reports it plainly.
        if apply_to == 'advance' and student_outstanding_paisa(student.id) > 0:
            flash('This student still has outstanding dues, so the payment was '
                  'applied to those first.', 'info')
            apply_to = 'oldest'
        if apply_to == 'month':
            apply_month = (request.form.get('apply_month') or '').strip()
            allowed = {month for month, _balance in student_dues_months(student.id)}
            if apply_month not in allowed:
                flash('Choose a month with outstanding dues for "Apply to a '
                      'specific month", or keep the choice on oldest dues first.', 'danger')
                return redirect(request.referrer
                                or url_for('main.fees_list', month_year=month_year))
        try:
            payment_transaction = record_payment(
                student, month_year, amount_paid,
                method=request.form.get('method') or 'cash',
                reference=typed_reference or None,
                note=remarks or None,
                created_by=getattr(current_user, 'id', None),
                payment_date=payment_date,
                apply_month=apply_month,
            )
        except DuplicateReferenceError as error:
            # Safety net for two cashiers saving the same number at the same moment.
            db.session.rollback()
            flash(f'{error} Please enter a different number '
                  f'(next free: {error.suggestion}).', 'danger')
            return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))
        except ValueError as error:
            # E.g. the payment cap: more than the student's total dues.
            db.session.rollback()
            flash(str(error), 'danger')
            return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))

    record = recompute_fee_record(student.id, month_year, remarks=remarks or None)

    automation_settings = AutomationSettings.get()
    receipt_phone = normalize_whatsapp_number(student.guardian_phone or '')
    if (payment_transaction and automation_settings.enabled
            and automation_settings.notify_fee_receipts and receipt_phone):
        charged_after, paid_after, _wo = ledger_totals(student.id, month_year)
        receipt_message = (
            f'Fee payment receipt for {student.student_name}: '
            f'{payment_transaction.amount:,.2f} PKR received for {month_year}. '
            f'Reference: {payment_transaction.reference}. '
            f'Remaining balance: {max(charged_after - paid_after, 0):,.2f} PKR.'
        )
        db.session.add(MessageQueue(
            phone=receipt_phone,
            message=receipt_message,
            status='pending' if automation_settings.mode == 'approval' else 'approved',
            trigger='fee_receipt',
            student_id=student.id,
            ref_date=date.today(),
        ))

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
    if payment_transaction is not None:
        allocation_summary = payment_allocation_summary(payment_transaction)
        if allocation_summary:
            flash('Rs %s received for %s — %s.'
                  % ('{:,.0f}'.format(payment_transaction.amount),
                     student.student_name, allocation_summary), 'info')
    # Carry the fees-list filters through to the receipt so the user can get back
    # to the exact filtered view they came from. The form posts them in the body
    # (the action URL has no query string), so read from the form here.
    # ``month_year`` for the receipt path is the explicit billing month, so the
    # returned copy is dropped to avoid a duplicate keyword argument.
    carried = receipt_return_args(request.form)
    # The receipt's own month is a URL path segment, which the receipt route
    # cannot read back from the query string, so the list's billing month is
    # always carried explicitly under its return_* name.
    return redirect(url_for('main.fee_receipt', student_id=student.id,
                            month_year=month_year, **carried))


@main.route('/fees/receipt/<int:student_id>/<month_year>')
def fee_receipt(student_id, month_year):
    student = StudentModel.query.get_or_404(student_id)
    record = FeeRecordModel.query.filter_by(
        student_id=student_id, month_year=month_year).first()
    if record is None:
        # Read-only view: build the summary in memory instead of writing a
        # cache row on a GET (an expired-license school keeps full read access).
        from types import SimpleNamespace as _NS
        charged, paid, written_off = ledger_totals(student_id, month_year)
        status = ('Paid' if charged > 0 and paid + written_off + 0.001 >= charged
                  else 'Partial' if paid > 0 else 'Pending')
        record = _NS(amount_due=charged, amount_paid=paid,
                     amount_written_off=written_off, status=status,
                     balance=round(charged - paid - written_off, 2), remarks=None)

    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    transactions = transactions_for(student_id, month_year)

    # Where the month's settling transactions actually put the money, oldest
    # month first (display only — the allocations are already in the ledger).
    allocation_lines = []
    for txn in transactions:
        for month_label, amount in payment_allocation_lines(txn):
            allocation_lines.append({'type': txn.type_label,
                                     'reference': txn.reference,
                                     'month': month_label,
                                     'amount': amount})

    allocation_total = round(sum(line['amount'] for line in allocation_lines
                                 if line['month'] not in ('Advance credit',
                                                          'Not applied to any month')), 2)

    # Filters reported by the fees page, validated against the whitelist, so the
    # "Back to Fees" link can restore the same class/month/view/search. Nothing
    # here is trusted verbatim: only these four keys survive, each coerced.
    back_args = receipt_return_args(request.args)

    return render_template('fee_receipt.html',
                           student=student,
                           record=record,
                           school=school,
                           month_year=month_year,
                           remaining_dues=round(
                               student_outstanding_paisa(student_id) / 100.0, 2),
                           dues_breakdown=student_dues_months(student_id),
                           transactions=transactions,
                           allocation_lines=allocation_lines,
                           allocation_total=allocation_total,
                           back_to_fees_url=back_to_fees_url(**back_args),
                           back_has_filters=bool(back_args))


@main.route('/fees/reconciliation', methods=['GET'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def fees_reconciliation():
    month_year = (request.args.get('month_year') or '').strip() or None
    rows, totals, discrepancies = reconcile(month_year)
    months = sorted({t.month_year for t in FeeTransaction.query.all()})
    # Requirement 19: surface settling rows that settle nothing, so unapplied
    # payments/write-offs are visible (and repairable) from this page.
    orphans = orphaned_settlements()
    return render_template('fees_reconciliation.html',
                           rows=rows,
                           totals=totals,
                           discrepancies=discrepancies,
                           month_year=month_year,
                           months=months,
                           orphan_count=len(orphans),
                           orphan_total=round(sum(t.amount or 0.0 for t in orphans), 2),
                           orphan_students=sorted({t.student_id for t in orphans}))


@main.route('/fees/reconciliation/repair', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def fees_repair_allocations():
    """Rebuild allocations for settling rows that settle nothing.

    Requirement 19: a payment or write-off can sit in the ledger with no
    allocation at all (historically because allocation only matched
    ``charge`` rows, never ``adjustment`` rows).  Such a row is reported as
    advance credit while the charge it should have cleared stays outstanding,
    so dues and credit appear at once.

    Deliberately manual: it writes ledger rows, so it never runs at startup
    or on a page load.  A safety backup is taken first, and only rows with no
    active allocation are touched, so running it twice changes nothing.
    """
    orphans = orphaned_settlements()
    if not orphans:
        flash('Nothing to repair — every payment and write-off already settles '
              'the correct dues.', 'success')
        return redirect(url_for('main.fees_reconciliation'))

    try:
        from app.services.db_backup import backup_database
        backup_path = backup_database()
    except Exception as error:  # noqa: BLE001 - never repair without a backup
        db.session.rollback()
        flash('Repair cancelled: the safety backup could not be created (%s).' % error,
              'danger')
        return redirect(url_for('main.fees_reconciliation'))

    _, username, _ = current_actor()
    result = repair_allocations(actor=username or 'system')
    db.session.commit()

    log_action('adjustment', entity_type='FeeAllocation', entity_id=None,
               summary=('Fee allocation repair: rebuilt %d row(s) that settled '
                        'nothing (students: %s)'
                        % (result['repaired'],
                           ', '.join(str(s) for s in sorted(result['students'])))),
               after={'repaired': result['repaired'],
                      'students': sorted(result['students']),
                      'backup': str(backup_path)})
    db.session.commit()

    flash('%d payment/write-off row(s) repaired and now settle the correct dues. '
          'Safety backup saved as %s.'
          % (result['repaired'], backup_path.name), 'success')
    return redirect(url_for('main.fees_reconciliation'))


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
    # Billing-month dropdown: only months in which someone still owes money, plus the
    # current month and the month being viewed (newest first) - nothing to type.
    student_query = StudentModel.query.filter_by(is_active=True)
    if class_id:
        student_query = student_query.filter_by(class_id=class_id)
    owed_months = set()
    for student in student_query.all():
        owed_months.update(due_month for due_month, _balance in student_dues_months(student.id))
    month_options = sorted(owed_months | {month_year, current_month()},
                           key=_month_sort_key, reverse=True)
    return render_template('fee_reminders.html',
                           month_year=month_year,
                           month_options=month_options,
                           pending_months=owed_months,
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
        'written_off': round(sum(r['written_off'] for r in summary_rows), 2),
        'balance': round(sum(r['balance'] for r in summary_rows), 2),
        'outstanding': round(student_outstanding_paisa(student_id) / 100.0, 2),
        'credit': round(student_credit_paisa(student_id) / 100.0, 2),
    }
    return render_template('fee_ledger.html', student=student, rows=summary_rows, totals=totals)

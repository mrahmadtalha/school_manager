from datetime import date, datetime
from types import SimpleNamespace

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.models import (
    AutomationSettings, ClassModel, FeeRecordModel, FeeTransaction, MessageQueue, StudentModel,
    ROLE_ACCOUNTANT, ROLE_ADMIN, TXN_CHARGE, TXN_PAYMENT,
)
from app.routes import main
from app.security import role_required
from app.services.audit import current_actor, log_action
from app.services import fee_reminders as fee_reminders_service
from app.services import admission_fee
from app.services.fee_ledger import (
    DuplicateReferenceError, advance_credit_enabled, current_month, ensure_charge,
    ledger_totals, next_reference, payment_allocation_lines,
    payment_allocation_summary,
    record_refund, record_writeoff, reconcile, recompute_fee_record, record_payment,
    orphaned_settlements, repair_allocations,
    reference_in_use, set_month_charge, student_credit_paisa, student_dues_months,
    student_month_outstanding_paisa, student_outstanding_paisa, student_summary,
    transactions_for, void_transaction,
)
from app.services.whatsapp_automation import normalize_whatsapp_number

PAYMENT_METHODS = ('cash', 'bank', 'online', 'other')

# --------------------------------------------------------------------------- #
# Returning to the fees list with the same filters
#
# The filters live in the query string (see ``fees_list``).  A form or a link
# cannot forward the current query string on its own, so the active filters are
# carried through the receipt round-trip as ``return_*`` values.  Everything is
# whitelisted and rebuilt server-side with url_for -- a return URL is never
# taken verbatim from the request, which would be an open redirect.
# --------------------------------------------------------------------------- #

#: query-string name -> (return form/param name, coercion)
RETURN_FILTERS = {
    'class_id': ('return_class_id', 'int'),
    'month_year': ('return_month_year', 'text'),
    'show_unpaid': ('return_show_unpaid', 'bool01'),
    'ref_query': ('return_ref_query', 'text'),
}


def _coerce_filter(kind, value):
    """Coerce one reported filter value; None when it is not usable."""
    if kind == 'int':
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None
    if kind == 'bool01':
        return '1' if str(value).strip() in ('1', 'true', 'yes', 'on') else '0'
    text = str(value or '').strip()
    return text or None


def list_return_filters(class_id=None, month_year=None, show_unpaid=False,
                        ref_query=None):
    """Build the ``return_*`` values for the fees list currently being viewed.

    Called by ``fees_list`` with its *resolved* filter values (after defaults),
    so the hidden form fields describe exactly what the user is looking at.
    The Collect Fee form posts to a URL with no query string, so these have to
    travel in the form body rather than being read back from request.args.
    """
    values = {}
    if class_id:
        values['return_class_id'] = str(class_id)
    if month_year:
        values['return_month_year'] = str(month_year).strip()
    if ref_query:
        values['return_ref_query'] = str(ref_query).strip()
    # Always record the view mode so "By Class" vs "All Unpaid" round-trips even
    # when the other filters happen to be empty.
    values['return_show_unpaid'] = '1' if show_unpaid else '0'
    return values


def return_filter_values(source):
    """Read and validate ``return_*`` values into fees-list query arguments.

    Unknown keys are ignored and every value is coerced, so nothing from the
    request can influence the redirect target beyond these four fields.
    """
    if source is None:
        return {}
    resolved = {}
    for query_name, (return_name, kind) in RETURN_FILTERS.items():
        if return_name not in source:
            continue
        value = _coerce_filter(kind, source.get(return_name))
        if value is not None:
            resolved[query_name] = value
    return resolved


def receipt_return_args(source):
    """Validate ``return_*`` values, keyed by their ``return_*`` names.

    Used when building the receipt URL, so the receipt can hand them straight
    back to ``back_to_fees_url`` without re-parsing.
    """
    if source is None:
        return {}
    resolved = {}
    for _query_name, (return_name, kind) in RETURN_FILTERS.items():
        if return_name not in source:
            continue
        value = _coerce_filter(kind, source.get(return_name))
        if value is not None:
            resolved[return_name] = value
    return resolved


def back_to_fees_url(**kwargs):
    """URL for the fees list, restoring the given filters.

    Accepts either the ``return_*`` names (as carried on the receipt URL) or the
    plain query names, and ignores anything else. With no usable filter it falls
    back to the plain list, so the link is always safe.
    """
    by_return_name = {return_name: query_name
                      for query_name, (return_name, _kind) in RETURN_FILTERS.items()}
    allowed = {}
    for key, value in kwargs.items():
        if key in RETURN_FILTERS:
            allowed[key] = value
        elif key in by_return_name:
            allowed[by_return_name[key]] = value
    if not allowed:
        return url_for('main.fees_list')
    return url_for('main.fees_list', **allowed)


@main.route('/fees', methods=['GET'])
def fees_list():
    selected_class_id = request.args.get('class_id', type=int)
    month_year = (request.args.get('month_year') or '').strip() or current_month()
    show_unpaid = request.args.get('show_unpaid', '0') == '1'
    ref_query = (request.args.get('ref_query') or request.args.get('reference') or request.args.get('q') or '').strip()

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

    if ref_query:
        matching_ids = {
            txn.student_id for txn in FeeTransaction.query.filter(
                FeeTransaction.reference.ilike(f'%{ref_query}%')
            ).all()
        }
        students = [student for student in students if student.id in matching_ids]

    records = {r.student_id: r for r in
               FeeRecordModel.query.filter_by(month_year=month_year).all()}

    # Read-only view: the ledger is the source of truth, so students without a
    # cached summary row are rendered straight from their transactions.  A page
    # load must never write (an expired-license school keeps full read access
    # here) - charges are created explicitly via POST /fees/generate-charges.
    pending_charges = 0
    for student in students:
        record = records.get(student.id)
        if record is None:
            charged, paid, _written_off = ledger_totals(student.id, month_year)
            if charged == 0 and (student.monthly_fee or 0) > 0:
                pending_charges += 1
            if charged == 0 and paid == 0:
                record = None
            else:
                status = ('Paid' if charged > 0 and paid + 0.001 >= charged
                          else 'Partial' if paid > 0 else 'Pending')
                record = SimpleNamespace(amount_due=charged, amount_paid=paid,
                                         status=status, balance=round(charged - paid, 2))

        latest_payment = None
        if record is not None:
            latest_payment = (FeeTransaction.query
                             .filter_by(student_id=student.id, month_year=month_year,
                                        txn_type='payment', is_void=False)
                             .order_by(FeeTransaction.created_at.desc(), FeeTransaction.id.desc())
                             .first())

        row = {
            'student': student,
            'record': record,
            'due': record.amount_due if record else 0.0,
            'paid': record.amount_paid if record else 0.0,
            'balance': max((record.balance if record else 0.0), 0.0),
            'class_name': student.class_info.name if student.class_info else '—',
            'reference': latest_payment.reference if latest_payment else None,
            'due_months': student_dues_months(student.id),
            'total_outstanding': round(student_outstanding_paisa(student.id) / 100.0, 2),
            'advance_credit': round(student_credit_paisa(student.id) / 100.0, 2),
        }

        # Which "Apply to" choices make sense for THIS student right now.
        #  - money still owed  -> a month can be targeted (never advance)
        #  - nothing owed      -> only an advance payment is left to record
        row['has_dues'] = row['total_outstanding'] > 0.005
        row['can_advance'] = not row['has_dues']
        row['this_month_balance'] = round(
            student_month_outstanding_paisa(student.id, month_year) / 100.0, 2)
        row['this_month_paid'] = (row['can_advance']
                                  and row['this_month_balance'] <= 0.005)
        if show_unpaid and record and record.amount_due > 0 and record.amount_paid + 0.001 >= record.amount_due:
            continue
        fee_data.append(row)

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

    selected_class_fee = None
    if selected_class_id:
        for class_obj in classes:
            if class_obj.id == selected_class_id:
                selected_class_fee = class_obj.monthly_fee
                break

    return render_template('fees.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           month_year=month_year,
                           fee_data=fee_data,
                           pending_charges=pending_charges,
                           show_unpaid=show_unpaid,
                           summary=summary,
                           payment_methods=PAYMENT_METHODS,
                           admission_settings=admission_fee.settings_context(),
                           admission_is_admin=admission_fee.is_admin(current_user),
                           class_fee_by_class={str(c.id): c.monthly_fee
                                               for c in classes
                                               if c.monthly_fee is not None},
                           selected_class_fee=selected_class_fee,
                           ref_query=ref_query,
                           suggested_reference=next_reference(),
                           today=date.today(),
                           # Carried to the receipt so "Back to Fees" can restore
                           # exactly this filtered view.
                           return_filters=list_return_filters(
                               class_id=selected_class_id, month_year=month_year,
                               show_unpaid=show_unpaid, ref_query=ref_query))


@main.route('/fees/generate-charges', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def generate_monthly_charges():
    """Create the monthly fee charge for every enrolled student (explicitly).

    Posting the monthly charge is a deliberate billing action, not a side
    effect of opening the page: only this endpoint writes charges, so the fees
    list stays viewable (read-only) for schools with an expired license.  Any
    month may be generated (e.g. to bill a month that was skipped).
    """
    month_year = (request.form.get('month_year') or '').strip() or current_month()
    class_filter = request.form.get('class_id', type=int)

    query = StudentModel.query.filter_by(is_active=True)
    if class_filter:
        query = query.filter_by(class_id=class_filter)
    students = query.order_by(StudentModel.class_id, StudentModel.student_name).all()

    created = 0
    for student in students:
        if not (student.monthly_fee or 0) > 0:
            continue
        existing = FeeTransaction.query.filter_by(
            student_id=student.id, month_year=month_year,
            txn_type=TXN_CHARGE, is_void=False).first()
        if existing:
            continue
        ensure_charge(student, month_year)
        recompute_fee_record(student.id, month_year)
        created += 1

    db.session.commit()
    if created:
        log_action('charge', entity_type='FeeTransaction',
                   summary=f'Generated {created} monthly fee charge(s) for {month_year}')
        db.session.commit()
        flash(f'Generated {created} monthly fee charge(s) for {month_year}.', 'success')
    else:
        flash(f'All monthly charges for {month_year} were already posted.', 'info')
    return redirect(url_for('main.fees_list', month_year=month_year,
                            class_id=class_filter or None))


@main.route('/fees/class-bulk-update', methods=['POST'])
def bulk_update_class_fees():
    class_id = request.form.get('class_id', type=int)
    fee_input = (request.form.get('monthly_fee') or '').strip().replace(',', '')

    if request.form.get('confirm_bulk_update') != 'yes':
        flash('Bulk fee update requires confirmation before changes are saved.', 'danger')
        return redirect(url_for('main.fees_list', class_id=class_id))

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
        return redirect(url_for('main.fees_list', class_id=class_id))

    # Keep the class standard fee (managed on the Classes page) in sync.
    previous_standard = class_obj.monthly_fee
    class_obj.monthly_fee = fee_value
    if previous_standard != fee_value:
        log_action('settings_change', entity_type='ClassModel', entity_id=class_obj.id,
                   summary=f'Class standard fee for {class_obj.name} set to '
                           f'{fee_value if fee_value is not None else "none"}',
                   before={'monthly_fee': previous_standard},
                   after={'monthly_fee': fee_value})

    students = StudentModel.query.filter_by(class_id=class_id, is_active=True).all()

    # A bulk update changes the students' monthly_fee setting (so future
    # charges use it) and the CURRENT calendar month's charge only when that
    # charge has no payments.  Past months' charges, and any charge with
    # payments, are never modified.
    target_month = current_month()
    updated_charges = 0
    left_paid = 0
    for student in students:
        before = student.monthly_fee
        student.monthly_fee = fee_value
        log_action('charge', entity_type='StudentModel', entity_id=student.id,
                   summary=f'Monthly fee for {student.student_name} set to '
                           f'{fee_value if fee_value is not None else "none"}',
                   before={'monthly_fee': before}, after={'monthly_fee': fee_value})
        charge = (FeeTransaction.query
                  .filter_by(student_id=student.id, month_year=target_month,
                             txn_type=TXN_CHARGE, is_void=False)
                  .order_by(FeeTransaction.id.asc()).first())
        if charge is None:
            recompute_fee_record(student.id, target_month)
            continue
        has_payments = FeeTransaction.query.filter_by(
            student_id=student.id, month_year=target_month,
            txn_type=TXN_PAYMENT, is_void=False).first() is not None
        if has_payments:
            left_paid += 1
        elif fee_value is not None:
            set_month_charge(student, target_month, fee_value)
            updated_charges += 1
        recompute_fee_record(student.id, target_month)

    db.session.commit()
    if fee_value is None:
        flash(f'Monthly fee cleared for {len(students)} student(s) in '
              f'{class_obj.name}. Past months were not touched.', 'success')
    else:
        flash(f'Monthly fee set to {fee_value:,.0f} for {len(students)} student(s) in '
              f'{class_obj.name}; {target_month} charges updated for {updated_charges} '
              f'student(s), {left_paid} left unchanged (already have payments). '
              f'Past months were not touched.', 'success')
    return redirect(url_for('main.fees_list', class_id=class_id, month_year=target_month))


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
            if existing_charge is None or abs(due_override - existing_amount) > 0.005:
                # Explicit charge change: a month with payments must be
                # corrected by voiding the payment, never by rewriting the charge.
                has_payments = FeeTransaction.query.filter_by(
                    student_id=student.id, month_year=month_year,
                    txn_type=TXN_PAYMENT, is_void=False).first() is not None
                if has_payments:
                    flash(f'{month_year} already has payments, so its charged amount can no '
                          'longer be overwritten. Void the payment first if the charge is wrong.', 'danger')
                    return redirect(request.referrer or url_for('main.fees_list', month_year=month_year))
                student.monthly_fee = due_override
                set_month_charge(student, month_year, due_override)

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
        'written_off': round(sum(r['written_off'] for r in summary_rows), 2),
        'balance': round(sum(r['balance'] for r in summary_rows), 2),
        'outstanding': round(student_outstanding_paisa(student_id) / 100.0, 2),
        'credit': round(student_credit_paisa(student_id) / 100.0, 2),
    }
    return render_template('fee_ledger.html', student=student, rows=summary_rows, totals=totals)

@main.route('/fees/transactions/<int:txn_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def fee_txn_void(txn_id):
    """Void any fee ledger row (payment, charge, adjustment, refund, write-off)
    with a mandatory reason. Voided rows leave every total but stay in history."""
    txn = FeeTransaction.query.get_or_404(txn_id)
    if txn.is_void:
        flash('This transaction is already voided.', 'warning')
        return redirect(request.referrer or url_for('main.fees_list'))

    reason = (request.form.get('void_reason') or '').strip()
    if not reason:
        flash('A reason is required to void a transaction.', 'danger')
        return redirect(request.referrer or url_for('main.fees_list'))

    student = txn.student_info
    affected = void_transaction(txn, reason=reason,
                                actor_name=getattr(current_user, 'username', None) or 'system')
    for month in affected:
        recompute_fee_record(student.id, month)
    log_action('void', entity_type='FeeTransaction', entity_id=txn.id,
               before={'amount': txn.amount, 'type': txn.txn_type, 'month': txn.month_year},
               summary='Fee %s voided for %s (%s): %s'
                       % (txn.type_label, student.student_name if student else txn.student_id,
                          '{:,.0f}'.format(txn.amount), reason))
    db.session.commit()
    flash('%s of Rs. %s voided — excluded from all totals, kept in history.'
          % (txn.type_label, '{:,.2f}'.format(txn.amount)), 'warning')
    return redirect(request.referrer or url_for('main.fee_student_ledger', student_id=txn.student_id))


@main.route('/fees/payments/<int:txn_id>/refund', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def fee_payment_refund(txn_id):
    """Refund part of a payment (linked to the original receipt)."""
    payment = FeeTransaction.query.filter_by(id=txn_id, txn_type=TXN_PAYMENT).first_or_404()
    if payment.is_void:
        flash('A voided payment cannot be refunded.', 'warning')
        return redirect(url_for('main.fee_student_ledger', student_id=payment.student_id))

    try:
        amount = float(request.form.get('amount') or 0)
    except (TypeError, ValueError):
        amount = 0.0
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('A reason is required for a refund.', 'danger')
        return redirect(url_for('main.fee_student_ledger', student_id=payment.student_id))

    try:
        refund, affected = record_refund(payment, amount, note=reason)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
        return redirect(url_for('main.fee_student_ledger', student_id=payment.student_id))

    for month in affected:
        recompute_fee_record(payment.student_id, month)
    log_action('payment', entity_type='FeeTransaction', entity_id=refund.id,
               summary='Refund of Rs. %s against payment #%d for %s: %s'
                       % ('{:,.0f}'.format(refund.amount), payment.id,
                          payment.student_info.student_name, reason))
    db.session.commit()
    flash('Refund of Rs. %s recorded against receipt %s.'
          % ('{:,.2f}'.format(refund.amount), payment.reference or '#%d' % payment.id), 'warning')
    return redirect(url_for('main.fee_student_ledger', student_id=payment.student_id))


@main.route('/fees/students/<int:student_id>/writeoff', methods=['POST'])
@role_required(ROLE_ADMIN)
def fee_student_writeoff(student_id):
    """Write off a student's entire outstanding balance (owner decision).

    Turned off while FEATURE_ADVANCE_CREDIT_WRITEOFF is disabled: even a
    crafted admin POST is refused and creates nothing."""
    if not current_app.config.get('FEATURE_ADVANCE_CREDIT_WRITEOFF', False):
        flash('This feature is turned off.', 'danger')
        return redirect(url_for('main.fee_student_ledger', student_id=student_id))
    student = StudentModel.query.get_or_404(student_id)
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('A reason is required to write off dues.', 'danger')
        return redirect(url_for('main.fee_student_ledger', student_id=student_id))

    try:
        txn, affected = record_writeoff(student, note=reason)
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
        return redirect(url_for('main.fee_student_ledger', student_id=student_id))

    for month in affected:
        recompute_fee_record(student.id, month)
    log_action('adjustment', entity_type='FeeTransaction', entity_id=txn.id,
               summary='Dues written off for %s: Rs. %s (%s)'
                       % (student.student_name, '{:,.0f}'.format(txn.amount), reason))
    db.session.commit()
    flash('Dues of Rs. %s written off for %s — removed from Receivables, '
          'reported as Written Off.' % ('{:,.2f}'.format(txn.amount), student.student_name),
          'warning')
    return redirect(url_for('main.fee_student_ledger', student_id=student_id))

"""Fee list, return-filter helpers and shared fee-page helpers."""

from datetime import date
from types import SimpleNamespace
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from app.database import db
from app.models import (
    ClassModel,
    FeeRecordModel,
    FeeTransaction,
    StudentModel,
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    TXN_ADJUSTMENT,
    TXN_CHARGE,
    TXN_PAYMENT,
)
from app.routes import main
from app.security import role_required
from app.services.audit import log_action
from app.services import admission_fee
from app.services.fee_ledger import (
    current_month,
    ensure_charge,
    ledger_totals,
    next_reference,
    record_adjustment,
    recompute_fee_record,
    set_month_charge,
    student_credit_paisa,
    student_dues_months,
    student_month_outstanding_paisa,
    student_outstanding_paisa,
)
from app.services.fee_ledger import _month_sort_key


PAYMENT_METHODS = ('cash', 'bank', 'online', 'other')


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
    pending_months = set()      # months in which someone in this view still owes money
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

        pending_months.update(due_month for due_month, _balance in row['due_months'])

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

    # Billing-month dropdown: only months that still have unpaid fees in this view,
    # plus the current month and whatever month is open now (newest first).
    month_options = sorted(pending_months | {month_year, current_month()},
                           key=_month_sort_key, reverse=True)

    return render_template('fees.html',
                           classes=classes,
                           selected_class_id=selected_class_id,
                           month_year=month_year,
                           month_options=month_options,
                           pending_months=pending_months,
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


@main.route('/fees/extra-charge', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def add_extra_charge():
    """One-off charge (trip, event, party...) added to a month's fee.

    It is an ordinary ledger *adjustment*: it is owed like the monthly fee,
    payments settle it, it shows on the fee list and receipt, and it can be
    voided with a reason.  The student's standing monthly fee is never touched.
    Applies to every active student of the class, or to one student when
    ``student_id`` is posted.  Posting the same event twice does not charge a
    student twice.
    """
    month_year = (request.form.get('month_year') or '').strip() or current_month()
    event_name = (request.form.get('event_name') or '').strip()[:80]
    class_id = request.form.get('class_id', type=int)
    student_id = request.form.get('student_id', type=int)
    back = url_for('main.fees_list', class_id=class_id or None, month_year=month_year)

    try:
        amount = float(request.form.get('amount') or 0)
    except ValueError:
        amount = 0.0
    if not event_name:
        flash('Type the name of the event or trip (for example "Picnic").', 'danger')
        return redirect(back)
    if amount <= 0:
        flash('The extra charge must be more than zero.', 'danger')
        return redirect(back)

    query = StudentModel.query.filter_by(is_active=True)
    if student_id:
        query = query.filter_by(id=student_id)
    elif class_id:
        query = query.filter_by(class_id=class_id)
    else:
        flash('Choose a class first.', 'danger')
        return redirect(back)
    students = query.all()
    if not students:
        flash('No active students found for this charge.', 'warning')
        return redirect(back)

    note = f'Extra charge: {event_name}'
    added = skipped = 0
    for student in students:
        already = FeeTransaction.query.filter_by(
            student_id=student.id, month_year=month_year,
            txn_type=TXN_ADJUSTMENT, note=note, is_void=False).first()
        if already:
            skipped += 1
            continue
        # The month's normal charge must exist first, so the extra amount is
        # an addition to the fee and not the only charge of the month.
        if (student.monthly_fee or 0) > 0:
            ensure_charge(student, month_year)
        record_adjustment(student, month_year, amount, note=note)
        recompute_fee_record(student.id, month_year)
        added += 1

    if added:
        log_action('charge', entity_type='FeeTransaction',
                   summary=f'Extra charge "{event_name}" of Rs. {amount:,.0f} added for '
                           f'{added} student(s) in {month_year}',
                   after={'event': event_name, 'amount': round(amount, 2),
                          'students': added, 'month_year': month_year})
    db.session.commit()
    message = (f'"{event_name}": Rs. {amount:,.0f} added to {month_year} for {added} student(s). '
               'It is part of their fee now; the monthly fee on the student record is unchanged.')
    if skipped:
        message += f' {skipped} already had this charge and were skipped.'
    flash(message, 'success' if added else 'info')
    return redirect(back)


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

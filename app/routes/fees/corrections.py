"""Fee corrections: void a payment, refund, and student write-off."""

from flask import current_app, flash, redirect, request, url_for
from flask_login import current_user
from app.database import db
from app.models import FeeTransaction, StudentModel, ROLE_ACCOUNTANT, ROLE_ADMIN, TXN_PAYMENT
from app.routes import main
from app.security import role_required
from app.services.audit import log_action
from app.services.fee_ledger import (
    record_refund,
    record_writeoff,
    recompute_fee_record,
    void_transaction,
)


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

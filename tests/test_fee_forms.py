"""Regression tests from manual testing on the migrated copy (fee forms).

Reproduction data — one student, four charged months, two partly/fully paid,
exactly like production (total pending 7,120):
    October 2026  2,400 / paid 200      February 2026  2,520 / paid 2,400
    October 2025  2,400 / paid 0        February 2025  2,400 / paid 0
"""

from datetime import date

import pytest

from app.database import db
from app.models import ClassModel, FeeTransaction, StudentModel
from app.services.fee_ledger import (ensure_charge, record_payment,
                                     student_dues_months,
                                     student_month_outstanding_paisa)

@pytest.fixture()
def maryam(app):
    klass = ClassModel(name='Play Group', monthly_fee=2400.0)
    db.session.add(klass)
    db.session.flush()
    student = StudentModel(roll_number=1005, student_name='Maryam Butt',
                           father_name='F Maryam', guardian_phone='03001110005',
                           address='X', class_id=klass.id, monthly_fee=2400.0)
    db.session.add(student)
    db.session.commit()

    ensure_charge(student, 'October 2026', amount=2400.0)
    ensure_charge(student, 'February 2026', amount=2520.0)
    ensure_charge(student, 'October 2025', amount=2400.0)
    ensure_charge(student, 'February 2025', amount=2400.0)
    db.session.commit()
    # The two existing payments, each pinned to its own month.
    record_payment(student, 'October 2026', 200.0, method='cash',
                   apply_month='October 2026', payment_date=date(2026, 10, 2))
    record_payment(student, 'February 2026', 2400.0, method='cash',
                   apply_month='February 2026', payment_date=date(2026, 2, 10))
    db.session.commit()
    return {'student_id': student.id, 'class_id': klass.id}


def _month_outstanding(student_id, label):
    return round(student_month_outstanding_paisa(student_id, label) / 100.0, 2)


def test_collect_fee_oldest_first_saves_despite_existing_payment(app, maryam,
                                                                 admin_client):
    """Posting the real collect-fee form (the readonly due field included)
    for a month that already has a partial payment must SAVE, and the money
    goes to the oldest unpaid charge."""
    student_id = maryam['student_id']
    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026',
        'amount_paid': '1000',
        'amount_due_override': '2400',      # what the readonly field posts
        'apply_to': 'oldest',
        'method': 'cash',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'can no longer be overwritten' not in response.data

    with app.app_context():
        payments = FeeTransaction.query.filter_by(
            student_id=student_id, txn_type='payment', is_void=False).all()
        assert len(payments) == 3                    # the new payment was saved
        # Oldest unpaid charge first: February 2025 absorbs the 1,000.
        assert _month_outstanding(student_id, 'February 2025') == 1400.0
        assert _month_outstanding(student_id, 'October 2026') == 2200.0
        assert _month_outstanding(student_id, 'October 2025') == 2400.0


def test_specific_month_dropdown_lists_only_months_with_dues(app, maryam,
                                                             admin_client):
    student_id = maryam['student_id']
    with app.app_context():
        months = student_dues_months(student_id)
    assert months == [('February 2025', 2400.0), ('October 2025', 2400.0),
                      ('February 2026', 120.0), ('October 2026', 2200.0)]

    body = admin_client.get(
        '/fees?class_id=%d&month_year=October%%202026' % maryam['class_id']) \
        .get_data(as_text=True)
    assert 'October 2025 - Rs 2,400' in body          # oldest dues first
    assert 'February 2026 - Rs 120' in body
    assert 'No dues' not in body                       # Maryam has dues


def test_specific_month_dropdown_no_dues_on_page(admin_client, app):
    klass = ClassModel(name='Clear Class', monthly_fee=2400.0)
    db.session.add(klass)
    db.session.flush()
    clear = StudentModel(roll_number=1007, student_name='Clear Nada',
                         father_name='F Nada', guardian_phone='03001110007',
                         address='X', class_id=klass.id, monthly_fee=2400.0)
    db.session.add(clear)
    db.session.commit()

    body = admin_client.get(
        '/fees?class_id=%d&month_year=October%%202026' % klass.id) \
        .get_data(as_text=True)
    # The dues-month service always reports nothing for a zero-dues student.
    with app.app_context():
        from app.services.fee_ledger import student_dues_months
        assert student_dues_months(clear.id) == []
        advance_on = app.config.get('FEATURE_ADVANCE_CREDIT_WRITEOFF', False)
    if advance_on:
        # With advance credit on, a zero-dues student keeps the collect form so
        # an advance payment can be recorded (D4), instead of "Fully paid".
        assert 'payModal%d' % clear.id in body
    else:
        assert 'Fully paid' in body
        assert 'payModal%d' % clear.id not in body


def test_collect_modal_prefills_total_outstanding_and_toggles(app, maryam,
                                                              admin_client):
    """The amount field auto-fills with the viewed month's OWN dues (never
    the all-months total), while the helper text shows the total outstanding;
    the Specific-month control only shows once 'Specific month' is selected."""
    body = admin_client.get(
        '/fees?class_id=%d&month_year=October%%202026' % maryam['class_id']) \
        .get_data(as_text=True)
    # PART 4: every dues month with its balance, oldest first, plus the total.
    assert ('Dues: February 2025 - Rs 2,400 · October 2025 - Rs 2,400 · '
            'February 2026 - Rs 120 · October 2026 - Rs 2,200') in body
    assert 'Total outstanding: Rs 7,120.00' in body
    assert 'id="apply_to_' in body
    assert 'id="applyMonth_' in body and 'hidden' in body   # hidden until chosen
    assert "sel.value !== 'month'" in body             # the toggle is wired


def test_receipt_shows_total_remaining_dues_and_one_page_css(app, maryam,
                                                              admin_client):
    receipt = admin_client.get(
        '/fees/receipt/%d/October%%202026' % maryam['student_id'])
    assert receipt.status_code == 200
    body = receipt.get_data(as_text=True)
    assert 'Total remaining dues (all months)' in body
    assert 'Rs. 7,120.00' in body
    assert 'Rs. 2,200.00 (October 2026)' in body      # per-month breakdown
    assert 'School Copy' in body and 'Student / Parent Copy' in body
    # One-page A4 print contract.
    assert 'size: A4 portrait' in body
    assert 'page-break-inside: avoid' in body


def test_overpayment_rejected_and_no_credit_created(app, maryam, admin_client):
    """A payment above the student's total dues is rejected server-side with a
    plain message; no transaction and no advance-credit balance is created."""
    student_id = maryam['student_id']
    with app.app_context():
        before = FeeTransaction.query.filter_by(
            student_id=student_id, txn_type='payment', is_void=False).count()
    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026', 'amount_paid': '8000',
        'amount_due_override': '2400', 'apply_to': 'oldest', 'method': 'cash',
    }, follow_redirects=True)
    assert b"more than the student&#39;s total dues of Rs 7120.00" in response.data
    with app.app_context():
        assert FeeTransaction.query.filter_by(
            student_id=student_id, txn_type='payment', is_void=False).count() == before
        from app.services.fee_ledger import student_credit_paisa
        assert student_credit_paisa(student_id) == 0
        assert student_month_outstanding_paisa(student_id, 'October 2026') == 220000


def test_exact_total_settles_to_zero_then_post_rejected(app, maryam, admin_client):
    """Paying the exact remaining balance (7,120) settles every month to zero;
    a further POST is rejected with 'This student has no dues.'"""
    student_id = maryam['student_id']
    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026', 'amount_paid': '7120',
        'amount_due_override': '2400', 'apply_to': 'oldest', 'method': 'cash',
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        from app.services.fee_ledger import (student_credit_paisa,
                                             student_outstanding_paisa)
        assert student_outstanding_paisa(student_id) == 0
        assert student_credit_paisa(student_id) == 0
        for label in ('October 2026', 'February 2026', 'October 2025', 'February 2025'):
            assert student_month_outstanding_paisa(student_id, label) == 0

    response = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026', 'amount_paid': '100', 'method': 'cash',
    }, follow_redirects=True)
    assert b'This student has no dues.' in response.data
    with app.app_context():
        assert FeeTransaction.query.filter_by(
            student_id=student_id, txn_type='payment', is_void=False).count() == 3


def test_two_partial_payments_in_a_row_then_zero_blocks(app, maryam, admin_client):
    """Two partial payments in a row both save and allocate oldest-first; once
    the total reaches zero, a further POST is rejected."""
    student_id = maryam['student_id']
    first = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026', 'amount_paid': '2000',
        'amount_due_override': '2400', 'apply_to': 'oldest', 'method': 'cash',
    }, follow_redirects=True)
    assert b'more than the student' not in first.data
    second = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026', 'amount_paid': '5120',
        'amount_due_override': '2400', 'apply_to': 'oldest', 'method': 'cash',
    }, follow_redirects=True)
    assert b'more than the student' not in second.data
    with app.app_context():
        from app.services.fee_ledger import (student_credit_paisa,
                                             student_outstanding_paisa)
        assert student_outstanding_paisa(student_id) == 0
        assert student_credit_paisa(student_id) == 0
    third = admin_client.post(f'/fees/pay/{student_id}', data={
        'month_year': 'October 2026', 'amount_paid': '50', 'method': 'cash',
    }, follow_redirects=True)
    assert b'This student has no dues.' in third.data


def test_flag_off_hides_labels_and_blocks_writeoff(app, maryam, admin_client):
    """With FEATURE_ADVANCE_CREDIT_WRITEOFF off: no 'Advance credit' or
    'Written off' labels on the money pages, the write-off button is gone, and
    a crafted write-off POST is refused without creating anything."""
    student_id = maryam['student_id']
    with app.app_context():
        assert db.session.get(StudentModel, student_id) is not None

    pages = {
        'fees list': admin_client.get(
            '/fees?class_id=%d&month_year=October%%202026' % maryam['class_id']),
        'student ledger': admin_client.get(f'/fees/student/{student_id}'),
        'student 360': admin_client.get(f'/students/{student_id}/history'),
        'fee receipt': admin_client.get(
            '/fees/receipt/%d/October%%202026' % student_id),
        'financial summary': admin_client.get('/financials/summary'),
        'student outstanding list': admin_client.get(
            '/financials/student-outstanding?status=all'),
        'dashboard': admin_client.get('/'),
    }
    for page_name, page in pages.items():
        assert page.status_code == 200, '%s returned %s' % (page_name, page.status_code)
        text = page.get_data(as_text=True)
        assert 'Advance credit' not in text, '%s still shows Advance credit' % page_name
        assert 'Written off' not in text, '%s still shows Written off' % page_name
        assert 'Write off dues' not in text, '%s still shows the write-off button' % page_name

    # Crafted admin POST: refused, nothing created.
    response = admin_client.post(f'/fees/students/{student_id}/writeoff', data={
        'reason': 'crafted POST',
    }, follow_redirects=True)
    assert 'This feature is turned off.' in response.get_data(as_text=True)
    with app.app_context():
        assert FeeTransaction.query.filter_by(
            student_id=student_id, txn_type='writeoff').count() == 0
        from app.services.fee_ledger import student_outstanding_paisa
        assert student_outstanding_paisa(student_id) > 0   # dues untouched


def test_fees_list_fully_paid_button_state(app, maryam, admin_client):
    """A student with zero total dues gets a disabled 'Fully paid' button and
    no collect modal; a student with dues keeps an active button."""
    with app.app_context():
        mate = StudentModel(roll_number=1009, student_name='Fully Paid Ali',
                            father_name='F Ali', guardian_phone='03001110009',
                            address='X', class_id=maryam['class_id'],
                            monthly_fee=2400.0)
        db.session.add(mate)
        db.session.commit()
        mate_id = mate.id
        advance_on = app.config.get('FEATURE_ADVANCE_CREDIT_WRITEOFF', False)

    body = admin_client.get(
        '/fees?class_id=%d&month_year=October%%202026' % maryam['class_id'])         .get_data(as_text=True)
    if advance_on:
        # With advance credit on, a fully paid student keeps an active collect
        # form too (D4) so an advance payment can be recorded.
        assert 'payModal%d' % mate_id in body
    else:
        assert 'Fully paid' in body
        disabled_pos = body.find('Fully paid')
        assert 'disabled' in body[max(0, disabled_pos - 300):disabled_pos]
        assert 'payModal%d' % mate_id not in body      # no modal for the paid student
    assert 'payModal%d' % maryam['student_id'] in body  # active for Maryam


def test_bulk_update_confirmation_gate(app, maryam, admin_client):
    # Without the confirmation flag: nothing changes.
    response = admin_client.post('/fees/class-bulk-update', data={
        'class_id': str(maryam['class_id']), 'monthly_fee': '3900',
    }, follow_redirects=True)
    assert b'requires confirmation' in response.data
    with app.app_context():
        student = db.session.get(StudentModel, maryam['student_id'])
        assert student.monthly_fee == 2400.0

    # With the confirmation flag: saved.
    response = admin_client.post('/fees/class-bulk-update', data={
        'class_id': str(maryam['class_id']), 'monthly_fee': '3900',
        'confirm_bulk_update': 'yes',
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        student = db.session.get(StudentModel, maryam['student_id'])
        assert student.monthly_fee == 3900.0


def test_bulk_update_never_touches_past_months_or_paid_charges(app, maryam,
                                                               admin_client,
                                                               monkeypatch):
    # The scenario treats October 2026 as the current calendar month; pin it
    # so the test does not break when the real month changes.
    monkeypatch.setattr('app.routes.fees.core.current_month',
                        lambda: 'October 2026')
    student_id, class_id = maryam['student_id'], maryam['class_id']
    # A classmate whose current-month charge has NO payments gets updated.
    with app.app_context():
        mate = StudentModel(roll_number=1008, student_name='Hamza Rauf',
                            father_name='F Hamza', guardian_phone='03001110008',
                            address='X', class_id=class_id, monthly_fee=2400.0)
        db.session.add(mate)
        db.session.commit()
        ensure_charge(mate, 'October 2026', amount=2400.0)
        db.session.commit()
        mate_id = mate.id

    response = admin_client.post('/fees/class-bulk-update', data={
        'class_id': str(class_id), 'monthly_fee': '3900',
        'confirm_bulk_update': 'yes',
    }, follow_redirects=True)
    assert b'left unchanged (already have payments)' in response.data

    with app.app_context():
        # Past months are never modified.
        assert _month_outstanding(student_id, 'February 2025') == 2400.0
        assert _month_outstanding(student_id, 'October 2025') == 2400.0
        assert _month_outstanding(student_id, 'February 2026') == 120.0
        # Maryam's current-month charge has payments → untouched.
        assert _month_outstanding(student_id, 'October 2026') == 2200.0
        charge = FeeTransaction.query.filter_by(
            student_id=student_id, month_year='October 2026',
            txn_type='charge', is_void=False).one()
        assert charge.amount == 2400.0
        # The classmate's unpaid current-month charge IS updated.
        assert _month_outstanding(mate_id, 'October 2026') == 3900.0

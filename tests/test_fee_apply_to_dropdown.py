"""Requirement 19 section 3: the Apply To dropdown in every state.

Dues pending        -> Oldest (default) + Specific month with the real per-month
                       balances; Advance must not be offered.
Nothing owed        -> Advance Payment is offered (and is the default when the
                       month on screen is already paid); normal collection stays
                       available when the month is still unpaid.
Advance posted by
hand while dues
remain              -> the money settles the dues; no credit is created.

The flag-ON mode is used throughout, because that is the mode in which advance
credit and write-offs are reachable at all.
"""

import pytest

from app import create_app
from app.database import db
from app.models import (AdminUser, ClassModel, ROLE_ADMIN, SectionModel,
                        StudentModel)
from app.services.fee_ledger import (ensure_charge, recompute_fee_record,
                                     record_payment)

MONTH = 'October 2026'
PREV = 'September 2026'


@pytest.fixture()
def app_on(tmp_path):
    application = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'FEATURE_ADVANCE_CREDIT_WRITEOFF': True,
        'SQLALCHEMY_DATABASE_URI':
            'sqlite:///' + (tmp_path / 'req19_dropdown.db').as_posix(),
    })
    with application.app_context():
        db.drop_all()
        db.create_all()
        admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='Dropdown Admin')
        admin.set_password('dropdown-test-pass')
        db.session.add(admin)
        db.session.commit()
        application.config['ADMIN_ID'] = admin.id
        yield application
        db.session.remove()


@pytest.fixture()
def admin_client(app_on):
    client = app_on.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(app_on.config['ADMIN_ID'])
        sess['_fresh'] = True
    return client


@pytest.fixture()
def student(app_on):
    """One student at 2,500/month."""
    with app_on.app_context():
        klass = ClassModel(name='Dropdown Class', monthly_fee=2500.0)
        db.session.add(klass)
        db.session.flush()
        section = SectionModel(name='A', class_id=klass.id)
        db.session.add(section)
        db.session.flush()
        pupil = StudentModel(roll_number=991910, student_name='Dropdown Student',
                             father_name='F', guardian_phone='03001991910',
                             address='X', class_id=klass.id, section_id=section.id,
                             monthly_fee=2500.0)
        db.session.add(pupil)
        db.session.flush()
        ids = {'student_id': pupil.id, 'class_id': klass.id, 'section_id': section.id}
        db.session.commit()
        return ids


def _apply_block(client, student_id, class_id, month):
    body = client.get('/fees?class_id=%d&month_year=%s'
                      % (class_id, month.replace(' ', '%20'))
                      ).get_data(as_text=True)
    segment = body.split('id="apply_to_%d"' % student_id)
    if len(segment) < 2:
        return None, body
    return segment[1].split('</select>')[0], body


def _charge(student_id, *months):
    pupil = db.session.get(StudentModel, student_id)
    for month in months:
        ensure_charge(pupil, month)
        db.session.commit()
        recompute_fee_record(pupil.id, month)


# ------------------------------------------------------------------ case 1
def test_case1_dues_pending_offers_oldest_and_month_but_not_advance(
        admin_client, app_on, student):
    sid, cid = student['student_id'], student['class_id']
    with app_on.app_context():
        _charge(sid, MONTH, PREV)

    block, body = _apply_block(admin_client, sid, cid, MONTH)
    assert block, 'collect form missing'
    assert 'value="oldest"' in block
    assert 'selected' in block.split('value="oldest"')[1].split('>')[0], \
        'Oldest dues first must be the default while dues remain'
    assert 'value="month"' in block
    assert 'value="advance"' not in block, 'advance must not be usable with dues'

    # The Specific Month list carries the real remaining balance.
    assert 'September 2026 - Rs' in body
    assert 'still due' in body


# ------------------------------------------------------------------ case 2
def test_case2_nothing_owed_offers_advance(admin_client, app_on, student):
    sid, cid = student['student_id'], student['class_id']
    with app_on.app_context():
        # Only the month on screen is charged, and it is paid up.
        _charge(sid, MONTH)
        record_payment(db.session.get(StudentModel, sid), MONTH, 2500.0,
                       method='cash')
        db.session.commit()
        recompute_fee_record(sid, MONTH)

    block, _body = _apply_block(admin_client, sid, cid, MONTH)
    assert block, 'collect form missing'
    assert 'value="advance"' in block
    assert 'selected' in block.split('value="advance"')[1].split('>')[0]
    assert 'value="oldest"' not in block, \
        'nothing is left to settle monthly, so the month choices are withdrawn'


# ------------------------------------------------------------------ case 3
def test_case3_no_old_dues_month_unpaid_keeps_normal_collection(
        admin_client, app_on, student):
    """No old dues, but the month on screen is unpaid.

    That unpaid month IS the outstanding due, so the normal collection options
    (Oldest dues first, which settles this month; Specific month) are the
    applicable ones and Advance Payment must stay withdrawn.
    """
    sid, cid = student['student_id'], student['class_id']
    with app_on.app_context():
        _charge(sid, MONTH)          # only the current month, unpaid
        from app.services.fee_ledger import student_dues_months
        assert student_dues_months(sid) == [(MONTH, 2500.0)], 'only this month'

    block, body = _apply_block(admin_client, sid, cid, MONTH)
    assert block, 'collect form missing'
    assert 'value="oldest"' in block, 'normal collection must stay available'
    assert 'value="month"' in block
    assert 'value="advance"' not in block, \
        'an unpaid month is a due, so advance must not be offered'
    # The month list shows only the month that is actually owed.
    assert 'October 2026 - Rs' in body
    assert 'September 2026 - Rs' not in body


# ------------------------------------------------------------------ case 4
def test_case4_advance_posted_with_dues_settles_the_dues(
        admin_client, app_on, student):
    sid, cid = student['student_id'], student['class_id']
    with app_on.app_context():
        _charge(sid, MONTH, PREV)

    response = admin_client.post('/fees/pay/%d' % sid, data={
        'month_year': MONTH, 'amount_paid': '5000', 'method': 'cash',
        'reference': '', 'apply_to': 'advance',
    }, follow_redirects=True)
    assert response.status_code == 200

    with app_on.app_context():
        from app.services.fee_ledger import (student_credit_paisa,
                                             student_outstanding_paisa)
        # A crafted 'advance' post cannot park money as credit: all 5,000 settles
        # the two outstanding months and nothing is left over.
        assert student_outstanding_paisa(sid) == 0
        assert student_credit_paisa(sid) == 0

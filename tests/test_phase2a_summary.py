"""Phase 2a: the /financials/summary money page and the student dues list.

Covers the nine money cards (cash vs accrual), the fee and payroll sections,
former students by leaving status, the filtered student-wise dues list, and
the mandatory leaving date/reason rule for SLC Issued and Struck Off.
"""

from datetime import date

import pytest

from app.database import db
from app.models import (ClassModel, Expense, ExpenseCategory, SectionModel,
                        StaffPayroll, StudentModel, TeacherModel)
from app.services import (expense_service, financial_summary as fs,
                          payroll_service)
from app.services.fee_ledger import (ensure_charge, record_payment,
                                     record_writeoff, recompute_fee_record)
from app.services.payroll_service import record_salary_payment


def _month_key():
    today = date.today()
    return '%04d-%02d' % (today.year, today.month)


@pytest.fixture()
def world(app):
    """One class, two sections, students across statuses, payroll + expenses.

    Returns plain IDs: ORM objects created in this fixture's session detach
    once a test opens its own app context, so tests re-query with
    ``db.session.get`` inside the context they use them in.
    """
    teacher = TeacherModel(teacher_id_str='P2A', teacher_name='Ms Phase',
                           qualification='MA')
    klass = ClassModel(name='Phase 2a', monthly_fee=2500.0)
    db.session.add_all([teacher, klass])
    db.session.flush()
    section_a = SectionModel(name='A', class_id=klass.id)
    section_b = SectionModel(name='B', class_id=klass.id)
    db.session.add_all([section_a, section_b])
    db.session.flush()

    def make(name, section, roll):
        student = StudentModel(roll_number=roll, student_name=name,
                               father_name='Father ' + name,
                               guardian_phone='030011111%02d' % roll,
                               address='X', class_id=klass.id,
                               section_id=section.id if section else None,
                               monthly_fee=2500.0)
        db.session.add(student)
        return student

    ali = make('Ali Current', section_a, 8100)
    sara = make('Sara Quiet', section_b, 8101)
    bilal = make('Bilal Fresh', section_a, 8102)
    db.session.commit()
    return {'teacher_id': teacher.id, 'class_id': klass.id,
            'section_a_id': section_a.id, 'section_b_id': section_b.id,
            'ali_id': ali.id, 'sara_id': sara.id, 'bilal_id': bilal.id}


def _archive_via_route(admin_client, student_id, status, reason=None, when=None):
    data = {'status': status}
    if reason is not None:
        data['leaving_reason'] = reason
    if when is not None:
        data['leaving_date'] = when
    return admin_client.post(f'/students/delete/{student_id}', data=data,
                             follow_redirects=True)


def test_money_cards_and_salary_remaining(app, world):
    month_key = _month_key()

    with app.app_context():
        teacher = db.session.get(TeacherModel, world['teacher_id'])
        ali = db.session.get(StudentModel, world['ali_id'])
        expense_service.seed_default_categories()
        prev = payroll_service.shift_month(month_key, -1)
        # Ali: 2,500 this month + 2,500 last month; 4,000 paid this month
        # settles last month fully (arrears) and 1,500 of this month.
        ensure_charge(ali, fs.month_label(prev))
        ensure_charge(ali, fs.month_label(month_key))
        record_payment(ali, fs.month_label(month_key), 4000.0, method='cash',
                       payment_date=date.today())
        # 400 non-salary expense this month.
        utilities = ExpenseCategory.query.filter_by(name='Utilities').one()
        db.session.add(Expense(category_id=utilities.id, amount=400.0,
                               date=date.today()))
        # Current month's payroll is generated but only partly paid: accrual
        # stays visible as Salary Remaining (2,000 due, 1,200 paid).
        payroll_service.generate(month_key, {
            'include_%d' % teacher.id: 'on',
            'base_%d' % teacher.id: '2000',
            'bonus_%d' % teacher.id: '0',
            'deductions_%d' % teacher.id: '0',
        }, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=month_key).one()
        record_salary_payment(record, 1200.0, payment_date=date.today())
        db.session.commit()

        snap = fs.month_snapshot(month_key)
        assert snap['cash_in'] == 4000.0
        assert snap['salaries_paid'] == 1200.0
        assert snap['other_expenses'] == 400.0        # excludes salaries
        assert snap['cash_out'] == 1600.0             # salaries + other
        assert snap['net_position'] == 2400.0         # 4,000 in - 1,600 out
        # Salary Remaining: includes the still-running month, never in cash.
        assert fs.salary_remaining_total() == 800.0
        assert snap['payroll_pending'] == 800.0
        assert snap['payroll'] == 2000.0
        assert snap['payroll_partial_count'] == 1     # 1,200 of 2,000 paid
        assert snap['net_position'] == snap['cash_in'] - snap['cash_out']


def test_fee_month_overview_splits_current_and_arrears(app, world):
    month_key = _month_key()

    with app.app_context():
        ali = db.session.get(StudentModel, world['ali_id'])
        prev = payroll_service.shift_month(month_key, -1)
        ensure_charge(ali, fs.month_label(prev))
        ensure_charge(ali, fs.month_label(month_key))
        record_payment(ali, fs.month_label(month_key), 4000.0, method='cash',
                       payment_date=date.today())
        for m in (prev, month_key):
            recompute_fee_record(ali.id, fs.month_label(m))
        db.session.commit()

        overview = fs.fee_month_overview(month_key)
        assert overview['expected'] == 2500.0
        # Option B default: the OLDEST dues (September) are settled first,
        # so this month's own collection is only the leftover 1,500 and the
        # 2,500 that went to September is arrears recovery.
        assert overview['collected'] == 1500.0
        assert overview['arrears'] == 2500.0
        assert overview['remaining'] == 1000.0
        assert overview['rate'] == 60.0

        snap = fs.month_snapshot(month_key)
        assert snap['fee_collected_current'] == overview['collected']
        assert snap['arrears_recovered'] == overview['arrears']


def test_expense_breakdown_excludes_salaries(app, world):
    month_key = _month_key()

    with app.app_context():
        teacher = db.session.get(TeacherModel, world['teacher_id'])
        expense_service.seed_default_categories()
        utilities = ExpenseCategory.query.filter_by(name='Utilities').one()
        db.session.add(Expense(category_id=utilities.id, amount=400.0,
                               date=date.today()))
        payroll_service.generate(month_key, {
            'include_%d' % teacher.id: 'on',
            'base_%d' % teacher.id: '1000',
            'bonus_%d' % teacher.id: '0',
            'deductions_%d' % teacher.id: '0',
        }, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=teacher.id,
                                              month_year=month_key).one()
        record_salary_payment(record, 1000.0, payment_date=date.today())
        db.session.commit()

        names = [row['name'] for row in
                 fs.expense_breakdown(date.today(), date.today())]
        assert 'Utilities' in names
        assert 'Salaries' not in names


def test_former_students_by_leaving_status(app, world, admin_client):
    with app.app_context():
        prev = payroll_service.shift_month(_month_key(), -1)
        for name, roll in (('Former SLC', 8110), ('Former Struck', 8111),
                           ('Former Grad', 8112)):
            student = StudentModel(roll_number=roll, student_name=name,
                                   father_name='F ' + name,
                                   guardian_phone='03002222%04d' % roll,
                                   address='X', class_id=world['class_id'],
                                   monthly_fee=2500.0)
            db.session.add(student)
            db.session.commit()
            if name == 'Former SLC':
                ensure_charge(student, fs.month_label(prev), amount=3000.0)
            elif name == 'Former Struck':
                ensure_charge(student, fs.month_label(prev), amount=1200.0)
            else:
                ensure_charge(student, fs.month_label(prev), amount=500.0)
            db.session.commit()
            if name == 'Former SLC':
                _archive_via_route(admin_client, student.id, 'slc_issued',
                                   reason='Family moved', when='2026-09-15')
            elif name == 'Former Struck':
                _archive_via_route(admin_client, student.id, 'struck_off',
                                   reason='Absent since April', when='2026-09-20')
            else:
                _archive_via_route(admin_client, student.id, 'graduated')

        # A written-off former student drops out of the dues list but the
        # written-off total remembers the money.
        waseem = StudentModel(roll_number=8113, student_name='Former WOff',
                              father_name='F Waseem',
                              guardian_phone='030022221113', address='X',
                              class_id=world['class_id'], monthly_fee=2500.0)
        db.session.add(waseem)
        db.session.commit()
        ensure_charge(waseem, fs.month_label(prev), amount=700.0)
        db.session.commit()
        record_writeoff(waseem, note='untraceable')
        db.session.commit()

        former = fs.former_students_summary()
        assert former['count'] == 3                    # waseem now owes nothing
        assert former['total'] == 4700.0               # 3000 + 1200 + 500
        assert former['written_off'] == 700.0
        by_status = former['by_status']
        assert by_status['slc_issued']['count'] == 1
        assert by_status['slc_issued']['total'] == 3000.0
        assert by_status['struck_off']['count'] == 1
        assert by_status['struck_off']['total'] == 1200.0
        assert by_status['graduated']['count'] == 1
        assert by_status['graduated']['total'] == 500.0
        assert by_status['slc_issued']['label'] == 'SLC Issued'
        assert by_status['struck_off']['label'] == 'Struck Off'
        assert by_status['graduated']['label'] == 'Graduated'
        assert 'Ali Current' not in [i['student'].student_name for i in former['rows']]


def test_student_outstanding_rows_filters(app, world):
    month_key = _month_key()

    with app.app_context():
        ali = db.session.get(StudentModel, world['ali_id'])
        sara = db.session.get(StudentModel, world['sara_id'])
        bilal = db.session.get(StudentModel, world['bilal_id'])
        ensure_charge(ali, fs.month_label(month_key))          # 2,500 owed
        ensure_charge(sara, fs.month_label(month_key), amount=800.0)
        record_payment(ali, fs.month_label(month_key), 1500.0, method='cash',
                       payment_date=date.today())
        recompute_fee_record(ali.id, fs.month_label(month_key))
        recompute_fee_record(sara.id, fs.month_label(month_key))
        db.session.commit()

        # Active students with dues, all months (ledger figures).  Zero-dues
        # students (Bilal) are not part of a dues list.
        names = {r['student'].student_name: r['outstanding']
                 for r in fs.student_outstanding_rows()}
        assert names['Ali Current'] == 1000.0
        assert names['Sara Quiet'] == 800.0
        assert 'Bilal Fresh' not in names

        # Section filter: section A's only debtor is Ali (Bilal owes nothing).
        only_a = fs.student_outstanding_rows(section_id=world['section_a_id'])
        assert {r['student'].student_name for r in only_a} == {'Ali Current'}

        # Month filter reads that month's own fee record.
        monthly = {r['student'].student_name: r['outstanding']
                   for r in fs.student_outstanding_rows(month_year=month_key)}
        assert monthly['Ali Current'] == 1000.0
        assert monthly['Sara Quiet'] == 800.0

        # Status filter buckets.
        assert all(r['student'].is_active for r in fs.student_outstanding_rows())
        assert fs.student_outstanding_rows(status_filter='former') == []


def test_summary_page_renders_new_cards_and_links(admin_client, app, world):
    with app.app_context():
        expense_service.seed_default_categories()
        # One former student with dues so the former-students section and its
        # click-through link render.
        leaver = StudentModel(roll_number=8150, student_name='Ex Student',
                              father_name='F Ex', guardian_phone='030044441150',
                              address='X', class_id=world['class_id'],
                              is_active=False, status='slc_issued',
                              leaving_reason='Moved', leaving_date=date.today())
        db.session.add(leaver)
        db.session.flush()
        ensure_charge(leaver, fs.month_label(_month_key()), amount=900.0)
        db.session.commit()

    page = admin_client.get('/financials/summary')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    for marker in ('Other Income', 'Fee Collection', 'Cash Out',
                   'Salaries Paid', 'Other Expenses', 'Net Position',
                   'Fees Remaining', 'Salary Remaining', 'Collection rate',
                   'CASH', 'ACCRUAL', 'Total payable', 'View their dues',
                   'SLC Issued'):
        assert marker in body, 'missing on summary page: %s' % marker
    assert 'student-outstanding' in body            # former-students click-through


def test_student_outstanding_list_page(admin_client, app, world):
    month_key = _month_key()

    with app.app_context():
        ali = db.session.get(StudentModel, world['ali_id'])
        sara = db.session.get(StudentModel, world['sara_id'])
        ensure_charge(ali, fs.month_label(month_key))
        ensure_charge(sara, fs.month_label(month_key))
        recompute_fee_record(ali.id, fs.month_label(month_key))
        recompute_fee_record(sara.id, fs.month_label(month_key))
        db.session.commit()

    page = admin_client.get('/financials/student-outstanding')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'Ali Current' in body and 'Sara Quiet' in body
    assert 'Total owed' in body

    former_page = admin_client.get('/financials/student-outstanding?status=all')
    assert former_page.status_code == 200
    assert 'Ali Current' in former_page.get_data(as_text=True)

    class_page = admin_client.get(
        '/financials/student-outstanding?class_id=%d' % world['class_id'])
    assert class_page.status_code == 200

    month_page = admin_client.get(
        '/financials/student-outstanding?month=%s' % month_key)
    assert month_page.status_code == 200


def test_leaving_requires_date_and_reason_for_slc_and_struck(app, world,
                                                             admin_client):
    with app.app_context():
        bilal_id = world['bilal_id']
        sara_id = world['sara_id']

    # SLC Issued without reason and date: refused, student untouched.
    response = _archive_via_route(admin_client, bilal_id, 'slc_issued')
    assert b'leaving date' in response.data and b'leaving reason' in response.data
    with app.app_context():
        still = db.session.get(StudentModel, bilal_id)
        assert still.is_active is True and still.status == 'enrolled'

    # Reason given but date missing: still refused.
    response = _archive_via_route(admin_client, bilal_id, 'slc_issued',
                                  reason='Family moved')
    assert b'leaving date' in response.data
    with app.app_context():
        assert db.session.get(StudentModel, bilal_id).is_active is True

    # Both provided: archived with the exact values.
    response = _archive_via_route(admin_client, bilal_id, 'slc_issued',
                                  reason='Family moved', when='2026-09-30')
    with app.app_context():
        saved = db.session.get(StudentModel, bilal_id)
        assert saved.is_active is False and saved.status == 'slc_issued'
        assert saved.leaving_reason == 'Family moved'
        assert saved.leaving_date == date(2026, 9, 30)

    # Struck Off without a reason: refused; with both: saved.
    response = _archive_via_route(admin_client, sara_id, 'struck_off',
                                  when='2026-09-25')
    assert b'leaving reason' in response.data
    with app.app_context():
        assert db.session.get(StudentModel, sara_id).is_active is True
    response = _archive_via_route(admin_client, sara_id, 'struck_off',
                                  reason='Absent since April', when='2026-09-25')
    with app.app_context():
        saved = db.session.get(StudentModel, sara_id)
        assert saved.status == 'struck_off' and saved.leaving_reason

    # Graduated does not demand the leaving fields.
    grad = StudentModel(roll_number=8120, student_name='Grad Free',
                        father_name='F Grad', guardian_phone='030033331120',
                        address='X', class_id=world['class_id'],
                        monthly_fee=2500.0)
    db.session.add(grad)
    db.session.commit()
    response = _archive_via_route(admin_client, grad.id, 'graduated')
    with app.app_context():
        saved = db.session.get(StudentModel, grad.id)
        assert saved.is_active is False and saved.status == 'graduated'

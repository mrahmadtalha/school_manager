"""The demo-data generator fills EVERY module, so optional features can be tried on real-looking data.

Each test seeds a small school (fixed random seed) and checks one area against the
application's own rules (fee ledger, stock arithmetic, admission balances, ...).
"""

from collections import Counter

from app.database import db
from app.models import (
    AdminUser, AuditLog, GuardianStudentLink, AutomationSettings, CanteenEntry, CanteenPayment, ClassModel, DeliveryLog,
    Expense, FeePaymentAllocation, FeeRecordModel, FeeTransaction, IssuedDocument, MessageQueue,
    OtherIncome, Product, ProductSet, Purchase, QrAbsentRun, QrConfig, Sale, SalaryPayment,
    StaffPayroll, StudentIssue, StudentModel, StudentRemark, SupplierPayment, TeacherModel,
    TeachingAssignment, TimetableCell, TimetableRow,
)
from app.services.seed_generator import SeedConfig, run_seed


def _seed(**overrides):
    config = SeedConfig(student_count=40, teacher_count=6, monthly_fee=2500.0, months=4, random_seed=7)
    for key, value in overrides.items():
        setattr(config, key, value)
    return run_seed(config)


# ---------------------------------------------------------------- fee ledger ----

def test_fee_amounts_are_real_money_not_zero(app):
    with app.app_context():
        _seed()
        by_type = Counter()
        for txn in FeeTransaction.query.all():
            assert txn.amount_paisa > 0, f'{txn.txn_type} {txn.month_year} has no amount'
            by_type[txn.txn_type] += 1
        assert by_type['charge'] and by_type['payment']
        for record in FeeRecordModel.query.all():
            assert record.amount_due_paisa > 0
        assert FeeRecordModel.query.filter(FeeRecordModel.amount_paid_paisa > 0).count() > 0


def test_payments_carry_a_cash_date_and_a_unique_slip(app):
    with app.app_context():
        _seed()
        payments = FeeTransaction.query.filter_by(txn_type='payment', is_void=False).all()
        assert payments
        slips = [p.reference for p in payments]
        assert all(p.payment_date is not None for p in payments)
        assert all(slips) and len(slips) == len(set(slips))


def test_ledger_is_fully_allocated_and_reconciles(app):
    from app.services.fee_ledger import orphaned_settlements, reconcile

    with app.app_context():
        _seed()
        assert FeePaymentAllocation.query.count() > 0
        assert orphaned_settlements() == []
        rows, totals, mismatches = reconcile()
        assert mismatches == []
        assert totals['rows'] == FeeRecordModel.query.count()


def test_ledger_has_refunds_voids_extra_charges_and_writeoffs(app):
    with app.app_context():
        _seed(student_count=80, months=6)
        kinds = Counter(t.txn_type for t in FeeTransaction.query.all())
        assert kinds['refund'] and kinds['adjustment']
        assert FeeTransaction.query.filter_by(is_void=True).count() > 0
        assert FeeTransaction.query.filter(FeeTransaction.note.like('Extra charge:%')).count() > 0
        for refund in FeeTransaction.query.filter_by(txn_type='refund').all():
            original = db.session.get(FeeTransaction, refund.related_txn_id)
            assert original.txn_type == 'payment' and refund.amount_paisa < original.amount_paisa


def test_student_monthly_fee_follows_the_discount(app):
    with app.app_context():
        _seed(student_count=80)
        checked = 0
        for student in StudentModel.query.filter(StudentModel.discount_type.isnot(None)).all():
            if student.discount_type == 'percentage':
                expected = student.class_fee * (1 - student.discount_value / 100.0)
            else:
                expected = student.class_fee - student.discount_value
            assert abs(student.monthly_fee - round(expected, 2)) < 0.01
            checked += 1
        assert checked > 0


# ------------------------------------------------------------------- payroll ----

def test_paid_salaries_are_real_payments_mirrored_in_expenses(app):
    with app.app_context():
        _seed()
        payments = SalaryPayment.query.all()
        assert payments
        for payment in payments:
            assert payment.expense is not None and not payment.expense.is_void
            assert payment.expense.amount_paisa == payment.amount_paisa
            assert payment.expense.category.name == 'Salaries'
        for record in StaffPayroll.query.filter_by(payment_status='Paid').all():
            assert abs(record.paid_amount - record.net_salary) < 0.01
        assert StaffPayroll.query.filter_by(payment_status='Pending').count() > 0


# ----------------------------------------------------------------- inventory ----

def test_inventory_stock_equals_purchases_minus_sales(app):
    with app.app_context():
        summary = _seed()
        assert summary['products'] > 40 and summary['product_sets'] > 0
        for product in Product.query.all():
            bought = sum(p.quantity for p in Purchase.query.filter_by(product_id=product.id, is_void=False))
            sold = sum(s.quantity for s in Sale.query.filter_by(product_id=product.id, is_void=False))
            assert product.stock_qty == bought - sold >= 0, product.name
        assert Product.query.filter_by(is_active=False).count() >= 1


def test_every_class_has_a_books_and_a_uniform_set(app):
    with app.app_context():
        _seed()
        for class_obj in ClassModel.query.filter(ClassModel.name != 'Class 1').all():
            kinds = {s.kind for s in ProductSet.query.filter_by(class_id=class_obj.id, is_active=True)}
            assert {'books', 'uniform'} <= kinds, class_obj.name
            assert class_obj.books_fee and class_obj.uniform_fee and class_obj.uniform_sets


def test_supplier_dues_payments_and_low_stock_exist(app):
    from app.services import inventory_service as inv

    with app.app_context():
        _seed(months=6)
        assert inv.total_supplier_dues_paisa() > 0
        assert SupplierPayment.query.count() > 0
        assert inv.low_stock_list()
        assert Sale.query.filter_by(is_void=True).count() + Purchase.query.filter_by(is_void=True).count() >= 1


# ----------------------------------------------------------------- admission ----

def test_every_student_has_admission_terms_in_a_mix_of_states(app):
    from app.services.admission_fee.balances import summary

    with app.app_context():
        _seed(student_count=80)
        states = Counter()
        for student in StudentModel.query.all():
            if student.admission_number is None:        # the two fixture students
                continue
            assert student.admission_fee_net_paisa is not None
            assert student.admission_fee_date is not None
            states[summary(student)['status']] += 1
        assert states['paid'] and (states['partial'] or states['pending'])


def test_admission_receipts_and_stock_issues_match_the_students(app):
    with app.app_context():
        _seed(student_count=80)
        receipts = OtherIncome.query.filter(OtherIncome.student_id.isnot(None)).all()
        assert receipts and all(r.receipt_no.startswith('ADM-') for r in receipts)
        issues = StudentIssue.query.filter_by(is_void=False).all()
        assert issues
        for issue in issues:
            assert db.session.get(StudentModel, issue.student_id).stock_tracked is True
            assert all(sale.unit_price_paisa == 0 and sale.source == 'admission'
                       for sale in issue.sales)


# ------------------------------------------------------------- other income -----

def test_other_income_canteen_and_documents_are_filled(app):
    from app.services import canteen_service, document_fees

    with app.app_context():
        summary = _seed(student_count=80, months=6)
        assert summary['other_income'] > 0
        assert canteen_service.get_mode() == 'totals'
        assert CanteenEntry.query.filter_by(kind='sale').count() and CanteenEntry.query.filter_by(kind='purchase').count()
        assert CanteenPayment.query.count() > 0
        assert document_fees.fee_settings()['id_card'] == 200.0
        issued = IssuedDocument.query.all()
        assert issued
        for row in issued:
            if row.fee_paisa > 0:
                assert row.income is not None and row.income.amount_paisa == row.fee_paisa
                assert row.income.income_date == row.issue_date


# --------------------------------------------------------------- school life ----

def test_timetable_has_no_teacher_in_two_rooms_at_once(app):
    with app.app_context():
        _seed()
        assert TimetableRow.query.count() == ClassModel.query.count()
        seen = set()
        for cell in TimetableCell.query.filter(TimetableCell.teacher_id.isnot(None)).all():
            key = (cell.period_no, cell.teacher_id)
            assert key not in seen
            seen.add(key)
        assert TeachingAssignment.query.count() > 0


def test_remarks_qr_and_whatsapp_queue_are_filled(app):
    with app.app_context():
        _seed()
        assert StudentRemark.query.count() > 0
        assert QrConfig.get().auto_absent_enabled is True and QrAbsentRun.query.count() > 0
        assert AutomationSettings.get().enabled is True
        states = {m.status for m in MessageQueue.query.all()}
        assert 'sent' in states and len(states) > 1
        for message in MessageQueue.query.filter(MessageQueue.status.in_(['sent', 'failed'])):
            assert DeliveryLog.query.filter_by(message_id=message.id).count() == 1


def test_demo_accounts_exist_for_every_role_and_teacher_is_linked(app):
    with app.app_context():
        _seed()
        roles = {u.role for u in AdminUser.query.all()}
        assert {'admin', 'teacher', 'parent', 'owner', 'accountant', 'guard'} <= roles
        teacher_user = AdminUser.query.filter_by(username='teacher1').first()
        assert teacher_user.teacher_id and db.session.get(TeacherModel, teacher_user.teacher_id)
        parent2 = AdminUser.query.filter_by(username='parent2').first()
        assert GuardianStudentLink.query.filter_by(user_id=parent2.id).count() == 2


def test_custom_fields_are_defined_and_filled(app):
    from app.models.settings import get_custom_fields
    from app.services.custom_fields import parse_custom_fields_json

    with app.app_context():
        _seed()
        assert [f['name'] for f in get_custom_fields('student')][:1] == ['blood_group']
        for student in StudentModel.query.filter(StudentModel.admission_number.isnot(None)):
            assert parse_custom_fields_json(student.custom_fields_data).get('blood_group')
        for teacher in TeacherModel.query.filter(TeacherModel.cnic.isnot(None)):
            assert parse_custom_fields_json(teacher.custom_fields_data).get('blood_group')


# ------------------------------------------------------------ switches / audit ---

def test_optional_features_can_be_switched_off(app):
    with app.app_context():
        summary = _seed(include_inventory=False, include_admission=False, include_canteen=False,
                        include_other_income=False, include_documents=False, include_school_life=False)
        assert Product.query.count() == 0 and CanteenEntry.query.count() == 0
        assert IssuedDocument.query.count() == 0 and TimetableRow.query.count() == 0
        assert OtherIncome.query.count() == 0 and StudentRemark.query.count() == 0
        assert 'products' not in summary
        assert FeeTransaction.query.count() > 0 and SalaryPayment.query.count() > 0


def test_same_seed_gives_the_same_school(app):
    with app.app_context():
        first = _seed()
        db.drop_all()
        db.create_all()
        from tests.conftest import seed_reference_data
        seed_reference_data()
        second = _seed()
        for key in ('students', 'fee_transactions', 'fee_records', 'sales', 'purchases',
                    'admission_receipts', 'issued_documents', 'canteen_entries', 'payroll_rows'):
            assert first[key] == second[key], key


def test_full_seed_does_not_flood_the_audit_log(app):
    with app.app_context():
        _seed(student_count=80, months=6)
        assert AuditLog.query.count() < 10
        assert Expense.query.count() > 0


def test_running_the_seed_twice_does_not_double_anything(app):
    with app.app_context():
        _seed()
        first = {model.__name__: model.query.count()
                 for model in (FeeTransaction, FeePaymentAllocation, Product, Sale, Purchase, StudentIssue,
                               OtherIncome, CanteenEntry, IssuedDocument, StaffPayroll, SalaryPayment,
                               StudentRemark, MessageQueue, TimetableCell)}
        _seed()                                   # must neither crash nor repeat the money
        second = {model.__name__: model.query.count() for model in (FeeTransaction, FeePaymentAllocation,
                  Product, Sale, Purchase, StudentIssue, OtherIncome, CanteenEntry, IssuedDocument,
                  StaffPayroll, SalaryPayment, StudentRemark, MessageQueue, TimetableCell)}
        assert first == second


def test_recent_days_have_guard_qr_scan_times(app):
    from app.models import AttendanceModel

    with app.app_context():
        _seed()
        scanned = AttendanceModel.query.filter(AttendanceModel.qr_time.isnot(None)).all()
        assert scanned
        for row in scanned:
            assert row.target_type == 'student' and row.status in ('Present', 'Late')
            if row.status == 'Late':
                assert row.qr_time == row.late_time

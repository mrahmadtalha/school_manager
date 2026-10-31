"""Schema migrations and backfills for fees, payments, payroll, expenses, admission fees and inventory."""

import os

from app.database import db
from app.migrations.common import _safety_backup, _sqlite_connection, _sqlite_db_path, _table_columns


FINANCIAL_V2_TABLES_SQL = '''
-- fee_transactions: money -> integer paisa; adds payment_date (explicit cash
-- date), related_txn_id (refund -> original payment), void bookkeeping.
CREATE TABLE fee_transactions_new (
    id INTEGER NOT NULL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    month_year VARCHAR(20) NOT NULL,
    txn_type VARCHAR(20) NOT NULL,
    amount_paisa INTEGER NOT NULL DEFAULT 0,
    method VARCHAR(30),
    reference VARCHAR(80),
    note VARCHAR(255),
    is_void BOOLEAN NOT NULL DEFAULT 0,
    void_reason VARCHAR(255),
    voided_at DATETIME,
    voided_by_name VARCHAR(80),
    payment_date DATE,
    related_txn_id INTEGER,
    created_at DATETIME NOT NULL,
    created_by_id INTEGER,
    created_by_name VARCHAR(80) DEFAULT 'system',
    FOREIGN KEY(student_id) REFERENCES students (id),
    FOREIGN KEY(related_txn_id) REFERENCES fee_transactions (id)
)
'''


FEE_RECORDS_TABLE_SQL = '''
CREATE TABLE fee_records_new (
    id INTEGER NOT NULL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    month_year VARCHAR(20) NOT NULL,
    amount_due_paisa INTEGER NOT NULL DEFAULT 0,
    amount_paid_paisa INTEGER NOT NULL DEFAULT 0,
    amount_written_off_paisa INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    payment_date DATE,
    remarks VARCHAR(200),
    FOREIGN KEY(student_id) REFERENCES students (id)
)
'''


STAFF_PAYROLL_TABLE_SQL = '''
CREATE TABLE staff_payroll_new (
    id INTEGER NOT NULL PRIMARY KEY,
    teacher_id INTEGER NOT NULL,
    month_year VARCHAR(10) NOT NULL,
    base_salary_paisa INTEGER NOT NULL DEFAULT 0,
    bonus_paisa INTEGER NOT NULL DEFAULT 0,
    deductions_paisa INTEGER NOT NULL DEFAULT 0,
    net_salary_paisa INTEGER NOT NULL DEFAULT 0,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    payment_date DATE,
    payment_method VARCHAR(20),
    notes VARCHAR(255),
    generated_by VARCHAR(80) DEFAULT 'system',
    updated_by_id INTEGER,
    updated_by_name VARCHAR(80),
    working_days INTEGER,
    present_days INTEGER,
    absent_days INTEGER,
    late_days INTEGER,
    leave_days INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_staff_payroll_teacher_month UNIQUE (teacher_id, month_year),
    FOREIGN KEY(teacher_id) REFERENCES teachers (id)
)
'''


EXPENSES_TABLE_SQL = '''
CREATE TABLE expenses_new (
    id INTEGER NOT NULL PRIMARY KEY,
    category_id INTEGER NOT NULL,
    amount_paisa INTEGER NOT NULL DEFAULT 0,
    payment_method VARCHAR(20) NOT NULL DEFAULT 'Cash',
    date DATE NOT NULL,
    receipt_no VARCHAR(80),
    description VARCHAR(255),
    logged_by_id INTEGER,
    logged_by_name VARCHAR(80) DEFAULT 'system',
    updated_by_id INTEGER,
    updated_by_name VARCHAR(80),
    updated_at DATETIME,
    is_void BOOLEAN NOT NULL DEFAULT 0,
    void_reason VARCHAR(255),
    voided_at DATETIME,
    voided_by_name VARCHAR(80),
    created_at DATETIME NOT NULL,
    FOREIGN KEY(category_id) REFERENCES expense_categories (id)
)
'''


def migrate_financial_v2_schema(app):
    """Financial v2 (Phase 1): integer paisa storage + explicit cash dates.

    Converts the four money tables to integer paisa in one rebuild (SQLite
    cannot change column types), takes a safety backup first, and backfills
    the new columns from existing data:

    * ``fee_transactions``: + ``amount_paisa``, ``payment_date`` (backfilled
      from ``created_at`` shifted UTC -> PKT, +5 hours, for payments),
      ``related_txn_id``, void bookkeeping.
    * ``fee_records``: paisa totals + ``amount_written_off_paisa``.
    * ``staff_payroll``: paisa amounts + ``updated_by`` columns.
    * ``expenses``: paisa amount + void bookkeeping + ``updated_by`` columns.

    Follow-up backfills (payment allocations, salary payments + their Salaries
    expense rows) run once through :func:`backfill_financial_v2` after all
    tables exist.  No row is ever deleted; totals in rupees are unchanged.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        fee_cols = _table_columns(connection, 'fee_transactions')
        if not fee_cols or 'payment_date' in fee_cols:
            return  # fresh install or already migrated

        from app.services.db_backup import backup_database
        backup = backup_database(db_path=db_path)
        print(f'Migration: safety backup before financial v2 conversion: {backup}')

        connection.execute(FINANCIAL_V2_TABLES_SQL)
        connection.execute('''
            INSERT INTO fee_transactions_new
                (id, student_id, month_year, txn_type, amount_paisa, method,
                 reference, note, is_void, created_at, created_by_id,
                 created_by_name, payment_date)
            SELECT id, student_id, month_year, txn_type,
                   CAST(ROUND(COALESCE(amount, 0) * 100) AS INTEGER),
                   method, reference, note, is_void, created_at,
                   created_by_id, created_by_name,
                   CASE WHEN txn_type = 'payment'
                        THEN DATE(created_at, '+5 hours') END
            FROM fee_transactions
        ''')
        connection.execute('DROP TABLE fee_transactions')
        connection.execute('ALTER TABLE fee_transactions_new RENAME TO fee_transactions')

        connection.execute(FEE_RECORDS_TABLE_SQL)
        connection.execute('''
            INSERT INTO fee_records_new
                (id, student_id, month_year, amount_due_paisa, amount_paid_paisa,
                 amount_written_off_paisa, status, payment_date, remarks)
            SELECT id, student_id, month_year,
                   CAST(ROUND(COALESCE(amount_due, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(amount_paid, 0) * 100) AS INTEGER),
                   0, status, payment_date, remarks
            FROM fee_records
        ''')
        connection.execute('DROP TABLE fee_records')
        connection.execute('ALTER TABLE fee_records_new RENAME TO fee_records')

        connection.execute(STAFF_PAYROLL_TABLE_SQL)
        connection.execute('''
            INSERT INTO staff_payroll_new
                (id, teacher_id, month_year, base_salary_paisa, bonus_paisa,
                 deductions_paisa, net_salary_paisa, payment_status, payment_date,
                 payment_method, notes, generated_by, working_days, present_days,
                 absent_days, late_days, leave_days, created_at, updated_at)
            SELECT id, teacher_id, month_year,
                   CAST(ROUND(COALESCE(base_salary, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(bonus, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(deductions, 0) * 100) AS INTEGER),
                   CAST(ROUND(COALESCE(net_salary, 0) * 100) AS INTEGER),
                   payment_status, payment_date, payment_method, notes,
                   generated_by, working_days, present_days, absent_days,
                   late_days, leave_days, created_at, updated_at
            FROM staff_payroll
        ''')
        connection.execute('DROP TABLE staff_payroll')
        connection.execute('ALTER TABLE staff_payroll_new RENAME TO staff_payroll')

        connection.execute(EXPENSES_TABLE_SQL)
        connection.execute('''
            INSERT INTO expenses_new
                (id, category_id, amount_paisa, payment_method, date, receipt_no,
                 description, logged_by_id, logged_by_name, created_at)
            SELECT id, category_id,
                   CAST(ROUND(COALESCE(amount, 0) * 100) AS INTEGER),
                   payment_method, date, receipt_no, description,
                   logged_by_id, logged_by_name, created_at
            FROM expenses
        ''')
        connection.execute('DROP TABLE expenses')
        connection.execute('ALTER TABLE expenses_new RENAME TO expenses')

        if 'is_system' not in _table_columns(connection, 'expense_categories'):
            connection.execute("ALTER TABLE expense_categories "
                               "ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT 0")
        # created_at is NOT NULL without a SQL default on legacy tables — supply it.
        connection.execute("INSERT OR IGNORE INTO expense_categories "
                           "(name, is_active, is_system, created_at) "
                           "VALUES ('Salaries', 1, 1, CURRENT_TIMESTAMP)")
        connection.execute('UPDATE expense_categories SET is_system = 1 '
                           "WHERE name = 'Salaries'")

        # A receipt / slip number may only be used by one active transaction.
        connection.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fee_txn_active_reference
            ON fee_transactions(reference)
            WHERE is_void = 0 AND reference IS NOT NULL AND reference <> ''
        ''')
        print('Migration: financial v2 conversion complete '
              '(paisa storage, payment_date backfilled UTC+5h, Salaries category reserved)')


def backfill_financial_v2():
    """One-time derivation of allocations and salary payments from legacy rows.

    Runs after the schema conversion (guard flag ``financial_v2_backfilled``):
    every payment is allocated across the student's outstanding charges
    (its own month first, then older months), every already-Paid payroll row
    gets a SalaryPayment plus its mirrored Salaries expense row, and every
    cached fee summary is recomputed from the new source of truth.
    """
    from datetime import datetime

    from app.models import (Expense, ExpenseCategory, FeeTransaction, SalaryPayment,
                            StaffPayroll, SystemSettingModel, TXN_PAYMENT)
    from app.services.fee_ledger import allocate_transaction, repair_summaries

    flag = SystemSettingModel.query.filter_by(key='financial_v2_backfilled').first()
    if flag and flag.value == '1':
        return
    if flag is None:
        flag = SystemSettingModel(key='financial_v2_backfilled', value='1')
        db.session.add(flag)

    payments = (FeeTransaction.query.filter_by(txn_type=TXN_PAYMENT, is_void=False)
                .order_by(FeeTransaction.created_at, FeeTransaction.id).all())
    for payment in payments:
        allocate_transaction(payment, actor='migration')

    salaries_category = (ExpenseCategory.query.filter_by(name='Salaries').first()
                         or ExpenseCategory(name='Salaries', is_system=True))
    if salaries_category.id is None:
        db.session.add(salaries_category)
        db.session.flush()
    for record in StaffPayroll.query.filter_by(payment_status='Paid').all():
        already = SalaryPayment.query.filter_by(payroll_id=record.id, is_void=False).first()
        if already is not None:
            continue
        payment_date = record.payment_date
        if payment_date is None:
            year, month = record.month_year.split('-')
            from calendar import monthrange
            payment_date = datetime(int(year), int(month), monthrange(int(year), int(month))[1]).date()
        payment = SalaryPayment(
            teacher_id=record.teacher_id, payroll_id=record.id,
            amount_paisa=record.net_salary_paisa, payment_date=payment_date,
            method=record.payment_method or 'Cash',
            note='Migrated from payroll payment status',
            created_by_name='migration')
        db.session.add(payment)
        db.session.flush()
        if salaries_category is not None:
            expense = Expense(
                category_id=salaries_category.id, amount_paisa=record.net_salary_paisa,
                payment_method=payment.method, date=payment_date,
                description='Salary payment (migrated): %s — %s' % (
                    record.teacher.teacher_name if record.teacher else record.teacher_id,
                    record.month_year),
                logged_by_name='migration')
            db.session.add(expense)
            db.session.flush()
            payment.expense_id = expense.id

    repair_summaries()
    db.session.commit()
    print('Financial v2 backfill: allocations + salary payments derived from legacy rows')


def migrate_payment_apply_month(app):
    """Option B allocation rule: add ``fee_transactions.apply_month``.

    The column is the per-transaction allocation override (NULL = default
    oldest-dues-first; a month label settles that month first).  The ALTER is
    additive and safe for SQLite.  Existing payment and write-off rows are
    stamped once with their own ``month_year`` — the rule they were originally
    allocated under — so a later refund re-allocates them exactly as before
    and no migrated figure moves.  New payments stay NULL (oldest-first).
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'fee_transactions')
        if not columns:
            return
        if 'apply_month' not in columns:
            connection.execute('ALTER TABLE fee_transactions '
                               'ADD COLUMN apply_month VARCHAR(20)')
            print('Migration: added apply_month to fee_transactions')

        from app.models import SystemSettingModel
        flag = SystemSettingModel.query.filter_by(
            key='payment_apply_month_stamped').first()
        if flag and flag.value == '1':
            return
        if flag is None:
            flag = SystemSettingModel(key='payment_apply_month_stamped', value='1')
            db.session.add(flag)
        updated = connection.execute(
            "UPDATE fee_transactions SET apply_month = month_year "
            "WHERE apply_month IS NULL AND txn_type IN ('payment', 'writeoff') "
            "AND month_year IS NOT NULL").rowcount
        connection.commit()
        db.session.commit()
        print('Migration: stamped %d existing payment/write-off row(s) '
              'with their original allocation month' % updated)


def _admission_fee_columns():
    return {
        'students': [
            ('admission_fee_standard_paisa', 'INTEGER'),
            ('admission_fee_net_paisa', 'INTEGER'),
            ('admission_discount_type', 'VARCHAR(20)'),
            ('admission_discount_value', 'FLOAT'),
            ('admission_note', 'VARCHAR(200)'),
            ('admission_fee_date', 'DATE'),
            ('admission_fee_prior_paid_paisa', 'INTEGER'),
            ('books_fee_paisa', 'INTEGER'),
            ('books_qty', 'INTEGER'),
            ('uniform_qty', 'INTEGER'),
            ('uniform_unit_paisa', 'INTEGER'),
            ('stock_tracked', 'BOOLEAN'),
        ],
        'classes': [('admission_fee', 'FLOAT'), ('books_fee', 'FLOAT'),
                    ('uniform_fee', 'FLOAT'), ('uniform_sets', 'INTEGER')],
        'school_settings': [('default_admission_fee', 'FLOAT')],
        'other_income': [
            ('student_id', 'INTEGER'),
            ('receipt_no', 'VARCHAR(40)'),
            ('payment_method', 'VARCHAR(20)'),
        ],
    }


def migrate_admission_fee_schema(app):
    """Add the admission-fee columns (all nullable, so nothing changes for
    existing rows: a student without an admission fee simply has none).

    Existing installs get a safety copy of the database first, but only when
    the schema really has to change and the school already holds students.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:' or not os.path.exists(db_path):
        return

    wanted = _admission_fee_columns()
    with _sqlite_connection(db_path) as connection:
        missing = []
        for table, columns in wanted.items():
            existing = _table_columns(connection, table)
            if not existing:
                continue
            missing.extend((table, name, sql_type) for name, sql_type in columns
                           if name not in existing)
        has_students = bool(_table_columns(connection, 'students')) and bool(
            connection.execute('SELECT 1 FROM students LIMIT 1').fetchone())

    if missing and has_students and (
            not app.config.get('TESTING') or app.config.get('PRE_MIGRATION_BACKUP')):
        _safety_backup(app, db_path, 'before-admission-fee')

    with _sqlite_connection(db_path) as connection:
        for table, name, sql_type in missing:
            connection.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, sql_type))
            print('Migration: added %s to %s' % (name, table))
        if _table_columns(connection, 'other_income'):
            connection.execute('CREATE INDEX IF NOT EXISTS idx_other_income_student '
                               'ON other_income (student_id)')
            connection.execute('CREATE INDEX IF NOT EXISTS idx_other_income_receipt '
                               'ON other_income (receipt_no)')
        connection.commit()


def migrate_inventory_schema(app):
    """Inventory columns: ``paid_paisa`` (supplier dues, NULL = paid in full),
    ``bill_label`` (marks the lines of one set purchase) and ``is_opening``
    (opening stock, Phase 4).

    Every purchase made before this column existed was paid in full, so the
    NULL default keeps all old numbers exactly as they were.  The new
    ``supplier_payments`` table is created by ``db.create_all()``.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or db_path == ':memory:' or not os.path.exists(db_path):
        return
    with _sqlite_connection(db_path) as connection:
        existing = _table_columns(connection, 'inventory_purchases')
        # Phase 4: ``is_opening`` marks opening stock (never cash out).  Every
        # older purchase is an ordinary purchase, so the default keeps all numbers.
        # Later: ``is_void`` & co. let a purchase typed by mistake be voided.
        for name, sql_type in (('paid_paisa', 'INTEGER'), ('bill_label', 'VARCHAR(120)'),
                               ('is_opening', 'BOOLEAN NOT NULL DEFAULT 0'),
                               ('is_void', 'BOOLEAN NOT NULL DEFAULT 0'),
                               ('void_reason', 'VARCHAR(255)'),
                               ('voided_at', 'DATETIME'),
                               ('voided_by_name', 'VARCHAR(80)')):
            if existing and name not in existing:
                connection.execute('ALTER TABLE inventory_purchases ADD COLUMN %s %s'
                                   % (name, sql_type))
                print('Migration: added %s to inventory_purchases' % name)
        # Phase 3: sales can be linked to a student / an admission issue, and a
        # wrong issue can be voided.  Old rows become ordinary, non-void sales.
        existing = _table_columns(connection, 'inventory_sales')
        for name, ddl in (('student_id', 'INTEGER'),
                          ('source', "VARCHAR(20) NOT NULL DEFAULT 'sale'"),
                          ('issue_id', 'INTEGER'),
                          ('is_void', 'BOOLEAN NOT NULL DEFAULT 0'),
                          ('void_reason', 'VARCHAR(255)'),
                          ('voided_at', 'DATETIME'),
                          ('voided_by_name', 'VARCHAR(80)')):
            if existing and name not in existing:
                connection.execute('ALTER TABLE inventory_sales ADD COLUMN %s %s'
                                   % (name, ddl))
                print('Migration: added %s to inventory_sales' % name)
        # Canteen totals can now be bought on credit (supplier udhaar).  Every
        # older entry stays exactly as it was: NULL bill = paid in full.  The
        # ``canteen_payments`` table is created by db.create_all().
        existing = _table_columns(connection, 'canteen_entries')
        for name, ddl in (('supplier', 'VARCHAR(120)'),
                          ('bill_paisa', 'INTEGER'),
                          ('paid_paisa', 'INTEGER'),
                          ('void_flag', 'BOOLEAN NOT NULL DEFAULT 0'),
                          ('void_note', 'VARCHAR(255)')):
            if existing and name not in existing:
                connection.execute('ALTER TABLE canteen_entries ADD COLUMN %s %s'
                                   % (name, ddl))
                print('Migration: added %s to canteen_entries' % name)
        connection.commit()


def migrate_expense_schema(app):
    """Seed default expense categories when none exist yet."""
    from app.models import DEFAULT_EXPENSE_CATEGORIES, ExpenseCategory

    with app.app_context():
        if ExpenseCategory.query.count() > 0:
            return
        for name in DEFAULT_EXPENSE_CATEGORIES:
            db.session.add(ExpenseCategory(name=name))
        db.session.commit()
        print('Migration: seeded %d default expense categories'
              % len(DEFAULT_EXPENSE_CATEGORIES))

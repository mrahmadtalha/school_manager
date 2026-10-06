"""Tests for recurring expenses on /expenses: current-month default and the
one-click "continue previous month's expense" shortcut.

The behaviour under test:
* the page opens on the **current month** (not the whole history),
* historical data stays reachable and is never modified,
* a continued expense pre-fills the Add form, stays editable, and saves as a
  **separate** record.
"""

from datetime import date

from app.database import db
from app.models import Expense, ExpenseCategory
from app.services import expense_service, payroll_service


def _category(name='Recurring Cat'):
    category = ExpenseCategory.query.filter_by(name=name).first()
    if category is None:
        category = ExpenseCategory(name=name)
        db.session.add(category)
        db.session.flush()
    return category


def _expense(category, when, amount, method='Cash', receipt=None, description=None):
    expense = Expense(
        category_id=category.id, amount=amount, payment_method=method,
        date=when, receipt_no=receipt, description=description,
        logged_by_name='tester')
    db.session.add(expense)
    db.session.flush()
    return expense


def _month_dates(offset):
    """(year, month, first_day) for this month shifted by ``offset``."""
    key = payroll_service.shift_month(payroll_service.current_month_key(), offset)
    year, month = payroll_service.parse_month(key)
    return key, date(year, month, 1)


# ==========================================
# SERVICE HELPERS
# ==========================================

def test_previous_month_expenses_returns_only_last_month(app):
    with app.app_context():
        category = _category()
        _, this_month = _month_dates(0)
        _, last_month = _month_dates(-1)
        _, two_months_ago = _month_dates(-2)
        current = _expense(category, this_month, 100.0)
        previous = _expense(category, last_month, 200.0)
        older = _expense(category, two_months_ago, 300.0)
        db.session.commit()

        rows = expense_service.previous_month_expenses()
        ids = [row.id for row in rows]
        assert previous.id in ids
        assert current.id not in ids
        assert older.id not in ids


def test_previous_month_expenses_empty_when_no_history(app):
    with app.app_context():
        _category()
        db.session.commit()
        assert expense_service.previous_month_expenses() == []


def test_continue_payload_copies_fields_but_not_the_date(app):
    with app.app_context():
        category = _category()
        _, last_month = _month_dates(-1)
        source = _expense(category, last_month, 1234.5, method='Bank',
                          receipt='R-1', description='Internet')
        db.session.commit()

        payload = expense_service.continue_payload(source)
        assert payload['source_id'] == source.id
        assert payload['category_id'] == category.id
        assert payload['category_name'] == category.name
        assert payload['amount'] == 1234.5
        assert payload['payment_method'] == 'Bank'
        assert payload['receipt_no'] == 'R-1'
        assert payload['description'] == 'Internet'
        # The date is intentionally reported for display but never copied as
        # the new record's date.
        assert payload['source_date'] == last_month.isoformat()
        assert 'date' not in {k for k in payload if k != 'source_date'}

        assert expense_service.continue_payload(None) is None


# ==========================================
# CURRENT-MONTH DEFAULT
# ==========================================

def _main_table(body):
    """Just the main expense table, excluding the continue pick list.

    Last month's rows legitimately appear in the "Continue Previous Month"
    pick list, so month-default assertions must look only at the main table.
    """
    start = body.index('id="expenseMainTable"') if 'id="expenseMainTable"' in body else None
    if start is None:
        # Fall back to the header row of the first table.
        start = body.index('<th>Date</th>')
    end = body.index('</table>', start)
    return body[start:end]


def test_expenses_page_defaults_to_current_month(admin_client, app):
    with app.app_context():
        category = _category()
        _, this_month = _month_dates(0)
        _, last_month = _month_dates(-1)
        _expense(category, this_month, 111.0, description='ThisMonthOnly')
        _expense(category, last_month, 222.0, description='LastMonthOnly')
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'ThisMonthOnly' in body
    # The main table is month-scoped; last month's rows appear only in the
    # "continue" pick list, never in the month's own listing.
    table = _main_table(body)
    assert 'ThisMonthOnly' in table
    assert 'LastMonthOnly' not in table
    # ...and the page says which period it is showing and how to see history.
    assert 'All History' in body
    assert payroll_service.month_label(payroll_service.current_month_key()) in body


def test_current_month_default_scopes_the_summary(admin_client, app):
    with app.app_context():
        category = _category()
        _, this_month = _month_dates(0)
        _, last_month = _month_dates(-1)
        _expense(category, this_month, 100.0)
        _expense(category, last_month, 987654.0)
        db.session.commit()

    table = _main_table(admin_client.get('/expenses').get_data(as_text=True))
    # Only this month's 100 is in the listing; the huge last-month amount is not.
    assert '987654' not in table
    assert '100' in table


def test_all_history_link_shows_every_expense(admin_client, app):
    with app.app_context():
        category = _category()
        _, this_month = _month_dates(0)
        _, last_month = _month_dates(-1)
        _expense(category, this_month, 111.0, description='ThisMonthOnly')
        _expense(category, last_month, 222.0, description='LastMonthOnly')
        db.session.commit()

    body = admin_client.get('/expenses?all=1').get_data(as_text=True)
    table = _main_table(body)
    assert 'ThisMonthOnly' in table
    assert 'LastMonthOnly' in table
    assert 'All months' in body


def test_explicit_month_parameter_is_honoured(admin_client, app):
    with app.app_context():
        category = _category()
        _, last_month = _month_dates(-1)
        _expense(category, last_month, 222.0, description='LastMonthOnly')
        _expense(category, _month_dates(0)[1], 111.0, description='ThisMonthOnly')
        db.session.commit()

    last_key, _ = _month_dates(-1)
    body = admin_client.get(f'/expenses?month={last_key}').get_data(as_text=True)
    table = _main_table(body)
    assert 'LastMonthOnly' in table
    assert 'ThisMonthOnly' not in table
    assert payroll_service.month_label(last_key) in body


def test_explicit_date_filters_override_the_month_default(admin_client, app):
    with app.app_context():
        category = _category()
        _, last_month = _month_dates(-1)
        _expense(category, last_month, 222.0, description='LastMonthOnly')
        _expense(category, _month_dates(0)[1], 111.0, description='ThisMonthOnly')
        db.session.commit()

    table = _main_table(admin_client.get(
        f'/expenses?date_from={last_month}&date_to={last_month}').get_data(as_text=True))
    assert 'LastMonthOnly' in table
    assert 'ThisMonthOnly' not in table


def test_category_filter_still_works_with_month_default(admin_client, app):
    with app.app_context():
        wanted = _category('Wanted Cat')
        other = _category('Other Cat')
        _, this_month = _month_dates(0)
        _expense(wanted, this_month, 10.0, description='WantedDesc')
        _expense(other, this_month, 20.0, description='OtherDesc')
        db.session.commit()
        wanted_id = wanted.id

    table = _main_table(admin_client.get(
        f'/expenses?category_id={wanted_id}').get_data(as_text=True))
    assert 'WantedDesc' in table
    assert 'OtherDesc' not in table


def test_month_navigation_links_present_and_valid(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)
    current = payroll_service.current_month_key()
    assert f'month={payroll_service.shift_month(current, -1)}' in body
    assert f'month={payroll_service.shift_month(current, 1)}' in body
    assert 'This Month' in body
    assert 'name="month"' in body


# ==========================================
# CONTINUE PREVIOUS MONTH
# ==========================================

def test_continue_button_lists_previous_month_expenses(admin_client, app):
    with app.app_context():
        category = _category()
        _, last_month = _month_dates(-1)
        _expense(category, last_month, 4321.0, method='Cheque',
                 receipt='REC-77', description='ContinueTarget')
        _expense(category, _month_dates(0)[1], 1.0, description='CurrentOnly')
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'Continue Previous Month' in body
    assert 'ContinueTarget' in body            # listed in the pick list
    assert 'data-source-id=' in body
    assert 'data-amount="4321.00"' in body
    assert 'data-method="Cheque"' in body
    assert 'data-receipt="REC-77"' in body
    assert 'continueExpenseModal' in body
    assert 'data-continue-note' in body


def test_continue_button_disabled_when_no_previous_month_data(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'Continue Previous Month' in body
    # Nothing to continue, so the action must not be an active modal trigger.
    assert 'data-bs-target="#continueExpenseModal"' not in body


def test_every_row_offers_a_continue_action(admin_client, app):
    with app.app_context():
        category = _category()
        _, this_month = _month_dates(0)
        first = _expense(category, this_month, 500.0, description='RowOne')
        db.session.commit()
        first_id = first.id

    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'continue-expense-btn' in body
    assert f'data-source-id="{first_id}"' in body
    # The Add form carries the provenance field and stays a normal Add form.
    assert 'name="continue_from"' in body
    assert 'class="modal fade" id="addExpenseModal"' in body


# ==========================================
# SAVING: SEPARATE RECORD, NO OVERWRITES
# ==========================================

def _post_expense(client, category_id, amount, when, **extra):
    data = {
        'category_id': str(category_id),
        'amount': str(amount),
        'date': when.isoformat(),
        'payment_method': 'Cash',
    }
    data.update(extra)
    return client.post('/expenses/add', data=data)


def test_continuing_an_expense_creates_a_new_record_and_keeps_the_original(
        admin_client, app):
    with app.app_context():
        category = _category()
        _, last_month = _month_dates(-1)
        source = _expense(category, last_month, 1000.0, method='Bank',
                          receipt='ORIG-1', description='OriginalRow')
        db.session.commit()
        source_id = source.id
        category_id = category.id
        original = (source.amount, source.payment_method, source.receipt_no,
                    source.description, source.date)

    today = date.today()
    response = _post_expense(admin_client, category_id, 1250.0, today,
                             payment_method='Bank',
                             continue_from=str(source_id))
    assert response.status_code == 302

    with app.app_context():
        rows = Expense.query.order_by(Expense.id).all()
        assert len(rows) == 2, 'the continued expense must be a separate record'
        original_row = db.session.get(Expense, source_id)
        # Untouched, field by field.
        assert (original_row.amount, original_row.payment_method,
                original_row.receipt_no, original_row.description,
                original_row.date) == original
        # The new row holds the edited values the user submitted.
        new_row = next(row for row in rows if row.id != source_id)
        assert new_row.amount == 1250.0
        assert new_row.date == today


def test_continued_values_are_editable_before_saving(admin_client, app):
    """Every copied field can be changed; the edit is what gets saved."""
    with app.app_context():
        category = _category()
        other = _category('Edited Cat')
        _, last_month = _month_dates(-1)
        source = _expense(category, last_month, 1000.0, method='Bank',
                          receipt='ORIG-2', description='OriginalRow')
        db.session.commit()
        source_id, other_id = source.id, other.id

    today = date.today()
    _post_expense(admin_client, other_id, 777.25, today,
                  payment_method='Cheque', receipt_no='EDITED-9',
                  description='Edited description',
                  continue_from=str(source_id))

    with app.app_context():
        new_row = (Expense.query.filter(Expense.id != source_id)
                   .order_by(Expense.id.desc()).first())
        assert new_row.category_id == other_id          # category edited
        assert new_row.amount == 777.25                 # amount edited
        assert new_row.payment_method == 'Cheque'       # method edited
        assert new_row.receipt_no == 'EDITED-9'         # receipt edited
        assert new_row.description == 'Edited description'
        # Original is still exactly as it was.
        original_row = db.session.get(Expense, source_id)
        assert original_row.amount == 1000.0
        assert original_row.payment_method == 'Bank'
        assert original_row.receipt_no == 'ORIG-2'
        assert original_row.description == 'OriginalRow'
        assert original_row.date == last_month


def test_continued_expense_is_logged_with_provenance(admin_client, app):
    with app.app_context():
        from app.models import AuditLog
        category = _category()
        _, last_month = _month_dates(-1)
        source = _expense(category, last_month, 400.0, description='ProvSource')
        db.session.commit()
        source_id, category_id = source.id, category.id

    _post_expense(admin_client, category_id, 400.0, date.today(),
                  continue_from=str(source_id))

    with app.app_context():
        from app.models import AuditLog
        entry = (AuditLog.query.filter(AuditLog.action == 'create')
                 .order_by(AuditLog.id.desc()).first())
        assert entry is not None
        assert 'continued from expense #%d' % source_id in (entry.summary or '')


def test_plain_add_expense_unaffected_by_continue_field(admin_client, app):
    """A normal Add (no continue_from) must not mention any source."""
    with app.app_context():
        from app.models import AuditLog
        category = _category()
        db.session.commit()
        category_id = category.id

    _post_expense(admin_client, category_id, 88.0, date.today())

    with app.app_context():
        from app.models import AuditLog
        entry = (AuditLog.query.filter(AuditLog.action == 'create')
                 .order_by(AuditLog.id.desc()).first())
        assert 'continued from' not in (entry.summary or '')
        assert Expense.query.count() == 1


def test_unknown_continue_source_does_not_break_saving(admin_client, app):
    with app.app_context():
        category = _category()
        db.session.commit()
        category_id = category.id

    response = _post_expense(admin_client, category_id, 50.0, date.today(),
                             continue_from='999999')
    assert response.status_code == 302
    with app.app_context():
        assert Expense.query.count() == 1


# ==========================================
# CATEGORIES BEHIND A BUTTON
# ==========================================

def _categories_section(body):
    """The categories modal's markup (its contents must all live in there)."""
    start = body.index('id="categoriesModal"')
    end = body.index('id="continueExpenseModal"')
    return body[start:end]


def test_categories_are_a_button_not_an_inline_form(admin_client, app):
    """The page must not render the category form/table as a big always-on block."""
    with app.app_context():
        _category()
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)

    # A button labelled "Categories" that opens the modal.
    assert 'id="categoriesButton"' in body
    assert 'data-bs-target="#categoriesModal"' in body
    button = body[body.index('id="categoriesButton"'):]
    assert 'Categories' in button[:200]

    # The old visible card header is gone.
    assert 'fa-tags me-2"></i>Categories</div>' not in body
    # The add-category form is no longer rendered outside the modal.
    before_modal = body[:body.index('id="categoriesModal"')]
    assert 'expenses/categories/add' not in before_modal


def test_every_category_feature_lives_inside_the_modal(admin_client, app):
    """Add, list, edit and deactivate/reactivate are all still available."""
    with app.app_context():
        category = _category('Modal Check Cat')
        db.session.commit()
        category_id = category.id

    body = admin_client.get('/expenses').get_data(as_text=True)
    section = _categories_section(body)

    # Add form (name + description + submit).
    assert 'expenses/categories/add' in section
    assert 'name="name"' in section
    assert 'placeholder="e.g. Transport Fuel"' in section
    assert 'Add Category' in section

    # The listing with all its columns.
    for heading in ('Name', 'Description', 'Entries', 'Total (Rs.)', 'Status', 'Actions'):
        assert heading in section, heading
    assert 'Modal Check Cat' in section

    # Per-row edit + deactivate/reactivate.
    assert f'/expenses/categories/{category_id}/edit' in section
    assert f'/expenses/categories/{category_id}/toggle' in section
    assert 'data-bs-target="#editCategoryModal"' in section
    assert 'can be deactivated' in section

    # And the modal closes.
    assert 'modal-footer' in section


def test_category_actions_still_work_after_the_move(admin_client, app, seed):
    """The routes themselves are untouched by the UI move."""
    with app.app_context():
        db.session.commit()

    # Add.
    response = admin_client.post('/expenses/categories/add',
                                 data={'name': 'Route Check Cat',
                                       'description': 'created by test'})
    assert response.status_code == 302
    with app.app_context():
        created = ExpenseCategory.query.filter_by(name='Route Check Cat').first()
        assert created is not None
        created_id = created.id

    # Edit.
    response = admin_client.post(f'/expenses/categories/{created_id}/edit',
                                 data={'name': 'Route Check Cat Renamed',
                                       'description': 'edited'})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(ExpenseCategory, created_id).name == 'Route Check Cat Renamed'

    # Deactivate then reactivate.
    assert admin_client.post(f'/expenses/categories/{created_id}/toggle').status_code == 302
    with app.app_context():
        assert db.session.get(ExpenseCategory, created_id).is_active is False
    assert admin_client.post(f'/expenses/categories/{created_id}/toggle').status_code == 302
    with app.app_context():
        assert db.session.get(ExpenseCategory, created_id).is_active is True

    # The new category shows up inside the modal listing.
    section = _categories_section(admin_client.get('/expenses').get_data(as_text=True))
    assert 'Route Check Cat Renamed' in section


def test_category_button_shows_a_count(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()

    body = admin_client.get('/expenses').get_data(as_text=True)
    button_start = body.index('id="categoriesButton"')
    button_end = body.index('</button>', button_start)
    button_html = body[button_start:button_end]
    assert 'badge' in button_html


def test_exports_follow_the_visible_month(admin_client, app):
    """The export buttons carry the month scope, so downloads match the page."""
    with app.app_context():
        category = _category()
        _, this_month = _month_dates(0)
        _expense(category, this_month, 321.0, description='ExportedThisMonth')
        db.session.commit()

    csv_response = admin_client.get('/expenses/export.csv')
    assert csv_response.status_code == 200
    text = csv_response.get_data(as_text=True)
    assert 'ExportedThisMonth' in text

    pdf_response = admin_client.get('/expenses/export.pdf')
    assert pdf_response.status_code == 200
    assert pdf_response.data.startswith(b'%PDF')


def test_all_history_export_includes_older_months(admin_client, app):
    """Exporting from the All-History view must not silently re-apply the
    current-month default."""
    with app.app_context():
        category = _category()
        _, last_month = _month_dates(-1)
        _expense(category, last_month, 432.0, description='HistoricalRow')
        db.session.commit()

    # Default (page) month export: history excluded.
    default_text = admin_client.get('/expenses/export.csv').get_data(as_text=True)
    assert 'HistoricalRow' not in default_text

    # All-history export: history included.
    all_text = admin_client.get('/expenses/export.csv?all=1').get_data(as_text=True)
    assert 'HistoricalRow' in all_text



def test_export_links_carry_the_visible_scope(admin_client, app):
    with app.app_context():
        _category()
        db.session.commit()

    default_body = admin_client.get('/expenses').get_data(as_text=True)
    # Scoped view: the links include the resolved month bounds.
    assert 'date_from=' in default_body and 'date_to=' in default_body

    all_body = admin_client.get('/expenses?all=1').get_data(as_text=True)
    assert 'all=1' in all_body

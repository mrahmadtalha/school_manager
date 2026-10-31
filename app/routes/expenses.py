"""Operational expense tracker routes: entries, categories and exports (admin only)."""
import io  # noqa: F401  (ledger_csv's sibling — the XLSX export writes into a BytesIO)
from datetime import date, datetime
from app.timeutil import utcnow

import pandas as pd
from flask import (Response, abort, current_app, flash, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user

from app.database import db
from app.models import (ROLE_ACCOUNTANT, ROLE_ADMIN, EXPENSE_PAYMENT_METHODS, Expense,
                        ExpenseCategory)
from app.routes import main
from app.security import role_required
from app.services import expense_service
from app.services.audit import log_action


def _parse_date(value):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _current_filters():
    return {
        'date_from': (request.args.get('date_from') or '').strip(),
        'date_to': (request.args.get('date_to') or '').strip(),
        'category_id': request.args.get('category_id', type=int),
        'q': (request.args.get('q') or '').strip(),
        'month': (request.args.get('month') or '').strip(),
    }


def _resolve_month(filters):
    """Work out which month the list should show.

    The page opens on the **current month** so it never drowns the user in
    history.  Any explicit narrowing the user asked for wins:

    * a ``month=YYYY-MM`` selection (the month navigation strip),
    * explicit ``date_from`` / ``date_to``,
    * category or search filters typed without a month (those are not
      time-scoped; with a month they stay inside that month).

    ``all=1`` is the escape hatch that restores the old "every expense" view.
    """
    from app.services import payroll_service

    current = payroll_service.current_month_key()
    if request.args.get('all') in ('1', 'true', 'yes'):
        return None, current
    if filters['date_from'] or filters['date_to']:
        return None, current
    explicit = filters['month'] if payroll_service.parse_month(filters['month']) else None
    if explicit:
        # A month the person picked stays in force even when a search or a
        # category is added, so "Electricity" is searched inside that month.
        return explicit, current
    if filters['category_id'] or filters['q']:
        return None, current
    return current, current


def _filtered_expenses():
    """Return (filters, expenses, month, current_month) for this request.

    ``month`` is the resolved 'YYYY-MM' being shown, or None when the request
    asks for all history.  It is returned rather than re-derived afterwards
    because resolving a month writes its bounds into ``filters``, which would
    make a second call mistake our own default for an explicit filter.
    """
    filters = _current_filters()
    month, current_month = _resolve_month(filters)
    date_from = _parse_date(filters['date_from'])
    date_to = _parse_date(filters['date_to'])
    if month:
        from app.services import payroll_service
        date_from, date_to = payroll_service.month_bounds(month)
        filters['date_from'] = date_from.isoformat()
        filters['date_to'] = date_to.isoformat()
    expenses = expense_service.filter_expenses(
        date_from=date_from,
        date_to=date_to,
        category_id=filters['category_id'],
        search=filters['q'],
    )
    return filters, expenses, month, current_month


def _validate_expense_form():
    """Return (category, amount, values, errors) for add/edit submissions."""
    category_id = request.form.get('category_id', type=int) or 0
    category = db.session.get(ExpenseCategory, category_id)
    amount = request.form.get('amount', type=float)
    method = (request.form.get('payment_method') or '').strip()
    expense_date = _parse_date(request.form.get('date'))
    receipt_no = (request.form.get('receipt_no') or '').strip()
    description = (request.form.get('description') or '').strip()

    errors = []
    if category is None or not category.is_active:
        errors.append('Please choose a valid category.')
    elif getattr(category, 'is_system', False):
        errors.append('The "%s" category is reserved for payroll payments and '
                      'cannot be used for manual expenses.' % category.name)
    if amount is None or amount <= 0:
        errors.append('Amount must be a positive number.')
    if method not in EXPENSE_PAYMENT_METHODS:
        errors.append('Please choose a valid payment method.')
    if expense_date is None:
        errors.append('Please provide a valid date.')

    values = {
        'category': category,
        'amount': round(float(amount), 2) if amount is not None else None,
        'method': method,
        'date': expense_date,
        'receipt_no': receipt_no or None,
        'description': description or None,
    }
    return values, errors


def _stock_info(month):
    """Stock money kept in Inventory (not an expense): paid to suppliers in the
    shown month and still owed.  ``None`` when Inventory is switched off."""
    from app.services import inventory_service, payroll_service
    if not inventory_service.inventory_enabled():
        return None
    if month:
        start, end = payroll_service.month_bounds(month)
        paid = inventory_service.month_purchase_totals(start, end)
    else:
        paid = inventory_service.month_purchase_totals(date(2000, 1, 1), date(2100, 1, 1))
    return {'paid': paid,
            'dues': inventory_service.total_supplier_dues_paisa() / 100.0}


def _month_options(current_month, selected_month, count=24):
    """(key, label) pairs for the month dropdown: this month and the months
    before it, plus the selected month (or the month of the oldest expense) so
    a chosen month is never missing from the list."""
    from app.services import payroll_service

    keys = [payroll_service.shift_month(current_month, -offset) for offset in range(count)]
    oldest = db.session.query(db.func.min(Expense.date)).scalar()
    if oldest:
        oldest_key = '%04d-%02d' % (oldest.year, oldest.month)
        while keys[-1] > oldest_key and len(keys) < 240:
            keys.append(payroll_service.shift_month(keys[-1], -1))
    for extra in (selected_month, payroll_service.shift_month(current_month, 1)):
        if extra and payroll_service.parse_month(extra) and extra not in keys:
            keys.append(extra)
    keys = sorted(set(keys), reverse=True)
    return [(key, payroll_service.month_label(key)) for key in keys]


def _is_salary_expense(expense):
    """True when a salary payment created this expense.

    ``salary_payment`` is a back-reference; depending on how it is mapped it can
    be a list or a single object, so test truthiness instead of ``is not None``
    (an empty list is "not None" but means "no salary payment").
    """
    return bool(expense.salary_payment)


@main.route('/expenses')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_list():
    from app.services import payroll_service

    expense_service.seed_default_categories()
    filters, expenses, month, current_month = _filtered_expenses()
    previous_month = payroll_service.shift_month(current_month, -1)
    stock_info = _stock_info(month)
    return render_template(
        'expenses.html',
        expenses=expenses,
        summary=expense_service.summary(expenses),
        filter_categories=expense_service.active_categories(),
        all_categories=expense_service.categories_with_usage(),
        filters=filters,
        payment_methods=EXPENSE_PAYMENT_METHODS,
        today=date.today(),
        # Month navigation + the "continue previous month" shortcut.
        stock_info=stock_info,
        month=month or '',
        current_month=current_month,
        month_label=payroll_service.month_label(month) if month else 'All months',
        prev_month=payroll_service.shift_month(month, -1) if month else None,
        next_month=payroll_service.shift_month(month, 1) if month else None,
        month_options=_month_options(current_month, month),
        show_all=(month is None),
        previous_month=previous_month,
        previous_month_label=payroll_service.month_label(previous_month),
        previous_month_expenses=expense_service.previous_month_expenses(current_month),
    )


@main.route('/expenses/add', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_add():
    values, errors = _validate_expense_form()
    if errors:
        for message in errors:
            flash(message, 'danger')
        return redirect(url_for('main.expenses_list'))

    expense = Expense(
        category_id=values['category'].id,
        amount=values['amount'],
        payment_method=values['method'],
        date=values['date'],
        receipt_no=values['receipt_no'],
        description=values['description'],
        logged_by_id=getattr(current_user, 'id', None),
        logged_by_name=getattr(current_user, 'username', None) or 'system',
    )
    db.session.add(expense)
    db.session.flush()

    # A "continued" expense is always a brand-new row; the source record is
    # only referenced here for the audit trail and never modified.
    source_id = request.form.get('continue_from', type=int)
    source = db.session.get(Expense, source_id) if source_id else None
    summary = 'Expense logged: %s Rs. %s' % (
        values['category'].name, '{:,.0f}'.format(expense.amount))
    if source is not None:
        summary += ' (continued from expense #%d)' % source.id
    log_action('create', entity_type='Expense', entity_id=expense.id,
               after={'amount': expense.amount, 'category': values['category'].name},
               summary=summary)
    db.session.commit()
    flash('Expense recorded: %s — Rs. %s.' % (
        values['category'].name, '{:,.0f}'.format(expense.amount)), 'success')
    return redirect(url_for('main.expenses_list'))


@main.route('/expenses/<int:id>/edit', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_edit(id):
    expense = db.session.get(Expense, id)
    if expense is None:
        abort(404)
    if expense.is_void:
        flash('Voided expenses cannot be edited.', 'warning')
        return redirect(url_for('main.expenses_list'))
    if _is_salary_expense(expense):
        flash('Salary-generated expenses are managed from Payroll — void the '
              'salary payment instead.', 'warning')
        return redirect(url_for('main.expenses_list'))

    values, errors = _validate_expense_form()
    if errors:
        for message in errors:
            flash(message, 'danger')
        return redirect(url_for('main.expenses_list'))

    expense.category_id = values['category'].id
    expense.amount = values['amount']
    expense.payment_method = values['method']
    expense.date = values['date']
    expense.receipt_no = values['receipt_no']
    expense.description = values['description']
    expense.updated_by_id = getattr(current_user, 'id', None)
    expense.updated_by_name = getattr(current_user, 'username', None) or 'system'
    from datetime import datetime as _dt
    expense.updated_at = utcnow()
    log_action('update', entity_type='Expense', entity_id=expense.id,
               summary='Expense #%d updated (%s, Rs. %s)' % (
                   expense.id, values['category'].name,
                   '{:,.0f}'.format(expense.amount)))
    db.session.commit()
    flash('Expense #%d updated.' % expense.id, 'success')
    return redirect(url_for('main.expenses_list'))


@main.route('/expenses/<int:id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_void(id):
    """Void an expense with a mandatory reason — never deleted, excluded from
    every total but kept visible in history."""
    expense = db.session.get(Expense, id)
    if expense is None:
        abort(404)
    if expense.is_void:
        flash('This expense is already voided.', 'warning')
        return redirect(url_for('main.expenses_list'))
    if _is_salary_expense(expense):
        flash('Salary-generated expenses are voided from Payroll by voiding '
              'the salary payment.', 'warning')
        return redirect(url_for('main.expenses_list'))

    reason = (request.form.get('void_reason') or '').strip()
    if not reason:
        flash('A reason is required to void an expense.', 'danger')
        return redirect(url_for('main.expenses_list'))

    category_name = expense.category.name if expense.category else '—'
    amount = expense.amount
    expense_service.void_expense(expense, reason,
                                 actor_name=getattr(current_user, 'username', None) or 'system')
    log_action('void', entity_type='Expense', entity_id=expense.id,
               before={'amount': amount, 'category': category_name},
               summary='Expense #%d voided (%s, Rs. %s): %s' % (
                   expense.id, category_name, '{:,.0f}'.format(amount or 0), reason))
    db.session.commit()
    flash('Expense #%d voided — it is excluded from all totals but kept in history.' % expense.id,
          'warning')
    return redirect(url_for('main.expenses_list'))


@main.route('/expenses/categories/add', methods=['POST'])
@role_required(ROLE_ADMIN)
def expenses_categories_add():
    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()

    if not name:
        flash('Category name is required.', 'danger')
    elif ExpenseCategory.query.filter(
            db.func.lower(ExpenseCategory.name) == name.lower()).first():
        flash('That category already exists.', 'warning')
    else:
        category = ExpenseCategory(name=name[:100],
                                   description=description[:200] or None)
        db.session.add(category)
        db.session.flush()
        log_action('create', entity_type='ExpenseCategory', entity_id=category.id,
                   summary='Expense category added: %s' % category.name)
        db.session.commit()
        flash('Category "%s" added.' % category.name, 'success')
    return redirect(url_for('main.expenses_list'))


@main.route('/expenses/categories/<int:id>/edit', methods=['POST'])
@role_required(ROLE_ADMIN)
def expenses_categories_edit(id):
    category = db.session.get(ExpenseCategory, id)
    if category is None:
        abort(404)

    if getattr(category, 'is_system', False):
        flash('The "%s" category is system-reserved (fed by payroll) and '
              'cannot be edited.' % category.name, 'danger')
        return redirect(url_for('main.expenses_list'))

    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    if not name:
        flash('Category name is required.', 'danger')
    elif ExpenseCategory.query.filter(
            db.func.lower(ExpenseCategory.name) == name.lower(),
            ExpenseCategory.id != category.id).first():
        flash('Another category already uses that name.', 'warning')
    else:
        category.name = name[:100]
        category.description = description[:200] or None
        log_action('update', entity_type='ExpenseCategory', entity_id=category.id,
                   summary='Expense category updated: %s' % category.name)
        db.session.commit()
        flash('Category updated.', 'success')
    return redirect(url_for('main.expenses_list'))


@main.route('/expenses/categories/<int:id>/toggle', methods=['POST'])
@role_required(ROLE_ADMIN)
def expenses_categories_toggle(id):
    category = db.session.get(ExpenseCategory, id)
    if category is None:
        abort(404)

    if getattr(category, 'is_system', False):
        flash('The "%s" category is system-reserved (fed by payroll) and '
              'cannot be deactivated.' % category.name, 'danger')
        return redirect(url_for('main.expenses_list'))

    category.is_active = not category.is_active
    state = 'reactivated' if category.is_active else 'deactivated'
    log_action('update', entity_type='ExpenseCategory', entity_id=category.id,
               summary='Expense category %s: %s' % (state, category.name))
    db.session.commit()
    flash('Category "%s" %s.' % (category.name, state), 'success')
    return redirect(url_for('main.expenses_list'))


def _range_label(filters):
    parts = []
    if filters['date_from']:
        parts.append('from ' + filters['date_from'])
    if filters['date_to']:
        parts.append('to ' + filters['date_to'])
    if filters['q']:
        parts.append('search: %r' % filters['q'])
    if filters['category_id']:
        category = db.session.get(ExpenseCategory, filters['category_id'])
        if category:
            parts.append('category: ' + category.name)
    return ('Filters ' + ' | '.join(parts)) if parts else ''


@main.route('/expenses/export.csv')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_export_csv():
    filters, expenses, _month, _current = _filtered_expenses()
    text = expense_service.ledger_csv(expenses)
    log_action('export', entity_type='Expense',
               summary='Expense ledger exported to CSV (%d rows)' % len(expenses))
    db.session.commit()
    filename = 'expenses_ledger_%s.csv' % datetime.now().strftime('%Y%m%d')
    return Response(text, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=%s' % filename})


@main.route('/expenses/export.pdf')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_export_pdf():
    filters, expenses, _month, _current = _filtered_expenses()
    output = expense_service.ledger_pdf(expenses, current_app.root_path,
                                        range_label=_range_label(filters))
    log_action('export', entity_type='Expense',
               summary='Expense ledger exported to PDF (%d rows)' % len(expenses))
    db.session.commit()
    filename = 'expenses_ledger_%s.pdf' % datetime.now().strftime('%Y%m%d')
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=filename)


@main.route('/expenses/export.xlsx')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def expenses_export_xlsx():
    """Excel twin of ``/expenses/export.pdf`` (spec section 9: "PDF/Excel").

    Same rows as the CSV/PDF export — one row per expense inside the current
    filters, then a TOTAL row — written with the project's standard pandas +
    openpyxl pattern (see ``reports._hub_export_file``).
    """
    filters, expenses, _month, _current = _filtered_expenses()
    headers = ['Date', 'Category', 'Amount (Rs)', 'Payment Method',
               'Receipt No', 'Description', 'Logged By']
    rows = [[expense.date.strftime('%Y-%m-%d') if expense.date else '',
             expense.category.name if expense.category else '',
             round(float(expense.amount or 0), 2),
             expense.payment_method or '',
             expense.receipt_no or '',
             expense.description or '',
             expense.logged_by_name or '']
            for expense in expenses]
    frame = pd.DataFrame(rows, columns=headers)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        frame.to_excel(writer, index=False, sheet_name='Expenses')
        writer.sheets['Expenses'].append(
            ['', 'TOTAL', round(sum(row[2] for row in rows), 2), '', '', '', ''])
    output.seek(0)
    log_action('export', entity_type='Expense',
               summary='Expense ledger exported to XLSX (%d rows)' % len(expenses))
    db.session.commit()
    filename = 'expenses_ledger_%s.xlsx' % datetime.now().strftime('%Y%m%d')
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name=filename)

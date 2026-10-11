"""Other Income routes (Phase 3a): canteen, events, trips, certificates...

Owner/Admin and Accountant can enter; every other role is denied.  Money is
append-only — corrections void a row with a mandatory reason.
"""
from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.models import (OtherIncome, OtherIncomeCategory, ROLE_ACCOUNTANT,
                        ROLE_ADMIN, ROLE_OWNER)
from app.routes import main
from app.security import role_required
from app.services import other_income_service, payroll_service
from app.services.audit import log_action


def _parse_date(value):
    value = (value or '').strip()
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _selected_month():
    value = (request.args.get('month') or '').strip()
    return value if payroll_service.parse_month(value) \
        else payroll_service.current_month_key()


@main.route('/other-income')
@role_required(ROLE_ADMIN, ROLE_OWNER, ROLE_ACCOUNTANT)
def other_income_page():
    other_income_service.seed_default_categories()
    month = _selected_month()
    start, end = payroll_service.month_bounds(month)
    rows = (OtherIncome.query.filter(OtherIncome.income_date >= start,
                                     OtherIncome.income_date <= end)
            .order_by(OtherIncome.income_date.desc(),
                      OtherIncome.id.desc()).all())
    total = sum(r.amount for r in rows if not r.is_void)
    return render_template(
        'other_income.html', rows=rows, total=total, month=month,
        month_label=payroll_service.month_label(month),
        categories=other_income_service.active_categories(),
        prev_month=payroll_service.shift_month(month, -1),
        next_month=payroll_service.shift_month(month, 1),
        today=date.today())


@main.route('/other-income/add', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER, ROLE_ACCOUNTANT)
def other_income_add():
    category = db.session.get(OtherIncomeCategory,
                              request.form.get('category_id', type=int) or 0)
    income_date = _parse_date(request.form.get('income_date'))
    try:
        amount = float((request.form.get('amount') or '').strip())
    except ValueError:
        amount = -1
    description = (request.form.get('description') or '').strip()

    if category is None:
        flash('Please choose a category.', 'danger')
    elif income_date is None:
        flash('Please enter a valid date (YYYY-MM-DD).', 'danger')
    else:
        try:
            row = other_income_service.record_income(
                category, amount, income_date, description=description,
                actor=current_user)
            log_action('create', entity_type='OtherIncome', entity_id=row.id,
                       summary='Other income recorded: %s Rs. %s (%s)' % (
                           category.name, '{:,.2f}'.format(row.amount),
                           income_date.strftime('%d %b %Y')))
            db.session.commit()
            flash('Other income of Rs. %s recorded for %s.'
                  % ('{:,.2f}'.format(row.amount), category.name), 'success')
            return redirect(url_for('main.other_income_page',
                                    month=income_date.strftime('%Y-%m')))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
    return redirect(url_for('main.other_income_page'))


@main.route('/other-income/<int:row_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER, ROLE_ACCOUNTANT)
def other_income_void(row_id):
    row = OtherIncome.query.get_or_404(row_id)
    reason = (request.form.get('reason') or '').strip()
    try:
        other_income_service.void_income(row, reason, actor=current_user)
        log_action('void', entity_type='OtherIncome', entity_id=row.id,
                   summary='Other income voided: %s' % (reason[:120]))
        db.session.commit()
        flash('Record voided — it no longer counts in any total.', 'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(request.referrer or url_for('main.other_income_page'))


@main.route('/other-income/categories/add', methods=['POST'])
@role_required(ROLE_ADMIN, ROLE_OWNER)
def other_income_category_add():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Category name is required.', 'danger')
    elif OtherIncomeCategory.query.filter(
            db.func.lower(OtherIncomeCategory.name) == name.lower()).first():
        flash('That category already exists.', 'warning')
    else:
        category = OtherIncomeCategory(name=name[:80])
        db.session.add(category)
        db.session.commit()
        flash('Category "%s" added.' % category.name, 'success')
    return redirect(url_for('main.other_income_page'))

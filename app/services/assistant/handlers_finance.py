"""Handlers: fees collected, fees due, expenses, profit, salary, class fees, fee payments and period comparison."""

from datetime import date

from app.database import db
from app.models import ClassModel, StudentModel
from app.services.payroll_service import month_bounds, month_label, shift_month, current_month_key

from .constants import MAX_LIST_ROWS
from .formatting import _link, _links, _period_label, _reply, rs
from .lookup import _ask_which_student, _students_by_ids


def h_fees_collected(ctx):
    from app.services.financial_summary import collection_split, fee_collections
    if ctx.day and not ctx.month_explicit:
        start = end = ctx.day
        label = ctx.t('today' if ctx.day == date.today() else
                      'on %s' % ctx.day.strftime('%d %b'),
                      'aaj' if ctx.day == date.today() else
                      '%s ko' % ctx.day.strftime('%d %b'))
        total = fee_collections(start, end)
        text = ctx.t('Fees collected %s: %s.', 'Fees wasooli %s: %s.') % (
            label, rs(total))
    else:
        start, end = month_bounds(ctx.month)
        total = fee_collections(start, end)
        split = collection_split(ctx.month)
        text = ctx.t(
            'Fees collected in %s: %s (current-month fees %s, arrears %s).',
            '%s mein fees wasooli: %s (isi mahine ki %s, purana baqaya %s).'
        ) % (_period_label(ctx), rs(total), rs(split['current']),
             rs(split['arrears']))
    return _reply('fees_collected', text,
                  links=_links(_link('Fees Management', 'main.fees_list'),
                               _link('Financial Overview',
                                     'main.financials_summary')),
                  suggestions=[ctx.t('defaulters', 'defaulters kaun hain?')])


def h_fees_due(ctx):
    from app.services import fee_ledger
    from app.services.financial_summary import student_outstanding_rows

    if ctx.students:
        students = _students_by_ids(ctx.students)
        if len(students) > 1 and not ctx.exact_student:
            return _ask_which_student(ctx, students, 'fees_due')
        student = students[0]
        total = fee_ledger.student_outstanding_paisa(student.id) / 100.0
        months = fee_ledger.student_dues_months(student.id)
        klass = student.class_info.name if student.class_info else '-'
        if total <= 0:
            text = ctx.t('%s (%s) has no outstanding fees.',
                         '%s (%s) ka koi baqaya nahi.') % (
                             student.student_name, klass)
            table = None
        else:
            text = ctx.t('%s (%s) owes %s in total.',
                         '%s (%s) ka kul baqaya %s hai.') % (
                             student.student_name, klass, rs(total))
            table = {'columns': [ctx.t('Month', 'Mahina'),
                                 ctx.t('Due', 'Baqaya')],
                     'rows': [[m, rs(v)] for m, v in months]}
        return _reply('fees_due', text, table=table,
                      links=_links(_link('Fee ledger', 'main.fee_student_ledger',
                                         student_id=student.id)))

    class_id = ctx.class_obj.id if ctx.class_obj else None
    month_key = ctx.month if ctx.month_explicit else None
    rows = student_outstanding_rows(class_id=class_id, month_year=month_key)
    scope = ''
    if ctx.class_obj:
        scope += ' %s' % ctx.class_obj.name
    if month_key:
        scope += ' (%s)' % month_label(month_key)
    if not rows:
        return _reply('fees_due', ctx.t('No outstanding fees%s.',
                                        'Koi baqaya fees nahi%s.') % scope,
                      links=_links(_link('Fees Management', 'main.fees_list')))
    total = sum(item['outstanding'] for item in rows)
    text = ctx.t('%d students owe %s%s.', '%d students ka baqaya %s hai%s.') % (
        len(rows), rs(total), scope)
    if len(rows) > MAX_LIST_ROWS:
        text += ctx.t(' Top %d shown.', ' Sab se zyada wale %d dikhaye gaye.'
                      ) % MAX_LIST_ROWS
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         ctx.t('Due', 'Baqaya')],
             'rows': [[item['student'].student_name, item['class_name'],
                       rs(item['outstanding'])]
                      for item in rows[:MAX_LIST_ROWS]]}
    return _reply('fees_due', text, table=table,
                  links=_links(_link('Student dues',
                                     'main.financials_student_outstanding'),
                               _link('Fees Management', 'main.fees_list')))


def h_expenses(ctx):
    from app.services.financial_summary import (expense_breakdown,
                                                expenses_total, month_snapshot)
    if ctx.day and not ctx.month_explicit:
        total = expenses_total(ctx.day, ctx.day)
        label = ctx.t('today' if ctx.day == date.today() else
                      'on %s' % ctx.day.strftime('%d %b'),
                      'aaj' if ctx.day == date.today() else
                      '%s ko' % ctx.day.strftime('%d %b'))
        text = ctx.t('Expenses %s: %s.', 'Kharcha %s: %s.') % (label, rs(total))
        return _reply('expenses', text,
                      links=_links(_link('Expenses', 'main.expenses_list')))
    snapshot = month_snapshot(ctx.month)
    start, end = month_bounds(ctx.month)
    breakdown = expense_breakdown(start, end)
    text = ctx.t(
        'Expenses in %s: %s in total (salaries %s, other expenses %s).',
        '%s ka kul kharcha: %s (salaries %s, baqi kharcha %s).'
    ) % (_period_label(ctx), rs(snapshot['expenses']),
         rs(snapshot['salaries_paid']), rs(snapshot['other_expenses']))
    table = None
    if breakdown:
        table = {'columns': [ctx.t('Category', 'Category'),
                             ctx.t('Amount', 'Raqam')],
                 'rows': [[row['name'], rs(row['total'])]
                          for row in breakdown[:6]]}
    return _reply('expenses', text, table=table,
                  links=_links(_link('Expenses', 'main.expenses_list')))


def h_profit(ctx):
    from app.services.financial_summary import month_snapshot
    snap = month_snapshot(ctx.month)
    net = snap['net']
    verdict_en = 'surplus' if net >= 0 else 'deficit'
    verdict_ur = 'munafa' if net >= 0 else 'nuqsan'
    text = ctx.t(
        '%s: cash in %s, cash out %s, so a %s of %s.',
        '%s: aamdani %s, kharcha %s, yani %s %s.'
    ) % (_period_label(ctx), rs(snap['cash_in']), rs(snap['cash_out']),
         ctx.t(verdict_en, verdict_ur), rs(abs(net)))
    text += '\n' + ctx.t('Fees still to be collected: %s.',
                         'Abhi wasool honay wali fees: %s.') % rs(
                             snap['fees_remaining'])
    return _reply('profit', text,
                  links=_links(_link('Financial Overview',
                                     'main.financials_summary')))


def h_salary(ctx):
    from app.services.financial_summary import payroll_snapshot
    snap = payroll_snapshot(ctx.month)
    if not snap['count']:
        text = ctx.t('Payroll for %s has not been generated yet.',
                     '%s ki payroll abhi generate nahi hui.') % _period_label(ctx)
    else:
        text = ctx.t(
            'Payroll %s: total %s, paid %s, pending %s (%d paid, %d partly '
            'paid, %d unpaid).',
            'Payroll %s: kul %s, ada %s, baqaya %s (%d ada, %d adhoori ada, '
            '%d baqi).'
        ) % (_period_label(ctx), rs(snap['total']), rs(snap['paid']),
             rs(snap['pending']), snap['paid_count'], snap['partial_count'],
             snap['unpaid_count'])
    return _reply('salary', text,
                  links=_links(_link('Payroll', 'main.payroll_page')))


def _pct_change(current, previous):
    if not previous:
        return '-'
    change = (current - previous) * 100.0 / previous
    return '%+.0f%%' % change


def h_class_fees(ctx):
    from app.services.financial_summary import student_outstanding_rows
    month_key = ctx.month if ctx.month_explicit else None
    rows = student_outstanding_rows(month_year=month_key)
    scope = (' (%s)' % month_label(month_key)) if month_key else ''
    if not rows:
        return _reply('class_fees', ctx.t('No outstanding fees%s.',
                                          'Koi baqaya fees nahi%s.') % scope,
                      links=_links(_link('Fees Management', 'main.fees_list')))
    per_class = {}
    for item in rows:
        entry = per_class.setdefault(item['class_name'], [0, 0.0])
        entry[0] += 1
        entry[1] += item['outstanding']
    ranked = sorted(per_class.items(), key=lambda pair: -pair[1][1])
    total = sum(item['outstanding'] for item in rows)
    text = ctx.t('%d students in %d classes owe %s%s.',
                 '%d students (%d classes mein) ka baqaya %s hai%s.'
                 ) % (len(rows), len(per_class), rs(total), scope)
    table = {'columns': [ctx.t('Class', 'Class'),
                         ctx.t('Students owing', 'Baqaya wale students'),
                         ctx.t('Total due', 'Kul baqaya')],
             'rows': [[name, count, rs(amount)]
                      for name, (count, amount) in ranked]}
    return _reply('class_fees', text, table=table,
                  links=_links(_link('Student dues',
                                     'main.financials_student_outstanding'),
                               _link('Fees Management', 'main.fees_list')),
                  suggestions=[ctx.t('defaulters of %s' % ranked[0][0],
                                     '%s ke defaulters' % ranked[0][0])])


def h_compare(ctx):
    from app.services.financial_summary import month_snapshot
    # "pichle mahine se muqabla" means THIS month against last month, so the
    # word "pichle" must not shift the base month; only a named month does.
    base = ctx.month if ctx.month_named else current_month_key()
    before = shift_month(base, -1)
    now_snap, old_snap = month_snapshot(base), month_snapshot(before)
    pairs = [
        (ctx.t('Fees collected', 'Fees wasooli'),
         now_snap['fee_income'], old_snap['fee_income']),
        (ctx.t('Expenses', 'Kharcha'),
         now_snap['expenses'], old_snap['expenses']),
        (ctx.t('Net (cash in - cash out)', 'Bachat (aamdani - kharcha)'),
         now_snap['net'], old_snap['net']),
    ]
    table = {'columns': [ctx.t('Item', 'Cheez'), month_label(base),
                         month_label(before), ctx.t('Change', 'Farq')],
             'rows': [[label, rs(now), rs(old), _pct_change(now, old)]
                      for label, now, old in pairs]}
    tokens = set(ctx.tokens)
    if tokens & {'expense', 'expenses', 'kharcha', 'kharch', 'kharche'}:
        label, now, old = pairs[1]
        word = ctx.t('higher', 'zyada') if now > old else ctx.t('lower', 'kam')
    elif tokens & {'profit', 'munafa', 'nafa', 'net', 'loss', 'nuqsan'}:
        label, now, old = pairs[2]
        word = ctx.t('higher', 'zyada') if now > old else ctx.t('lower', 'kam')
    else:
        label, now, old = pairs[0]
        word = ctx.t('higher', 'zyada') if now > old else ctx.t('lower', 'kam')
    if now == old:
        text = ctx.t('%s is the same in %s and %s (%s).',
                     '%s %s aur %s mein barabar hai (%s).') % (
                         label, month_label(base), month_label(before), rs(now))
    else:
        text = ctx.t('%s: %s in %s, which is %s %s than %s (%s).',
                     '%s: %s mein %s, jo %s ke muqable mein %s %s hai.'
                     ) % ((label, rs(now), month_label(base), rs(abs(now - old)),
                           word, month_label(before), rs(old))
                          if ctx.lang == 'en' else
                          (label, month_label(base), rs(now),
                           month_label(before), rs(abs(now - old)), word))
    return _reply('compare', text, table=table,
                  links=_links(_link('Financial Overview',
                                     'main.financials_summary')))


def h_fees_payments(ctx):
    """Who paid on a given day (default today) - the cash-book view."""
    from app.models import FeeTransaction
    from app.services.financial_summary import _cash_date_column
    day = ctx.day or date.today()
    is_today = day == date.today()
    day_word = ctx.t('today' if is_today else 'on %s' % day.strftime('%d %b'),
                     'aaj' if is_today else '%s ko' % day.strftime('%d %b'))
    cash_date = _cash_date_column()
    query = (db.session.query(StudentModel.student_name, ClassModel.name,
                              FeeTransaction.amount_paisa,
                              FeeTransaction.method)
             .select_from(FeeTransaction)
             .join(StudentModel, StudentModel.id == FeeTransaction.student_id)
             .outerjoin(ClassModel, ClassModel.id == StudentModel.class_id)
             .filter(FeeTransaction.txn_type == 'payment',
                     FeeTransaction.is_void.is_(False),
                     # same comparison shape as financial_summary.fee_collections
                     cash_date >= day.isoformat(),
                     cash_date <= day.isoformat()))
    if ctx.class_obj:
        query = query.filter(StudentModel.class_id == ctx.class_obj.id)
    rows = query.order_by(FeeTransaction.id).all()
    links = _links(_link('Fees Management', 'main.fees_list'))
    if not rows:
        return _reply('fees_payments', ctx.t('No fee payments %s.',
                                             'Fees ki koi wasooli %s nahi hui.'
                                             ) % day_word, links=links)
    total = sum(paisa or 0 for _n, _c, paisa, _m in rows) / 100.0
    text = ctx.t('%d payments %s, %s in total.',
                 '%s: %d payments, kul %s.') % (
                     (len(rows), day_word, rs(total)) if ctx.lang == 'en'
                     else (day_word, len(rows), rs(total)))
    if len(rows) > MAX_LIST_ROWS:
        text += ctx.t(' (showing first %d)', ' (pehle %d dikhaye gaye)'
                      ) % MAX_LIST_ROWS
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         ctx.t('Amount', 'Raqam'), ctx.t('Method', 'Tareeqa')],
             'rows': [[name, class_name or '-', rs((paisa or 0) / 100.0),
                       (method or '-').title()]
                      for name, class_name, paisa, method in rows[:MAX_LIST_ROWS]]}
    return _reply('fees_payments', text, table=table, links=links,
                  suggestions=[ctx.t('defaulters', 'defaulters kaun hain?')])

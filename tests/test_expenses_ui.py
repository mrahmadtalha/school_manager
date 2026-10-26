"""Expenses page redesign: flat summary band, one filter bar, labelled row actions."""


def _body(admin_client):
    resp = admin_client.get('/expenses')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_expenses_uses_the_flat_page_look(admin_client, app, seed):
    body = _body(admin_client)
    assert 'class="ex-page"' in body
    assert 'class="ex-band"' in body
    assert 'class="ex-bar"' in body
    assert 'Total spent' in body and 'Average per expense' in body


def test_filters_keep_their_field_names(admin_client, app, seed):
    body = _body(admin_client)
    for name in ('name="q"', 'name="category_id"', 'name="date_from"', 'name="date_to"', 'name="month"'):
        assert name in body, name
    assert 'Choose exact dates' in body


def test_period_buttons_are_still_there(admin_client, app, seed):
    body = _body(admin_client)
    for text in ('This Month', 'All History', 'Next', 'Previous', 'Continue Previous Month'):
        assert text in body, text


def test_exports_live_in_one_menu(admin_client, app, seed):
    body = _body(admin_client)
    assert 'Excel / CSV file' in body and 'PDF to print' in body
    assert '/expenses/export' in body


def test_row_actions_have_words_not_just_icons(admin_client, app, seed):
    from datetime import date
    from app.database import db
    from app.models import Expense, ExpenseCategory
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name='UI Probe').first()
        if cat is None:
            cat = ExpenseCategory(name='UI Probe')
            db.session.add(cat)
            db.session.flush()
        db.session.add(Expense(category_id=cat.id, amount=75.0, payment_method='Cash',
                               date=date.today(), logged_by_name='t', description='ui-probe-row'))
        db.session.commit()
    body = _body(admin_client)
    table = body[body.index('id="expenseMainTable"'):]
    table = table[:table.index('</table>')]
    assert 'ui-probe-row' in table
    for word in ('Copy</button>', 'Edit</button>', 'Void</button>'):
        assert word in table, word
    assert 'ex-acts' in table
    assert 'Paid by' in table

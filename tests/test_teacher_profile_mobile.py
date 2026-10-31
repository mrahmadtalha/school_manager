"""Teacher profile on phones: sliding tabs, tidy buttons, tables as cards."""

import json
from datetime import date

from app.database import db
from app.models import TeacherModel


def _profile(client, app):
    with app.app_context():
        teacher = TeacherModel(
            teacher_id_str='T-951', teacher_name='Profile Teacher', qualification='MSc',
            designation='Teacher', is_active=True, monthly_salary=45000.0,
            salary=45000.0, joining_date=date(2021, 4, 1), assigned_classes=json.dumps([]))
        db.session.add(teacher)
        db.session.commit()
        teacher_id = teacher.id
    return client.get('/teachers/%d' % teacher_id).get_data(as_text=True)


def test_both_tables_become_cards_on_phones(admin_client, app):
    body = _profile(admin_client, app)
    assert body.count('pf-cards') >= 2 + 1          # two tables + the CSS rule(s)
    assert body.count('class="table profile-table align-middle mb-0 pf-cards"') == 2


def test_phone_css_tabs_and_buttons(admin_client, app):
    body = _profile(admin_client, app)
    assert 'content: attr(data-label)' in body
    assert '.profile-tabs { flex-wrap: nowrap; overflow-x: auto;' in body
    assert 'profile-actions' in body


def test_every_table_cell_has_a_label_in_the_template(app):
    source = app.jinja_env.loader.get_source(app.jinja_env, 'teacher_profile.html')[0]
    for label in ('Day', 'Status', 'Check-in / Late', 'Locked', 'Base', 'Bonus',
                  'Deductions', 'Net Salary', 'Payslip'):
        assert 'data-label="%s"' % label in source, label


def test_all_tabs_and_actions_are_still_there(admin_client, app):
    body = _profile(admin_client, app)
    for pane in ('pane-overview', 'pane-assignments', 'pane-attendance',
                 'pane-payroll', 'pane-documents'):
        assert 'id="%s"' % pane in body, pane
    assert 'Back' in body and 'Download ID Card' in body

"""Teachers page on phones: buttons, filters, cards and full-screen forms.
The page is the same HTML for every screen size, so these tests check the
pieces the phone layout relies on and that no desktop feature went missing."""

import json
from datetime import date

from app.database import db
from app.models import TeacherModel


def _add_teacher(tid, name):
    teacher = TeacherModel(
        teacher_id_str=tid, teacher_name=name, qualification='MSc',
        designation='Teacher', is_active=True, monthly_salary=45000.0,
        salary=45000.0, joining_date=date(2021, 4, 1),
        assigned_classes=json.dumps([]))
    db.session.add(teacher)
    db.session.flush()
    return teacher


def _page(client, app):
    with app.app_context():
        teacher = _add_teacher('T-901', 'Phone Teacher')
        db.session.commit()
        teacher_id = teacher.id
    return client.get('/teachers').get_data(as_text=True), teacher_id


def test_phone_css_is_on_the_page(admin_client, app):
    body, _ = _page(admin_client, app)
    assert '@media (max-width: 767.98px)' in body
    assert '.tm-foot { flex-wrap: wrap;' in body
    assert 'font-size: 16px' in body
    assert '.tm-tools > .btn-primary { order: -1;' in body


def test_add_and_edit_forms_are_full_screen_on_small_phones(admin_client, app):
    body, teacher_id = _page(admin_client, app)
    for modal_id in ('addTeacherModal', 'editTeacher%d' % teacher_id):
        dialog = body.split('id="%s"' % modal_id, 1)[1].split('>', 2)[1]
        assert 'modal-fullscreen-sm-down' in dialog, modal_id
        assert 'modal-lg' in dialog, modal_id          # desktop size unchanged


def test_cards_table_and_tools_are_still_there(admin_client, app):
    body, teacher_id = _page(admin_client, app)
    for needle in ('class="tm-card', 'id="teacherTable"', 'data-tm-view="cards"',
                   'data-tm-view="table"', 'data-column-picker', 'data-export-view="pdf"',
                   'id="importModal"', 'id="deleteTeacher%d"' % teacher_id,
                   'id="filterForm"', 'id="visibleCount"'):
        assert needle in body, needle

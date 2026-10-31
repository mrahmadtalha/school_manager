"""Users & Roles page redesign: plain header, summary band, filters, one shared
Edit / Password / Children window, tick-box child picker, friendly wording."""

import re

from app.database import db
from app.models import AdminUser


def _make_user(app, username, role, active=True, full_name=None):
    with app.app_context():
        user = AdminUser(username=username, role=role, full_name=full_name, is_active=active)
        user.set_password('LongPass#123')
        db.session.add(user)
        db.session.commit()
        return user.id


def test_page_has_plain_header_hint_and_add_button(admin_client):
    body = admin_client.get('/users').get_data(as_text=True)
    assert 'Users &amp; Roles' in body
    assert 'What to do now:' in body
    assert 'data-bs-target="#createUserModal"' in body
    assert 'What can each role do?' in body


def test_summary_band_counts_people(admin_client, app):
    _make_user(app, 'acct1', 'accountant')
    _make_user(app, 'gone1', 'teacher', active=False)
    body = admin_client.get('/users').get_data(as_text=True)
    assert 'Logins in all' in body
    assert re.search(r'Accountant <b>1</b>', body)
    assert re.search(r'1 switched off', body)


def test_one_shared_window_not_one_per_user(admin_client, app):
    _make_user(app, 'one', 'teacher')
    _make_user(app, 'two', 'teacher')
    body = admin_client.get('/users').get_data(as_text=True)
    assert body.count('id="editUserModal"') == 1
    assert body.count('id="resetPassModal"') == 1
    assert 'editUserModal1' not in body


def test_row_buttons_carry_the_action_urls(admin_client, app):
    uid = _make_user(app, 'teach9', 'teacher', full_name='Teach Nine')
    body = admin_client.get('/users').get_data(as_text=True)
    assert 'data-user-edit="%d"' % uid in body
    assert 'data-url="/users/%d/edit"' % uid in body
    assert 'data-url="/users/%d/password"' % uid in body
    assert 'Teach Nine' in body


def test_parent_without_children_is_flagged(admin_client, app):
    uid = _make_user(app, 'lonely-parent', 'parent')
    body = admin_client.get('/users').get_data(as_text=True)
    assert 'No child linked yet' in body
    assert 'data-user-children="%d"' % uid in body


def test_child_picker_uses_tick_boxes(admin_client, seed):
    body = admin_client.get('/users').get_data(as_text=True)
    assert 'data-child-picker' in body
    assert 'type="checkbox" name="student_ids"' in body
    assert 'multiple size=' not in body  # no more Ctrl+click list


def test_own_login_cannot_be_switched_off_and_is_marked(admin_client):
    body = admin_client.get('/users').get_data(as_text=True)
    assert '>You<' in body
    assert 'You cannot switch off your own login' in body


def test_switching_off_asks_for_confirmation(admin_client, app):
    _make_user(app, 'confirm-me', 'teacher')
    body = admin_client.get('/users').get_data(as_text=True)
    assert 'data-confirm="Switch off' in body


def test_old_actions_still_work(admin_client, app):
    uid = _make_user(app, 'edit-me', 'teacher')
    assert admin_client.post('/users/%d/edit' % uid, data={
        'full_name': 'Edited', 'role': 'teacher'}, follow_redirects=True).status_code == 200
    assert admin_client.post('/users/%d/password' % uid, data={
        'password': 'NewPass#456'}, follow_redirects=True).status_code == 200
    assert admin_client.post('/users/%d/toggle' % uid, follow_redirects=True).status_code == 200
    with app.app_context():
        assert db.session.get(AdminUser, uid).full_name == 'Edited'
        assert db.session.get(AdminUser, uid).is_active is False


def test_urdu_labels_exist():
    from app.services.i18n_ur import UR
    for text in ('Add User', 'What can each role do?', 'Never signed in', 'Save Children'):
        assert text in UR

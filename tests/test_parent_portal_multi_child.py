"""Multi-child guardian accounts: link backfill, portal switching, admin linking."""

from app import bootstrap
from app.database import db
from app.models import AdminUser, ClassModel, GuardianStudentLink, StudentModel
from tests.conftest import PARENT_PASSWORD, login


def _second_class(app):
    with app.app_context():
        class_obj = ClassModel(name='Class 9')
        db.session.add(class_obj)
        db.session.commit()
        return class_obj.id


def _make_child(app, name, roll, class_id, phone='03000000001'):
    with app.app_context():
        student = StudentModel(
            roll_number=roll, student_name=name, father_name=f'{name} Father',
            guardian_phone=phone, address='Street', monthly_fee=1000.0,
            class_id=class_id, is_active=True,
        )
        db.session.add(student)
        db.session.commit()
        return student.id


def _make_parent(app, username, student_ids, password='Guardian#2026'):
    with app.app_context():
        user = AdminUser(username=username, role='parent', full_name=username)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        for student_id in student_ids:
            db.session.add(GuardianStudentLink(user_id=user.id, student_id=student_id))
        user.student_id = student_ids[0]
        db.session.commit()
        return user.id


def test_backfill_mirrors_legacy_student_id(app, seed):
    with app.app_context():
        user = AdminUser(username='legacy-parent', role='parent',
                         student_id=seed['other_student_id'])
        user.set_password('Guardian#2026')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        assert GuardianStudentLink.query.filter_by(user_id=user_id).count() == 0

    bootstrap.migrate_guardian_links(app)

    with app.app_context():
        links = GuardianStudentLink.query.filter_by(user_id=user_id).all()
        assert len(links) == 1
        assert links[0].student_id == seed['other_student_id']

    bootstrap.migrate_guardian_links(app)  # idempotent

    with app.app_context():
        assert GuardianStudentLink.query.filter_by(user_id=user_id).count() == 1


def test_portal_shows_all_children_and_switches(client, app, seed):
    class_id = _second_class(app)
    child_a = _make_child(app, 'Child Alpha', 1001, class_id)
    child_b = _make_child(app, 'Child Beta', 1002, class_id)
    _make_parent(app, 'multi-parent', [child_a, child_b])

    assert login(client, 'multi-parent', 'Guardian#2026').status_code == 302

    body = client.get('/portal').get_data(as_text=True)
    assert 'Child Alpha' in body and 'Child Beta' in body  # switcher lists both
    assert '1001' in body and '1002' not in body           # Alpha is the default view

    switched = client.get(f'/portal?student_id={child_b}').get_data(as_text=True)
    assert '1002' in switched and '1001' not in switched   # Beta now selected


def test_portal_blocks_unlinked_child(client, app, seed):
    class_id = _second_class(app)
    linked = _make_child(app, 'Linked Kid', 1001, class_id)
    stranger = _make_child(app, 'Unlinked Kid', 1002, class_id)
    _make_parent(app, 'single-parent', [linked])

    login(client, 'single-parent', 'Guardian#2026')

    ok = client.get(f'/portal?student_id={linked}')
    assert ok.status_code == 200
    assert 'Linked Kid' in ok.get_data(as_text=True)

    blocked = client.get(f'/portal?student_id={stranger}')
    assert blocked.status_code == 404
    assert 'Unlinked Kid' not in blocked.get_data(as_text=True)


def test_users_admin_links_multiple_children(admin_client, app, seed):
    class_id = _second_class(app)
    child_a = _make_child(app, 'Child Alpha', 1001, class_id)
    child_b = _make_child(app, 'Child Beta', 1002, class_id)

    created = admin_client.post('/users/create', data={
        'username': 'admin-made-parent',
        'password': 'LongPass#123',
        'role': 'parent',
        'full_name': 'Made Parent',
        'student_ids': [str(child_a), str(child_b)],
    }, follow_redirects=True)
    assert created.status_code == 200

    with app.app_context():
        user = AdminUser.query.filter_by(username='admin-made-parent').one()
        links = sorted(link.student_id for link in
                       GuardianStudentLink.query.filter_by(user_id=user.id).all())
        assert links == sorted([child_a, child_b])
        assert user.student_id == child_a  # first selection is the primary child
        user_id = user.id

    page = admin_client.get('/users').get_data(as_text=True)
    assert 'Child Alpha' in page and 'Child Beta' in page
    assert f'linkChildrenModal{user_id}' in page

    # Narrow the account to one child.
    edited = admin_client.post(f'/users/{user_id}/students', data={
        'student_ids': [str(child_b)],
    }, follow_redirects=True)
    assert edited.status_code == 200
    with app.app_context():
        user = db.session.get(AdminUser, user_id)
        links = [link.student_id for link in
                 GuardianStudentLink.query.filter_by(user_id=user.id).all()]
        assert links == [child_b]
        assert user.student_id == child_b

    # A parent without any child is refused.
    refused = admin_client.post('/users/create', data={
        'username': 'nochild',
        'password': 'LongPass#123',
        'role': 'parent',
    }, follow_redirects=True)
    assert 'at least one student' in refused.get_data(as_text=True)


def test_legacy_single_child_portal_still_works(client, app, seed):
    # conftest's parent account only carries the legacy student_id column.
    assert login(client, 'parent', PARENT_PASSWORD).status_code == 302
    body = client.get('/portal').get_data(as_text=True)
    assert 'Ali Khan' in body
    assert 'nav-pills' not in body  # single child -> no switcher shown

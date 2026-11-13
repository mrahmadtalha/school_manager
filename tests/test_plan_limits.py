"""Size limits in the license key: how many students and staff logins a school may have.

A key may carry ``max_students`` and ``max_staff``.  They only stop NEW additions (add / restore /
import a student, create / re-activate / re-role a login); a school that is already over a limit
keeps everything it has.  A key without them (every older key) is unlimited.
"""
import io
import re
from datetime import date

import pytest

from app.database import db
from app.models import AdminUser, StudentModel
from app.services import features as feature_catalog
from app.services import licensing, usage_limits
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (MACHINE, clock, keypair, licensed_app_factory,  # noqa: F401
                                      make_key, tool)

ALL = list(feature_catalog.ALL_FEATURES)
STUDENT_HEADER = ('Student Name,Father Name,Class,Guardian Phone,Address,'
                  'Roll Number,Section,Admission No,Date of Birth\n')


def _admin(application, key_text):
    application.extensions['license_manager'].activate(key_text)
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    return client


def _seed(application):
    return application.config['SEED_DATA']


def _student_form(application, roll, name):
    return {'roll_number': str(roll), 'student_name': name, 'father_name': 'Some Father',
            'guardian_phone': '03001112222', 'address': 'Street 5',
            'class_id': str(_seed(application)['class_id']),
            'section_id': str(_seed(application)['section_id']), 'monthly_fee': '1500'}


def _active_students():
    return StudentModel.query.filter_by(is_active=True).count()


def _add_archived_student(application, name='Old Student', roll=1500):
    with application.app_context():
        db.session.add(StudentModel(
            roll_number=roll, student_name=name, father_name='Father', guardian_phone='03000000000',
            address='Somewhere', class_id=_seed(application)['class_id'], monthly_fee=1000.0,
            is_active=False, status='slc_issued'))
        db.session.commit()


# ---- the key ---------------------------------------------------------------------------

def test_limits_are_read_from_the_key(keypair):
    parsed = licensing.verify_license_text(
        make_key(keypair[0], features=ALL, max_students=300, max_staff=5), keypair[1])
    assert parsed['_limits'] == {'max_students': 300, 'max_staff': 5}


def test_a_key_without_limits_is_unlimited(keypair):
    legacy = tool.build_payload(license_id='LIC-OLD', licensee='Old', machine_code=MACHINE,
                                issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7)
    parsed = licensing.verify_license_text(tool.sign_license(keypair[0], legacy), keypair[1])
    assert parsed['_limits'] == {}
    assert 'limits' not in legacy


def test_zero_is_a_real_limit_not_unlimited(keypair):
    parsed = licensing.verify_license_text(
        make_key(keypair[0], features=ALL, max_students=0), keypair[1])
    assert parsed['_limits'] == {'max_students': 0}


def test_a_limit_that_is_not_a_number_is_refused(keypair):
    payload = tool.build_payload(license_id='LIC-BAD', licensee='Bad', machine_code=MACHINE,
                                 issued=date(2026, 1, 10), expires=date(2026, 12, 31), grace_days=7)
    payload['limits'] = {'max_students': 'many'}
    with pytest.raises(licensing.LicenseError):
        licensing.verify_license_text(tool.sign_license(keypair[0], payload), keypair[1])


def test_status_limit_helper_returns_none_when_unlimited():
    base = dict(state='active', read_only=False, level='ok', title='', message='', machine_code=MACHINE)
    status = licensing.LicenseStatus(limits={'max_students': 10}, **base)
    assert status.limit(licensing.LIMIT_MAX_STUDENTS) == 10
    assert status.limit(licensing.LIMIT_MAX_STAFF) is None
    assert licensing.LicenseStatus(limits=None, **base).limit(licensing.LIMIT_MAX_STUDENTS) is None


# ---- students ----------------------------------------------------------------------------

def test_adding_a_student_stops_at_the_limit(licensed_app_factory, keypair):
    application = licensed_app_factory()                  # the seed has 2 active students
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=3))

    first = client.post('/students/add', data=_student_form(application, 1003, 'Third Student'))
    assert first.status_code == 302
    blocked = client.post('/students/add', data=_student_form(application, 1004, 'Fourth Student'),
                          follow_redirects=True)
    page = blocked.get_data(as_text=True)
    assert 'allows up to 3 active students' in page and 'upgrade your plan' in page
    with application.app_context():
        assert _active_students() == 3
        assert StudentModel.query.filter_by(student_name='Fourth Student').count() == 0


def test_a_key_without_limits_adds_students_freely(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL))
    for number in range(3):
        assert client.post('/students/add', data=_student_form(
            application, 1100 + number, f'Free Student {number}')).status_code == 302
    with application.app_context():
        assert _active_students() == 5


def test_a_school_already_over_its_limit_keeps_everything_but_cannot_add(licensed_app_factory, keypair):
    application = licensed_app_factory()                  # 2 students, limit 1: e.g. after a downgrade
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=1))
    assert client.get('/students').status_code == 200     # still readable
    page = client.post('/students/add', data=_student_form(application, 1003, 'Extra'),
                       follow_redirects=True).get_data(as_text=True)
    assert 'allows up to 1 active students and 2 are already in use' in page
    with application.app_context():
        assert _active_students() == 2                    # nobody was removed


def test_archived_students_do_not_count_towards_the_limit(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _add_archived_student(application)
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=3))
    assert client.post('/students/add', data=_student_form(application, 1003, 'Third')).status_code == 302
    with application.app_context():
        assert _active_students() == 3


def test_restoring_a_student_is_blocked_when_the_limit_is_full(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _add_archived_student(application)
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=2))
    with application.app_context():
        old_id = StudentModel.query.filter_by(student_name='Old Student').one().id
    page = client.post(f'/students/restore/{old_id}', follow_redirects=True).get_data(as_text=True)
    assert 'allows up to 2 active students' in page
    with application.app_context():
        assert db.session.get(StudentModel, old_id).is_active is False


def test_restoring_a_student_works_when_there_is_room(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _add_archived_student(application)
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=3))
    with application.app_context():
        old_id = StudentModel.query.filter_by(student_name='Old Student').one().id
    assert client.post(f'/students/restore/{old_id}').status_code == 302
    with application.app_context():
        assert db.session.get(StudentModel, old_id).is_active is True


def test_restore_all_needs_room_for_every_archived_student(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _add_archived_student(application, 'Old One', 1501)
    _add_archived_student(application, 'Old Two', 1502)
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=3))
    page = client.post('/students/restore-all', follow_redirects=True).get_data(as_text=True)
    assert 'only 1 more can be added, but 2 were requested' in page
    with application.app_context():
        assert _active_students() == 2                    # nothing was restored


def test_import_adds_what_fits_and_lists_the_rest_as_plan_limit(licensed_app_factory, keypair):
    application = licensed_app_factory()                  # 2 active; limit 3 -> room for 1
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=3))
    body = ('Import One,Father,Class 1,03001112222,Street,,,,\n'
            'Import Two,Father,Class 1,03001112223,Street,,,,\n'
            'Import Three,Father,Class 1,03001112224,Street,,,,\n')
    response = client.post('/students/import', data={
        'import_file': (io.BytesIO((STUDENT_HEADER + body).encode('utf-8')), 'students.csv')},
        content_type='multipart/form-data', follow_redirects=True)
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Plan limit' in page and 'only 1 more can be added, but 3 were requested' in page
    with application.app_context():
        assert _active_students() == 3
        names = {s.student_name for s in StudentModel.query.all()}
        assert 'Import One' in names and 'Import Two' not in names and 'Import Three' not in names


# ---- staff logins -------------------------------------------------------------------------

def _create_user(client, username, role, **extra):
    return client.post('/users/create', data={
        'username': username, 'password': 'Passw0rd!xx', 'role': role, **extra}, follow_redirects=True)


def test_staff_logins_stop_at_the_limit(licensed_app_factory, keypair):
    application = licensed_app_factory()                  # the seed has 1 teacher login
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_staff=2))
    assert 'created' in _create_user(client, 'acct1', 'accountant').get_data(as_text=True)
    page = _create_user(client, 'acct2', 'owner').get_data(as_text=True)
    assert 'allows up to 2 active staff logins' in page
    with application.app_context():
        assert AdminUser.query.filter_by(username='acct2').count() == 0
        assert usage_limits.count_staff() == 2


def test_parents_and_administrators_are_not_counted(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_staff=1))   # full already
    student_id = _seed(application)['student_id']
    assert 'created' in _create_user(client, 'mum', 'parent', student_ids=[student_id]).get_data(as_text=True)
    assert 'created' in _create_user(client, 'boss2', 'admin').get_data(as_text=True)
    assert 'allows up to' in _create_user(client, 'late', 'teacher').get_data(as_text=True)


def test_switching_a_staff_login_back_on_needs_room(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_staff=1))
    with application.app_context():
        teacher_id = AdminUser.query.filter_by(username='teacher').one().id
    client.post(f'/users/{teacher_id}/toggle')            # off: frees the only slot
    assert 'created' in _create_user(client, 'acct1', 'accountant').get_data(as_text=True)
    page = client.post(f'/users/{teacher_id}/toggle', follow_redirects=True).get_data(as_text=True)
    assert 'allows up to 1 active staff logins' in page
    with application.app_context():
        assert db.session.get(AdminUser, teacher_id).is_active is False


def test_changing_a_parent_into_a_teacher_needs_room(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_staff=1))
    with application.app_context():
        parent_id = AdminUser.query.filter_by(username='parent').one().id
    page = client.post(f'/users/{parent_id}/edit', data={'role': 'teacher', 'full_name': 'Parent'},
                       follow_redirects=True).get_data(as_text=True)
    assert 'allows up to 1 active staff logins' in page
    with application.app_context():
        assert db.session.get(AdminUser, parent_id).role == 'parent'


def test_guard_account_creation_respects_the_staff_limit(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_staff=1))
    page = client.post('/attendance/qr/guard/create', data={}, follow_redirects=True).get_data(as_text=True)
    assert 'allows up to 1 active staff logins' in page
    with application.app_context():
        assert AdminUser.query.filter_by(role='guard').count() == 0


def test_a_key_without_a_staff_limit_creates_logins_freely(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL))
    for number in range(3):
        assert 'created' in _create_user(client, f'free{number}', 'teacher').get_data(as_text=True)


# ---- what the school sees ------------------------------------------------------------------

def test_license_page_shows_plan_size_usage(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_students=10, max_staff=4))
    page = client.get('/license').get_data(as_text=True)
    assert 'Plan size' in page and 'Active students' in page and 'Staff logins' in page
    assert re.search(r'lc-wa-val">\s*2\s*<small>of 10</small>', page)      # 2 students of 10
    assert re.search(r'lc-wa-val">\s*1\s*<small>of 4</small>', page)       # the seeded teacher of 4


def test_license_page_has_no_plan_size_card_without_limits(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL))
    assert 'Plan size' not in client.get('/license').get_data(as_text=True)


def test_users_page_explains_the_staff_limit(licensed_app_factory, keypair):
    application = licensed_app_factory()
    client = _admin(application, make_key(keypair[0], rev=1, features=ALL, max_staff=1))
    page = client.get('/users').get_data(as_text=True)
    assert 'Staff logins in your plan' in page and '1 of 1 used' in page and 'limit is reached' in page


def test_limits_are_not_enforced_when_license_enforcement_is_off(app, admin_client, seed):
    """Development / test mode (no enforcement) never applies a limit."""
    with app.app_context():
        assert usage_limits.student_usage()['limit'] is None
        assert usage_limits.student_block_message() == ''
        assert usage_limits.staff_block_message('teacher') == ''
    response = admin_client.post('/students/add', data={
        'roll_number': '2001', 'student_name': 'Unlimited', 'father_name': 'F', 'guardian_phone': '03001112222',
        'address': 'A', 'class_id': str(seed['class_id']), 'section_id': str(seed['section_id']),
        'monthly_fee': '1000'})
    assert response.status_code == 302

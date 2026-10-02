"""Shared pytest fixtures.

Every test runs against an isolated SQLite file created in a temporary
directory, so tests never touch the developer's real ``instance/school.db``.
"""

import os
import pathlib
import tempfile

import pytest

_TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix='school-manager-tests-'))
# These must be set before ``app`` is imported: app.config resolves them at
# create_app() time, but the test modules import ``create_app`` at collection.
os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')
os.environ.setdefault('DEFAULT_DEMO_PASSWORD', 'School@2026')
os.environ['DATABASE_URL'] = 'sqlite:///' + (_TMP_DIR / 'test.db').as_posix()
os.environ.setdefault('APP_ENV', 'development')
# The existing suite exercises the app itself, not licensing; tests/test_licensing.py
# switches enforcement back on explicitly through create_app() config.
os.environ.setdefault('LICENSE_ENFORCEMENT', '0')

from app import create_app  # noqa: E402
from app.database import db  # noqa: E402
from app.models import (  # noqa: E402
    ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER,
    AdminUser, ClassModel, SectionModel, StudentModel, SubjectModel,
)

ADMIN_PASSWORD = 'adminpass123'
TEACHER_PASSWORD = 'teacherpass123'
PARENT_PASSWORD = 'parentpass123'

PUBLIC_ROUTES = {'/login', '/setup-admin', '/healthz', '/static/style.css'}


def seed_reference_data():
    """Create one class/section/subject, two students and three role accounts."""
    admin = AdminUser(username='admin', role=ROLE_ADMIN, full_name='Test Admin')
    admin.set_password(ADMIN_PASSWORD)
    teacher = AdminUser(username='teacher', role=ROLE_TEACHER, full_name='Test Teacher')
    teacher.set_password(TEACHER_PASSWORD)

    db.session.add_all([admin, teacher])
    db.session.flush()

    class_obj = ClassModel(name='Class 1')
    db.session.add(class_obj)
    db.session.flush()

    section = SectionModel(name='A', class_id=class_obj.id)
    subject = SubjectModel(name='Mathematics', class_id=class_obj.id)
    db.session.add_all([section, subject])
    db.session.flush()

    student = StudentModel(
        roll_number=1001, student_name='Ali Khan', father_name='Imran Khan',
        guardian_phone='03001234567', address='Street 1',
        class_id=class_obj.id, section_id=section.id, monthly_fee=2500.0,
    )
    other = StudentModel(
        roll_number=1002, student_name='Sara Ali', father_name='Nadeem Ali',
        guardian_phone='03007654321', address='Street 2',
        class_id=class_obj.id, section_id=section.id, monthly_fee=2000.0,
    )
    db.session.add_all([student, other])
    db.session.flush()

    parent = AdminUser(username='parent', role=ROLE_PARENT, student_id=student.id,
                       full_name='Guardian of Ali Khan')
    parent.set_password(PARENT_PASSWORD)
    db.session.add(parent)
    db.session.commit()

    return {
        'class_id': class_obj.id,
        'section_id': section.id,
        'subject_id': subject.id,
        'student_id': student.id,
        'other_student_id': other.id,
    }


def login(client, username, password, **kwargs):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False, **kwargs)


def logout(client):
    return client.get('/logout', follow_redirects=False)


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """The login throttle is in-process state; keep tests independent."""
    from app.security import login_attempts

    login_attempts.clear()
    yield
    login_attempts.clear()


@pytest.fixture()
def app():
    application = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    with application.app_context():
        db.drop_all()
        db.create_all()
        application.config['SEED_DATA'] = seed_reference_data()
        yield application
        db.session.remove()


@pytest.fixture()
def seed(app):
    return app.config['SEED_DATA']


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    login(client, 'admin', ADMIN_PASSWORD)
    return client


@pytest.fixture()
def teacher_client(client):
    login(client, 'teacher', TEACHER_PASSWORD)
    return client


@pytest.fixture()
def parent_client(client):
    login(client, 'parent', PARENT_PASSWORD)
    return client


@pytest.fixture()
def fresh_app_factory():
    """Create additional apps on their own database files."""
    created = []

    def _make(tmp_path, name='fresh.db', override=None):
        config = {
            'TESTING': True,
            'WTF_CSRF_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (pathlib.Path(tmp_path) / name).as_posix(),
        }
        if override:
            config.update(override)
        application = create_app(config)
        created.append(application)
        return application

    yield _make

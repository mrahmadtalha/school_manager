# -*- coding: utf-8 -*-
"""Login page redesign: school logo and name, clear wording, default-login hint, next link."""
from app.database import db
from app.models import AdminUser, SchoolSettings
from tests.conftest import ADMIN_PASSWORD, login


def _school(**fields):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
    for key, value in fields.items():
        setattr(settings, key, value)
    db.session.commit()
    return settings


def test_login_shows_school_name_logo_and_contact(client, app):
    with app.app_context():
        _school(school_name='Green Valley School', logo_filename='logo.png',
                address='Main Road, Attock', phone='0300 1234567')
    page = client.get('/login').get_data(as_text=True)
    assert 'Green Valley School' in page
    assert '/brand-logo' in page
    assert 'Main Road, Attock' in page and '0300 1234567' in page


def test_school_logo_loads_without_logging_in(client, app):
    with app.app_context():
        _school(logo_filename='logo.png')
    response = client.get('/brand-logo')
    assert response.status_code == 200
    assert response.mimetype.startswith('image/')


def test_login_without_a_logo_shows_a_school_icon_instead(client, app):
    with app.app_context():
        _school(school_name='No Logo School', logo_filename='')
    page = client.get('/login').get_data(as_text=True)
    assert 'No Logo School' in page
    assert '/brand-logo' not in page
    assert 'fa-school' in page


def test_login_page_has_plain_wording_and_helpers(client):
    page = client.get('/login').get_data(as_text=True)
    for text in ('Type your username', 'Type your password', 'Sign In',
                 'Forgot username / password?', 'Show', 'Caps Lock is on'):
        assert text in page, text
    assert 'autocomplete="current-password"' in page


def test_starting_login_hint_only_while_default_password_is_unchanged(client, app):
    with app.app_context():
        admin = AdminUser.query.filter_by(username='admin').first()
        admin.set_password('admin123')
        db.session.commit()
    assert 'admin123' in client.get('/login').get_data(as_text=True)

    with app.app_context():
        admin = AdminUser.query.filter_by(username='admin').first()
        admin.set_password(ADMIN_PASSWORD)
        db.session.commit()
    assert 'admin123' not in client.get('/login').get_data(as_text=True)


def test_wrong_password_keeps_the_username_typed(client):
    response = login(client, 'admin', 'wrong-password')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Incorrect username or password' in page
    assert 'value="admin"' in page


def test_form_keeps_the_page_you_wanted_after_login(client):
    page = client.get('/login?next=/students').get_data(as_text=True)
    assert 'action="/login?next=/students"' in page or 'next=%2Fstudents' in page
    response = client.post('/login?next=/students',
                           data={'username': 'admin', 'password': ADMIN_PASSWORD})
    assert response.status_code == 302
    assert response.location.endswith('/students')


def test_login_page_in_urdu(client):
    client.get('/language/ur')
    page = client.get('/login').get_data(as_text=True)
    assert 'dir="rtl"' in page
    assert 'اپنا صارف نام لکھیں' in page
    assert 'Type your username' not in page

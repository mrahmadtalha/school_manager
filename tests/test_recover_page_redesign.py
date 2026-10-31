# -*- coding: utf-8 -*-
"""Forgot username / password page redesign: school logo, plain steps, copy / WhatsApp, Urdu."""
import re

from app.database import db
from app.models import SchoolSettings


def _school(**fields):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
    for key, value in fields.items():
        setattr(settings, key, value)
    db.session.commit()


def test_recover_page_shows_school_logo_and_name(client, app):
    with app.app_context():
        _school(school_name='Green Valley School', logo_filename='logo.png')
    page = client.get('/recover').get_data(as_text=True)
    assert 'Green Valley School' in page
    assert '/brand-logo' in page
    assert client.get('/brand-logo').status_code == 200


def test_recover_page_has_three_plain_steps_and_helpers(client):
    page = client.get('/recover').get_data(as_text=True)
    for text in ('Send your request code to your vendor', 'Wait for your reset token',
                 'Paste the token in the box below', 'Copy code', 'Send on WhatsApp',
                 'Reset token from your vendor', 'Back to sign in'):
        assert text in page, text
    assert re.search(r'SMR1\.[\w\-]+\.[\w\-]+', page)
    assert 'wa.me/?text=' in page


def test_recover_page_in_urdu(client):
    client.get('/language/ur')
    page = client.get('/recover').get_data(as_text=True)
    assert 'dir="rtl"' in page
    assert 'اپنا ریکویسٹ کوڈ وینڈر کو بھیجیں' in page
    assert 'Send your request code to your vendor' not in page


def test_wrong_token_message_is_still_shown(client):
    client.get('/recover')
    response = client.post('/recover', data={'token': 'hello'})
    assert b'not a valid reset token' in response.data

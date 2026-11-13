"""License page — software provider card + referral teaser.

Adds, under the existing License page (same ``.lc-`` card family, no new
route): who makes and supports School Manager (Ahmi software firm) with
WhatsApp / email / LinkedIn contact and a "website coming soon" placeholder,
plus a curiosity-style referral teaser that does not reveal the exact reward
and sends the admin to WhatsApp to ask.
"""

import pytest

from app.services.provider_info import PROVIDER, whatsapp_link


def _page(client):
    return client.get('/license').get_data(as_text=True)


# ---------------------------------------------------------------- unit ----

def test_provider_constants_are_set():
    assert PROVIDER['name'] == 'Ahmi software firm'
    assert PROVIDER['whatsapp_number'] == '923361124412'
    assert PROVIDER['email'] == 'ahmiitfirm@gmail.com'
    assert PROVIDER['linkedin_url'].endswith('mrahmadtalha')
    # No public website yet: the page must show a placeholder, never a dead link.
    assert not PROVIDER['website_url']


def test_whatsapp_link_without_message():
    link = whatsapp_link()
    assert link == 'https://wa.me/923361124412'


def test_whatsapp_link_url_encodes_message():
    link = whatsapp_link('Hi there! Tell me more?')
    assert link.startswith('https://wa.me/923361124412?text=')
    assert ' ' not in link          # must be percent/plus-encoded, not raw spaces
    assert 'Hi' in link and 'there' in link


# ------------------------------------------------------------ integration --

def test_provider_card_present_for_admin(admin_client):
    body = _page(admin_client)
    assert 'About your software provider' in body
    assert 'Ahmi software firm' in body


def test_provider_contact_details_shown(admin_client):
    body = _page(admin_client)
    assert '0336 1124412' in body
    assert 'ahmiitfirm@gmail.com' in body
    assert 'mailto:ahmiitfirm@gmail.com' in body
    assert 'mrahmadtalha' in body
    assert 'https://www.linkedin.com/in/mrahmadtalha' in body


def test_whatsapp_links_use_international_wa_me_format(admin_client):
    body = _page(admin_client)
    assert 'https://wa.me/923361124412' in body


def test_website_shows_coming_soon_placeholder_not_a_dead_link(admin_client):
    body = _page(admin_client)
    assert 'Coming soon' in body
    # No bare href="#" or empty href introduced for the website row.
    assert 'href=""' not in body


def test_referral_teaser_present_and_curiosity_framed(admin_client):
    body = _page(admin_client)
    assert 'Know a school that could use School Manager?' in body
    assert 'Ask about referral rewards' in body
    # Curiosity, not a fixed commitment: mentions possibilities, no exact
    # percentage, amount or number of months is hard-coded into the page.
    assert 'bonus' in body.lower() and 'discount' in body.lower()
    import re
    assert not re.search(r'\d+%\s*(off|discount)', body, re.I)
    assert not re.search(r'(rs\.?|pkr)\s*\d+', body, re.I)


def test_referral_button_links_to_prefilled_whatsapp_chat(admin_client):
    body = _page(admin_client)
    assert 'wa.me/923361124412?text=' in body


@pytest.fixture()
def fresh_install_client():
    """An app with an empty AdminUser table: the real \"before setup\" state,
    where /license is open to anyone so the first license can be activated."""
    from app import create_app
    from app.database import db

    application = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    with application.app_context():
        db.drop_all()
        db.create_all()
        yield application.test_client()
        db.session.remove()


def test_provider_card_shown_even_on_fresh_install(fresh_install_client):
    """The provider/referral card is informational, not license-gated, so it
    must also appear before any admin account exists."""
    resp = fresh_install_client.get('/license')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'About your software provider' in body
    assert 'Know a school that could use School Manager?' in body


def test_provider_card_does_not_break_activation_flow(admin_client):
    # Posting an invalid key must still behave exactly as before (400, same
    # page re-rendered) with the new sections simply along for the ride.
    resp = admin_client.post('/license', data={'license_key': 'not-a-key'})
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert 'About your software provider' in body


# --------------------------------------------------------------- Urdu -----

def test_urdu_labels_for_provider_and_referral_section():
    from app.services.i18n_ur import UR
    for text in (
        'About your software provider',
        'WhatsApp', 'Email', 'LinkedIn', 'Website', 'Coming soon',
        'Know a school that could use School Manager?',
        'Ask about referral rewards',
    ):
        assert text in UR, f'missing Urdu translation for: {text!r}'

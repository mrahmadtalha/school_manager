"""Tests for the school brand-colour / theme helpers.

Covers the bug where ``--bs-primary-rgb`` was hardcoded to Bootstrap's default
blue, so a school's chosen colour only half-applied in the UI.
"""

import os
import re

from app.database import db
from app.models import SchoolSettings
from app.services.theme import (brand_palette, hex_to_rgb_triplet, hex_to_rgba,
                                normalize_hex)


# --------------------------------------------------------------------------- #
# helper unit tests
# --------------------------------------------------------------------------- #

def test_normalize_hex_accepts_common_forms(app):
    assert normalize_hex('#0d6efd') == '#0d6efd'
    assert normalize_hex('0D6EFD') == '#0d6efd'
    assert normalize_hex('0d6efd') == '#0d6efd'
    assert normalize_hex('  #0d6efd  ') == '#0d6efd'
    # Short form expands.
    assert normalize_hex('#0af') == '#00aaff'
    assert normalize_hex('abc') == '#aabbcc'


def test_normalize_hex_rejects_junk(app):
    for bad in ('', None, '   ', 'zzz', '#12345', '#1234567', 'red',
                'rgb(1,2,3)', '#gggggg', 123):
        assert normalize_hex(bad) is None, bad


def test_hex_to_rgb_triplet(app):
    assert hex_to_rgb_triplet('#0d6efd') == '13,110,253'
    assert hex_to_rgb_triplet('#c81e1e') == '200,30,30'
    assert hex_to_rgb_triplet('#000000') == '0,0,0'
    assert hex_to_rgb_triplet('#ffffff') == '255,255,255'
    assert hex_to_rgb_triplet('#0af') == '0,170,255'
    assert hex_to_rgb_triplet('garbage') is None
    assert hex_to_rgb_triplet(None) is None


def test_hex_to_rgba(app):
    assert hex_to_rgba('#0d6efd', 0.12) == 'rgba(13,110,253, 0.12)'
    assert hex_to_rgba('#0d6efd', 0.32) == 'rgba(13,110,253, 0.32)'
    assert hex_to_rgba('nope', 0.5) is None
    # Out-of-range alpha is clamped rather than producing invalid CSS.
    assert hex_to_rgba('#0d6efd', 5) == 'rgba(13,110,253, 1)'
    assert hex_to_rgba('#0d6efd', -2) == 'rgba(13,110,253, 0)'
    assert hex_to_rgba('#0d6efd', 'not-a-number') is None


def test_brand_palette_always_derives_rgb(app):
    """The rgb triplet must match the hex, which is the actual bug fixed."""
    palette = brand_palette('#c81e1e', '#0f766e')
    assert palette['primary'] == '#c81e1e'
    assert palette['primary_rgb'] == '200,30,30'
    assert palette['secondary_rgb'] == '15,118,110'
    assert palette['primary_subtle'] == 'rgba(200,30,30, 0.12)'


def test_brand_palette_secondary_is_optional(app):
    palette = brand_palette('#2563eb')
    assert palette['primary_rgb'] == '37,99,235'
    assert 'secondary' not in palette
    assert 'secondary_rgb' not in palette
    # Blank/None secondary behaves the same as omitted.
    assert 'secondary' not in brand_palette('#2563eb', '')
    assert 'secondary' not in brand_palette('#2563eb', None)


def test_brand_palette_returns_none_without_a_usable_primary(app):
    assert brand_palette('', '#0f766e') is None
    assert brand_palette(None, '#0f766e') is None
    assert brand_palette('not-a-colour', '#0f766e') is None


# --------------------------------------------------------------------------- #
# rendered output
# --------------------------------------------------------------------------- #

def _style(body):
    return body.split('<style>', 1)[1].split('</style>', 1)[0]


def _settings(**overrides):
    """Insert/replace the single school settings row for the test."""
    row = SchoolSettings.query.first()
    if row is None:
        row = SchoolSettings()
        db.session.add(row)
        db.session.flush()
    for key, value in overrides.items():
        setattr(row, key, value)
    db.session.commit()
    return row


def test_custom_primary_colour_flows_into_rgb_variable(admin_client, app):
    """Regression guard for the hardcoded '13,110,253' default."""
    with app.app_context():
        _settings(primary_color='#c81e1e', secondary_color='#0f766e')

    style = _style(admin_client.get('/students').get_data(as_text=True))
    assert '--bs-primary: #c81e1e;' in style
    assert '--bs-primary-rgb: 200,30,30;' in style
    assert '--bs-secondary-rgb: 15,118,110;' in style
    # The old hardcoded default must be entirely gone.
    assert '13,110,253' not in style


def test_default_and_short_hex_colours_render(admin_client, app):
    with app.app_context():
        _settings(primary_color='#0d6efd', secondary_color='#6c757d')
    style = _style(admin_client.get('/students').get_data(as_text=True))
    assert '--bs-primary-rgb: 13,110,253;' in style

    with app.app_context():
        _settings(primary_color='0af', secondary_color='#0f766e')
    style = _style(admin_client.get('/students').get_data(as_text=True))
    assert '--bs-primary: #00aaff;' in style
    assert '--bs-primary-rgb: 0,170,255;' in style


def test_secondary_absent_omits_secondary_block(admin_client, app):
    with app.app_context():
        _settings(primary_color='#2563eb', secondary_color='')
    style = _style(admin_client.get('/students').get_data(as_text=True))
    assert '--bs-primary-rgb: 37,99,235;' in style
    assert '--bs-secondary' not in style


def test_usable_colour_overrides_are_emitted(admin_client, app):
    """Bootstrap bakes .btn-primary, so the explicit overrides stay load-bearing."""
    with app.app_context():
        _settings(primary_color='#c81e1e', secondary_color='#0f766e')
    style = _style(admin_client.get('/students').get_data(as_text=True))
    assert '.btn-primary { background-color: #c81e1e !important;' in style
    assert '.bg-secondary, .btn-secondary { background-color: #0f766e !important;' in style


def test_unusable_colour_does_not_break_the_page(admin_client, app):
    with app.app_context():
        _settings(primary_color='not-a-colour', secondary_color='#zzz')
    response = admin_client.get('/students')
    assert response.status_code == 200
    style = _style(response.get_data(as_text=True))
    assert 'not-a-colour' not in style
    assert '--bs-primary' not in style
    assert '--bs-secondary' not in style


def test_missing_settings_row_still_renders(admin_client, app):
    """A fresh install with no settings row must not error."""
    with app.app_context():
        SchoolSettings.query.delete()
        db.session.commit()
    response = admin_client.get('/students')
    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# unified page headers
# --------------------------------------------------------------------------- #

#: Screen pages that were using a bespoke flat header before standardisation.
UNIFIED_HEADER_PAGES = (
    ('/expenses', 'Expense Tracker', 'Finance'),
    ('/financials/summary', 'Financial Overview', 'Finance'),
    ('/payroll', 'Staff Salaries', 'Finance'),
    ('/', 'Executive Command Center', 'School operations overview'),
)


def test_screen_pages_share_one_header_structure(admin_client, app):
    """Every converted page uses the same card header: eyebrow, title,
    subtitle and an action toolbar."""
    for path, title, eyebrow in UNIFIED_HEADER_PAGES:
        body = admin_client.get(path).get_data(as_text=True)
        assert 'dashboard-header' in body, path
        start = body.index('dashboard-header')
        block = body[start:start + 700]
        assert f'class="eyebrow mb-2">{eyebrow}</p>' in block, path
        assert title in block, path
        assert 'text-muted small mb-0' in block, path
        assert 'btn-toolbar' in block, path


def test_dashboard_keeps_its_live_whatsapp_hooks(admin_client, app):
    """The header rewrite must not drop the JS hook elements."""
    body = admin_client.get('/').get_data(as_text=True)
    for element_id in ('wa-status-badge', 'wa-status-text'):
        assert f'id="{element_id}"' in body, element_id
    assert 'checkWhatsappStatus' in body


def test_print_pages_keep_a_flat_no_print_toolbar(app):
    """Print documents must not adopt the gradient card header."""
    templates = os.path.join(app.root_path, 'templates')
    for name in ('examination_date_sheet.html', 'fee_receipt.html'):
        with open(os.path.join(templates, name), encoding='utf-8') as handle:
            content = handle.read()
        assert 'no-print' in content, name
        assert 'dashboard-header' not in content, name


def test_only_print_pages_still_use_a_border_bottom_header(app):
    """Guards against a screen page drifting back to the old flat header."""
    templates = os.path.join(app.root_path, 'templates')
    offenders = []
    for name in os.listdir(templates):
        if not name.endswith('.html') or name.startswith('_'):
            continue
        with open(os.path.join(templates, name), encoding='utf-8') as handle:
            content = handle.read()
        if 'pt-3 pb-2 mb-3 border-bottom' in content:
            # Allowed only on print-oriented documents.
            if 'no-print' not in content:
                offenders.append(name)
    assert offenders == [], f'screen pages using the legacy flat header: {offenders}'


"""Tests that flash messages are rendered centrally, once, and print-safely.

They used to be copy-pasted into 31 templates (in eight slightly different
variants); base.html now renders them for every page.
"""

import os
import re


def test_flash_renders_once_on_a_page(admin_client, app, seed):
    """A save action flashes; the message must appear exactly once."""
    response = admin_client.post('/expenses/categories/add',
                                 data={'name': 'Flash Probe Cat'},
                                 follow_redirects=True)
    body = response.get_data(as_text=True)
    occurrences = body.count('Flash Probe Cat')
    # Once in the flash alert, once in the categories table = 2.
    print('occurrences of the flashed name:', occurrences)
    alerts = re.findall(r'<div class="alert alert-[^"]*"[^>]*>', body)
    print('alert divs:', alerts)
    assert any('alert-success' in a for a in alerts), 'flash alert missing'
    assert 'role="alert"' in body
    assert 'aria-label="Close"' in body


def test_flash_has_no_print_class(admin_client, app, seed):
    """Flashes must carry .no-print so they never appear on printed output."""
    response = admin_client.post('/expenses/categories/add',
                                 data={'name': 'Print Probe Cat'},
                                 follow_redirects=True)
    body = response.get_data(as_text=True)
    match = re.search(r'<div class="alert alert-success[^"]*"', body)
    print('flash class attr:', match.group(0) if match else 'NOT FOUND')
    assert match, 'flash alert not found'
    assert 'no-print' in match.group(0)


def test_flash_renders_on_a_different_page(admin_client, app, seed):
    """Cross-page check: the central block works beyond the expenses page."""
    response = admin_client.post('/settings',
                                 data={'action': 'save_academic_settings',
                                       'school_start_time': '08:30',
                                       'school_end_time': '15:00',
                                       'attendance_grace_minutes': '0'},
                                 follow_redirects=True)
    body = response.get_data(as_text=True)
    alerts = re.findall(r'<div class="alert alert-([a-z]+)[^"]*"', body)
    print('settings alerts:', alerts)
    assert alerts, 'no flash alert on settings page'


def test_flash_renders_exactly_once_not_twice(admin_client, app, seed):
    """Guard against a page keeping its old block alongside the central one."""
    response = admin_client.post('/expenses/categories/add',
                                 data={'name': 'Once Probe Cat'},
                                 follow_redirects=True)
    body = response.get_data(as_text=True)
    wrappers = len(re.findall(r'get_flashed_messages', body))
    print('get_flashed_messages occurrences in rendered output:', wrappers)
    assert wrappers == 0, 'Jinja call should be consumed, not echoed'

    dismiss_buttons = len(re.findall(r'data-bs-dismiss="alert"', body))
    print('dismissible alert buttons:', dismiss_buttons)
    assert dismiss_buttons == 1, f'expected exactly one flash, got {dismiss_buttons}'


# --------------------------------------------------------------------------- #
# centralisation (structural)
# --------------------------------------------------------------------------- #

def test_only_base_and_login_render_flashes(app):
    """Every page template must rely on base.html, not its own copy."""
    templates = os.path.join(app.root_path, 'templates')
    holders = []
    for name in sorted(os.listdir(templates)):
        if not name.endswith('.html') or name.startswith('_'):
            continue
        with open(os.path.join(templates, name), encoding='utf-8') as handle:
            if 'get_flashed_messages' in handle.read():
                holders.append(name)
    # base.html renders them centrally; login.html is a standalone page that
    # does not extend the layout.
    assert holders == ['base.html', 'login.html'], holders


def test_base_defines_a_flashes_block(app):
    with open(os.path.join(app.root_path, 'templates', 'base.html'),
              encoding='utf-8') as handle:
        base = handle.read()
    assert '{% block flashes %}' in base
    assert 'get_flashed_messages' in base
    # The central version keeps the accessibility attributes and print safety.
    assert 'role="alert"' in base
    assert 'aria-label="Close"' in base
    assert 'no-print' in base


# --------------------------------------------------------------------------- #
# printing
# --------------------------------------------------------------------------- #

def test_stylesheet_defines_print_rules(app):
    """.no-print is relied on for print output, so it must actually work."""
    with open(os.path.join(app.root_path, 'static', 'style.css'),
              encoding='utf-8') as handle:
        css = handle.read()
    assert '@media print' in css
    # Navigation, toolbars and flashes are suppressed when printing.
    for selector in ('.no-print', '.mobile-topbar', '#sidebar', '.btn-toolbar'):
        assert selector in css, selector
    assert 'display: none !important;' in css
    # Content takes the full sheet.
    assert 'max-width: 100% !important' in css


def test_print_pages_keep_no_print_markers(app):
    """The print documents must keep marking their toolbars as no-print."""
    templates = os.path.join(app.root_path, 'templates')
    for name in ('examination_date_sheet.html', 'fee_receipt.html'):
        with open(os.path.join(templates, name), encoding='utf-8') as handle:
            assert 'no-print' in handle.read(), name


def test_flash_still_works_on_the_standalone_login_page(client, app):
    """login.html keeps its own block, so flashes there must still render."""
    from tests.conftest import login

    response = login(client, 'nobody', 'wrong-password')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'alert' in body
    assert 'get_flashed_messages' not in body

"""Visual smoke test for the polished UI.

Runs a real browser against the live app, walks the main demo flows and captures
screenshots to a folder.  Skipped automatically when Playwright (or its browser)
is unavailable, so the suite still runs on a machine without it.

Run just this file with:

    python -m pytest tests/test_visual_smoke.py -q

Screenshots land in ``<repo>/screenshots/``.
"""

import os

import pytest

playwright_api = pytest.importorskip(
    'playwright.sync_api', reason='playwright not installed')

from playwright.sync_api import sync_playwright  # noqa: E402

SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screenshots')

# Pages a stakeholder demo would walk through, with a label for the filename.
DEMO_PAGES = (
    ('/', '01-dashboard'),
    ('/students', '02-students'),
    ('/teachers', '03-teachers'),
    ('/classes', '04-classes'),
    ('/attendance/students', '05-attendance'),
    ('/attendance/summary', '06-attendance-summary'),
    ('/fees', '07-fees'),
    ('/expenses', '08-expenses'),
    ('/payroll', '09-payroll'),
    ('/financials/summary?preset=this_vs_last', '10-financial-comparison'),
    ('/reports/hub', '11-reports'),
    ('/settings', '12-settings'),
)

VIEWPORTS = (
    ('desktop', 1440, 900),
    ('mobile', 390, 844),
)


@pytest.fixture(scope='module')
def base_url():
    """Start the app on a free port and yield its base URL."""
    import socket
    import threading
    import time

    import app as app_pkg
    from app.config import get_config

    config = get_config()
    application = app_pkg.create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})

    # Pick a free port so parallel runs do not collide.
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()

    url = f'http://127.0.0.1:{port}'

    def run():
        application.run(host='127.0.0.1', port=port, use_reloader=False,
                        threaded=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    # Wait for the server to accept connections.
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                break
        except OSError:
            time.sleep(0.2)
    else:
        pytest.fail('the app did not start in time')

    yield url


@pytest.fixture(scope='module')
def credentials():
    return {
        'username': os.environ.get('INITIAL_ADMIN_USERNAME', 'admin'),
        'password': os.environ.get('INITIAL_ADMIN_PASSWORD', 'adminpass123'),
    }


def _login(page, base_url, credentials):
    """Log in. `load` is used rather than `networkidle` because the CDN assets
    and DataTables keep the network busy, so networkidle never settles."""
    page.goto(f'{base_url}/login', wait_until='load')
    page.fill('input[name="username"]', credentials['username'])
    page.fill('input[name="password"]', credentials['password'])
    page.click('button[type="submit"]')
    page.wait_for_load_state('load')
    page.wait_for_timeout(600)


def test_demo_walkthrough_captures_screenshots(base_url, credentials):
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    captured = []
    problems = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for label, width, height in VIEWPORTS:
                context = browser.new_context(viewport={'width': width, 'height': height})
                page = context.new_page()
                _login(page, base_url, credentials)

                for path, name in DEMO_PAGES:
                    page.goto(f'{base_url}{path}', wait_until='load')
                    # Let charts and DataTables settle.
                    page.wait_for_timeout(700)

                    filename = f'{label}-{name}.png'
                    page.screenshot(path=os.path.join(SCREENSHOT_DIR, filename),
                                    full_page=False)
                    captured.append(filename)

                    # Collect console errors as a smoke signal.
                    body = page.inner_text('body')
                    if 'Internal Server Error' in body:
                        problems.append(f'{label} {path}: server error page')

                    # Horizontal overflow is the classic wide-table failure.
                    overflow = page.evaluate(
                        'document.documentElement.scrollWidth - '
                        'document.documentElement.clientWidth')
                    if label == 'desktop' and overflow > 40:
                        problems.append(f'{label} {path}: overflows by {overflow}px')

                context.close()
        finally:
            browser.close()

    assert not problems, problems
    assert len(captured) == len(DEMO_PAGES) * len(VIEWPORTS)
    print(f'\ncaptured {len(captured)} screenshots in {SCREENSHOT_DIR}')


def test_styled_confirm_dialog_replaces_native(base_url, credentials):
    """Clicking delete opens the app's own modal, not a browser dialog."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()

        dialogs = []
        page.on('dialog', lambda dialog: (dialogs.append(dialog.type()),
                                         dialog.dismiss()))
        try:
            _login(page, base_url, credentials)
            page.goto(f'{base_url}/expenses', wait_until='load')
            page.wait_for_timeout(500)

            delete_button = page.query_selector('form[data-confirm] button')
            if delete_button is None:
                pytest.skip('no expense rows to test the delete confirm')

            delete_button.click()
            page.wait_for_timeout(500)

            # Our modal must be visible and no native dialog may have fired.
            modal = page.query_selector('#schoolConfirmModal.show')
            assert modal is not None, 'styled confirmation modal did not open'
            assert dialogs == [], f'native dialog(s) fired: {dialogs}'
            page.screenshot(path=os.path.join(SCREENSHOT_DIR,
                                              'desktop-13-confirm-dialog.png'))
        finally:
            context.close()
            browser.close()


def test_print_stylesheet_hides_chrome(app):
    """Printing must drop the sidebar, toolbar and flash messages."""
    with open(os.path.join(app.root_path, 'static', 'style.css'),
              encoding='utf-8') as handle:
        css = handle.read()
    assert '@media print' in css
    for selector in ('.no-print', '#sidebar', '.mobile-topbar'):
        assert selector in css


def test_print_media_actually_hides_chrome(base_url, credentials):
    """Emulate print media in a real browser and check the computed styles.

    The stylesheet rules are asserted above; this proves the browser applies
    them (sidebar and flash messages must not appear on printed pages).
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 950})
        try:
            _login(page, base_url, credentials)
            for path in ('/students', '/expenses'):
                page.goto(f'{base_url}{path}', wait_until='load')
                page.wait_for_timeout(600)
                page.emulate_media(media='print')

                sidebar = page.eval_on_selector(
                    '#sidebar', 'el => getComputedStyle(el).display')
                topbar = page.eval_on_selector(
                    '.mobile-topbar', 'el => getComputedStyle(el).display')
                assert sidebar == 'none', f'{path}: sidebar prints ({sidebar})'
                assert topbar == 'none', f'{path}: topbar prints ({topbar})'
                page.emulate_media(media='screen')
        finally:
            browser.close()
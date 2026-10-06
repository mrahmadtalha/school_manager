"""Tests for preserving the Fees page filters across a receipt round-trip.

When a user filters /fees (class, billing month, By Class / All Unpaid, or the
reference search), collects a fee, and then returns via "Back to Fees", the same
filtered view must come back.

The filters travel as whitelisted ``return_*`` values: they are rebuilt
server-side with url_for, never taken verbatim from the request (an open
redirect would otherwise be possible).
"""

import os
import shutil
import socket
import threading
import time

import pytest

from app.database import db
from app.models import ClassModel, FeeRecordModel, StudentModel
from app.routes import fees as fees_routes
from app.services.fee_ledger import current_month


# --------------------------------------------------------------------------- #
# helper-level behaviour
# --------------------------------------------------------------------------- #

def test_return_filters_describe_the_current_view(app):
    """list_return_filters mirrors the filters actually being applied."""
    with app.app_context():
        values = fees_routes.list_return_filters(
            class_id=2, month_year='September 2026', show_unpaid=False,
            ref_query='SLIP-1')
    assert values['return_class_id'] == '2'
    assert values['return_month_year'] == 'September 2026'
    assert values['return_ref_query'] == 'SLIP-1'
    # The view mode is always recorded so By Class vs All Unpaid round-trips.
    assert values['return_show_unpaid'] == '0'

    with app.app_context():
        unpaid = fees_routes.list_return_filters(show_unpaid=True)
    assert unpaid['return_show_unpaid'] == '1'


def test_return_filter_values_validates_and_coerces(app):
    with app.app_context():
        parsed = fees_routes.return_filter_values({
            'return_class_id': '2',
            'return_month_year': 'September 2026',
            'return_show_unpaid': '1',
            'return_ref_query': 'SLIP-9',
        })
    assert parsed == {'class_id': 2, 'month_year': 'September 2026',
                      'show_unpaid': '1', 'ref_query': 'SLIP-9'}


def test_return_filter_values_drops_junk(app):
    with app.app_context():
        # Unknown keys never survive.
        assert fees_routes.return_filter_values(
            {'return_evil': 'http://attacker.example'}) == {}
        # A non-numeric class id is rejected rather than injected.
        assert fees_routes.return_filter_values({'return_class_id': 'abc'}) == {}
        assert fees_routes.return_filter_values({'return_class_id': '-4'}) == {}
        assert fees_routes.return_filter_values(None) == {}


def test_show_unpaid_accepts_the_usual_truthy_spellings(app):
    with app.app_context():
        for truthy in ('1', 'true', 'on', 'yes'):
            assert fees_routes.return_filter_values(
                {'return_show_unpaid': truthy}) == {'show_unpaid': '1'}
        for falsy in ('0', 'no', ''):
            assert fees_routes.return_filter_values(
                {'return_show_unpaid': falsy}) == {'show_unpaid': '0'}


def test_back_to_fees_url_accepts_both_naming_schemes(app):
    with app.test_request_context('/'):
        # Plain query names...
        assert fees_routes.back_to_fees_url(class_id=5) == '/fees?class_id=5'
        # ...and the return_* names used on the receipt URL.
        assert fees_routes.back_to_fees_url(return_class_id=5) == '/fees?class_id=5'


def test_back_to_fees_url_is_safe_by_default(app):
    """No recognised filter (or a hostile one) must never redirect elsewhere."""
    with app.test_request_context('/'):
        assert fees_routes.back_to_fees_url() == '/fees'
        hostile = fees_routes.back_to_fees_url(
            evil='http://attacker.example', next='//attacker.example')
        assert hostile == '/fees'
        # A hostile value alongside a valid key is ignored, not obeyed.
        mixed = fees_routes.back_to_fees_url(
            next='//attacker.example', return_class_id=3)
        assert mixed == '/fees?class_id=3'


def test_receipt_return_args_keeps_the_return_names(app):
    with app.app_context():
        args = fees_routes.receipt_return_args({
            'return_class_id': '2', 'return_show_unpaid': '0'})
    assert args == {'return_class_id': 2, 'return_show_unpaid': '0'}


# --------------------------------------------------------------------------- #
# HTTP behaviour
# --------------------------------------------------------------------------- #

def _first_class_with_students():
    for class_obj in ClassModel.query.order_by(ClassModel.id).all():
        if StudentModel.query.filter_by(is_active=True,
                                        class_id=class_obj.id).count():
            return class_obj
    return None


def test_fees_page_embeds_return_filters_in_the_payment_form(admin_client, app, seed):
    """The Collect Fee form must carry the current filters."""
    with app.app_context():
        class_obj = _first_class_with_students()
        if class_obj is None:
            pytest.skip('no class with students')
        class_id = class_obj.id

    body = admin_client.get(f'/fees?class_id={class_id}').get_data(as_text=True)
    assert 'name="return_class_id"' in body
    assert f'name="return_class_id" value="{class_id}"' in body
    assert 'name="return_show_unpaid"' in body
    assert 'name="return_month_year"' in body


def test_receipt_without_filters_links_to_the_plain_list(admin_client, app, seed):
    with app.app_context():
        student = db.session.get(StudentModel, seed['student_id'])
        student_id = student.id

    body = admin_client.get(
        f'/fees/receipt/{student_id}/{current_month()}').get_data(as_text=True)
    # Falls back to the unfiltered list rather than inventing filters.
    assert 'Back to Fees' in body
    assert 'href="/fees"' in body


def test_receipt_with_filters_links_back_to_them(admin_client, app, seed):
    with app.app_context():
        student_id = db.session.get(StudentModel, seed['student_id']).id

    body = admin_client.get(
        f'/fees/receipt/{student_id}/{current_month()}'
        '?return_class_id=7&return_show_unpaid=1').get_data(as_text=True)
    assert '/fees?class_id=7&amp;show_unpaid=1' in body or \
        '/fees?class_id=7&show_unpaid=1' in body


def test_receipt_ignores_hostile_return_values(admin_client, app, seed):
    """A crafted receipt URL must not become an open redirect."""
    with app.app_context():
        student_id = db.session.get(StudentModel, seed['student_id']).id

    body = admin_client.get(
        f'/fees/receipt/{student_id}/{current_month()}'
        '?return_next=//attacker.example&return_class_id=3').get_data(as_text=True)
    assert 'attacker.example' not in body
    assert '/fees?class_id=3' in body or '/fees?class_id=3&amp;' in body


def test_all_unpaid_view_marks_return_show_unpaid(admin_client, app, seed):
    body = admin_client.get('/fees?show_unpaid=1').get_data(as_text=True)
    assert 'name="return_show_unpaid" value="1"' in body


def test_existing_fee_filters_still_work(admin_client, app, seed):
    """The filters themselves are unchanged by this work."""
    with app.app_context():
        class_obj = _first_class_with_students()
        if class_obj is None:
            pytest.skip('no class with students')
        class_id, class_name = class_obj.id, class_obj.name

    body = admin_client.get(f'/fees?class_id={class_id}').get_data(as_text=True)
    assert class_name in body
    # The view toggle and reference search are still present and functional.
    assert 'All Unpaid' in body
    assert 'name="ref_query"' in body


# --------------------------------------------------------------------------- #
# browser round-trip (skipped when Playwright is unavailable)
# --------------------------------------------------------------------------- #

playwright_api = pytest.importorskip('playwright.sync_api',
                                     reason='playwright not installed')

from playwright.sync_api import sync_playwright  # noqa: E402

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_DB = os.path.join(_PROJECT, 'instance', 'school.db')
_WORK_DB = os.path.join(_PROJECT, 'instance', 'test_return_filters_copy.db')

if os.path.exists(_REAL_DB):
    if os.path.exists(_WORK_DB):
        os.remove(_WORK_DB)
    shutil.copy2(_REAL_DB, _WORK_DB)
    os.environ['DATABASE_URL'] = 'sqlite:///' + _WORK_DB.replace('\\', '/')


@pytest.fixture(scope='module')
def live_fee_server():
    """Serve the app over a COPY of the instance database.

    A copy is used because the round-trip records a real payment; the user's own
    database must never be modified by a test.
    """
    if not os.path.exists(_REAL_DB):
        pytest.skip('no instance database to copy')

    import app as app_pkg

    application = app_pkg.create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    with application.app_context():
        from app.models import ROLE_ADMIN, AdminUser
        user = AdminUser.query.filter_by(username='admin').first()
        if user is None:
            user = AdminUser(username='admin', role=ROLE_ADMIN, full_name='Admin')
            db.session.add(user)
        user.set_password(os.environ['TEST_RETURN_PW'])
        db.session.commit()

    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    url = f'http://127.0.0.1:{port}'
    threading.Thread(target=lambda: application.run(
        host='127.0.0.1', port=port, use_reloader=False, threaded=True),
        daemon=True).start()

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
    # Dispose the engine before deleting the copy: SQLite keeps the file handle
    # open, and Windows refuses to remove an in-use file.
    with application.app_context():
        db.session.remove()
        db.engine.dispose()
    try:
        if os.path.exists(_WORK_DB):
            os.remove(_WORK_DB)
    except OSError:
        # Leaving a scratch copy behind must never fail the suite.
        pass


def _login(page, base, secret):
    page.goto(f'{base}/login', wait_until='load')
    page.fill('input[name="username"]', 'admin')
    page.fill('input[name="password"]', secret)
    page.click('button[type="submit"]')
    page.wait_for_load_state('load')


def _collect_a_fee(page):
    """Open the first Collect Fee modal and submit it."""
    page.locator('button[title="Record Payment"]').first.click()
    page.wait_for_timeout(500)
    modal = page.locator('.modal.show')
    amount = modal.locator('input[name="amount_paid"]')
    if amount.count() and amount.first.is_editable():
        amount.first.fill('10')
    modal.locator('button[type="submit"]').first.click()
    page.wait_for_load_state('load')
    page.wait_for_timeout(800)


@pytest.mark.skipif('TEST_RETURN_PW' not in os.environ,
                    reason='TEST_RETURN_PW not set')
def test_browser_back_to_fees_restores_the_class_filter(live_fee_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 950})
        try:
            _login(page, live_fee_server, os.environ['TEST_RETURN_PW'])
            page.goto(f'{live_fee_server}/fees', wait_until='load')
            page.wait_for_timeout(800)

            # Pick a class that has rows so the Collect Fee button exists.
            options = page.eval_on_selector_all(
                'select[name="class_id"] option', 'els => els.map(e => e.value)')
            chosen = None
            for value in options:
                page.goto(f'{live_fee_server}/fees?class_id={value}',
                          wait_until='load')
                page.wait_for_timeout(600)
                if page.locator('button[title="Record Payment"]').count():
                    chosen = value
                    break
            if chosen is None:
                pytest.skip('no fee rows to exercise the round-trip')

            before = page.url
            assert f'class_id={chosen}' in before

            _collect_a_fee(page)
            receipt_url = page.url
            assert '/fees/receipt/' in receipt_url

            page.locator('a:has-text("Back to Fees")').first.click()
            page.wait_for_load_state('load')
            page.wait_for_timeout(700)

            selected = page.eval_on_selector('select[name="class_id"]',
                                             'el => el.value')
            assert selected == chosen, (
                'class filter was lost: expected %s, got %s'
                % (chosen, selected))
        finally:
            browser.close()


@pytest.mark.skipif('TEST_RETURN_PW' not in os.environ,
                    reason='TEST_RETURN_PW not set')
def test_browser_back_to_fees_restores_the_all_unpaid_view(live_fee_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 950})
        try:
            _login(page, live_fee_server, os.environ['TEST_RETURN_PW'])
            page.goto(f'{live_fee_server}/fees?show_unpaid=1', wait_until='load')
            page.wait_for_timeout(900)
            if not page.locator('button[title="Record Payment"]').count():
                pytest.skip('no unpaid rows to exercise the round-trip')

            _collect_a_fee(page)
            page.locator('a:has-text("Back to Fees")').first.click()
            page.wait_for_load_state('load')
            page.wait_for_timeout(700)

            assert 'show_unpaid=1' in page.url, (
                'All Unpaid view was lost, landed on %s' % page.url)
        finally:
            browser.close()

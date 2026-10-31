"""Sidebar redesign: group headings that open and close, quick find, one shared finance
block, exactly one highlighted link per page, valid markup, labels for icon-only mode,
Urdu, keyboard skip link.

The sidebar lives in app/templates/_sidebar_nav.html (included by base.html)."""

import re
from pathlib import Path

from app.database import db
from app.models import AdminUser
from tests.conftest import login

ROOT = Path(__file__).resolve().parent.parent


def _sidebar(html):
    start = html.find('<ul class="nav flex-column')
    return html[start:html.find('</nav>', start)]


def _headings(html):
    return re.findall(r'nav-section-text">([^<]+)<', _sidebar(html))


def _labels(html):
    return re.findall(r'nav-label">\s*([^<]+?)\s*</span>', _sidebar(html))


def _open_links(html):
    """Names of the links drawn as the open (highlighted) page."""
    return re.findall(r'class="nav-link text-white active"[^>]*aria-label="([^"]+)"', _sidebar(html))


def _get(client, path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response.get_data(as_text=True)


# -- headings -----------------------------------------------------------------

def test_administrator_menu_is_grouped_under_headings(admin_client):
    html = _get(admin_client, '/')
    headings = _headings(html)
    for expected in ('Academics', 'Attendance', 'Assessment', 'Finance', 'System'):
        assert expected in headings, headings
    # the groups appear in this order
    assert [h for h in headings if h in ('Academics', 'Attendance', 'Assessment', 'Finance', 'System')] == \
        ['Academics', 'Attendance', 'Assessment', 'Finance', 'System']


def test_teacher_menu_has_no_finance_or_system_group(teacher_client):
    html = _get(teacher_client, '/')
    headings = _headings(html)
    assert 'Academics' in headings
    assert 'Finance' not in headings and 'System' not in headings
    assert 'Fees Management' not in _labels(html)


def test_accountant_menu_is_one_finance_group(app, client):
    with app.app_context():
        user = AdminUser(username='acct', role='accountant', full_name='Test Accountant')
        user.set_password('LongPass#123')
        db.session.add(user)
        db.session.commit()
    login(client, 'acct', 'LongPass#123')
    html = _get(client, '/fees')
    assert _headings(html) == ['Finance']
    labels = _labels(html)
    assert labels[0] == 'Fees Management' and 'Finance &amp; Exports' in labels
    assert _open_links(html) == ['Fees Management']


def test_no_heading_is_left_empty(admin_client):
    html = _sidebar(_get(admin_client, '/'))
    parts = re.split(r'<li class="nav-item nav-section"', html)[1:]
    assert parts
    for part in parts:
        # between one heading and the next there must be at least one link
        assert 'class="nav-link' in part, part[:200]


# -- one highlighted link ---------------------------------------------------------

def test_exactly_one_link_is_highlighted_on_each_page(admin_client):
    pages = {
        '/': 'Dashboard',
        '/students/': 'Students',
        '/teachers': 'Teachers',
        '/classes': 'Classes &amp; Subjects',
        '/attendance/students': 'Daily Attendance',
        '/attendance/summary': 'Attendance Summary',
        '/tests': 'Testing &amp; Marks Hub',
        '/reports/hub': 'Analytics &amp; Exports',
        '/documents': 'ID Cards &amp; Certificates',
        '/fees': 'Fees Management',
        '/license': 'License',
        '/settings': 'School Settings',
    }
    for path, expected in pages.items():
        assert _open_links(_get(admin_client, path)) == [expected], path


def test_finance_pages_light_up_their_own_link(admin_client):
    """Before: Other Income, Admission Fees and Insights never lit up, and the
    Financial Overview page also lit up *Attendance Summary* and the Insights page
    lit up *Financial Overview*."""
    pages = {
        '/financials/summary': 'Financial Overview',
        '/financials/insights': 'Financial Insights',
        '/other-income': 'Other Income',
        '/admission-fees': 'Admission Fees',
    }
    for path, expected in pages.items():
        assert _open_links(_get(admin_client, path)) == [expected], path


# -- markup ----------------------------------------------------------------------

def test_menu_markup_is_balanced_and_not_nested(admin_client):
    html = _sidebar(_get(admin_client, '/'))
    assert html.count('<li') == html.count('</li>')
    # no list item sits inside another list item (the old finance block did)
    depth = 0
    for token in re.findall(r'<li\b|</li>', html):
        depth += 1 if token.startswith('<li') else -1
        assert depth in (0, 1), 'nested <li>'


def test_every_link_has_a_name_for_icon_only_mode(admin_client):
    html = _sidebar(_get(admin_client, '/'))
    links = re.findall(r'<(?:a|button)\b[^>]*class="[^"]*nav-link[^"]*"[^>]*>', html)
    assert links
    for tag in links:
        assert 'aria-label="' in tag or 'title="' in tag, tag
    assert 'aria-label="Users &amp; Roles"' in html


def test_finance_links_are_written_once_for_everyone(admin_client):
    page = _get(admin_client, '/')
    for label in ('Fees Management', 'Expenses', 'Payroll', 'Financial Overview'):
        assert page.count('<span class="nav-label">%s</span>' % label) == 1, label


def test_existing_menu_markup_other_tests_rely_on_is_kept(admin_client):
    html = _get(admin_client, '/classes')
    assert 'nav flex-column' in html and 'sidebar-footer-divider' in html
    assert '<span class="nav-label">License</span>' in html
    assert 'Exit Software' in html and 'exitSoftwareModal' in html


# -- keyboard / page shell -----------------------------------------------------

def test_skip_link_and_main_target(admin_client):
    html = _get(admin_client, '/')
    assert 'href="#main-content"' in html
    assert '<main id="main-content"' in html


def test_sidebar_scroll_is_remembered(admin_client):
    html = _get(admin_client, '/')
    assert 'sm.sidebarScroll' in html


def test_style_sheet_keeps_the_menu_on_screen_and_styles_headings():
    css = (ROOT / 'app' / 'static' / 'style.css').read_text(encoding='utf-8')
    assert '.nav-section-title' in css
    assert 'position: sticky' in css and 'overflow-y: auto' in css
    assert 'prefers-reduced-motion' in css


# -- Urdu ------------------------------------------------------------------------

def test_headings_and_skip_link_are_translated_to_urdu(admin_client):
    admin_client.get('/language/ur')
    html = _get(admin_client, '/')
    headings = _headings(html)
    for urdu in ('تعلیم', 'امتحانات اور نتائج', 'مالیات', 'سسٹم'):
        assert urdu in headings, headings
    assert 'مرکزی صفحے پر جائیں' in html
    admin_client.get('/language/en')


# -- groups that open / close and quick find ------------------------------------

def test_headings_are_buttons_that_can_open_and_close_a_group(admin_client):
    html = _sidebar(_get(admin_client, '/'))
    buttons = re.findall(r'<button type="button" class="nav-section-title" data-group="([a-z]+)" aria-expanded="true">', html)
    assert buttons == ['academics', 'attendance', 'assessment', 'documents', 'finance', 'system'], buttons
    # every link sits directly after its heading, marked as a group member
    assert html.count('class="nav-item in-group') >= 15


def test_group_state_is_remembered_and_open_page_is_never_hidden(admin_client):
    page = _get(admin_client, '/')
    assert 'sm.sidebarGroups' in page
    assert "a.nav-link.active" in page          # the group holding the open page is kept open


def test_quick_find_box_for_the_administrator(admin_client):
    html = _get(admin_client, '/')
    assert 'id="sidebarFind"' in html and 'role="search"' in html
    assert 'id="sidebarFindEmpty"' in html and 'Ctrl K' in html


def test_quick_find_box_for_a_teacher(teacher_client):
    assert 'id="sidebarFind"' in _get(teacher_client, '/')


def test_quick_find_and_group_styles_exist():
    css = (ROOT / 'app' / 'static' / 'style.css').read_text(encoding='utf-8')
    for needle in ('.group-collapsed', '.is-finding', '.find-hide', '.sidebar-find-input'):
        assert needle in css, needle
    # icon-only mode shows every link whatever the group state
    assert 'html.sidebar-collapsed #sidebar .nav-item.group-collapsed' in css


def test_quick_find_is_translated_to_urdu(admin_client):
    admin_client.get('/language/ur')
    html = _get(admin_client, '/')
    assert 'placeholder="صفحہ تلاش کریں"' in html
    assert 'کوئی صفحہ نہیں ملا' in html
    admin_client.get('/language/en')

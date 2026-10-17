"""Requirement 18 - Subject Library lives on the Classes page.

Checks that the sidebar has no timetable / subject-library entries and that
/classes still offers the Subject Library button.  Uses the isolated test DB
from tests/conftest.py.
"""
import re


def _nav_labels(html):
    nav = html[html.find('nav flex-column'):html.find('sidebar-footer-divider')]
    return re.findall(r'nav-label">\s*([^<]+?)\s*</span>', nav)


def test_sidebar_no_longer_has_timetable_or_subject_library(admin_client):
    html = admin_client.get('/classes').data.decode('utf-8', 'ignore')
    labels = [l.lower() for l in _nav_labels(html)]
    assert labels, 'sidebar not found in page'
    assert not any('timetable' in l for l in labels), labels
    assert not any('subject library' in l for l in labels), labels
    assert any('classes' in l for l in labels), labels


def test_classes_page_has_subject_library_button(admin_client):
    html = admin_client.get('/classes').data.decode('utf-8', 'ignore')
    assert 'Subject Library' in html
    sl = re.search(r'href="([^"]+)"[^>]*>\s*<i class="fas fa-book-open me-1"></i>\s*Subject Library', html)
    assert sl and sl.group(1) == '/subjects/library', sl and sl.group(1)
    assert admin_client.get('/subjects/library').status_code == 200


def test_old_timetable_pages_are_gone_and_new_sheet_is_linked(admin_client):
    html = admin_client.get('/classes').data.decode('utf-8', 'ignore')
    assert '/timetable"' in html
    assert admin_client.get('/timetables').status_code == 404
    assert admin_client.get('/timetables/teachers').status_code == 404

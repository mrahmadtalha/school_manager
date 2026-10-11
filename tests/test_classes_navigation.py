"""Requirement 18 — Timetable and Subject Library live on the Classes page.

Checks that the sidebar entries are gone, that /classes offers both buttons
pointing at the existing interfaces, and that the 2 timetable templates remain.
Uses the isolated test DB from tests/conftest.py.
"""
import re

from app.services import timetable_redesign as redesign


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


def test_classes_page_has_both_buttons(admin_client):
    html = admin_client.get('/classes').data.decode('utf-8', 'ignore')
    assert 'Timetable Settings' in html
    assert 'Subject Library' in html

    tt = re.search(r'href="([^"]+)"[^>]*>\s*<i class="fas fa-calendar-days me-1"></i>\s*Timetable Settings', html)
    sl = re.search(r'href="([^"]+)"[^>]*>\s*<i class="fas fa-book-open me-1"></i>\s*Subject Library', html)
    assert tt and tt.group(1) == '/timetables', tt and tt.group(1)
    assert sl and sl.group(1) == '/subjects/library', sl and sl.group(1)


def test_buttons_open_existing_interfaces(admin_client):
    assert admin_client.get('/timetables').status_code == 200
    assert admin_client.get('/subjects/library').status_code == 200
    # the existing, non-duplicate interfaces must still be reachable
    assert admin_client.get('/timetables/teachers').status_code == 200


def test_two_customised_templates_still_available(admin_client):
    labels = {k: v.get('label') for k, v in redesign.REDESIGN_TEMPLATES.items()}
    assert len(labels) == 2, labels
    assert set(labels) == {'matrix', 'daygrid'}, labels
    for key in labels:
        assert admin_client.get('/timetables?template_key=' + key).status_code == 200

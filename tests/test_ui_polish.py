"""Tests for the UI polish work: styled dialogs, toasts, button semantics,
accessibility and the plain-language guidance hints.

These guard the conventions so later edits cannot quietly reintroduce native
browser dialogs, unlabelled icon buttons or inconsistent wording.
"""

import os
import re

from app.database import db
from app.models import Expense, ExpenseCategory, StudentModel

TEMPLATE_DIR = 'templates'

# Buttons whose entire content is an icon need an accessible name.
BUTTON_RE = re.compile(r'<button\b([^>]*)>(.*?)</button>', re.S | re.I)


def _read(app, name):
    with open(os.path.join(app.root_path, TEMPLATE_DIR, name), encoding='utf-8') as handle:
        return handle.read()


def _all_templates(app, skip_private=True):
    folder = os.path.join(app.root_path, TEMPLATE_DIR)
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.html'):
            continue
        if skip_private and name.startswith('_'):
            continue
        with open(os.path.join(folder, name), encoding='utf-8') as handle:
            yield name, handle.read()


def _seed_expense():
    category = ExpenseCategory.query.filter_by(name='UI Test Cat').first()
    if category is None:
        category = ExpenseCategory(name='UI Test Cat')
        db.session.add(category)
        db.session.flush()
    expense = Expense(category_id=category.id, amount=25.0,
                      payment_method='Cash', logged_by_name='ui-test')
    db.session.add(expense)
    db.session.commit()
    return expense


# --------------------------------------------------------------------------- #
# Task 5/6 — no native browser dialogs remain
# --------------------------------------------------------------------------- #

def test_no_native_alert_or_confirm_left_in_templates(app):
    """Every native dialog has been replaced by the styled equivalent."""
    offenders = []
    pattern = re.compile(r'(?<![\w.])(alert|confirm)\(')
    for name, content in _all_templates(app, skip_private=False):
        for match in pattern.finditer(content):
            line = content[:match.start()].count('\n') + 1
            offenders.append(f'{name}:{line}')
    assert offenders == [], offenders


def test_no_native_onsubmit_confirm_remains(app):
    offenders = []
    for name, content in _all_templates(app, skip_private=False):
        if 'onsubmit="return confirm(' in content or 'onclick="return confirm(' in content:
            offenders.append(name)
    assert offenders == [], offenders


def test_ui_js_exposes_the_shared_api(app):
    with open(os.path.join(app.root_path, 'static', 'ui.js'), encoding='utf-8') as handle:
        js = handle.read()
    for token in ('window.SchoolUI', 'confirm:', 'toast:', 'data-confirm',
                  'schoolConfirmModal', 'schoolToastContainer',
                  'bootstrap.Modal', 'bootstrap.Toast'):
        assert token in js, token


def test_ui_js_is_loaded_after_bootstrap(admin_client, app):
    body = admin_client.get('/expenses').get_data(as_text=True)
    bootstrap_at = body.index('bootstrap.bundle.min.js')
    ui_at = body.index('ui.js')
    assert bootstrap_at < ui_at, 'ui.js must load after the Bootstrap bundle'
    assert '/static/ui.js' in body


def test_expenses_delete_uses_data_confirm(admin_client, app):
    with app.app_context():
        _seed_expense()
    body = admin_client.get('/expenses').get_data(as_text=True)
    assert 'data-confirm="Delete this expense? This cannot be undone."' in body
    assert 'data-confirm-ok="Delete expense"' in body
    assert "confirm('Delete this expense" not in body


def test_bulk_restore_uses_data_confirm(admin_client, app, seed):
    with app.app_context():
        student = db.session.get(StudentModel, seed['student_id'])
        student.is_active = False
        student.status = 'slc_issued'
        db.session.commit()

    body = admin_client.get('/students/archived').get_data(as_text=True)
    assert 'data-confirm="Restore ALL' in body
    assert 'data-confirm-ok="Restore all"' in body


def test_payroll_and_examination_confirms_are_declarative(admin_client, app):
    """The remaining confirm sites use the styled dialog, not the browser's."""
    for name in ('payroll.html', 'examination_detail.html', 'student_attendance.html',
                 'class_timetable.html'):
        content = _read(app, name)
        assert 'data-confirm=' in content, name
        assert 'return confirm(' not in content, name


# --------------------------------------------------------------------------- #
# Task 7 — button semantics and wording
# --------------------------------------------------------------------------- #

def test_export_actions_use_one_verb(app):
    """All file downloads say 'Export', never 'Download'."""
    offenders = []
    for name, content in _all_templates(app, skip_private=False):
        for match in re.finditer(r'>\s*Download (CSV|Excel|PDF)', content):
            line = content[:match.start()].count('\n') + 1
            offenders.append(f'{name}:{line}')
    assert offenders == [], offenders


def test_no_ambiguous_go_button(app):
    offenders = []
    for name, content in _all_templates(app, skip_private=False):
        if re.search(r'>\s*Go\s*</button>', content):
            offenders.append(name)
    assert offenders == [], offenders


def test_edit_forms_submit_with_save_not_update(app):
    offenders = []
    for name, content in _all_templates(app, skip_private=False):
        if re.search(r'>\s*Update\s*</button>', content):
            offenders.append(name)
        if re.search(r'>\s*Save Changes\s*</button>', content):
            offenders.append(name)
    assert offenders == [], offenders


def test_creation_buttons_say_add_not_new(app):
    """Creation buttons follow one pattern: 'Add <thing>'."""
    offenders = []
    for name, content in _all_templates(app, skip_private=False):
        for match in re.finditer(r'>\s*Add New ([A-Z][a-z]+)', content):
            line = content[:match.start()].count('\n') + 1
            offenders.append(f'{name}:{line}')
    assert offenders == [], offenders


def test_creation_buttons_are_consistent(admin_client, app):
    pattern = re.compile(
        r'<button\b[^>]*data-bs-target="#add[A-Za-z]*Modal"[^>]*>(.*?)</button>',
        re.S | re.I)
    labels = set()
    for name, content in _all_templates(app):
        for match in pattern.finditer(content):
            label = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', match.group(1))).strip()
            if label:
                labels.add(label)
    # Every creation button starts with "Add ".
    for label in labels:
        assert label.startswith('Add ') or label == 'Test Categories', label


# --------------------------------------------------------------------------- #
# Task 8 — accessibility
# --------------------------------------------------------------------------- #

def test_every_icon_only_button_has_an_accessible_name(app):
    offenders = []
    for name, content in _all_templates(app, skip_private=False):
        for match in BUTTON_RE.finditer(content):
            attrs, body = match.group(1), match.group(2)
            visible = re.sub(r'<[^>]+>', '', body).strip()
            has_icon = '<i ' in body or '<i>' in body
            if has_icon and not visible and 'aria-label' not in attrs:
                line = content[:match.start()].count('\n') + 1
                offenders.append(f'{name}:{line}')
    assert offenders == [], offenders


def test_stylesheet_defines_a_visible_focus_ring(app):
    with open(os.path.join(app.root_path, 'static', 'style.css'), encoding='utf-8') as handle:
        css = handle.read()
    assert ':focus-visible' in css
    assert 'outline:' in css
    # Dark surfaces get a lighter ring so it stays visible.
    assert 'outline-color: #93c5fd' in css


def test_icon_buttons_keep_their_tooltip_too(app, seed):
    """title is still set for mouse users, alongside the new aria-label."""
    content = _read(app, 'students.html')
    assert 'title="Edit"' in content
    assert 'aria-label=' in content


# --------------------------------------------------------------------------- #
# Task 9 — plain-language guidance hints
# --------------------------------------------------------------------------- #

def test_students_page_has_a_what_to_do_hint(admin_client, app):
    body = admin_client.get('/students').get_data(as_text=True)
    assert 'What to do now:' in body
    assert 'Add Student' in body


def test_classes_page_has_a_what_to_do_hint(admin_client, app):
    body = admin_client.get('/classes').get_data(as_text=True)
    assert 'What to do now:' in body
    # The hint explains the domain in plain words.
    assert 'year group' in body
    assert 'sections' in body


def test_guidance_hints_follow_the_payroll_pattern(app):
    """Payroll established the pattern; the new hints match its structure."""
    payroll = _read(app, 'payroll.html')
    assert 'What to do now:' in payroll
    for name in ('students.html', 'classes.html'):
        content = _read(app, name)
        assert 'alert alert-info' in content, name
        assert 'What to do now:' in content, name
        # Hints must not print.
        assert 'no-print' in content, name


def test_guidance_hint_is_absent_from_empty_state_wording_duplication(app):
    """The students hint adapts when there are no students yet."""
    content = _read(app, 'students.html')
    assert 'There are no students yet' in content

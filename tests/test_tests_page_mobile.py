"""Class Tests page (/tests) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid,
the summary is two lines of two boxes, the tool bar stacks, every row of the
List view becomes a card, and the dialogs get finger-sized buttons. These tests
check the pieces that layout needs and that no number, button, filter or dialog
went missing."""

from app.database import db
from tests.test_tests_page_redesign import _body, _class_with_students, _test, _three_tests


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .tl-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.tl-head' in block][0]


def test_phone_header_buttons_sit_in_a_grid(admin_client, app):
    _three_tests(app)
    css = _css(_body(admin_client))
    phone = css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]
    for needle in ('.tl-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.tl-tools .tl-switch { grid-column: 1 / -1; display: flex; }',     # Class Tests / Term Examinations on its own line
                   '.tl-tools > .btn { width: 100%; min-height: 2.6rem;'):
        assert needle in phone, needle


def test_phone_summary_toolbar_and_cards_fit_the_screen(admin_client, app):
    _three_tests(app)
    css = _css(_body(admin_client))
    small = css.split('@media (max-width: 575.98px) {', 1)[1].split('@media (prefers-reduced-motion', 1)[0]
    for needle in ('.tl-ico { width: 36px; height: 36px;',
                   '.tl-search { flex: 1 1 100%; }',
                   '.tl-toolbar .form-select { flex: 1 1 calc(50% - 0.3rem);',        # the two menus side by side
                   'font-size: 16px',                                                  # no iPhone zoom when a box is tapped
                   '.tl-tabs button .n { display: block;',
                   '.tl-viewbox { margin: 0; width: 100%; }',
                   '.tl-acts .btn-go, .tl-acts .btn-del { min-height: 2.75rem; }'):
        assert needle in small, needle
    assert '.tl-tiles { grid-template-columns: 1fr; }' not in css                      # the summary is no longer one tall stack


def test_list_rows_are_cards_on_a_phone(admin_client, app):
    _three_tests(app)
    css = _css(_body(admin_client))
    phone = css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]
    for needle in ('.tl-reg .table-responsive { overflow: visible; }',
                   '.tl-reg .table thead { display: none; }',
                   'grid-template-columns: repeat(3, minmax(0, 1fr))',
                   'box-shadow: inset 4px 0 0 var(--tone)',
                   'html[dir="rtl"] .tl-reg .table > tbody > tr.tl-row { box-shadow: inset -4px 0 0 var(--tone); }',   # Urdu: bar on the other side
                   '.tl-reg .table > tbody > tr.tl-row > td.d-none { display: block !important; }',                  # Subjects / Total Marks show in the card
                   'content: attr(data-label)',
                   '.tl-reg .tl-row-acts .btn-go-label { display: inline; }'):
        assert needle in phone, needle


def test_every_list_cell_has_its_phone_label(admin_client, app):
    _three_tests(app)
    rows = _body(admin_client)
    rows = rows[rows.index('id="testsList"'):]
    row = rows.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Class', 'Subjects', 'Total Marks', 'Marks entered'):
        assert 'data-label="%s"' % label in row, label
    assert rows.count('tl-c-wide') >= 6                       # marks bar + buttons of the three rows


def test_modals_are_comfortable_on_a_phone(admin_client, app):
    _three_tests(app)
    body = _body(admin_client)
    css = _css(body)
    phone = css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]
    for needle in ('#addTestModal .modal-footer .btn { flex: 1 1 100%;',
                   '#addTestModal .btn-sm.py-0',
                   '#addTestTypeModal .btn-sm { min-width: 2.5rem; min-height: 2.5rem; }'):
        assert needle in phone, needle
    # the "new category" row stacks on a phone but keeps its four columns from md up
    for needle in ('col-12 col-md-5', 'col-6 col-md-2', 'col-6 col-md-3', 'col-12 col-md-2'):
        assert needle in body, needle


def test_nothing_was_removed_from_the_page(admin_client, app):
    with app.app_context():
        cls, subject, kids = _class_with_students('Mobile Class', roll_base=7100)
        _test(cls, subject, 'Quiz Phone', kids[:1])
        db.session.commit()
    body = _body(admin_client)
    for needle in ('Class Tests', 'Term Examinations', 'Test Categories', 'Add Test',
                   'Tests in all', 'Tests this month', 'Marks complete', 'Marks still to enter',
                   'id="tlSearch"', 'id="classFilter"', 'id="typeFilter"', 'All tests', 'Marks to enter',
                   "setTestMode('todo')", "setTestMode('done')", 'id="tlClear"', 'Show tests as',
                   "setTestView('cards')", "setTestView('list')", 'id="testsGrid"', 'id="testsList"',
                   'id="addTestModal"', 'id="deleteBatchModal"', 'id="addTestTypeModal"',
                   'Create Test', 'Create &amp; Enter Marks', 'Quick presets:', 'Apply to selected class',
                   'aria-label="Delete test Quiz Phone"', '/tests/batch_marks',
                   'data-search="quiz phone', 'sm.testsFilters', 'sm.testsView'):
        assert needle in body, needle

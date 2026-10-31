"""Term Examinations page (/examinations) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid,
the summary is two lines of two boxes, the tool bar stacks, every row of the
List view becomes a card, and the Add Term Exam window shows one small card per
subject instead of a 6-column table. These tests check the pieces that layout
needs and that no number, button, filter or window went missing."""

from tests.test_examinations_page_redesign import _body, _three_exams


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .tl-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.tl-head' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1].split('@media (prefers-reduced-motion', 1)[0]


def test_phone_header_buttons_sit_in_a_grid(admin_client, app):
    _three_exams(app)
    phone = _phone(_css(_body(admin_client)))
    for needle in ('.tl-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.tl-tools .tl-switch { grid-column: 1 / -1; display: flex; }',      # Class Tests / Term Examinations on its own line
                   '.tl-tools > .btn { grid-column: 1 / -1; width: 100%; min-height: 2.6rem;'):
        assert needle in phone, needle


def test_phone_summary_toolbar_and_cards_fit_the_screen(admin_client, app):
    _three_exams(app)
    css = _css(_body(admin_client))
    small = _small(css)
    for needle in ('.tl-ico { width: 36px; height: 36px;',
                   '.tl-search { flex: 1 1 100%; }',
                   '.tl-toolbar .form-select { flex: 1 1 calc(50% - 0.3rem);',         # class / status / session menus two by two
                   'font-size: 16px',                                                   # no iPhone zoom when a box is tapped
                   '.tl-tabs button .n { display: block;',
                   '.tl-viewbox { margin: 0; width: 100%; }',
                   '.tl-acts .btn-go, .tl-acts .btn-sheet { min-height: 2.75rem; }'):
        assert needle in small, needle
    assert '.tl-tiles { grid-template-columns: 1fr; }' not in css                       # the summary is no longer one tall stack


def test_list_rows_are_cards_on_a_phone(admin_client, app):
    _three_exams(app)
    phone = _phone(_css(_body(admin_client)))
    for needle in ('.tl-reg .table-responsive { overflow: visible; }',
                   '.tl-reg .table thead { display: none; }',
                   'grid-template-columns: repeat(3, minmax(0, 1fr))',
                   'box-shadow: inset 4px 0 0 var(--tone)',
                   'html[dir="rtl"] .tl-reg .table > tbody > tr.tl-row { box-shadow: inset -4px 0 0 var(--tone); }',   # Urdu: bar on the other side
                   '.tl-reg .table > tbody > tr.tl-row > td.d-none { display: block !important; }',                  # Subjects / Total Marks show in the card
                   'content: attr(data-label)',
                   '.tl-reg .tl-row-acts .btn:not(:last-child) { flex: 1; }',          # Enter Marks / Open share the line, print stays small
                   '.tl-reg .tl-row-acts .btn-go-label { display: inline; }'):
        assert needle in phone, needle


def test_every_list_cell_has_its_phone_label(admin_client, app):
    _three_exams(app)
    rows = _body(admin_client)
    rows = rows[rows.index('id="examList"'):]
    row = rows.split('<tbody>', 1)[1].split('</tr>', 1)[0]
    for label in ('Class', 'Subjects', 'Total Marks', 'Marks entered'):
        assert 'data-label="%s"' % label in row, label
    assert rows.count('tl-c-wide') >= 6                       # marks bar + buttons of the three rows


def test_date_sheet_is_one_card_per_subject_on_a_phone(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    phone = _phone(_css(body))
    for needle in ('#addTermExamModal .table-responsive { overflow: visible; }',
                   '.te-sheet thead { display: none; }',
                   '.te-sheet tbody tr.te-subject-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));',
                   '.te-sheet .te-c-name { grid-column: 2 / -1;',
                   '.te-sheet .te-c-f { grid-column: span 2; }',
                   '.te-sheet .te-c-f::before { content: attr(data-label);',
                   '#addTermExamModal .modal-footer .btn { flex: 1 1 100%;',
                   '#addTermExamModal .btn-sm.py-0'):
        assert needle in phone, needle
    row = body[body.index('<tr class="te-subject-row"'):].split('</tr>', 1)[0]
    for label in ('Exam Date', 'Time', 'Room', 'Max Marks'):
        assert 'class="te-c-f" data-label="%s"' % label in row, label
    assert 'te-c-inc' in row and 'te-c-name' in row
    assert 'style="display:none;"' in row        # still hidden / shown by the class menu, so it keeps working


def test_nothing_was_removed_from_the_page(admin_client, app):
    _three_exams(app)
    body = _body(admin_client)
    for needle in ('Term Examinations', 'Class Tests', 'Add Term Exam', 'Term exams in all', 'Results published',
                   'Marks complete', 'Marks still to enter', 'id="tlSearch"', 'id="classFilter"', 'id="statusFilter"',
                   'All Classes', 'All Status', 'All term exams', 'Marks to enter',
                   "setExamMode('todo')", "setExamMode('done')", 'id="tlClear"', 'Show exams as',
                   "setExamView('cards')", "setExamView('list')", 'id="examGrid"', 'id="examList"',
                   'id="addTermExamModal"', 'Create Term Exam', 'Select all', 'Select none', 'Use start date for all',
                   'name="start_date"', 'name="end_date"', 'name="announce_date"', 'name="session_label"',
                   'Date sheet', 'Enter Marks', 'Edit Marks', '/tests/batch_marks', 'sm.examsFilters', 'sm.testsView'):
        assert needle in body, needle

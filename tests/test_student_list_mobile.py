"""Students page on phones: one card per student, sort box, full-screen forms.

The page is the same HTML for every screen size - these tests make sure the
pieces the phone layout depends on (labels, sort box, full-screen modal
classes, phone CSS) are present and that no desktop feature was removed.
"""

import re

from app.services.i18n import translate_html


def _page(client):
    return client.get('/students/').get_data(as_text=True)


def _table_html(body):
    return body.split('id="studentTable"', 1)[1].split('</table>', 1)[0]


def test_every_cell_has_a_label_for_the_phone_card(admin_client, seed):
    table = _table_html(_page(admin_client))
    rows = re.findall(r'<tr class="student-row".*?</tr>', table, re.S)
    assert rows
    for row in rows:
        cells = re.findall(r'<td\b([^>]*)>', row)
        for attrs in cells:
            if 'data-col="actions"' in attrs:
                continue
            assert 'data-label="' in attrs, attrs
    assert 'data-col="student_name" data-label="Student Name"' in table
    assert 'data-col="roll_number" data-label="Roll No"' in table


def test_phone_css_is_on_the_page(admin_client, seed):
    body = _page(admin_client)
    assert '@media (max-width: 767.98px)' in body
    assert 'content: attr(data-label)' in body
    assert '#studentTable tr.student-row' in body
    # forms use 16px text on phones so iPhones do not zoom in on focus
    assert 'font-size: 16px' in body


def test_sort_box_lists_the_columns(admin_client, seed):
    body = _page(admin_client)
    assert 'id="sdSortCol"' in body and 'id="sdSortDir"' in body
    select = body.split('id="sdSortCol"', 1)[1].split('</select>', 1)[0]
    assert 'Roll No' in select and 'Student Name' in select
    # the photo column cannot be sorted
    assert '>Photo<' not in select
    # roll number is the default choice, like the desktop table
    assert re.search(r'<option value="\d+" selected>Roll No</option>', select)


def test_sort_box_is_hidden_when_there_are_no_students(admin_client, seed):
    body = admin_client.get('/students/?search=zzzz-no-such-student').get_data(as_text=True)
    assert 'id="sdSortCol"' not in body
    assert 'No students found' in body


def test_add_and_edit_forms_are_full_screen_on_small_phones(admin_client, seed):
    body = _page(admin_client)
    for modal_id in ('addStudentModal', 'editStudentModal'):
        dialog = body.split('id="%s"' % modal_id, 1)[1].split('>', 2)[1]
        assert 'modal-fullscreen-sm-down' in dialog, modal_id
        assert 'modal-lg' in dialog, modal_id          # desktop size unchanged


def test_desktop_features_are_still_there(admin_client, seed):
    body = _page(admin_client)
    table = _table_html(body)
    assert 'data-student-edit="%d"' % seed['student_id'] in table
    assert 'data-student-archive="%d"' % seed['student_id'] in table
    assert 'data-href=' in table                      # whole row opens the report
    for needle in ('id="filterForm"', 'data-column-picker', 'data-export-view="pdf"',
                   'id="addStudentModal"', 'id="importModal"', 'id="visibleCount"'):
        assert needle in body, needle


def test_urdu_page_translates_the_card_labels():
    html = '<table><tr><td data-label="Roll No">1</td><td data-label="Father Name">x</td></tr></table>'
    out = translate_html(html)
    assert 'data-label="Roll No"' not in out
    assert 'data-label="Father Name"' not in out
    assert 'data-label="' in out

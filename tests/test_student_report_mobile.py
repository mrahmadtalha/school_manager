"""Student report page on phones: tabs slide sideways, stat boxes two per line,
every table row becomes a labelled card. Desktop content must stay the same."""

import re


def _page(client, seed):
    return client.get('/students/%d/report' % seed['student_id']).get_data(as_text=True)


def _tables(body):
    return re.findall(r'<table class="[^"]*">.*?</table>', body, re.S)


def test_five_tables_become_cards_on_phones(admin_client, seed):
    tables = _tables(_page(admin_client, seed))
    assert len(tables) == 5
    assert all('rp-cards' in t.split('>', 1)[0] for t in tables)


def test_every_non_first_cell_has_a_label(admin_client, seed):
    for table in _tables(_page(admin_client, seed)):
        body = table.split('<tbody>', 1)[1]
        for row in re.findall(r'<tr>.*?</tr>', body, re.S):
            cells = re.findall(r'<td\b([^>]*)>', row)
            if len(cells) == 1 and 'colspan' in cells[0]:
                continue                                  # "nothing yet" row
            for attrs in cells[1:]:
                assert 'data-label="' in attrs, attrs


def test_phone_css_and_two_per_line_stats(admin_client, seed):
    body = _page(admin_client, seed)
    assert 'content: attr(data-label)' in body
    assert '.profile-tabs { flex-wrap: nowrap; overflow-x: auto;' in body
    assert body.count('col-6 col-md-3') >= 4
    assert 'report-actions' in body


def test_documents_buttons_wrap_two_per_line(admin_client, seed):
    docs = _page(admin_client, seed).split('id="tab-documents"', 1)[1]
    assert docs.count('col-12 col-sm-6 col-md-4') == 9


def test_all_tabs_and_actions_are_still_there(admin_client, seed):
    body = _page(admin_client, seed)
    for tab in ('tab-overview', 'tab-attendance', 'tab-results', 'tab-fees', 'tab-documents'):
        assert 'data-bs-target="#%s"' % tab in body and 'id="%s"' % tab in body
    for needle in ('Admission Form PDF', 'Transcript', 'History', 'Open Full Fee Ledger',
                   'Result Card (PDF)', 'Student ID Card (PDF)', 'Export PDF'):
        assert needle in body, needle

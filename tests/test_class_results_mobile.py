# -*- coding: utf-8 -*-
"""Class Results page (/reports/class-results) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid, the
summary is two lines of two boxes, the tool bar stacks, and every student becomes
one card (name and position, one box per subject, total / % / grade / result, the
remark box and a wide report-card button) instead of a wide table you had to swipe
sideways. These tests check the pieces that layout needs and that no number, button,
filter or remark box went missing."""

from app.services import i18n
from tests.test_class_results_redesign import _class_with_results, _page


def _css(html):
    # base.html has its own <style>; the page's styles are the block that holds .cr-head
    blocks = [part.split('</style>', 1)[0] for part in html.split('<style>')[1:]]
    return [block for block in blocks if '.cr-head' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1].split('@media (prefers-reduced-motion', 1)[0]


def test_phone_header_buttons_sit_in_a_grid(admin_client, app):
    cls, _ = _class_with_results('Phone Head', roll_base=9000)
    phone = _phone(_css(_page(admin_client, cls)))
    for needle in ('.cr-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.cr-tools > .btn, .cr-tools .dropdown .btn { width: 100%; min-height: 2.6rem;'):
        assert needle in phone, needle


def test_every_student_is_one_card_on_a_phone(admin_client, app):
    cls, _ = _class_with_results('Phone Cards', roll_base=9100)
    phone = _phone(_css(_page(admin_client, cls)))
    for needle in ('.cr-reg .table-responsive { overflow: visible; max-height: none; }',
                   '.cr-reg .table thead { display: none; }',
                   '.cr-reg .table > tbody > tr.cr-row { display: grid;',
                   '.cr-reg .table > tbody > tr.cr-row[hidden] { display: none; }',     # search / filters still hide cards
                   'tr.cr-row.is-fail { box-shadow: inset 4px 0 0 #dc2626; }',
                   'html[dir="rtl"] .cr-reg .table > tbody > tr.cr-row.is-fail { box-shadow: inset -4px 0 0 #dc2626; }',  # Urdu: bar on the other side
                   '.cr-reg .table > tbody > tr.cr-row > td.cr-stick { position: static;',
                   '.cr-reg .table > tbody > tr.cr-row > td.cr-c-wide { grid-column: 1 / -1; }',
                   'content: attr(data-label)',
                   'content: "/ " attr(data-max)',
                   '.cr-reg .cr-cell-test { display: block;',
                   '.cr-reg .cr-card-btn { width: 100%; min-height: 2.6rem;',
                   '.cr-reg .cr-card-text { display: inline; }'):
        assert needle in phone, needle


def test_small_phone_summary_toolbar_and_boxes_fit_the_screen(admin_client, app):
    cls, _ = _class_with_results('Phone Small', roll_base=9200)
    css = _css(_page(admin_client, cls))
    small = _small(css)
    for needle in ('.cr-ico { width: 36px; height: 36px;',
                   '.cr-toolbar .form-select, .cr-toolbar .cr-seg { width: 100%; max-width: none; }',
                   'font-size: 16px',                                                    # no iPhone zoom when a box is tapped
                   '.cr-seg button .n { display: block;',
                   '.cr-clear { width: 100%; min-height: 2.5rem; }',
                   '.cr-savebar .btn { min-height: 2.6rem; }'):
        assert needle in small, needle
    assert '.cr-tiles { grid-template-columns: 1fr; }' not in css                        # the summary is no longer one tall stack


def test_phone_only_pieces_are_hidden_on_a_computer(admin_client, app):
    cls, _ = _class_with_results('Desktop Same', roll_base=9300)
    css = _css(_page(admin_client, cls))
    assert '.cr-cell-test, .cr-card-text { display: none; }' in css
    assert css.index('.cr-cell-test, .cr-card-text { display: none; }') < css.index('@media (max-width: 767.98px)')


def test_every_cell_has_its_phone_label(admin_client, app):
    cls, kids = _class_with_results('Phone Labels', roll_base=9400)
    html = _page(admin_client, cls)
    row = html[html.index('<tr class="cr-row'):].split('</tr>', 1)[0]
    for label in ('data-label="Maths Phone Labels"', 'data-max="50"', 'data-label="Total"', 'data-label="%"',
                  'data-label="Grade"', 'data-label="Result"', 'data-label="Teacher Remarks"'):
        assert label in row, label
    assert 'Unit Test' in row and 'cr-cell-test' in row           # the test name is on the card too
    assert 'Report Card PDF' in row and 'cr-card-text' in row     # the report button has its words on a phone
    assert '/reports/student/%d/pdf' % kids[0].id in html


def test_nothing_was_removed_from_the_page(admin_client, app):
    cls, kids = _class_with_results('Phone Whole', roll_base=9500)
    html = _page(admin_client, cls)
    for needle in ('Class Results', 'All Report Cards PDF', 'More downloads', 'Export Whole Class Result (PDF)',
                   'Class average', 'Pass Rate', 'Top Scorer', 'id="crClass"', 'id="crType"', 'id="crSearch"',
                   'id="crSort"', 'data-mode="all"', 'data-mode="pass"', 'data-mode="fail"', 'id="crClear"',
                   'How grades work', 'Save Remarks', 'id="crSaveBar"', 'id="resultsTable"', 'name="announce_date"',
                   'name="session"', 'sm.resultsFilters', 'Individual Report Card PDF', 'out of 50'):
        assert needle in html, needle
    for kid in kids:
        assert 'remark_%d' % kid.id in html


def test_new_phone_words_are_translated_to_urdu(admin_client, app):
    cls, _ = _class_with_results('Phone Urdu', roll_base=9600)
    html = i18n.translate_html(_page(admin_client, cls))
    assert 'Report Card PDF' not in html
    assert 'data-label="Teacher Remarks"' not in html and 'data-label="Total"' not in html
    assert 'رپورٹ کارڈ (پی ڈی ایف)' in html

# -*- coding: utf-8 -*-
"""Documents page (/documents) on phones.

Same HTML for every screen size. On a phone the three big buttons are compact, the
"Who is it for?" choice and the certificate types are finger-sized, boxes use 16 px
text, and "Recently issued" is one small card per document instead of a table. These
tests check the pieces that layout needs and that no button, field or form went
missing."""

from app.services import i18n


def _page(admin_client, query=''):
    response = admin_client.get('/documents' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .dc-head
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.dc-head' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1].split('@media (prefers-reduced-motion', 1)[0]


def test_phone_buttons_choices_and_download_are_finger_sized(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.dc-tiles { grid-template-columns: 1fr; gap: 0.5rem; }',
                   '.dc-tile-ico { width: 40px; height: 40px;',
                   '.dc-panel { padding: 0.95rem 0.95rem; }',
                   '.dc-go .btn { width: 100%; min-height: 2.8rem; }',
                   '.dc-seg label { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 2.6rem;',
                   '.dc-types { grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr)); }',
                   '.dc-type label { min-height: 2.8rem;'):
        assert needle in phone, needle


def test_small_phone_boxes_do_not_zoom_and_fee_form_is_one_column(admin_client, app):
    small = _small(_css(_page(admin_client)))
    for needle in ('.dc-panel .form-control, .dc-panel .form-select, .dc-more-body .form-control { font-size: 16px; }',
                   '.dc-more-body .row > [class*="col-"] { flex: 0 0 100%; max-width: 100%; }',
                   '.dc-more-body .btn { width: 100%; min-height: 2.6rem; }'):
        assert needle in small, needle


def _issue_one(admin_client, seed):
    admin_client.post('/documents/fees', data={'id_card': '150', 'id_card_dup': '', 'cert': '', 'cert_dup': ''})
    admin_client.post('/documents/issue', data={'kind': 'id_card', 'student_id': seed['student_id'],
                                                'payment_method': 'cash'})


def test_recently_issued_is_one_card_per_document_on_a_phone(admin_client, seed):
    _issue_one(admin_client, seed)
    body = _page(admin_client)
    phone = _phone(_css(body))
    for needle in ('.dc-rec thead { display: none; }',
                   '.dc-rec tbody tr { display: grid; grid-template-columns: 1fr 1fr;',
                   '.dc-rec td::before { content: attr(data-label);',
                   '.dc-rec .dc-c-student { order: 3; grid-column: 1 / -1; }',
                   'html[dir="rtl"] .dc-rec td { text-align: right !important; }'):
        assert needle in phone, needle
    assert 'dc-rec' in body
    row = body[body.index('class="dc-c-date"'):].split('</tr>', 1)[0]
    for label in ('data-label="Date"', 'data-label="Student"', 'data-label="Document"',
                  'data-label="Fee"', 'data-label="Receipt"'):
        assert label in body, label
    assert 'dc-c-fee' in row and 'dc-c-rcpt' in row


def test_new_phone_word_is_translated_to_urdu(admin_client, seed):
    _issue_one(admin_client, seed)
    html = i18n.translate_html(_page(admin_client))
    assert 'data-label="Document"' not in html
    assert 'دستاویز' in html


def test_nothing_was_removed_from_the_page(admin_client, seed):
    body = _page(admin_client)
    for needle in ('What do you want to print?', 'Student ID Cards', 'Staff ID Cards', 'Certificates',
                   'Who is it for?', 'Everyone', 'A whole class', 'One student', 'All staff', 'One teacher',
                   'Certificate type', 'Issue date', 'Academic session', 'Remarks / achievement',
                   'Download student cards', 'Download staff cards', 'Download certificates PDF',
                   'Fees for ID cards', 'Save fees', 'Recently issued', 'id="doc-fees"', 'data-dc-tab="student"',
                   'data-dc-tab="staff"', 'data-dc-tab="cert"', '/documents/fees', '/documents/id-cards/students.pdf',
                   '/documents/id-cards/teachers.pdf', '/documents/certificates.pdf'):
        assert needle in body, needle
    for name in ('class_id', 'student_id', 'teacher_id', 'session', 'cert_type', 'issue_date', 'remarks',
                 'id_card', 'id_card_dup', 'cert', 'cert_dup'):
        assert 'name="%s"' % name in body, name

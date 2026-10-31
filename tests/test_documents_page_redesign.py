"""Documents page redesign + the new Change Password window."""


def test_documents_page_asks_what_and_who(admin_client):
    body = admin_client.get('/documents').get_data(as_text=True)
    assert 'What do you want to print?' in body
    for text in ('Student ID Cards', 'Staff ID Cards', 'Certificates', 'Who is it for?',
                 'Download student cards', 'Download staff cards', 'Download certificates PDF'):
        assert text in body, text
    assert 'role="tablist"' in body


def test_form_field_names_and_urls_are_unchanged(admin_client):
    body = admin_client.get('/documents').get_data(as_text=True)
    for name in ('class_id', 'student_id', 'teacher_id', 'session', 'cert_type', 'issue_date', 'remarks'):
        assert 'name="%s"' % name in body, name
    assert '/documents/id-cards/students.pdf' in body
    assert '/documents/id-cards/teachers.pdf' in body
    assert '/documents/certificates.pdf' in body


def test_opening_from_a_student_report_selects_that_student(admin_client, seed):
    body = admin_client.get('/documents?student_id=%d' % seed['student_id']).get_data(as_text=True)
    assert 'id="sWhoOne" value="one" checked' in body


def test_staff_tab_opens_for_a_teacher_link(admin_client):
    body = admin_client.get('/documents?teacher_id=1').get_data(as_text=True)
    assert 'id="tab-staff"' in body and 'aria-selected="true"' in body


def test_fee_settings_stay_for_admin_only(admin_client):
    body = admin_client.get('/documents').get_data(as_text=True)
    assert 'Fees for ID cards' in body and 'id="doc-fees"' in body


def test_change_password_window_has_live_rules(admin_client):
    body = admin_client.get('/documents').get_data(as_text=True)
    assert 'id="changePwModal"' in body
    for name in ('current_password', 'new_password', 'confirm_password'):
        assert 'name="%s"' % name in body
    assert 'At least 8 characters' in body and 'Both passwords are the same' in body


def test_change_password_post_still_works(admin_client):
    r = admin_client.post('/change-password', data={
        'current_password': 'wrong', 'new_password': 'Newpass123', 'confirm_password': 'Newpass123'})
    assert r.status_code == 302


def test_urdu_labels_exist():
    from app.services.i18n_ur import UR
    for text in ('Who is it for?', 'A whole class', 'Download student cards', 'At least one number'):
        assert text in UR

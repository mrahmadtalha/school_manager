"""School Settings page redesign: same tabs, forms and field names; plainer
wording, titled sections, a Save bar and merged Backups card."""


def _page(client, tab='general'):
    return client.get('/settings?tab=%s' % tab).get_data(as_text=True)


def test_header_hint_and_four_tabs(admin_client):
    body = _page(admin_client)
    assert 'What to do now:' in body
    for tab in ('General School Info', 'Academic Timings', 'Custom Fields Manager', 'System Integrations'):
        assert tab in body, tab


def test_general_tab_sections_and_field_names(admin_client):
    body = _page(admin_client)
    for text in ('School Identity', 'Brand Colors', 'Contact Details', 'Admission Numbers', 'Save School Info'):
        assert text in body, text
    for name in ('school_name', 'tagline', 'logo', 'primary_color', 'secondary_color', 'address', 'phone', 'email',
                 'auto_admission_number', 'admission_number_prefix', 'admission_number_digits', 'admission_number_start'):
        assert 'name="%s"' % name in body, name
    assert 'id="admPreview"' in body and 'id="previewName"' in body


def test_academic_tab_keeps_every_field(admin_client):
    body = _page(admin_client, 'academic')
    for name in ('academic_session', 'result_announcement_date', 'school_start_time', 'school_end_time',
                 'attendance_grace_minutes', 'late_display', 'percent_basis', 'saturday_off', 'sunday_off',
                 'custom_off_days', 'timetable_periods_per_day', 'timetable_period_minutes',
                 'timetable_break_after', 'timetable_break_minutes', 'timetable_break_label',
                 'timetable_assembly_minutes', 'timetable_assembly_label'):
        assert 'name="%s"' % name in body, name
    assert 'name="holiday_start[]"' in body or 'id="holiday-ranges-body"' in body
    assert 'Late arrival grace period' in body and 'Holidays / Vacations' in body
    assert 'Grading Scale' in body and 'Save Academic Settings' in body


def test_custom_fields_tab_posts_to_same_urls(admin_client):
    body = _page(admin_client, 'custom-fields')
    assert '/settings/custom_fields/student' in body
    assert '/settings/custom_fields/teacher' in body
    assert 'id="student-custom-fields-body"' in body and 'id="teacher-custom-fields-body"' in body


def test_backups_card_is_merged_and_working(admin_client):
    body = _page(admin_client, 'integrations')
    assert 'Backups' in body and 'Back up now' in body and 'Open WhatsApp Center' in body
    assert body.count('Database Protection') == 0


def test_saving_still_works_from_the_new_form(admin_client):
    r = admin_client.post('/settings', data={'action': 'save_general_info', 'school_name': 'Redesign School',
                                             'primary_color': '#123456', 'secondary_color': '#654321'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/settings?tab=general')


def test_urdu_labels_exist():
    from app.services.i18n_ur import UR
    for text in ('School Identity', 'Brand Colors', 'Save Academic Settings', 'Back up now'):
        assert text in UR

from app.database import db
from app.models import SchoolSettings


def test_general_and_academic_settings_save_independently(admin_client, app):
    with app.app_context():
        settings = SchoolSettings.query.first()
        if settings is None:
            settings = SchoolSettings(school_name='Original School')
            db.session.add(settings)
            db.session.commit()
        original_start_time = settings.school_start_time
        original_name = settings.school_name

    general_response = admin_client.post('/settings', data={
        'action': 'save_general_info',
        'school_name': 'Northside School',
        'tagline': 'Learning together',
        'address': '1 School Road',
        'phone': '03001234567',
        'email': 'office@example.test',
        'primary_color': '#123456',
        'secondary_color': '#654321',
    })

    assert general_response.status_code == 302
    assert general_response.headers['Location'].endswith('/settings?tab=general')
    with app.app_context():
        settings = SchoolSettings.query.first()
        assert settings.school_name == 'Northside School'
        assert settings.school_start_time == original_start_time

    academic_response = admin_client.post('/settings', data={
        'action': 'save_academic_settings',
        'academic_session': '2026-2027',
        'result_announcement_date': '2026-10-15',
        'school_start_time': '08:00',
        'school_end_time': '14:30',
        'custom_off_days': 'Friday',
        'weekend_off': 'on',
    })

    assert academic_response.status_code == 302
    assert academic_response.headers['Location'].endswith('/settings?tab=academic')
    with app.app_context():
        settings = SchoolSettings.query.first()
        assert settings.school_name == 'Northside School'
        assert settings.school_name != original_name
        assert settings.academic_session == '2026-2027'
        assert settings.school_start_time == '08:00'
        assert settings.school_end_time == '14:30'


def test_settings_page_exposes_all_four_tabs_and_selected_tab(admin_client):
    response = admin_client.get('/settings?tab=integrations')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'General School Info' in body
    assert 'Academic Timings' in body
    assert 'Custom Fields Manager' in body
    assert 'System Integrations' in body
    assert 'tab-pane fade show active' in body
    assert 'Open WhatsApp Center' in body


def test_documents_page_renders_responsive_export_cards(admin_client):
    response = admin_client.get('/documents')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Student ID Cards' in body
    assert 'Staff ID Cards' in body
    assert 'Certificates' in body
    assert 'Download student cards' in body

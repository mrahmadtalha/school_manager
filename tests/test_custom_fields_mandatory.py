import json

from app.database import db
from app.models import StudentModel, TeacherModel
from app.models.settings import get_system_value
from app.services.custom_fields import parse_custom_fields_json


def _save_required_field(admin_client, entity, name, label):
    return admin_client.post(f'/settings/custom_fields/{entity}', data={
        'field_name[]': [name],
        'field_label[]': [label],
        'field_type[]': ['text'],
        'field_required[]': [name],
    })


def test_custom_field_required_setting_persists(admin_client, app):
    response = _save_required_field(admin_client, 'student', 'medical_note', 'Medical Note')
    assert response.status_code == 302

    with app.app_context():
        definitions = json.loads(get_system_value('student_custom_fields'))
    assert definitions[0]['is_mandatory'] is True


def test_student_mandatory_custom_field_and_sponsor_cnic_validation(admin_client, app, seed):
    _save_required_field(admin_client, 'student', 'medical_note', 'Medical Note')
    base_form = {
        'roll_number': '1601',
        'student_name': 'Custom Student',
        'father_name': 'Sponsor Name',
        'sponsor_type': 'Guardian',
        'sponsor_cnic': '12345-1234567-1',
        'guardian_phone': '03001234567',
        'address': 'School Road',
        'class_id': str(seed['class_id']),
        'section_id': '',
        'monthly_fee': '',
    }
    rejected = admin_client.post('/students/add', data=base_form, follow_redirects=True)
    assert 'Complete required custom fields: Medical Note' in rejected.get_data(as_text=True)
    with app.app_context():
        assert not StudentModel.query.filter_by(roll_number=1601).first()

    invalid_cnic_form = dict(base_form, custom_medical_note='None', sponsor_cnic='12345-12')
    invalid = admin_client.post('/students/add', data=invalid_cnic_form, follow_redirects=True)
    assert 'CNIC must use the format' in invalid.get_data(as_text=True)

    valid = admin_client.post('/students/add', data=dict(base_form, custom_medical_note='Allergy note'),
                              follow_redirects=True)
    assert 'Student added successfully' in valid.get_data(as_text=True)
    with app.app_context():
        saved = StudentModel.query.filter_by(roll_number=1601).one()
        assert saved.sponsor_type == 'Guardian'
        assert saved.sponsor_cnic == '12345-1234567-1'
        assert parse_custom_fields_json(saved.custom_fields_data) == {'medical_note': 'Allergy note'}


def test_teacher_mandatory_custom_field_is_validated(admin_client, app):
    _save_required_field(admin_client, 'teacher', 'bank_branch', 'Bank Branch')
    form = {
        'teacher_id_str': 'T-MANDATORY-1',
        'teacher_name': 'Custom Teacher',
        'qualification': 'B.Ed',
        'joining_date': '2026-01-01',
        'salary_type': 'monthly',
        'monthly_salary': '40000',
        'hourly_rate': '',
        'salary': '40000',
        'assigned_classes': '',
        'assigned_subjects': '',
    }

    rejected = admin_client.post('/teachers/add', data=form, follow_redirects=True)
    assert 'Complete required custom fields: Bank Branch' in rejected.get_data(as_text=True)
    with app.app_context():
        assert not TeacherModel.query.filter_by(teacher_id_str='T-MANDATORY-1').first()

    saved_response = admin_client.post('/teachers/add',
                                       data=dict(form, custom_bank_branch='Central'),
                                       follow_redirects=True)
    assert 'Teacher added successfully' in saved_response.get_data(as_text=True)
    with app.app_context():
        teacher = TeacherModel.query.filter_by(teacher_id_str='T-MANDATORY-1').one()
        assert parse_custom_fields_json(teacher.custom_fields_data) == {'bank_branch': 'Central'}

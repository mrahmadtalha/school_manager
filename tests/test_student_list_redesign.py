"""Student list redesign: two row actions, clickable rows, summary band,
and the Admission fee button that moved to the student report."""

import re

from flask import url_for

from app.database import db
from app.models import ClassModel, StudentModel


def _add_student(class_id, roll, name, gender=None):
    student = StudentModel(
        roll_number=roll, student_name=name, father_name='Father',
        guardian_phone='03001234567', address='Street', gender=gender,
        class_id=class_id, monthly_fee=2500.0)
    db.session.add(student)
    db.session.flush()
    return student


def _table_html(body):
    return body.split('id="studentTable"', 1)[1].split('</table>', 1)[0]


def test_row_has_only_edit_and_archive_actions(admin_client, seed):
    table = _table_html(admin_client.get('/students').get_data(as_text=True))
    assert 'data-student-edit="%d"' % seed['student_id'] in table
    assert 'data-student-archive="%d"' % seed['student_id'] in table
    # ID card, certificate, detailed-report and admission-fee buttons are gone.
    for icon in ('fa-id-card', 'fa-certificate', 'fa-chart-line', 'fa-door-open'):
        assert icon not in table, icon


def test_row_opens_the_student_report(admin_client, app, seed):
    body = admin_client.get('/students').get_data(as_text=True)
    with app.test_request_context():
        report_url = url_for('main.student_detailed_report', id=seed['student_id'])
    assert 'data-href="%s"' % report_url in body
    # The name is still a real link (keyboard and middle-click keep working).
    assert 'href="%s"' % report_url in body


def test_summary_band_counts_gender_and_links_to_dues_filter(admin_client, app, seed):
    with app.app_context():
        _add_student(seed['class_id'], 3001, 'Boy One', 'Male')
        _add_student(seed['class_id'], 3002, 'Girl One', 'Female')
        db.session.commit()
    body = admin_client.get('/students').get_data(as_text=True)
    assert 'On this list' in body
    assert re.search(r'Boys <b>1</b>', body)
    assert re.search(r'Girls <b>1</b>', body)
    # The two seeded students have no gender recorded.
    assert re.search(r'Other <b>2</b>', body)
    assert re.search(r'class="sd-stat sd-dues"\s+href="[^"]*has_dues=1', body)


def test_empty_result_shows_message_and_no_summary_band(admin_client):
    body = admin_client.get('/students?search=zzzz-no-such-student').get_data(as_text=True)
    assert 'No students found' in body
    assert 'class="sd-ribbon' not in body


def test_gender_switch_keeps_the_filter_selected(admin_client):
    body = admin_client.get('/students?gender=Female').get_data(as_text=True)
    assert re.search(r'name="gender" id="genderOpt3" value="Female"\s+checked', body)


def test_report_offers_admission_fee_only_when_it_is_in_use(admin_client, app, seed):
    with app.test_request_context():
        link = url_for('main.admission_student', student_id=seed['student_id'])
    report = '/students/%d/report' % seed['student_id']

    assert link not in admin_client.get(report).get_data(as_text=True)

    with app.app_context():
        db.session.get(ClassModel, seed['class_id']).admission_fee = 500000
        db.session.commit()
    assert link in admin_client.get(report).get_data(as_text=True)

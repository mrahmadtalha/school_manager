"""Teacher list redesign: staff cards with a table switch, the summary band
(role mix, today's attendance, class coverage) and the shared edit dialogs."""

import json
import re
from datetime import date

from flask import url_for

from app.database import db
from app.models import ClassModel, TeacherModel
from app.models.attendance import AttendanceModel


def _add_teacher(tid, name, designation=None, classes=None, active=True, **extra):
    fields = dict(
        teacher_id_str=tid, teacher_name=name, qualification='MSc',
        designation=designation, is_active=active,
        monthly_salary=45000.0, salary=45000.0,
        joining_date=date(2021, 4, 1),
        assigned_classes=json.dumps(classes) if classes else None)
    fields.update(extra)
    teacher = TeacherModel(**fields)
    db.session.add(teacher)
    db.session.flush()
    return teacher


def _page(client, query=''):
    return client.get('/teachers' + query).get_data(as_text=True)


def test_page_offers_cards_and_the_full_table(admin_client, app):
    with app.app_context():
        teacher = _add_teacher('T-801', 'Card Teacher', 'Teacher')
        db.session.commit()
        teacher_id = teacher.id
    body = _page(admin_client)
    with app.test_request_context():
        profile = url_for('main.teacher_profile', id=teacher_id)
    # Both views are on the page; one switch chooses between them.
    assert 'class="tm-card' in body
    assert 'id="teacherTable"' in body
    assert 'data-tm-view="cards"' in body and 'data-tm-view="table"' in body
    # The card name is the link to the profile, and a table row opens it too.
    assert re.search(r'class="tm-name"\s+href="%s"' % re.escape(profile), body)
    assert 'data-href="%s"' % profile in body
    # The table keeps the order the server gave (by name), not photo order.
    assert 'data-order="[]"' in re.search(r'<table[^>]*id="teacherTable"[^>]*>', body).group(0)


def test_edit_and_archive_dialogs_exist_once_and_sit_outside_the_table(admin_client, app):
    with app.app_context():
        teacher = _add_teacher('T-802', 'Dialog Teacher', 'Teacher')
        db.session.commit()
        teacher_id = teacher.id
    body = _page(admin_client)
    for prefix in ('editTeacher', 'deleteTeacher'):
        marker = 'id="%s%d"' % (prefix, teacher_id)
        assert body.count(marker) == 1, marker
        assert body.index(marker) > body.index('</table>'), marker
    # Both the card and the table row open the same dialogs.
    assert body.count('data-bs-target="#editTeacher%d"' % teacher_id) == 2
    assert body.count('data-bs-target="#deleteTeacher%d"' % teacher_id) == 2


def test_summary_band_counts_the_role_mix(admin_client, app):
    with app.app_context():
        _add_teacher('T-811', 'Head One', 'Principal')
        _add_teacher('T-812', 'Senior One', 'Senior Teacher')
        _add_teacher('T-813', 'Plain One', 'Teacher')
        _add_teacher('T-814', 'Nobody One')            # no designation
        db.session.commit()
    body = _page(admin_client)
    assert 'class="tm-band' in body and 'On this list' in body
    assert re.search(r'Leadership <b>1</b>', body)
    assert re.search(r'Senior staff <b>1</b>', body)
    assert re.search(r'Teachers <b>1</b>', body)
    assert re.search(r'Other / not set <b>1</b>', body)


def test_card_dot_shows_todays_attendance(admin_client, app):
    with app.app_context():
        here = _add_teacher('T-821', 'Here Teacher', 'Teacher')
        away = _add_teacher('T-822', 'Away Teacher', 'Teacher')
        _add_teacher('T-823', 'Unmarked Teacher', 'Teacher')
        db.session.add_all([
            AttendanceModel(date=date.today(), target_type='teacher',
                            target_id=here.id, status='Present'),
            AttendanceModel(date=date.today(), target_type='teacher',
                            target_id=away.id, status='Absent'),
        ])
        db.session.commit()
    body = _page(admin_client)
    assert 'class="tm-dot tm-st-present"' in body
    assert 'class="tm-dot tm-st-absent"' in body
    assert 'title="Present today"' in body and 'title="Absent today"' in body
    assert 'title="Attendance not marked today"' in body
    assert 'In school today' in body


def test_band_says_so_when_nobody_is_marked_today(admin_client, app):
    with app.app_context():
        _add_teacher('T-831', 'Quiet Teacher', 'Teacher')
        db.session.commit()
    body = _page(admin_client)
    assert 'Staff attendance is not marked yet today' in body
    assert 'In school today' not in body


def test_attendance_of_other_days_is_not_shown_as_today(admin_client, app):
    with app.app_context():
        teacher = _add_teacher('T-832', 'Old Record', 'Teacher')
        db.session.add(AttendanceModel(date=date(2020, 1, 6), target_type='teacher',
                                       target_id=teacher.id, status='Present'))
        db.session.commit()
    body = _page(admin_client)
    assert 'class="tm-dot tm-st-present"' not in body
    assert 'Staff attendance is not marked yet today' in body


def test_class_coverage_names_classes_without_a_teacher(admin_client, app, seed):
    with app.app_context():
        _add_teacher('T-841', 'No Class Yet', 'Teacher')
        db.session.commit()
        class_name = db.session.get(ClassModel, seed['class_id']).name
        total = ClassModel.query.count()
    body = _page(admin_client)
    assert 'class="tm-stat tm-gap"' in body
    assert re.search(r'No teacher yet: <b>[^<]*%s' % re.escape(class_name), body)
    assert '<span class="tm-num">0<small>/%d</small></span>' % total in body


def test_class_coverage_counts_active_teachers_only(admin_client, app, seed):
    with app.app_context():
        class_name = db.session.get(ClassModel, seed['class_id']).name
        _add_teacher('T-851', 'Gone Teacher', 'Teacher', classes=[class_name], active=False)
        db.session.commit()
    body = _page(admin_client, '?status=all')
    assert 'class="tm-stat tm-gap"' in body, 'an archived teacher must not cover a class'

    with app.app_context():
        _add_teacher('T-852', 'Covering Teacher', 'Teacher', classes=[class_name])
        db.session.commit()
        total = ClassModel.query.count()
    body = _page(admin_client)
    assert 'No teacher yet:' not in body
    assert '<span class="tm-num">%d<small>/%d</small></span>' % (total, total) in body


def test_coverage_is_school_wide_even_when_the_list_is_filtered(admin_client, app, seed):
    with app.app_context():
        class_name = db.session.get(ClassModel, seed['class_id']).name
        _add_teacher('T-861', 'Covers It', 'Principal', classes=[class_name])
        _add_teacher('T-862', 'Other Role', 'Admin Staff')
        db.session.commit()
    body = _page(admin_client, '?designation=Admin+Staff')
    assert 'No teacher yet:' not in body


def test_archived_teacher_gets_restore_not_archive(admin_client, app):
    with app.app_context():
        teacher = _add_teacher('T-871', 'Archived One', 'Teacher', active=False)
        db.session.commit()
        teacher_id = teacher.id
    body = _page(admin_client, '?status=archived')
    with app.test_request_context():
        restore = url_for('main.restore_teacher', id=teacher_id)
    assert 'action="%s"' % restore in body
    assert 'tm-act-restore' in body
    # The archive button is only offered for teachers who are still active.
    assert 'data-bs-target="#deleteTeacher%d"' % teacher_id not in body
    # No live attendance dot for someone who is archived.
    assert 'class="tm-dot' not in body


def test_status_switch_keeps_the_filter_selected(admin_client):
    body = _page(admin_client, '?status=archived')
    assert re.search(r'name="status" id="statusOpt2" value="archived"\s+checked', body)
    body = _page(admin_client)
    assert re.search(r'name="status" id="statusOpt1" value="active"\s+checked', body)


def test_card_shows_pay_and_a_call_link(admin_client, app):
    with app.app_context():
        _add_teacher('T-881', 'Monthly Teacher', 'Teacher', contact_number='03211234567')
        _add_teacher('T-882', 'Hourly Teacher', 'Teacher', salary_type='hourly',
                     hourly_rate=650.0, monthly_salary=0.0, salary=0.0)
        db.session.commit()
    body = _page(admin_client)
    assert 'Rs. 45,000' in body
    assert 'Rs. 650<small>/hr</small>' in body
    assert 'href="tel:03211234567"' in body
    assert 'Since 2021' in body


def test_empty_result_shows_message_and_no_summary_band(admin_client):
    body = _page(admin_client, '?search=zzzz-no-such-teacher')
    assert 'No teachers found' in body
    assert 'class="tm-band' not in body
    assert 'class="tm-card' not in body
    assert 'Clear Filters' in body


def test_page_without_any_teacher_invites_adding_one(admin_client):
    body = _page(admin_client)
    assert 'No teachers found' in body
    assert 'class="tm-empty"' in body
    assert 'data-bs-target="#addTeacherModal"' in body


def test_search_text_covers_name_classes_and_phone(admin_client, app):
    with app.app_context():
        _add_teacher('T-891', 'Findable Person', 'Teacher', classes=['Class 7'],
                     contact_number='03451112223')
        db.session.commit()
    body = _page(admin_client)
    blob = re.search(r'class="tm-card[^"]*"\s+data-name="[^"]*"\s+data-search="([^"]*)"', body).group(1)
    for needle in ('findable person', 't-891', 'class 7', '03451112223'):
        assert needle in blob, needle

"""'All Students/Teachers at Time': one-click on-time entry for paper registers."""

from datetime import date

from app.database import db
from app.models import AttendanceModel, SchoolSettings, TeacherModel

PAST_DATE = date(2026, 9, 21)


def _settings(start='08:30', grace=5):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings()
        db.session.add(settings)
        db.session.flush()
    settings.school_start_time = start
    settings.attendance_grace_minutes = grace
    db.session.commit()


def test_student_page_offers_all_at_time_defaulting_to_school_start(admin_client, app, seed):
    with app.app_context():
        _settings('08:15')
    html = admin_client.get('/attendance/students?class_id=%d&date=%s'
                            % (seed['class_id'], PAST_DATE)).get_data(as_text=True)
    assert 'All Students at Time' in html
    assert 'id="allAtTime"' in html and 'value="08:15"' in html
    # the manual check-in boxes and Now buttons are still there
    assert 'name="checkin_time_%d"' % seed['student_id'] in html


def test_teacher_page_offers_all_at_time(admin_client, app):
    with app.app_context():
        _settings('08:15')
        db.session.add(TeacherModel(teacher_id_str='T777', teacher_name='Mr Time',
                                    qualification='BEd'))
        db.session.commit()
    html = admin_client.get('/attendance/teachers?date=%s' % PAST_DATE).get_data(as_text=True)
    assert 'All Teachers at Time' in html
    assert 'id="allTeachersAtTime"' in html and 'value="08:15"' in html


def test_students_on_time_then_edit_only_the_late_one(admin_client, app, seed):
    """What the buttons submit: everyone at school start, one student edited to 08:50."""
    with app.app_context():
        _settings('08:30', 5)
    data = {
        'class_id': str(seed['class_id']), 'date': PAST_DATE.isoformat(),
        'status_%d' % seed['student_id']: 'Present',
        'checkin_time_%d' % seed['student_id']: '08:30',
        'status_%d' % seed['other_student_id']: 'Present',
        'checkin_time_%d' % seed['other_student_id']: '08:50',   # edited: actually late
    }
    admin_client.post('/attendance/students', data=data)
    with app.app_context():
        on_time = AttendanceModel.query.filter_by(
            target_type='student', target_id=seed['student_id'], date=PAST_DATE).one()
        late = AttendanceModel.query.filter_by(
            target_type='student', target_id=seed['other_student_id'], date=PAST_DATE).one()
        assert (on_time.status, on_time.late_time, on_time.late_minutes) == ('Present', '08:30', None)
        assert (late.status, late.late_time, late.late_minutes) == ('Late', '08:50', 20)


def test_teachers_on_time_then_edit_only_the_late_one(admin_client, app):
    with app.app_context():
        _settings('08:30', 0)
        ids = []
        for n in (1, 2):
            t = TeacherModel(teacher_id_str='TT%d' % n, teacher_name='Teacher %d' % n,
                             qualification='BEd')
            db.session.add(t)
            db.session.flush()
            ids.append(t.id)
        db.session.commit()
    data = {'date': PAST_DATE.isoformat()}
    for index, tid in enumerate(ids):
        data['status_%d' % tid] = 'Present'
        data['checkin_time_%d' % tid] = '08:30' if index == 0 else '09:00'
    admin_client.post('/attendance/teachers', data=data)
    with app.app_context():
        first = AttendanceModel.query.filter_by(target_type='teacher', target_id=ids[0],
                                                date=PAST_DATE).one()
        second = AttendanceModel.query.filter_by(target_type='teacher', target_id=ids[1],
                                                 date=PAST_DATE).one()
        assert (first.status, first.late_minutes) == ('Present', None)
        assert (second.status, second.late_minutes) == ('Late', 30)
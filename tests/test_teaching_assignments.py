"""Phase 2: teaching assignments, teacher-conflict detection, teacher-wise
timetables, and school days driven by the School Settings off-day flags."""

from app.database import db
from app.models import (ClassModel, SchoolSettings, SubjectModel, TeacherModel,
                        TeachingAssignment, TimetableSlot)
from app.bootstrap import seed_teaching_assignments
from app.services import timetable as tt
from app.services import timetable_conflicts


def _teacher(name='Ms Hina'):
    teacher = TeacherModel(teacher_id_str='T9%d' % TeacherModel.query.count(),
                           teacher_name=name, qualification='MSc')
    db.session.add(teacher)
    db.session.flush()
    return teacher


def _subject(class_id, name, teacher_id=None, library_id=None):
    subject = SubjectModel(name=name, class_id=class_id, teacher_id=teacher_id,
                           library_id=library_id)
    db.session.add(subject)
    db.session.flush()
    return subject


def _second_class(name='Class 2'):
    klass = ClassModel(name=name)
    db.session.add(klass)
    db.session.flush()
    return klass


# ----------------------------------------------------------------- assignments

def test_seed_creates_assignments_from_subject_teachers(app, seed):
    teacher = _teacher()
    from app.models import SubjectLibrary
    lib = SubjectLibrary(name='Mathematics')
    db.session.add(lib)
    db.session.flush()
    subject = db.session.get(SubjectModel, seed['subject_id'])
    subject.teacher_id = teacher.id
    subject.library_id = lib.id
    db.session.commit()

    seed_teaching_assignments()

    assignment = TeachingAssignment.query.one()
    assert assignment.teacher_id == teacher.id
    assert assignment.library_id == lib.id
    assert assignment.class_id == seed['class_id']
    assert assignment.section_id is None and assignment.is_active

    seed_teaching_assignments()  # flag set: no duplicates
    assert TeachingAssignment.query.count() == 1


def test_edit_subject_syncs_assignment(app, seed, admin_client):
    from app.models import SubjectLibrary
    lib = SubjectLibrary(name='Mathematics')
    db.session.add(lib)
    db.session.flush()
    subject = db.session.get(SubjectModel, seed['subject_id'])
    subject.library_id = lib.id
    db.session.commit()

    admin_client.post('/subjects/edit/%d' % subject.id, data={
        'subject_name': 'Mathematics', 'teacher_id': ''})
    assert TeachingAssignment.query.count() == 0, 'no teacher -> no assignment'

    teacher = _teacher()
    admin_client.post('/subjects/edit/%d' % subject.id, data={
        'subject_name': 'Mathematics', 'teacher_id': str(teacher.id)})
    assignment = TeachingAssignment.query.one()
    assert assignment.teacher_id == teacher.id

    other = _teacher('Mr Bilal')
    admin_client.post('/subjects/edit/%d' % subject.id, data={
        'subject_name': 'Mathematics', 'teacher_id': str(other.id)})
    db.session.expire_all()
    assert TeachingAssignment.query.one().teacher_id == other.id

    admin_client.post('/subjects/edit/%d' % subject.id, data={
        'subject_name': 'Mathematics', 'teacher_id': ''})
    db.session.expire_all()
    assert TeachingAssignment.query.one().is_active is False, 'cleared teacher deactivates'


def test_archive_restore_syncs_assignment(app, seed, admin_client):
    from app.models import SubjectLibrary
    lib = SubjectLibrary(name='Mathematics')
    db.session.add(lib)
    db.session.flush()
    teacher = _teacher()
    subject = db.session.get(SubjectModel, seed['subject_id'])
    subject.teacher_id = teacher.id
    subject.library_id = lib.id
    db.session.commit()
    seed_teaching_assignments()  # the assignment exists before archiving
    assert TeachingAssignment.query.count() == 1

    admin_client.post('/subjects/archive/%d' % subject.id)
    db.session.expire_all()
    assert TeachingAssignment.query.one().is_active is False

    admin_client.post('/subjects/restore/%d' % subject.id)
    db.session.expire_all()
    assert TeachingAssignment.query.one().is_active is True


# -------------------------------------------------------------------- conflicts

def _slot(class_id, day, period, subject_id):
    db.session.add(TimetableSlot(class_id=class_id, day_of_week=day,
                                 period_no=period, subject_id=subject_id))


def test_conflict_detected_across_classes(app, seed):
    teacher = _teacher()
    klass2 = _second_class()
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    math1.teacher_id = teacher.id
    math2 = _subject(klass2.id, 'Mathematics 2', teacher_id=teacher.id)
    _slot(seed['class_id'], 0, 1, math1.id)
    _slot(klass2.id, 0, 1, math2.id)
    db.session.commit()

    conflicts = timetable_conflicts.all_teacher_conflicts()
    assert teacher.id in conflicts
    day_name, period, places = conflicts[teacher.id][0]
    assert period == 1 and len(places) == 2


def test_no_conflict_for_different_periods(app, seed):
    teacher = _teacher()
    klass2 = _second_class()
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    math1.teacher_id = teacher.id
    math2 = _subject(klass2.id, 'Mathematics 2', teacher_id=teacher.id)
    _slot(seed['class_id'], 0, 1, math1.id)
    _slot(klass2.id, 0, 2, math2.id)
    db.session.commit()
    assert timetable_conflicts.all_teacher_conflicts() == {}


def _hub_cells(klass, cells):
    """Hub save payload for a class grid; cells maps (day, period) -> subject id."""
    from app.services import timetable_redesign as redesign
    data = {}
    for row in redesign.master_rows():
        if row.get('kind') == 'break' or row.get('no') is None:
            continue
        for day in range(6):
            data['slot_%d_%d_subject' % (day, row['no'])] = str(
                cells.get((day, row['no']), '')) if cells.get((day, row['no'])) else ''
            data['slot_%d_%d_teacher' % (day, row['no'])] = ''
    return data


def test_save_allows_teacher_shared_across_classes(admin_client, app, seed):
    """One teacher teaching two classes in the SAME period is allowed - the
    save is never blocked (small schools share teachers)."""
    teacher = _teacher()
    klass2 = _second_class()
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    math1.teacher_id = teacher.id
    math2 = _subject(klass2.id, 'Mathematics 2', teacher_id=teacher.id)
    _slot(klass2.id, 0, 1, math2.id)  # the other class already uses the teacher
    db.session.commit()

    # Class 1 saves the same (day, period) with the same teacher - accepted.
    response = admin_client.post(
        '/timetables/save/%d' % seed['class_id'],
        data=_hub_cells(None, {(0, 1): math1.id}), follow_redirects=True)
    assert response.status_code == 200
    assert b'Not saved' not in response.data and b'double-book' not in response.data
    assert TimetableSlot.query.filter_by(class_id=seed['class_id']).count() == 1

    # Moving it to a free period works just the same.
    admin_client.post('/timetables/save/%d' % seed['class_id'],
                      data=_hub_cells(None, {(0, 2): math1.id}))
    assert TimetableSlot.query.filter_by(class_id=seed['class_id']).count() == 1


def test_generate_places_shared_teacher_lessons(admin_client, app, seed):
    """One-click generation fills the grid even when a teacher is busy in
    another class - sharing a period is normal, nothing is skipped."""
    teacher = _teacher()
    klass2 = _second_class()
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    math1.teacher_id = teacher.id
    _subject(klass2.id, 'Mathematics 2', teacher_id=teacher.id)
    _slot(klass2.id, 0, 1, math1.id)
    db.session.commit()

    admin_client.post('/timetables/generate',
                      data={'class_ids': [str(seed['class_id'])]},
                      follow_redirects=True)
    assert TimetableSlot.query.filter_by(class_id=seed['class_id']).count() > 0


# ------------------------------------------------------------------ school days

def test_school_days_follow_settings(app, seed):
    settings = SchoolSettings.query.first()
    if settings is None:
        settings = SchoolSettings(school_name='Test School')
        db.session.add(settings)
        db.session.commit()
    settings.saturday_off = True
    settings.custom_off_days = ''
    db.session.commit()
    days = tt.school_days(settings)
    assert [name for _idx, name in days] == ['Monday', 'Tuesday', 'Wednesday',
                                             'Thursday', 'Friday']

    settings.saturday_off = False
    settings.custom_off_days = 'friday'
    db.session.commit()
    days = tt.school_days(settings)
    names = [name for _idx, name in days]
    assert 'Saturday' in names and 'Friday' not in names


def test_hub_edit_grid_follows_school_days(admin_client, app, seed):
    """Default settings have Saturday off, so saved slots never land on it."""
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    db.session.commit()
    admin_client.post('/timetables/save/%d' % seed['class_id'],
                      data=_hub_cells(None, {(5, 1): math1.id}), follow_redirects=True)
    slots = TimetableSlot.query.filter_by(class_id=seed['class_id']).all()
    assert all(slot.day_of_week != 5 for slot in slots), \
        'Saturday (default off) must stay empty'


def test_generate_fills_only_school_days(admin_client, app, seed):
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    db.session.commit()
    admin_client.post('/timetables/generate',
                      data={'class_ids': [str(seed['class_id'])]},
                      follow_redirects=True)
    filled_days = {slot.day_of_week for slot in
                   TimetableSlot.query.filter_by(class_id=seed['class_id']).all()}
    assert filled_days == {0, 1, 2, 3, 4}, 'Saturday (default off) must stay empty'


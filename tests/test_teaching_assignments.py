"""Teaching assignments: seeded from subject teachers and kept in step with
subject changes."""

from app.database import db
from app.models import ClassModel, SubjectModel, TeacherModel, TeachingAssignment
from app.bootstrap import seed_teaching_assignments


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

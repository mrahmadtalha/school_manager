"""Subject Library (Phase 1): global subject catalog, class linking and routes.

The library is additive by design: class subjects keep working exactly as
before, with an optional ``library_id`` pointing at the shared catalog.  These
tests cover the one-time auto-link migration, class creation from library
selections, and the library management routes.
"""

from app.bootstrap import link_subjects_to_library
from app.database import db
from app.models import ClassModel, SubjectLibrary, SubjectModel, SystemSettingModel


def _class_subjects(class_obj):
    return (SubjectModel.query.filter_by(class_id=class_obj.id)
            .order_by(SubjectModel.name).all())


def test_auto_link_creates_library_and_marks_legacy_defaults(app, seed):
    """One-time pass: unlinked class subjects join the library by name."""
    subject = SubjectModel.query.filter_by(name='Mathematics').first()
    assert subject.library_id is None  # seeded before any library existed

    db.session.add(SubjectModel(name='math', class_id=subject.class_id))
    db.session.add(SubjectLibrary(name='Unrelated'))
    db.session.commit()

    link_subjects_to_library()

    math_lib = SubjectLibrary.query.filter(
        SubjectLibrary.name == 'Mathematics').one()
    assert subject.library_id == math_lib.id

    lower = SubjectModel.query.filter_by(name='math').one()
    # 'math' is a different name, so it gets its own library entry rather
    # than being silently merged into 'Mathematics'.
    assert lower.library.name == 'math'
    assert SubjectLibrary.query.count() == 3  # Mathematics, math, Unrelated

    defaults = {lib.name.lower() for lib in SubjectLibrary.query.filter_by(is_default=True)}
    # Only legacy defaults that actually exist in this DB get the star.
    assert defaults == {'mathematics'}, defaults


def test_auto_link_is_idempotent(app, seed):
    link_subjects_to_library()
    before = {lib.name for lib in SubjectLibrary.query.all()}
    link_subjects_to_library()
    assert {lib.name for lib in SubjectLibrary.query.all()} == before


def test_add_class_uses_selected_library_subjects(admin_client, app, seed):
    english = SubjectLibrary(name='English', is_default=True)
    art = SubjectLibrary(name='Art')
    db.session.add_all([english, art])
    db.session.commit()

    response = admin_client.post('/classes/add', data={
        'class_name': 'Class 9',
        'monthly_fee': '3000',
        'library_subject': [str(english.id)],
    }, follow_redirects=True)
    assert response.status_code == 200

    klass = ClassModel.query.filter_by(name='Class 9').one()
    assert klass.monthly_fee == 3000
    names = {s.name for s in _class_subjects(klass)}
    assert names == {'English'}, 'only the ticked subject is created'
    assert all(s.library_id for s in _class_subjects(klass))


def test_add_class_without_subjects_still_works(admin_client, app, seed):
    response = admin_client.post('/classes/add', data={
        'class_name': 'Empty Class',
    }, follow_redirects=True)
    assert response.status_code == 200
    klass = ClassModel.query.filter_by(name='Empty Class').one()
    assert _class_subjects(klass) == []
    assert [s.name for s in klass.sections] == ['A', 'B']


def test_add_class_rejects_duplicate_name(admin_client, app, seed):
    """The seeded class is 'Class 1'; creating it again must not duplicate it."""
    response = admin_client.post('/classes/add', data={
        'class_name': 'Class 1',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert ClassModel.query.filter_by(name='Class 1').count() == 1


def test_add_subject_links_existing_library_case_insensitive(admin_client, app, seed):
    lib = SubjectLibrary(name='Physics')
    db.session.add(lib)
    db.session.commit()

    admin_client.post('/subjects/add', data={
        'class_id': seed['class_id'],
        'subject_name': 'physics',
    }, follow_redirects=True)

    created = SubjectModel.query.filter_by(class_id=seed['class_id'],
                                           name='physics').one()
    assert created.library_id == lib.id, 'linked to the existing library entry'
    assert SubjectLibrary.query.count() == 1, 'no duplicate library entry'


def test_add_subject_creates_library_entry_when_new(admin_client, app, seed):
    admin_client.post('/subjects/add', data={
        'class_id': seed['class_id'],
        'subject_name': 'Computer Science',
    }, follow_redirects=True)

    created = SubjectModel.query.filter_by(name='Computer Science').one()
    assert created.library_id is not None
    assert created.library.name == 'Computer Science'


def test_edit_subject_relinks_when_library_match_exists(admin_client, app, seed):
    subject = SubjectModel.query.get(seed['subject_id'])  # 'Mathematics', unlinked
    other = SubjectLibrary(name='Math')
    db.session.add(other)
    db.session.commit()

    admin_client.post(f"/subjects/edit/{subject.id}", data={
        'subject_name': 'math',
    }, follow_redirects=True)

    db.session.expire(subject)
    assert subject.name == 'math'
    assert subject.library_id == other.id


def test_library_rename_cascades_to_class_rows(admin_client, app, seed):
    lib = SubjectLibrary(name='Drawing')
    db.session.add(lib)
    db.session.commit()
    subject = SubjectModel.query.get(seed['subject_id'])
    subject.library_id = lib.id
    db.session.commit()

    response = admin_client.post(f'/subjects/library/rename/{lib.id}', data={
        'subject_name': 'Fine Arts',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'class row(s) updated' in response.data

    db.session.expire(subject)
    assert subject.name == 'Fine Arts'
    assert lib.name == 'Fine Arts'


def test_library_rename_rejects_duplicates(admin_client, app, seed):
    db.session.add_all([SubjectLibrary(name='Biology'), SubjectLibrary(name='Botany')])
    db.session.commit()
    biology = SubjectLibrary.query.filter_by(name='Biology').one()

    admin_client.post(f'/subjects/library/rename/{biology.id}', data={
        'subject_name': 'botany',
    }, follow_redirects=True)

    db.session.expire(biology)
    assert biology.name == 'Biology', 'case-insensitive duplicate must be rejected'


def test_library_archive_and_restore(admin_client, app, seed):
    lib = SubjectLibrary(name='Sindhi')
    db.session.add(lib)
    db.session.commit()

    admin_client.post(f'/subjects/library/archive/{lib.id}', follow_redirects=True)
    db.session.expire(lib)
    assert lib.is_active is False

    admin_client.post(f'/subjects/library/restore/{lib.id}', follow_redirects=True)
    db.session.expire(lib)
    assert lib.is_active is True


def test_library_toggle_default(admin_client, app, seed):
    lib = SubjectLibrary(name='Pak Studies', is_default=False)
    db.session.add(lib)
    db.session.commit()

    admin_client.post(f'/subjects/library/default/{lib.id}', follow_redirects=True)
    db.session.expire(lib)
    assert lib.is_default is True

    admin_client.post(f'/subjects/library/default/{lib.id}', follow_redirects=True)
    db.session.expire(lib)
    assert lib.is_default is False


def test_library_page_lists_usage_counts(admin_client, app, seed):
    subject = SubjectModel.query.get(seed['subject_id'])
    lib = SubjectLibrary(name='Mathematics')
    db.session.add(lib)
    db.session.flush()
    subject.library_id = lib.id
    db.session.commit()

    response = admin_client.get('/subjects/library')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Mathematics' in body
    assert 'Subject Library' in body


def test_teacher_blocked_from_library(app, seed, teacher_client):
    """Library management is admin-only (deny-by-default role guard)."""
    assert teacher_client.get('/subjects/library').status_code == 403
    assert teacher_client.post('/subjects/library/add', data={
        'subject_name': 'Hack',
    }).status_code == 403


def test_library_add_rejects_duplicates(admin_client, app, seed):
    db.session.add(SubjectLibrary(name='Civics'))
    db.session.commit()

    admin_client.post('/subjects/library/add', data={'subject_name': 'civics'},
                      follow_redirects=True)
    assert SubjectLibrary.query.filter(SubjectLibrary.name.ilike('civics')).count() == 1

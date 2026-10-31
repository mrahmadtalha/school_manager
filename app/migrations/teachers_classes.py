"""Schema migrations for teachers, classes, timetable, subject library and teaching assignments."""

import os

from app.database import db
from app.migrations.common import _sqlite_connection, _sqlite_db_path, _table_columns


# Class subjects historically auto-created for every new class; marked as the
# default selection in the Subject Library on the one-time linking pass.
LEGACY_DEFAULT_SUBJECT_KEYS = ('english', 'urdu', 'mathematics', 'islamiyat')


def migrate_teacher_schema(app):
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        teacher_columns = _table_columns(connection, 'teachers')
        if not teacher_columns:
            return
        if 'salary_type' not in teacher_columns:
            connection.execute("ALTER TABLE teachers ADD COLUMN salary_type VARCHAR(20) DEFAULT 'monthly'")
            print('Migration: added salary_type to teachers')
        if 'monthly_salary' not in teacher_columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN monthly_salary FLOAT DEFAULT 0')
            print('Migration: added monthly_salary to teachers')
        if 'hourly_rate' not in teacher_columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN hourly_rate FLOAT DEFAULT 0')
            print('Migration: added hourly_rate to teachers')

        for column, ddl in (
            ('cnic', 'VARCHAR(30)'),
            ('address', 'TEXT'),
            ('contact_number', 'VARCHAR(30)'),
            ('emergency_contact_number', 'VARCHAR(30)'),
            ('previous_experience_years', 'FLOAT'),
            ('previous_salary', 'FLOAT'),
            ('assigned_classes', 'TEXT'),
            ('assigned_subjects', 'TEXT'),
        ):
            if column not in teacher_columns:
                connection.execute(f'ALTER TABLE teachers ADD COLUMN {column} {ddl}')
                print(f'Migration: added {column} to teachers')

        connection.commit()


def migrate_teacher_profile_schema(app):
    """Teacher profile extras: designation/gender columns + salary normalization."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'teachers')
        if not columns:
            return
        if 'designation' not in columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN designation VARCHAR(80)')
            print('Migration: added designation to teachers')
        if 'gender' not in columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN gender VARCHAR(20)')
            print('Migration: added gender to teachers')
        if 'photo_filename' not in columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN photo_filename VARCHAR(120)')
            print('Migration: added photo_filename to teachers')

        # Salary normalization: monthly_salary is the single source of truth;
        # backfill it once from the legacy salary column where it is still empty.
        cursor = connection.execute(
            'UPDATE teachers SET monthly_salary = salary '
            'WHERE (monthly_salary IS NULL OR monthly_salary = 0) '
            "AND salary > 0 AND COALESCE(salary_type, 'monthly') != 'hourly'")
        if cursor.rowcount:
            print('Migration: backfilled monthly_salary from salary for %d teacher(s)'
                  % cursor.rowcount)

        if not connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                ('idx_teachers_is_active',)).fetchone():
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_teachers_is_active ON teachers(is_active)')
            print('Migration: created index idx_teachers_is_active')

        connection.commit()


def migrate_class_integrity_schema(app):
    """Class integrity: subject archiving column, indexes and unique name guards."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        subject_columns = _table_columns(connection, 'subjects')
        if subject_columns:
            if 'is_active' not in subject_columns:
                connection.execute('ALTER TABLE subjects ADD COLUMN is_active BOOLEAN DEFAULT 1')
                print('Migration: added is_active to subjects')
            connection.execute('UPDATE subjects SET is_active = 1 WHERE is_active IS NULL')

        def _has_index(name):
            return connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
            ).fetchone()

        for index_name, statement in (
            ('idx_sections_class', 'CREATE INDEX IF NOT EXISTS idx_sections_class ON sections(class_id)'),
            ('idx_subjects_class', 'CREATE INDEX IF NOT EXISTS idx_subjects_class ON subjects(class_id)'),
            ('uq_sections_class_name',
             'CREATE UNIQUE INDEX IF NOT EXISTS uq_sections_class_name ON sections(class_id, name)'),
            ('uq_subjects_class_name',
             'CREATE UNIQUE INDEX IF NOT EXISTS uq_subjects_class_name ON subjects(class_id, name)'),
        ):
            if _has_index(index_name):
                continue
            try:
                connection.execute(statement)
                print('Migration: created index %s' % index_name)
            except Exception as exc:  # duplicate data present — skip, app layer still guards
                print('Migration: skipped %s (%s)' % (index_name, exc))

        connection.commit()


def migrate_timetable_schema(app):
    """Optional subject-teacher mapping: adds the subjects.teacher_id column."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        subject_columns = _table_columns(connection, 'subjects')
        if subject_columns and 'teacher_id' not in subject_columns:
            connection.execute('ALTER TABLE subjects ADD COLUMN teacher_id INTEGER')
            print('Migration: added teacher_id to subjects')
        connection.commit()


def migrate_subject_library_schema(app):
    """Global Subject Library (Phase 1): subjects.library_id column.

    The subject_library table itself is created by db.create_all().  When an
    existing database first gains the column, a safety backup is taken first
    and a one-time auto-link pass then connects every class subject to its
    library entry (see link_subjects_to_library).  Nothing is renamed,
    merged or deleted.
    """
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        subject_columns = _table_columns(connection, 'subjects')
        if subject_columns and 'library_id' not in subject_columns:
            from app.services.db_backup import backup_database
            backup = backup_database(db_path=db_path)
            print(f'Migration: safety backup before subject-library link: {backup}')
            connection.execute('ALTER TABLE subjects ADD COLUMN library_id INTEGER')
            print('Migration: added library_id to subjects')
        connection.commit()


def link_subjects_to_library():
    """One-time auto-link of existing class subjects to the Subject Library.

    Guarded by the ``subject_library_linked`` system setting.  Every class
    subject is linked to the library entry with the same name
    (case-insensitive); the entry is created when missing, keeping the most
    common spelling already in use.  Afterwards the historic defaults
    (English, Urdu, Mathematics, Islamiyat) are marked as the default
    selection for new classes — only when nothing is marked yet, so school
    choices made later are never overwritten.
    """
    from app.models import SubjectLibrary, SubjectModel, SystemSettingModel

    flag = SystemSettingModel.query.filter_by(key='subject_library_linked').first()
    if flag and flag.value == '1':
        return
    if flag is None:
        flag = SystemSettingModel(key='subject_library_linked', value='1')
        db.session.add(flag)

    library_by_lower = {lib.name.strip().lower(): lib for lib in SubjectLibrary.query.all()}
    unlinked = SubjectModel.query.filter(SubjectModel.library_id.is_(None)).all()

    # Pick the most common spelling per subject name so the library entry
    # looks like what the school already types.
    casing_counts = {}
    for subject in unlinked:
        key = subject.name.strip().lower()
        casing_counts.setdefault(key, {})
        casing_counts[key][subject.name.strip()] = casing_counts[key].get(subject.name.strip(), 0) + 1

    for subject in unlinked:
        key = subject.name.strip().lower()
        library = library_by_lower.get(key)
        if library is None:
            name = max(casing_counts[key].items(), key=lambda item: item[1])[0]
            library = SubjectLibrary(name=name, is_active=True, is_default=False)
            db.session.add(library)
            db.session.flush()
            library_by_lower[key] = library
        subject.library_id = library.id

    if not SubjectLibrary.query.filter_by(is_default=True).first():
        for library in library_by_lower.values():
            if library.name.strip().lower() in LEGACY_DEFAULT_SUBJECT_KEYS:
                library.is_default = True

    db.session.commit()
    if unlinked:
        print(f'Subject Library: linked {len(unlinked)} existing class subject(s)')


def seed_teaching_assignments():
    """One-time seed of teaching assignments from legacy subjects.teacher_id links.

    Guarded by the ``teaching_assignments_seeded`` system setting.  Every class
    subject that has both a teacher and a library link gets one class-level
    (section NULL) TeachingAssignment.  From then on the assignments are kept
    in step by the subject edit/archive/restore flows.
    """
    from app.models import SubjectModel, TeachingAssignment, SystemSettingModel

    flag = SystemSettingModel.query.filter_by(key='teaching_assignments_seeded').first()
    if flag and flag.value == '1':
        return
    if flag is None:
        flag = SystemSettingModel(key='teaching_assignments_seeded', value='1')
        db.session.add(flag)

    created = 0
    subjects = (SubjectModel.query
                .filter(SubjectModel.teacher_id.isnot(None),
                        SubjectModel.library_id.isnot(None)).all())
    for subject in subjects:
        exists = TeachingAssignment.query.filter_by(
            teacher_id=subject.teacher_id, library_id=subject.library_id,
            class_id=subject.class_id, section_id=None).first()
        if exists is None:
            db.session.add(TeachingAssignment(
                teacher_id=subject.teacher_id, library_id=subject.library_id,
                class_id=subject.class_id, section_id=None, is_active=True))
            created += 1

    db.session.commit()
    if created:
        print(f'Teaching assignments: created {created} from existing subject teachers')

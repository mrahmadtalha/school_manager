"""Throwaway dev server for visually reviewing the redesigned Timetables hub.

Seeds a fresh temp SQLite database with classes, subjects, teachers and
teaching assignments (bilingual-style subject names like the reference),
then serves the app on http://127.0.0.1:5099.

Login: admin / adminpass123
"""

import os
import pathlib
import sys
import tempfile
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_TMP = pathlib.Path(tempfile.mkdtemp(prefix='tt-preview-'))
os.environ['SECRET_KEY'] = 'preview-secret-' + uuid.uuid4().hex
os.environ['INITIAL_ADMIN_USERNAME'] = 'admin'
os.environ['INITIAL_ADMIN_PASSWORD'] = 'adminpass123'
os.environ['DATABASE_URL'] = 'sqlite:///' + (_TMP / 'preview.db').as_posix()
os.environ['APP_ENV'] = 'development'
os.environ['LICENSE_ENFORCEMENT'] = '0'

from app import create_app            # noqa: E402
from app.database import db           # noqa: E402
from app.models import (ClassModel, SubjectLibrary,  # noqa: E402
                        SubjectModel, TeacherModel, TeachingAssignment)

app = create_app({'TESTING': False, 'WTF_CSRF_ENABLED': False})


def seed():
    # The initial admin (admin/adminpass123) is auto-created by create_app.
    teachers = []
    for name in ('Ms. Hina', 'Sir Kamran', 'Mrs. Anum', 'Sir Zeeshan'):
        teacher = TeacherModel(teacher_id_str='T%02d' % (len(teachers) + 1),
                               teacher_name=name, qualification='MSc')
        db.session.add(teacher)
        teachers.append(teacher)
    db.session.flush()

    library = {}
    for subject_name in ('English', 'Urdu', 'Mathematics', 'Islamiat', 'Science',
                         'Drawing'):
        lib = SubjectLibrary(name=subject_name, is_default=True)
        db.session.add(lib)
        library[subject_name] = lib
    db.session.flush()

    # Three classes; a different teacher owns each subject so the chart
    # looks like the reference (every teacher busy most periods).
    plan = [
        ('Nursery', [('English', 0), ('Urdu', 1), ('Mathematics', 2), ('Drawing', 3)]),
        ('Class 1', [('English', 1), ('Urdu', 0), ('Mathematics', 3), ('Islamiat', 2)]),
        ('Class 2', [('English', 2), ('Urdu', 3), ('Mathematics', 1), ('Science', 0)]),
    ]
    for class_name, subject_plan in plan:
        klass = ClassModel(name=class_name)
        db.session.add(klass)
        db.session.flush()
        for subject_name, teacher_index in subject_plan:
            subject = SubjectModel(name=subject_name, class_id=klass.id,
                                   library_id=library[subject_name].id,
                                   teacher_id=teachers[teacher_index].id)
            db.session.add(subject)
            db.session.flush()
            db.session.add(TeachingAssignment(
                teacher_id=teachers[teacher_index].id,
                library_id=library[subject_name].id,
                class_id=klass.id, section_id=None,
                periods_per_week=8, is_active=True))
    db.session.commit()


with app.app_context():
    seed()

if __name__ == '__main__':
    print('Timetable preview server → http://127.0.0.1:5099/timetables '
          '(admin / adminpass123)')
    app.run(host='127.0.0.1', port=5099, debug=False)

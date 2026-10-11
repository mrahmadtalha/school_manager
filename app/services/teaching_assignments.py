"""Teaching-assignment bookkeeping.

The :class:`~app.models.class_.TeachingAssignment` table is the scheduling-grade
link between a teacher, a library subject and a class.  Class-level (section
NULL) assignments mirror the teacher set on the class subject row in the
Classes page, so the two never disagree.  Per-section assignments arrive with
section-level timetables (Phase 3) and will live in the same table.
"""

from app.database import db
from app.models import SubjectModel, TeachingAssignment


def _class_level_assignment(library_id, class_id):
    return (TeachingAssignment.query
            .filter_by(library_id=library_id, class_id=class_id, section_id=None)
            .first())


def sync_for_class_subject(subject):
    """Align the class-level assignment with one class subject row.

    Call after creating, editing (teacher change), archiving or restoring a
    ``SubjectModel`` row.  When several active rows of the class share the
    library subject, the row that keeps its teacher wins; when none does, the
    assignment is deactivated rather than deleted (history stays reviewable).
    """
    if subject.library_id is None:
        return None

    assignment = _class_level_assignment(subject.library_id, subject.class_id)
    active_rows = (SubjectModel.query
                   .filter(SubjectModel.class_id == subject.class_id,
                           SubjectModel.library_id == subject.library_id,
                           SubjectModel.is_active.is_(True))
                   .order_by(SubjectModel.id).all())
    active_rows = [row for row in active_rows if row.teacher_id]

    if subject.is_active and subject.teacher_id:
        if assignment is None:
            assignment = TeachingAssignment(
                teacher_id=subject.teacher_id, library_id=subject.library_id,
                class_id=subject.class_id, section_id=None, is_active=True)
            db.session.add(assignment)
        else:
            assignment.teacher_id = subject.teacher_id
            assignment.is_active = True
        return assignment

    if assignment is None:
        return None
    if active_rows:
        assignment.teacher_id = active_rows[0].teacher_id
        assignment.is_active = True
    else:
        assignment.is_active = False
    return assignment


def active_assignments(teacher_id=None, class_id=None):
    """Active assignments, optionally narrowed, with their ORM relations loaded."""
    query = (TeachingAssignment.query
             .filter_by(is_active=True)
             .filter(TeachingAssignment.section_id.is_(None)))
    if teacher_id is not None:
        query = query.filter_by(teacher_id=teacher_id)
    if class_id is not None:
        query = query.filter_by(class_id=class_id)
    return query.all()

"""Student class-enrollment history helpers.

Every student keeps one OPEN enrollment row (``end_date`` is NULL) describing
the class they are currently in.  Promotion, class changes, archiving and
restoring close the open row (snapshot untouched) and open a new one from the
student's current fields.
"""
from datetime import date

from app.database import db
from app.models import SchoolSettings, StudentEnrollment


def session_label_default():
    """The current academic-session label (configured setting, else month rule)."""
    from app.services.id_documents import academic_session
    school = SchoolSettings.query.first()
    value = (school.academic_session or '').strip() if school else ''
    return value or academic_session()


def open_enrollment(student):
    return (StudentEnrollment.query
            .filter_by(student_id=student.id, end_date=None)
            .order_by(StudentEnrollment.id.desc())
            .first())


def close_open_enrollment(student, end_date=None):
    """Close the student's open enrollment (if any); the snapshot stays intact."""
    row = open_enrollment(student)
    if row:
        row.end_date = end_date or date.today()
    return row


def start_enrollment(student, reason, start_date=None, session_label=None, end_previous=True):
    """Open a fresh enrollment snapshot from the student's current fields.

    ``start_date=None`` leaves the start unknown (NULL) — used by the backfill.
    """
    # Flush first so a brand-new student has a primary key before we read it.
    db.session.flush()
    if end_previous:
        close_open_enrollment(student, end_date=start_date or date.today())
    row = StudentEnrollment(
        student_id=student.id,
        class_id=student.class_id,
        class_name=student.class_info.name if student.class_info else '',
        section_name=student.section_info.name if student.section_info else None,
        roll_number=student.roll_number,
        session_label=(session_label or session_label_default()),
        start_date=start_date,
        reason=reason,
    )
    db.session.add(row)
    return row


def sync_open_enrollment(student):
    """Refresh the open row after non-structural edits (roll, section, name)."""
    row = open_enrollment(student)
    if not row:
        return start_enrollment(student, reason='backfill', start_date=None)
    row.class_id = student.class_id
    row.class_name = student.class_info.name if student.class_info else ''
    row.section_name = student.section_info.name if student.section_info else None
    row.roll_number = student.roll_number
    return row

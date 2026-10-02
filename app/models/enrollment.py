from datetime import datetime
from app.database import db


class StudentEnrollment(db.Model):
    """A student's class enrollment for a period (typically one academic session).

    Exactly one row per student has ``end_date`` NULL — the current, open
    enrollment.  Promotion, class changes, archiving and restoring close the
    open row and open a new snapshot, keeping a reliable class-by-class
    history for transcripts and the promotion wizard.
    """
    __tablename__ = 'student_enrollments'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=True)
    class_name = db.Column(db.String(50), nullable=False, default='')   # snapshot (survives renames)
    section_name = db.Column(db.String(20), nullable=True)
    roll_number = db.Column(db.Integer, nullable=True)
    session_label = db.Column(db.String(50), nullable=False, default='')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)          # NULL = current/active enrollment
    reason = db.Column(db.String(50), nullable=True)      # enrolled | promoted | class_change | restored | backfill
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    student_info = db.relationship('StudentModel', backref='enrollments', lazy=True)

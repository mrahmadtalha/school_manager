"""Formal term examinations: groups subject test rows under one scheduled exam."""
from datetime import datetime

from app.database import db

TERM_EXAM_STATUSES = ('Scheduled', 'Ongoing', 'Published')


class TermExam(db.Model):
    """A formal term exam (Mid-Term / Final / Pre-Board) for one class."""

    __tablename__ = 'term_exams'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False, default='Mid-Term')
    session_label = db.Column(db.String(50), nullable=False, default='')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    announce_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Scheduled')
    created_by = db.Column(db.String(80), nullable=True, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    class_info = db.relationship('ClassModel', backref='term_exams')

    def __repr__(self):
        return (f'<TermExam {self.name} class={self.class_id} '
                f'status={self.status}>')

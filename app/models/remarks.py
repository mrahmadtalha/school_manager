from datetime import datetime
from app.database import db


class StudentRemark(db.Model):
    """Teacher remarks shown on class results, scoped by class/exam/session."""
    __tablename__ = 'student_remarks'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, nullable=True)
    test_type = db.Column(db.String(50), nullable=False, default='')
    session = db.Column(db.String(50), nullable=False, default='')
    remarks = db.Column(db.Text, nullable=False, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

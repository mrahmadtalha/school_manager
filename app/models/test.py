from datetime import datetime
from app.database import db


class TestModel(db.Model):
    __tablename__ = 'tests'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    test_title = db.Column(db.String(100), nullable=False)  # e.g., "Math Monthly Test"
    test_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    test_type = db.Column(db.String(50), nullable=False)    # "Monthly", "Mid-Term", "Final", "Quiz"
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    total_marks = db.Column(db.Float, nullable=False)

    # Relationships
    marks = db.relationship('StudentMarkModel', backref='test_info', cascade='all, delete-orphan')
    subject_info = db.relationship('SubjectModel', backref='tests', lazy=True)


class StudentMarkModel(db.Model):
    __tablename__ = 'student_marks'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    marks_obtained = db.Column(db.Float, nullable=False)
    percentage = db.Column(db.Float, nullable=True)
    grade = db.Column(db.String(5), nullable=True)  # A+, A, B, C, F

    student_info = db.relationship('StudentModel', backref='marks', lazy=True)


class TestTypeModel(db.Model):
    __tablename__ = 'test_types'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

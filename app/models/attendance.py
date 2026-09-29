from app.database import db


class AttendanceModel(db.Model):
    __tablename__ = 'attendance'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    target_type = db.Column(db.String(20), nullable=False)  # "student" or "teacher"
    target_id = db.Column(db.Integer, nullable=False)       # Student ID or Teacher ID
    status = db.Column(db.String(20), nullable=False, default="Present")  # "Present", "Absent", "Late", "Leave"
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=True)
    is_locked = db.Column(db.Boolean, default=False)
    late_time = db.Column(db.String(10), nullable=True)

from datetime import datetime
from app.database import db


class TeacherModel(db.Model):
    __tablename__ = 'teachers'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    teacher_id_str = db.Column(db.String(50), unique=True, nullable=False)  # e.g. T001
    teacher_name = db.Column(db.String(100), nullable=False)
    joining_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    qualification = db.Column(db.String(100), nullable=False)
    salary = db.Column(db.Float, nullable=False, default=0.0)
    salary_type = db.Column(db.String(20), nullable=False, default='monthly')  # monthly or hourly
    monthly_salary = db.Column(db.Float, nullable=False, default=0.0)
    hourly_rate = db.Column(db.Float, nullable=False, default=0.0)
    assigned_class = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=True)

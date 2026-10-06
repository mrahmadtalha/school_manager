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
    custom_fields_data = db.Column(db.Text, nullable=True) # JSON string of custom fields
    cnic = db.Column(db.String(30), nullable=True)                    # Teacher CNIC (optional)
    address = db.Column(db.Text, nullable=True)                       # Home address (optional)
    contact_number = db.Column(db.String(30), nullable=True)          # Primary contact (optional)
    emergency_contact_number = db.Column(db.String(30), nullable=True)  # Emergency contact (optional)
    previous_experience_years = db.Column(db.Float, nullable=True)    # Years of prior experience (optional)
    previous_salary = db.Column(db.Float, nullable=True)              # Prior salary (optional)
    assigned_classes = db.Column(db.Text, nullable=True)              # JSON list of assigned class names
    assigned_subjects = db.Column(db.Text, nullable=True)             # JSON list of assigned subject names
    date_of_birth = db.Column(db.Date, nullable=True)                 # Optional birthday (widgets)
    designation = db.Column(db.String(80), nullable=True)             # e.g. Senior Teacher (optional)
    gender = db.Column(db.String(20), nullable=True)                  # Optional gender
    photo_filename = db.Column(db.String(120), nullable=True)         # Optional profile picture (see app/services/photos.py)

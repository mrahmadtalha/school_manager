from app.database import db

STUDENT_STATUSES = ('enrolled', 'slc_issued', 'graduated', 'struck_off')
STUDENT_STATUS_LABELS = {
    'enrolled': 'Enrolled',
    'slc_issued': 'SLC Issued',
    'graduated': 'Graduated',
    'struck_off': 'Struck Off',
}


class StudentModel(db.Model):
    __tablename__ = 'students'
    __table_args__ = (
        # Roll numbers are plain integers, unique per class (see app/services/roll_numbers.py).
        db.UniqueConstraint('class_id', 'roll_number', name='uq_students_class_roll'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.Integer, nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    father_name = db.Column(db.String(100), nullable=False)
    sponsor_type = db.Column(db.String(20), nullable=False, default='Father')
    sponsor_cnic = db.Column(db.String(20), nullable=True)
    guardian_phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    monthly_fee = db.Column(db.Float, nullable=True)  # Optional monthly fee
    is_active = db.Column(db.Boolean, default=True)   # Soft delete flag (False when status != 'enrolled')
    status = db.Column(db.String(20), nullable=False, default='enrolled')  # enrolled | slc_issued | graduated | struck_off
    leaving_reason = db.Column(db.String(200), nullable=True)  # Why the student left (optional)
    leaving_date = db.Column(db.Date, nullable=True)           # Date the student left (optional)
    date_of_birth = db.Column(db.Date, nullable=True)          # Optional birthday (widgets)
    gender = db.Column(db.String(10), nullable=True)           # Optional: Male | Female | Other
    admission_number = db.Column(db.String(40), nullable=True)  # Optional admission/registration no
    admission_date = db.Column(db.Date, nullable=True)          # Optional date of admission
    custom_fields_data = db.Column(db.Text, nullable=True) # JSON string of custom fields
    class_fee = db.Column(db.Float, nullable=True)        # Fee for the class at admission (before discount)
    discount_type = db.Column(db.String(20), nullable=True)  # 'percentage' or 'fixed'
    discount_value = db.Column(db.Float, nullable=True)   # Discount value (percent or PKR amount)

    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=True)

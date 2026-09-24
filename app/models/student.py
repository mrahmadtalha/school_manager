from app.database import db


class StudentModel(db.Model):
    __tablename__ = 'students'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(50), unique=True, nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    father_name = db.Column(db.String(100), nullable=False)
    guardian_phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    monthly_fee = db.Column(db.Float, nullable=True)  # Optional monthly fee
    is_active = db.Column(db.Boolean, default=True)   # Soft delete flag

    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=True)

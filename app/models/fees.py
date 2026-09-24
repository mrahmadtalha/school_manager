from app.database import db


class FeeRecordModel(db.Model):
    __tablename__ = 'fee_records'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    month_year = db.Column(db.String(20), nullable=False)  # e.g., "September 2026"
    amount_due = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default='Pending')  # Paid, Pending, Partial
    payment_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(200), nullable=True)

    student_info = db.relationship('StudentModel', backref='fee_records', lazy=True)

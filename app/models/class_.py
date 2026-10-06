from app.database import db


class ClassModel(db.Model):
    __tablename__ = 'classes'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    monthly_fee = db.Column(db.Float, nullable=True)   # Standard monthly fee for this class

    sections = db.relationship('SectionModel', backref='class_info', cascade='all, delete-orphan')
    students = db.relationship('StudentModel', backref='class_info', lazy=True)
    subjects = db.relationship('SubjectModel', backref='class_info', lazy=True)
    tests = db.relationship('TestModel', backref='class_info', lazy=True)


class SectionModel(db.Model):
    __tablename__ = 'sections'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(10), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    students = db.relationship('StudentModel', backref='section_info', lazy=True)


class SubjectModel(db.Model):
    __tablename__ = 'subjects'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # archived subjects stay for history
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)  # optional
    teacher = db.relationship('TeacherModel', lazy=True)  # optional subject-teacher mapping


class TimetableSlot(db.Model):
    """Optional Mon-Sat period grid per class; empty cells are simply absent."""
    __tablename__ = 'timetable_slots'
    __table_args__ = (
        db.UniqueConstraint('class_id', 'day_of_week', 'period_no',
                            name='uq_timetable_slot'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)   # 0=Mon .. 5=Sat
    period_no = db.Column(db.Integer, nullable=False)     # 1-based period number
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)

    subject = db.relationship('SubjectModel', lazy=True)


class TimetableConfig(db.Model):
    """Per-class timetable setup: period timings (incl. breaks) and class in-charge.

    ``rows_json`` is an ordered JSON list such as
    ``[{"kind": "period", "start": "08:30", "end": "09:10", "label": ""},
       {"kind": "break",  "start": "11:10", "end": "11:30", "label": "Break"}]``.
    Lesson rows are numbered 1..N in order; those numbers match
    ``TimetableSlot.period_no``. The table is created by ``db.create_all()``,
    so no manual migration is needed.
    """
    __tablename__ = 'timetable_configs'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), unique=True, nullable=False)
    incharge_teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)
    template_key = db.Column(db.String(30), nullable=True)
    rows_json = db.Column(db.Text, nullable=True)

    incharge = db.relationship('TeacherModel', lazy=True)
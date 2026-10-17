from app.database import db


class ClassModel(db.Model):
    __tablename__ = 'classes'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    monthly_fee = db.Column(db.Float, nullable=True)   # Standard monthly fee for this class
    admission_fee = db.Column(db.Float, nullable=True)  # One-time admission fee for this class (NULL = use the school default)
    books_fee = db.Column(db.Float, nullable=True)       # Books for a new student of this class (NULL/0 = none)
    uniform_fee = db.Column(db.Float, nullable=True)     # Price of ONE uniform set for this class (NULL/0 = none)
    uniform_sets = db.Column(db.Integer, nullable=True)  # Default number of uniform sets at admission (NULL = 1)

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


class SubjectLibrary(db.Model):
    """Global subject catalog.

    A library subject exists once for the whole school; each class chooses
    which subjects it offers through its own :class:`SubjectModel` rows
    (``library_id``).  Renaming or archiving here never deletes or rewrites
    class data — a rename cascades to the linked class rows, an archive only
    hides the subject from pickers.
    """
    __tablename__ = 'subject_library'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    code = db.Column(db.String(20), nullable=True)      # optional short code, e.g. MATH
    is_active = db.Column(db.Boolean, default=True)     # archived = hidden from pickers
    is_default = db.Column(db.Boolean, default=False)   # pre-ticked when creating a class

    subjects = db.relationship('SubjectModel', backref='library', lazy=True)


class SubjectModel(db.Model):
    __tablename__ = 'subjects'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # archived subjects stay for history
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)  # optional
    teacher = db.relationship('TeacherModel', lazy=True)  # optional subject-teacher mapping
    library_id = db.Column(db.Integer, db.ForeignKey('subject_library.id'), nullable=True)


class TeachingAssignment(db.Model):
    """Scheduling-grade teaching allocation.

    Who teaches which library subject to which class (``section_id`` NULL
    means all sections of the class), and how many periods per week are
    required.  Seeded once from the legacy ``subjects.teacher_id`` links and
    kept in step when a class subject's teacher changes on the Classes page.
    This table — not the teacher's free-text class/subject name lists — is
    what a future timetable generator will consume.
    """
    __tablename__ = 'teaching_assignments'
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'library_id', 'class_id', 'section_id',
                            name='uq_teaching_assignment'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    library_id = db.Column(db.Integer, db.ForeignKey('subject_library.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=True)
    periods_per_week = db.Column(db.Integer, nullable=True)  # required periods; NULL = unset
    is_active = db.Column(db.Boolean, default=True)

    teacher = db.relationship('TeacherModel', lazy=True)
    library_subject = db.relationship('SubjectLibrary', lazy=True)
    class_info = db.relationship('ClassModel', lazy=True)
    section = db.relationship('SectionModel', lazy=True)

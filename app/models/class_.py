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
    what the timetable conflict checker and the future generator consume.
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


class TimetableSlot(db.Model):
    """Weekly period grid per class; empty cells are simply absent.

    ``section_id`` NULL means the slot belongs to the whole class (applies to
    every section that does not keep its own slot at that day/period); a
    non-NULL ``section_id`` is a section's own grid entry that overrides the
    class-level one.  Existing rows created before sections were supported all
    have NULL and keep working unchanged.
    """
    __tablename__ = 'timetable_slots'
    __table_args__ = (
        db.UniqueConstraint('class_id', 'section_id', 'day_of_week', 'period_no',
                            name='uq_timetable_slot'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=True)
    day_of_week = db.Column(db.Integer, nullable=False)   # 0=Mon .. 5=Sat
    period_no = db.Column(db.Integer, nullable=False)     # 1-based period number
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)
    # Manual per-cell teacher override (set by the redesigned Timetables page or
    # the generator).  NULL = the subject's own teacher teaches this period.
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)

    subject = db.relationship('SubjectModel', lazy=True)
    section = db.relationship('SectionModel', lazy=True)
    teacher = db.relationship('TeacherModel', lazy=True)


class TimetableMasterConfig(db.Model):
    """School-wide master timetable settings (single row, id=1 in practice).

    ``rows_json`` is the same ordered period/break list used by the per-class
    :class:`TimetableConfig`; the master copy is what the generator applies to
    the classes it schedules.  Teaching days come from the School Settings
    off-day flags, not from here.
    """
    __tablename__ = 'timetable_master_configs'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    rows_json = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
    # Which redesigned template the school uses on the Timetables page:
    # 'matrix' (teacher-wise chart) or 'daygrid' (class weekly grid).
    template_key = db.Column(db.String(30), nullable=True)


class TimetableOverride(db.Model):
    """One-date change to the weekly timetable (e.g. teacher-absence cover).

    Applies only to ``date``: for that class/section/period the substitute
    ``teacher_id`` (and optionally a different ``subject_id``) is shown instead
    of the weekly slot; ``subject_id`` NULL means the period is declared free
    for that day.  Weekly timetables are never touched.
    """
    __tablename__ = 'timetable_overrides'
    __table_args__ = (
        db.UniqueConstraint('date', 'class_id', 'section_id', 'period_no',
                            name='uq_timetable_override'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=True)
    period_no = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)
    note = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)

    subject = db.relationship('SubjectModel', lazy=True)
    teacher = db.relationship('TeacherModel', lazy=True)
    class_info = db.relationship('ClassModel', lazy=True)
    section = db.relationship('SectionModel', lazy=True)


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
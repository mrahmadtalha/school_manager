from app.database import db


class ClassModel(db.Model):
    __tablename__ = 'classes'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

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

"""One-page timetable sheet: rows of classes x period columns -> teacher.

Kept deliberately small.  A row holds one *or more* classes (merged rows such
as "Class 2 + Class 4"), and each cell is the teacher taking that row in one
period.  The period structure itself (periods, minutes, break, assembly)
lives in School Settings and is never copied here.
"""
from app.database import db


class TimetableRow(db.Model):
    __tablename__ = 'timetable_grid_rows'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    class_ids = db.Column(db.Text, nullable=False, default='[]')   # JSON list of classes.id

    cells = db.relationship('TimetableCell', backref='row',
                            cascade='all, delete-orphan', lazy=True)


class TimetableCell(db.Model):
    __tablename__ = 'timetable_grid_cells'
    __table_args__ = (
        db.UniqueConstraint('row_id', 'period_no', name='uq_timetable_grid_cell'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    row_id = db.Column(db.Integer, db.ForeignKey('timetable_grid_rows.id'), nullable=False)
    period_no = db.Column(db.Integer, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import db

ROLE_ADMIN = 'admin'
ROLE_TEACHER = 'teacher'
ROLE_PARENT = 'parent'
ROLE_OWNER = 'owner'
ROLE_ACCOUNTANT = 'accountant'

ROLES = (ROLE_ADMIN, ROLE_TEACHER, ROLE_PARENT, ROLE_OWNER, ROLE_ACCOUNTANT)

ROLE_LABELS = {
    ROLE_ADMIN: 'Administrator',
    ROLE_TEACHER: 'Teacher',
    ROLE_PARENT: 'Parent / Guardian',
    ROLE_OWNER: 'Principal / Owner',
    ROLE_ACCOUNTANT: 'Accountant',
}


class GuardianStudentLink(db.Model):
    """Link table: one parent account can be linked to one or more students."""

    __tablename__ = 'guardian_students'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'student_id', name='uq_guardian_students_user_student'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('admin_users.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)


class AdminUser(UserMixin, db.Model):
    """A login account.

    ``role`` drives access control (see ``app.security``).  A parent account is
    linked to one or more students through ``guardian_students``; the legacy
    single ``student_id`` column is kept in sync with the first linked child so
    older code keeps working.
    """

    __tablename__ = 'admin_users'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(20), nullable=False, default=ROLE_ADMIN)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship('StudentModel', foreign_keys=[student_id], lazy='joined')
    teacher = db.relationship('TeacherModel', foreign_keys=[teacher_id], lazy=True)
    linked_students = db.relationship(
        'StudentModel',
        secondary='guardian_students',
        order_by='StudentModel.student_name',
    )

    # -- helpers ---------------------------------------------------------
    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role or 'unknown')

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    @property
    def is_teacher(self):
        return self.role == ROLE_TEACHER

    @property
    def is_parent(self):
        return self.role == ROLE_PARENT

    @property
    def is_owner(self):
        return self.role == ROLE_OWNER

    @property
    def is_accountant(self):
        return self.role == ROLE_ACCOUNTANT

    @property
    def finance_access(self):
        """True when the account may see financial data (admins + accountants)."""
        return self.is_admin or self.is_accountant

    def __repr__(self):
        return f'<AdminUser {self.username} role={self.role}>'

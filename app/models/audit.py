"""Audit trail model.

Rows are written automatically for every create/update/delete of an audited
model (see ``app/services/audit.py``) and explicitly for business actions such
as login, payment, settings change or export.
"""

import json
from datetime import datetime

from app.database import db

ACTION_CREATE = 'create'
ACTION_UPDATE = 'update'
ACTION_DELETE = 'delete'
ACTION_LOGIN = 'login'
ACTION_LOGIN_FAILED = 'login_failed'
ACTION_LOGOUT = 'logout'
ACTION_CHARGE = 'charge'
ACTION_PAYMENT = 'payment'
ACTION_VOID = 'void'
ACTION_SETTINGS = 'settings_change'
ACTION_EXPORT = 'export'
ACTION_USER = 'user_admin'
ACTION_REMINDER = 'reminder'

ACTIONS = (
    ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE, ACTION_LOGIN, ACTION_LOGIN_FAILED,
    ACTION_LOGOUT, ACTION_CHARGE, ACTION_PAYMENT, ACTION_VOID, ACTION_SETTINGS,
    ACTION_EXPORT, ACTION_USER, ACTION_REMINDER,
)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    __table_args__ = (
        db.Index('idx_audit_entity', 'entity_type', 'entity_id'),
        db.Index('idx_audit_created', 'created_at'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(80), nullable=False, default='system')
    role = db.Column(db.String(20), nullable=False, default='system')
    action = db.Column(db.String(40), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=False, default='')
    before_json = db.Column(db.Text, nullable=True)
    after_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    # -- presentation helpers -------------------------------------------
    @staticmethod
    def _load(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    @property
    def before(self):
        return self._load(self.before_json)

    @property
    def after(self):
        return self._load(self.after_json)

    @property
    def changed_fields(self):
        """Column names whose value differs between before and after."""
        before = self.before or {}
        after = self.after or {}
        keys = set(before) | set(after)
        return sorted(k for k in keys if before.get(k) != after.get(k))

    def __repr__(self):
        return f'<AuditLog {self.id} {self.action} {self.entity_type}#{self.entity_id}>'

"""Audit trail service.

Two layers:

* **Automatic** - a SQLAlchemy ``before_flush`` hook snapshots every
  create/update/delete of an audited model (students, teachers, classes,
  sections, subjects, attendance, marks, fees, settings, users) with the acting
  user, timestamp and a JSON before/after pair.
* **Explicit** - ``log_action()`` records business-level events that are not a
  plain row mutation (login, failed login, logout, payment, void, settings
  change, export, user administration).

The hook is deliberately defensive: a failure inside auditing must never break
the application transaction. Failures are logged and swallowed.
"""

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import event, inspect as sa_inspect, update
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SUSPEND_KEY = 'audit_suspended'
PENDING_KEY = 'audit_pending_ids'
_MARKER = '_audit_skip'

# Columns that should never be copied into the audit trail.
_SECRET_COLUMNS = {'password_hash'}

_MODEL_LABEL_ATTRS = (
    'student_name', 'teacher_name', 'test_title', 'username', 'name',
    'school_name', 'key',
)


def _audited_models():
    """Imported lazily to avoid a circular import at module load."""
    from app.models import (
        AdminUser, AttendanceModel, ClassModel, Expense, ExpenseCategory,
        FeeRecordModel, FeeTransaction, StaffPayroll, TermExam,
        SchoolSettings, SectionModel, StudentMarkModel, StudentModel,
        SubjectModel, TeacherModel, TestModel, TestTypeModel,
    )
    from app.models.audit import AuditLog

    models = {
        AdminUser, AttendanceModel, ClassModel, Expense, ExpenseCategory,
        FeeRecordModel, FeeTransaction, StaffPayroll, TermExam,
        SchoolSettings, SectionModel, StudentMarkModel, StudentModel,
        SubjectModel, TeacherModel, TestModel, TestTypeModel,
    }
    return {cls.__name__: cls for cls in models}, AuditLog


def suspend_audit(session=None):
    (session or _default_session()).info[SUSPEND_KEY] = True


def resume_audit(session=None):
    (session or _default_session()).info[SUSPEND_KEY] = False


def _default_session():
    from app.database import db
    return db.session


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def local_tz():
    """Timezone used to display audit timestamps (the server's local zone).

    Timestamps are stored as naive UTC; display converts them using the
    server's current fixed offset, which is exact for zones without DST
    (e.g. Pakistan Standard Time).  The full timezone-aware storage migration
    is tracked in docs/BACKLOG.md (P2-7).
    """
    return datetime.now().astimezone().tzinfo


def to_local(value):
    """Convert a stored (naive UTC) datetime into local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(local_tz())


def format_local(value, fmt='%Y-%m-%d %H:%M:%S'):
    """Format a stored datetime for display in local time (Jinja filter)."""
    converted = to_local(value)
    return converted.strftime(fmt) if converted else ''


def local_date_to_utc(day, end_of_day=False):
    """Translate a local calendar date to a naive-UTC comparison boundary."""
    moment = datetime.max.time() if end_of_day else datetime.min.time()
    return (datetime.combine(day, moment)
            .replace(tzinfo=local_tz())
            .astimezone(timezone.utc)
            .replace(tzinfo=None))


def serialize(instance):
    """Return a JSON-safe dict of the instance's mapped columns."""
    data = {}
    try:
        mapper = sa_inspect(type(instance))
        for column in mapper.columns:
            key = column.key
            if key in _SECRET_COLUMNS:
                continue
            data[key] = _jsonable(getattr(instance, key, None))
    except Exception:  # pragma: no cover - defensive
        logger.exception('audit: could not serialize %r', instance)
    return data


def _entity_label(instance):
    for attr in _MODEL_LABEL_ATTRS:
        value = getattr(instance, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f'{type(instance).__name__}#{getattr(instance, "id", "?")}'


def current_actor():
    """Return ``(user_id, username, role)`` for the active request, else system."""
    try:
        from flask_login import current_user
        if current_user is not None and getattr(current_user, 'is_authenticated', False):
            return (
                getattr(current_user, 'id', None),
                getattr(current_user, 'username', None) or 'user',
                getattr(current_user, 'role', None) or 'user',
            )
    except Exception:
        pass
    return (None, 'system', 'system')


def _request_meta():
    try:
        from flask import has_request_context, request
        if not has_request_context():
            return None, None
        agent = ''
        try:
            agent = request.user_agent.string or ''
        except Exception:
            agent = ''
        return (request.remote_addr, agent[:255] or None)
    except Exception:
        return None, None


def build_log(action, *, entity_type=None, entity_id=None, summary='', before=None,
              after=None, actor=None):
    from app.models.audit import AuditLog

    if actor is None:
        actor = current_actor()
    user_id, username, role = actor
    ip_address, user_agent = _request_meta()

    return AuditLog(
        created_at=datetime.utcnow(),
        user_id=user_id,
        username=username or 'system',
        role=role or 'system',
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=(summary or '')[:255],
        before_json=json.dumps(before, default=str) if before is not None else None,
        after_json=json.dumps(after, default=str) if after is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_action(action, *, entity_type=None, entity_id=None, summary='', before=None,
               after=None, session=None, actor=None):
    """Record an explicit business action. Returns the AuditLog row (or None)."""
    try:
        session = session or _default_session()
        row = build_log(action, entity_type=entity_type, entity_id=entity_id,
                        summary=summary, before=before, after=after, actor=actor)
        session.add(row)
        return row
    except Exception:  # pragma: no cover - defensive
        logger.exception('audit: log_action failed')
        return None


def _changed_snapshot(instance):
    """Return (before, after) dicts for the changed columns of a dirty instance."""
    before, after = {}, {}
    insp = sa_inspect(instance)
    for column in insp.mapper.columns:
        key = column.key
        if key in _SECRET_COLUMNS:
            continue
        try:
            history = insp.attrs[key].history
        except Exception:
            continue
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else getattr(instance, key, None)
        before[key] = _jsonable(old)
        after[key] = _jsonable(new)
    return before, after


def _before_flush(session, flush_context, instances):
    if session.info.get(SUSPEND_KEY):
        return

    try:
        models, audit_cls = _audited_models()
    except Exception:  # pragma: no cover - defensive
        return

    try:
        actor = current_actor()
        rows = []

        for obj in list(session.new):
            cls = type(obj)
            if cls is audit_cls or cls not in models.values():
                continue
            row = build_log('create', entity_type=cls.__name__,
                            entity_id=getattr(obj, 'id', None),
                            summary=f'{cls.__name__} "{_entity_label(obj)}" created',
                            before=None, after=serialize(obj), actor=actor)
            rows.append(row)
            # Primary keys are only assigned during the flush; fill them in
            # from the after_flush hook below.
            session.info.setdefault(PENDING_KEY, []).append((row, obj))

        for obj in list(session.dirty):
            cls = type(obj)
            if cls is audit_cls or cls not in models.values():
                continue
            if session.info.get(_MARKER) == id(obj):
                continue
            before, after = _changed_snapshot(obj)
            if not before and not after:
                continue
            rows.append(build_log('update', entity_type=cls.__name__,
                                  entity_id=getattr(obj, 'id', None),
                                  summary=f'{cls.__name__} "{_entity_label(obj)}" updated',
                                  before=before, after=after, actor=actor))

        for obj in list(session.deleted):
            cls = type(obj)
            if cls is audit_cls or cls not in models.values():
                continue
            rows.append(build_log('delete', entity_type=cls.__name__,
                                  entity_id=getattr(obj, 'id', None),
                                  summary=f'{cls.__name__} "{_entity_label(obj)}" deleted',
                                  before=serialize(obj), after=None, actor=actor))

        for row in rows:
            session.add(row)
    except Exception:  # pragma: no cover - defensive
        logger.exception('audit: before_flush hook failed (transaction continues)')


_installed = False


def _after_flush(session, flush_context):
    """Back-fill primary keys for 'create' audit rows.

    Auto-increment ids only exist once the flush has emitted the INSERT, so the
    already-flushed audit rows are patched with a direct UPDATE (which cannot
    re-trigger the ORM flush machinery and therefore cannot loop).
    """
    pending = session.info.pop(PENDING_KEY, None)
    if not pending:
        return

    try:
        models, audit_cls = _audited_models()
    except Exception:  # pragma: no cover - defensive
        return

    for row, obj in pending:
        obj_id = getattr(obj, 'id', None)
        row_id = getattr(row, 'id', None)
        if obj_id is None or row_id is None:
            continue
        try:
            session.execute(
                update(audit_cls).where(audit_cls.id == row_id).values(entity_id=obj_id)
            )
            row.entity_id = obj_id
        except Exception:  # pragma: no cover - defensive
            logger.exception('audit: could not back-fill entity id')


def install_audit_hooks():
    """Attach the listeners to the SQLAlchemy Session class exactly once."""
    global _installed
    if _installed:
        return
    event.listen(Session, 'before_flush', _before_flush)
    event.listen(Session, 'after_flush', _after_flush)
    _installed = True


# -- query helpers ------------------------------------------------------

def history_for(entity_type, entity_id, limit=200):
    from app.models.audit import AuditLog
    return (AuditLog.query
            .filter_by(entity_type=entity_type, entity_id=entity_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .all())


def query_logs(entity_type=None, action=None, username=None, date_from=None,
               date_to=None, search=None, limit=None):
    from app.models.audit import AuditLog

    query = AuditLog.query
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action == action)
    if username:
        query = query.filter(AuditLog.username == username)
    if date_from:
        query = query.filter(AuditLog.created_at >= local_date_to_utc(date_from))
    if date_to:
        query = query.filter(AuditLog.created_at <= local_date_to_utc(date_to, end_of_day=True))
    if search:
        like = f'%{search}%'
        query = query.filter(AuditLog.summary.ilike(like) | AuditLog.username.ilike(like))
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def distinct_usernames():
    from app.database import db
    from app.models.audit import AuditLog
    rows = db.session.query(AuditLog.username).distinct().order_by(AuditLog.username).all()
    return [r[0] for r in rows if r[0]]


def distinct_entity_types():
    from app.database import db
    from app.models.audit import AuditLog
    rows = db.session.query(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type).all()
    return [r[0] for r in rows if r[0]]

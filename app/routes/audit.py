"""Audit trail browsing and per-entity history."""

import csv
import io
from datetime import datetime

from flask import Response, render_template, request
from sqlalchemy import or_

from app.database import db
from app.models import ACTIONS, ROLE_ADMIN, StudentModel
from app.models.audit import AuditLog
from app.routes import main
from app.security import role_required
from app.services import audit as audit_service

ENTITY_LABELS = {
    'StudentModel': 'Student',
    'TeacherModel': 'Teacher',
    'ClassModel': 'Class',
    'SectionModel': 'Section',
    'SubjectModel': 'Subject',
    'TestModel': 'Test',
    'TestTypeModel': 'Test type',
    'StudentMarkModel': 'Mark',
    'AttendanceModel': 'Attendance',
    'FeeRecordModel': 'Fee summary',
    'FeeTransaction': 'Fee transaction',
    'SchoolSettings': 'School settings',
    'AdminUser': 'User',
    'ExecutiveSummary': 'Executive summary',
}


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _local_iso(value):
    """Local-time ISO string (with offset) for the CSV export."""
    converted = audit_service.to_local(value)
    return converted.isoformat(sep=' ', timespec='seconds') if converted else ''


def _filters():
    return {
        'entity_type': (request.args.get('entity_type') or '').strip() or None,
        'action': (request.args.get('action') or '').strip() or None,
        'username': (request.args.get('username') or '').strip() or None,
        'date_from': _parse_date(request.args.get('date_from')),
        'date_to': _parse_date(request.args.get('date_to')),
        'search': (request.args.get('search') or '').strip() or None,
    }


def _json_id_match(column, key, value):
    """Match a JSON integer field without matching longer numbers (12 vs 120)."""
    return or_(
        column.like(f'%"{key}": {value},%'),
        column.like(f'%"{key}": {value}}}%'),
    )


@main.route('/audit-log')
@role_required(ROLE_ADMIN)
def audit_log():
    filters = _filters()
    rows = audit_service.query_logs(limit=500, **filters)
    return render_template(
        'audit_log.html',
        rows=rows,
        filters=filters,
        entity_labels=ENTITY_LABELS,
        actions=ACTIONS,
        entity_types=audit_service.distinct_entity_types(),
        usernames=audit_service.distinct_usernames(),
    )


@main.route('/audit-log/export.csv')
@role_required(ROLE_ADMIN)
def audit_log_export():
    filters = _filters()
    rows = audit_service.query_logs(**filters)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['timestamp', 'username', 'role', 'action', 'entity_type',
                     'entity_id', 'summary', 'changed_fields', 'ip_address',
                     'before_json', 'after_json'])
    for row in rows:
        writer.writerow([
            _local_iso(row.created_at),
            row.username, row.role, row.action, row.entity_type or '', row.entity_id or '',
            row.summary or '', ','.join(row.changed_fields), row.ip_address or '',
            row.before_json or '', row.after_json or '',
        ])
    buffer.seek(0)

    audit_service.log_action('export', entity_type='AuditLog',
                             summary=f'Audit log exported ({len(rows)} rows)')
    db.session.commit()

    filename = f'audit-log-{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv'
    return Response(buffer.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@main.route('/students/<int:id>/history')
def student_history(id):
    student = StudentModel.query.get_or_404(id)

    conditions = [
        (AuditLog.entity_type == 'StudentModel') & (AuditLog.entity_id == student.id),
        _json_id_match(AuditLog.after_json, 'student_id', student.id),
        _json_id_match(AuditLog.before_json, 'student_id', student.id),
        _json_id_match(AuditLog.after_json, 'target_id', student.id),
    ]
    rows = (AuditLog.query
            .filter(or_(*conditions))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(500)
            .all())

    return render_template('student_history.html', student=student, rows=rows,
                           entity_labels=ENTITY_LABELS)

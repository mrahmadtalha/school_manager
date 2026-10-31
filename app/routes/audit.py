"""Audit trail browsing and per-entity history."""

import csv
import io
from datetime import datetime, timedelta

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


# Plain-language wording for each action: (label, badge colour, icon).
ACTION_INFO = {
    'create': ('Added', 'ok', 'fa-plus'),
    'update': ('Changed', 'warn', 'fa-pen'),
    'delete': ('Deleted', 'bad', 'fa-trash'),
    'login': ('Signed in', 'ok', 'fa-right-to-bracket'),
    'login_failed': ('Failed sign-in', 'bad', 'fa-triangle-exclamation'),
    'logout': ('Signed out', 'muted', 'fa-right-from-bracket'),
    'charge': ('Fee charged', 'warn', 'fa-file-invoice-dollar'),
    'payment': ('Payment received', 'ok', 'fa-coins'),
    'void': ('Cancelled (void)', 'bad', 'fa-ban'),
    'settings_change': ('Settings changed', 'warn', 'fa-gear'),
    'export': ('Data exported', 'muted', 'fa-download'),
    'user_admin': ('User account', 'warn', 'fa-user-gear'),
    'reminder': ('Reminder sent', 'muted', 'fa-bell'),
}

RANGES = {'today': 0, '7d': 6, '30d': 29}
_HIDDEN_FIELDS = {'id', 'updated_at', 'created_at'}
_DETAIL_LIMIT = 12


def action_info(action):
    return ACTION_INFO.get(action) or (str(action or '').replace('_', ' ').capitalize(), 'muted', 'fa-circle')


def _pretty_value(value):
    if value is None or value == '':
        return '—'
    if value is True:
        return 'Yes'
    if value is False:
        return 'No'
    text = str(value)
    return text if len(text) <= 80 else text[:77] + '…'


def _pretty_field(name):
    return str(name).replace('_', ' ').strip().capitalize()


def change_details(row):
    """What changed, as plain rows: [(field, before, after)] plus how many were left out."""
    before = row.before if isinstance(row.before, dict) else {}
    after = row.after if isinstance(row.after, dict) else {}
    if before and after:
        names = [k for k in row.changed_fields if k not in _HIDDEN_FIELDS]
    else:
        names = [k for k in sorted(before or after) if k not in _HIDDEN_FIELDS
                 and (before or after).get(k) not in (None, '')]
    items = [(_pretty_field(k), _pretty_value(before.get(k)), _pretty_value(after.get(k)))
             for k in names[:_DETAIL_LIMIT]]
    return {'items': items, 'more': max(0, len(names) - _DETAIL_LIMIT),
            'kind': 'changed' if before and after else ('added' if after else 'deleted')}


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
    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'))
    quick = (request.args.get('range') or '').strip()
    if quick in RANGES and not date_from and not date_to:
        date_from = datetime.now().date() - timedelta(days=RANGES[quick])
    return {
        'entity_type': (request.args.get('entity_type') or '').strip() or None,
        'action': (request.args.get('action') or '').strip() or None,
        'username': (request.args.get('username') or '').strip() or None,
        'date_from': date_from,
        'date_to': date_to,
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
    quick = (request.args.get('range') or '').strip()
    view_rows = []
    counts = {'create': 0, 'update': 0, 'delete': 0, 'login_failed': 0}
    for row in rows:
        if row.action in counts:
            counts[row.action] += 1
        label, tone, icon = action_info(row.action)
        view_rows.append({'row': row, 'label': label, 'tone': tone, 'icon': icon,
                          'detail': change_details(row) if (row.before_json or row.after_json) else None})
    stats = {
        'total': len(rows),
        'added': counts['create'],
        'changed': counts['update'],
        'deleted': counts['delete'],
        'failed': counts['login_failed'],
        'other': len(rows) - counts['create'] - counts['update'] - counts['delete'],
        'capped': len(rows) >= 500,
    }
    filters['range'] = quick if (quick in RANGES and not request.args.get('date_from')
                                 and not request.args.get('date_to')) else ''
    filters['active'] = any(v for k, v in filters.items() if k != 'range') or bool(filters['range'])
    return render_template(
        'audit_log.html',
        rows=rows,
        view_rows=view_rows,
        stats=stats,
        action_info=ACTION_INFO,
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

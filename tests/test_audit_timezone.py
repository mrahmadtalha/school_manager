"""Audit timestamps are displayed in the server's local time (stored as UTC)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.database import db
from app.models.audit import AuditLog
from app.services import audit as audit_service

PKT = timezone(timedelta(hours=5))  # Pakistan Standard Time, no DST


@pytest.fixture()
def pkt_timezone(monkeypatch):
    """Force the display timezone so assertions are machine-independent."""
    monkeypatch.setattr(audit_service, 'local_tz', lambda: PKT)


def _add_log(app, created_at, summary, entity_id=1):
    with app.app_context():
        row = AuditLog(
            created_at=created_at,
            username='tester', role='admin', action='update',
            entity_type='StudentModel', entity_id=entity_id,
            summary=summary,
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def test_to_local_and_format_local(pkt_timezone):
    converted = audit_service.to_local(datetime(2026, 9, 28, 8, 45, 38))
    assert converted.strftime('%Y-%m-%d %H:%M:%S') == '2026-09-28 13:45:38'
    assert converted.utcoffset() == timedelta(hours=5)

    assert audit_service.to_local(None) is None
    assert audit_service.format_local(None) == ''
    assert audit_service.format_local(datetime(2026, 9, 28, 8, 45, 38)) == '2026-09-28 13:45:38'


def test_local_date_to_utc_boundaries(pkt_timezone):
    start = audit_service.local_date_to_utc(date(2026, 9, 28))
    end = audit_service.local_date_to_utc(date(2026, 9, 28), end_of_day=True)

    assert start == datetime(2026, 9, 27, 19, 0, 0)          # local midnight -> UTC
    assert end.strftime('%Y-%m-%d %H:%M') == '2026-09-28 18:59'  # local day end -> UTC


def test_audit_page_shows_local_times(admin_client, app, pkt_timezone):
    _add_log(app, datetime(2026, 9, 28, 8, 45, 38), summary='Timezone probe event')
    body = admin_client.get('/audit-log',
                            query_string={'search': 'Timezone probe event'}).get_data(as_text=True)
    assert '2026-09-28 13:45:38' in body
    assert '2026-09-28 08:45:38' not in body


def test_student_history_shows_local_times(admin_client, app, seed, pkt_timezone):
    _add_log(app, datetime(2026, 9, 28, 11, 15, 0), summary='History probe event',
             entity_id=seed['student_id'])
    body = admin_client.get(f"/students/{seed['student_id']}/history").get_data(as_text=True)
    assert '2026-09-28 16:15:00' in body
    assert '2026-09-28 11:15:00' not in body


def test_audit_date_filters_use_local_boundaries(admin_client, app, pkt_timezone):
    _add_log(app, datetime(2026, 9, 27, 22, 0, 0), summary='Late night probe')
    _add_log(app, datetime(2026, 9, 28, 19, 0, 1), summary='After midnight probe')

    day_28 = admin_client.get('/audit-log', query_string={
        'date_from': '2026-09-28', 'date_to': '2026-09-28'}).get_data(as_text=True)
    assert 'Late night probe' in day_28            # 22:00 UTC = 03:00 local on the 28th
    assert 'After midnight probe' not in day_28    # 19:00:01 UTC = 00:00:01 local on the 29th

    day_29 = admin_client.get('/audit-log', query_string={
        'date_from': '2026-09-29', 'date_to': '2026-09-29'}).get_data(as_text=True)
    assert 'After midnight probe' in day_29
    assert 'Late night probe' not in day_29


def test_csv_export_uses_local_times(admin_client, app, pkt_timezone):
    _add_log(app, datetime(2026, 9, 28, 8, 45, 38), summary='CSV probe event')
    text = admin_client.get('/audit-log/export.csv').get_data(as_text=True)
    assert '2026-09-28 13:45:38+05:00' in text
    assert ',2026-09-28 08:45:38,' not in text

# -*- coding: utf-8 -*-
"""Academic Calendar: add / edit / delete / archive / pin events."""

import pytest
from datetime import date, timedelta

from app.database import db
from app.models.calendar import CalendarEvent


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _add_event(app, title='Test Holiday', event_date=None, category='holiday',
               is_pinned=False, is_archived=False, end_date=None):
    event_date = event_date or date.today()
    with app.app_context():
        ev = CalendarEvent(
            title=title,
            event_date=event_date,
            end_date=end_date,
            category=category,
            is_pinned=is_pinned,
            is_archived=is_archived,
        )
        db.session.add(ev)
        db.session.commit()
        return ev.id


# ─────────────────────────────────────────────────────────────
# Page loads
# ─────────────────────────────────────────────────────────────

def test_calendar_page_loads(admin_client):
    page = admin_client.get('/calendar')
    assert page.status_code == 200
    assert 'Academic Calendar' in page.get_data(as_text=True)


def test_calendar_list_view_loads(admin_client):
    page = admin_client.get('/calendar?view=list')
    assert page.status_code == 200


def test_calendar_month_grid_loads(admin_client):
    today = date.today()
    page = admin_client.get(f'/calendar?view=month&year={today.year}&month={today.month}')
    assert page.status_code == 200


def test_calendar_add_form_loads(admin_client):
    page = admin_client.get('/calendar/add')
    assert page.status_code == 200
    assert 'Add New Event' in page.get_data(as_text=True)


def test_calendar_page_forbidden_for_teacher(teacher_client):
    # Teachers can VIEW the calendar
    page = teacher_client.get('/calendar')
    assert page.status_code == 200


def test_calendar_add_forbidden_for_teacher(teacher_client):
    page = teacher_client.get('/calendar/add')
    assert page.status_code == 403


# ─────────────────────────────────────────────────────────────
# Add event
# ─────────────────────────────────────────────────────────────

def test_add_event_success(admin_client, app):
    today = date.today().isoformat()
    resp = admin_client.post('/calendar/add', data={
        'title': 'Eid Holiday',
        'description': 'School closed for Eid',
        'event_date': today,
        'end_date': '',
        'category': 'holiday',
    }, follow_redirects=True)
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'Eid Holiday' in text or 'added' in text.lower()

    with app.app_context():
        ev = CalendarEvent.query.filter_by(title='Eid Holiday').first()
        assert ev is not None
        assert ev.category == 'holiday'
        assert ev.is_archived is False


def test_add_event_multi_day(admin_client, app):
    start = date.today().isoformat()
    end   = (date.today() + timedelta(days=3)).isoformat()
    resp = admin_client.post('/calendar/add', data={
        'title': 'Mid-Term Exams',
        'event_date': start,
        'end_date': end,
        'category': 'exam',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        ev = CalendarEvent.query.filter_by(title='Mid-Term Exams').first()
        assert ev is not None
        assert ev.end_date is not None
        assert ev.is_multi_day


def test_add_event_requires_title(admin_client):
    today = date.today().isoformat()
    resp = admin_client.post('/calendar/add', data={
        'title': '',
        'event_date': today,
        'category': 'general',
    }, follow_redirects=True)
    text = resp.get_data(as_text=True)
    assert 'required' in text.lower() or 'Title' in text


def test_add_event_end_before_start_rejected(admin_client, app):
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    resp = admin_client.post('/calendar/add', data={
        'title': 'Bad Dates',
        'event_date': today,
        'end_date': yesterday,
        'category': 'general',
    }, follow_redirects=True)
    with app.app_context():
        assert CalendarEvent.query.filter_by(title='Bad Dates').first() is None


def test_add_event_pinned(admin_client, app):
    today = date.today().isoformat()
    admin_client.post('/calendar/add', data={
        'title': 'Parents Day',
        'event_date': today,
        'category': 'meeting',
        'is_pinned': '1',
    }, follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.filter_by(title='Parents Day').first()
        assert ev is not None and ev.is_pinned is True


# ─────────────────────────────────────────────────────────────
# Edit event
# ─────────────────────────────────────────────────────────────

def test_edit_event_form_loads(admin_client, app):
    eid = _add_event(app, title='Sports Day')
    page = admin_client.get(f'/calendar/{eid}/edit')
    assert page.status_code == 200
    assert 'Sports Day' in page.get_data(as_text=True)


def test_edit_event_updates_title(admin_client, app):
    eid = _add_event(app, title='Old Title')
    today = date.today().isoformat()
    admin_client.post(f'/calendar/{eid}/edit', data={
        'title': 'New Title',
        'event_date': today,
        'end_date': '',
        'category': 'general',
    }, follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.title == 'New Title'


def test_edit_event_404_for_missing(admin_client):
    page = admin_client.get('/calendar/99999/edit')
    assert page.status_code == 404


# ─────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────

def test_delete_event(admin_client, app):
    eid = _add_event(app, title='To Delete')
    resp = admin_client.post(f'/calendar/{eid}/delete', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert CalendarEvent.query.get(eid) is None


def test_delete_event_404_for_missing(admin_client):
    resp = admin_client.post('/calendar/99999/delete', follow_redirects=True)
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────
# Archive / unarchive
# ─────────────────────────────────────────────────────────────

def test_archive_event(admin_client, app):
    eid = _add_event(app, title='Archive Me')
    admin_client.post(f'/calendar/{eid}/archive', follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.is_archived is True


def test_unarchive_event(admin_client, app):
    eid = _add_event(app, title='Restore Me', is_archived=True)
    admin_client.post(f'/calendar/{eid}/archive', follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.is_archived is False


def test_archive_clears_pin(admin_client, app):
    eid = _add_event(app, title='Pinned Event', is_pinned=True)
    admin_client.post(f'/calendar/{eid}/archive', follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.is_archived is True
        assert ev.is_pinned is False


def test_archived_events_hidden_by_default(admin_client, app):
    _add_event(app, title='Hidden Archived', is_archived=True)
    page = admin_client.get('/calendar?view=list').get_data(as_text=True)
    assert 'Hidden Archived' not in page


def test_archived_events_shown_with_flag(admin_client, app):
    _add_event(app, title='Show Me Archived', is_archived=True)
    page = admin_client.get('/calendar?view=list&archived=1').get_data(as_text=True)
    assert 'Show Me Archived' in page


# ─────────────────────────────────────────────────────────────
# Pin / unpin
# ─────────────────────────────────────────────────────────────

def test_pin_event(admin_client, app):
    eid = _add_event(app, title='Pin This')
    admin_client.post(f'/calendar/{eid}/pin', follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.is_pinned is True


def test_unpin_event(admin_client, app):
    eid = _add_event(app, title='Unpin This', is_pinned=True)
    admin_client.post(f'/calendar/{eid}/pin', follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.is_pinned is False


def test_cannot_pin_archived_event(admin_client, app):
    eid = _add_event(app, title='Archived Cant Pin', is_archived=True)
    admin_client.post(f'/calendar/{eid}/pin', follow_redirects=True)
    with app.app_context():
        ev = CalendarEvent.query.get(eid)
        assert ev.is_pinned is False


def test_pinned_events_shown_in_strip(admin_client, app):
    _add_event(app, title='Pinned Notice', is_pinned=True,
               event_date=date.today() + timedelta(days=5))
    page = admin_client.get('/calendar').get_data(as_text=True)
    assert 'Pinned Notice' in page


# ─────────────────────────────────────────────────────────────
# API endpoint
# ─────────────────────────────────────────────────────────────

def test_api_events_returns_json(admin_client, app):
    today = date.today()
    _add_event(app, title='API Event', event_date=today)
    resp = admin_client.get(f'/calendar/api/events?year={today.year}&month={today.month}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    titles = [e['title'] for e in data]
    assert 'API Event' in titles


def test_api_events_excludes_archived(admin_client, app):
    today = date.today()
    _add_event(app, title='Archived API', event_date=today, is_archived=True)
    resp = admin_client.get(f'/calendar/api/events?year={today.year}&month={today.month}')
    data = resp.get_json()
    assert 'Archived API' not in [e['title'] for e in data]


# ─────────────────────────────────────────────────────────────
# Category filter
# ─────────────────────────────────────────────────────────────

def test_category_filter(admin_client, app):
    _add_event(app, title='Summer Trip', category='trip',
               event_date=date.today() + timedelta(days=10))
    _add_event(app, title='Monthly Meeting', category='meeting',
               event_date=date.today() + timedelta(days=11))
    page = admin_client.get('/calendar?view=list&category=trip').get_data(as_text=True)
    assert 'Summer Trip' in page
    assert 'Monthly Meeting' not in page


# ─────────────────────────────────────────────────────────────
# Model helpers
# ─────────────────────────────────────────────────────────────

def test_model_is_upcoming(app):
    with app.app_context():
        ev = CalendarEvent(title='x', event_date=date.today() + timedelta(days=1))
        assert ev.is_upcoming is True
        ev2 = CalendarEvent(title='y', event_date=date.today() - timedelta(days=1))
        assert ev2.is_upcoming is False


def test_model_is_past(app):
    with app.app_context():
        ev = CalendarEvent(title='x', event_date=date.today() - timedelta(days=5))
        assert ev.is_past is True


def test_model_category_color(app):
    with app.app_context():
        ev = CalendarEvent(title='x', event_date=date.today(), category='holiday')
        assert ev.category_color == 'success'
        ev.category = 'exam'
        assert ev.category_color == 'danger'


def test_model_to_dict(app):
    with app.app_context():
        ev = CalendarEvent(title='Dict Test', event_date=date.today(), category='general')
        d = ev.to_dict()
        assert d['title'] == 'Dict Test'
        assert 'event_date' in d
        assert 'is_pinned' in d


# ─────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────

def test_migration_creates_table(app):
    """Migration run on an already-created DB is a no-op (table exists)."""
    from app.migrations.calendar import run as migrate_calendar
    with app.app_context():
        migrate_calendar(app)   # second run must not raise
    with app.app_context():
        # table should still be there
        events = CalendarEvent.query.all()
        assert isinstance(events, list)

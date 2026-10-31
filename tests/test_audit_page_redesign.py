# -*- coding: utf-8 -*-
"""Audit Log page redesign: plain wording, summary band, quick ranges, what-changed details."""
from app.database import db
from app.services import audit as audit_service


def _log(action, summary, **kwargs):
    audit_service.log_action(action, entity_type=kwargs.pop('entity_type', 'StudentModel'),
                             entity_id=kwargs.pop('entity_id', 1), summary=summary, **kwargs)


def test_audit_page_uses_plain_words_and_summary(admin_client, app, seed):
    with app.app_context():
        _log('create', 'Added student Zed')
        _log('delete', 'Removed student Old')
        _log('login_failed', 'Failed login for "ghost"', entity_type='AdminUser')
        db.session.commit()
    page = admin_client.get('/audit-log').get_data(as_text=True)
    for text in ('Audit Log', 'What to do now', 'Entries on this list', 'Failed sign-in',
                 'Deleted', 'Added', 'What happened'):
        assert text in page, text
    assert 'filter-me' not in page


def test_what_changed_shows_before_and_after(admin_client, app, seed):
    with app.app_context():
        _log('update', 'Fee changed for diff-check',
             before={'id': 1, 'monthly_fee': 2500, 'updated_at': 'x'},
             after={'id': 1, 'monthly_fee': 3000, 'updated_at': 'y'})
        db.session.commit()
    page = admin_client.get('/audit-log?search=diff-check').get_data(as_text=True)
    assert 'See what changed' in page
    assert 'Monthly fee' in page and '2500' in page and '3000' in page
    assert 'updated_at' not in page and 'Updated at' not in page


def test_quick_range_and_filters_keep_working(admin_client, app, seed):
    with app.app_context():
        _log('settings_change', 'range-check entry', entity_type='SchoolSettings')
        db.session.commit()
    for rng in ('today', '7d', '30d'):
        page = admin_client.get(f'/audit-log?range={rng}&search=range-check').get_data(as_text=True)
        assert 'range-check entry' in page, rng
    unknown = admin_client.get('/audit-log?range=bogus&search=range-check')
    assert unknown.status_code == 200
    csv_page = admin_client.get('/audit-log/export.csv?range=today&search=range-check')
    assert csv_page.status_code == 200 and 'range-check entry' in csv_page.get_data(as_text=True)


def test_empty_audit_page_has_a_clear_message(admin_client):
    page = admin_client.get('/audit-log?entity_type=DoesNotExist').get_data(as_text=True)
    assert 'No audit entries match these filters.' in page
    assert 'Show everything' in page


def test_audit_page_in_urdu(admin_client):
    admin_client.get('/language/ur')
    page = admin_client.get('/audit-log').get_data(as_text=True)
    assert 'dir="rtl"' in page
    assert 'اس فہرست میں اندراجات' in page or 'کیا ہوا' in page
    assert 'What happened' not in page


def test_audit_page_is_admin_only(teacher_client):
    assert teacher_client.get('/audit-log').status_code == 403

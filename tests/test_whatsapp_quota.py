"""Daily / monthly WhatsApp caps carried by the license."""

import json
from datetime import date, timedelta

from app.database import db
from app.models import MessageQueue
from app.services import whatsapp_quota
from tests.conftest import ADMIN_PASSWORD, login
from tests.licensing_fixtures import (clock, keypair, licensed_app_factory, make_key)  # noqa: F401


def _queue(application, count):
    with application.app_context():
        for index in range(count):
            db.session.add(MessageQueue(phone='923001234567', message=f'm{index}', status='approved'))
        db.session.commit()


def _admin(application):
    client = application.test_client()
    login(client, 'admin', ADMIN_PASSWORD)
    return client


def _activate(application, keypair, **extra):
    application.extensions['license_manager'].activate(make_key(keypair[0], rev=1, **extra))


def test_pending_never_hands_over_more_than_the_daily_cap(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=3, wa_monthly=50)
    _queue(application, 5)
    admin = _admin(application)

    first = admin.get('/api/whatsapp/pending').get_json()
    assert len(first['items']) == 3

    # The three are "in flight": a second poll must not hand out more.
    second = admin.get('/api/whatsapp/pending').get_json()
    assert second['items'] == [] and 'Daily WhatsApp limit' in second['paused']

    for item in first['items']:
        assert admin.post('/api/whatsapp/update-status',
                          json={'id': item['id'], 'status': 'sent'}).status_code == 200

    exhausted = admin.get('/api/whatsapp/pending').get_json()
    assert exhausted['items'] == [] and 'Daily WhatsApp limit' in exhausted['paused']
    with application.app_context():
        info = whatsapp_quota.summary()
        assert info['day_used'] == 3 and info['day_remaining'] == 0
        assert MessageQueue.query.filter_by(status='approved').count() == 2   # nothing lost


def test_monthly_cap_applies_even_when_daily_has_room(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=10, wa_monthly=2)
    _queue(application, 4)
    admin = _admin(application)
    assert len(admin.get('/api/whatsapp/pending').get_json()['items']) == 2
    with application.app_context():
        assert whatsapp_quota.allowance() == 0
        assert whatsapp_quota.summary()['blocked_by'] == 'month'


def test_failed_messages_do_not_use_up_the_cap(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=2, wa_monthly=20)
    _queue(application, 2)
    admin = _admin(application)
    for item in admin.get('/api/whatsapp/pending').get_json()['items']:
        admin.post('/api/whatsapp/update-status', json={'id': item['id'], 'status': 'failed'})
    with application.app_context():
        assert whatsapp_quota.summary()['day_used'] == 0


def test_unlimited_without_limits(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'])          # no wa_* limits
    _queue(application, 5)
    assert len(_admin(application).get('/api/whatsapp/pending').get_json()['items']) == 5


def test_counter_survives_deleting_queue_rows_and_the_counter_file(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=3, wa_monthly=50)
    _queue(application, 3)
    admin = _admin(application)
    for item in admin.get('/api/whatsapp/pending').get_json()['items']:
        admin.post('/api/whatsapp/update-status', json={'id': item['id'], 'status': 'sent'})

    with application.app_context():
        MessageQueue.query.delete()                    # cheat 1: wipe the queue history
        db.session.commit()
        assert whatsapp_quota.summary()['day_used'] == 3
        path = whatsapp_quota._path()
        assert path.is_file()
        path.write_text('{"s": null, "d": {}, "m": {}, "sig": "forged"}')   # cheat 2: forge counter
        assert whatsapp_quota.summary()['day_used'] == 0      # forged file ignored, queue empty
    _queue(application, 3)
    with application.app_context():
        for row in MessageQueue.query.all():           # rows sent earlier today again
            row.status, row.sent_at = 'sent', __import__('datetime').datetime.utcnow()
        db.session.commit()
        assert whatsapp_quota.summary()['day_used'] == 3      # queue view still counts


def test_clock_rollback_does_not_reset_the_day(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=2, wa_monthly=50)
    _queue(application, 2)
    admin = _admin(application)
    for item in admin.get('/api/whatsapp/pending').get_json()['items']:
        admin.post('/api/whatsapp/update-status', json={'id': item['id'], 'status': 'sent'})
    with application.app_context():
        yesterday = date.today() - timedelta(days=1)
        assert whatsapp_quota.summary(today=yesterday)['day_used'] == 2   # "today" never goes backwards


def test_next_day_gets_a_fresh_daily_quota(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=2, wa_monthly=500)
    _queue(application, 2)
    admin = _admin(application)
    for item in admin.get('/api/whatsapp/pending').get_json()['items']:
        admin.post('/api/whatsapp/update-status', json={'id': item['id'], 'status': 'sent'})
    with application.app_context():
        tomorrow = whatsapp_quota.summary(today=date.today() + timedelta(days=1))
        assert tomorrow['day_used'] == 0 and tomorrow['allowance'] == 2


def test_test_message_is_refused_when_the_cap_is_reached(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=0, wa_monthly=0)
    admin = _admin(application)
    response = admin.post('/api/whatsapp/send-test', json={'phone': '923001234567'})
    assert response.status_code == 429 and response.get_json()['error'] == 'whatsapp_limit'


def test_automation_page_shows_the_usage_meter(licensed_app_factory, keypair):
    application = licensed_app_factory()
    _activate(application, keypair, features=['whatsapp'], wa_daily=100, wa_monthly=2000)
    page = _admin(application).get('/automation')
    assert page.status_code == 200 and b'Sending limits' in page.data and b'/ 100' in page.data

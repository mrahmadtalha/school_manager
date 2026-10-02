from app.database import db
from app.models import AutomationSettings, MessageQueue, TeacherModel


def bridge_headers(app):
    app.config['WHATSAPP_BRIDGE_TOKEN'] = 'queue-test-token'
    return {'X-Bridge-Token': 'queue-test-token'}


def test_dispatch_claims_approved_only_and_only_once(app, client):
    headers = bridge_headers(app)
    with app.app_context():
        settings = AutomationSettings.get()
        settings.enabled = True
        settings.mode = 'approval'
        pending = MessageQueue(phone='923001234567', message='Needs approval', status='pending')
        approved = MessageQueue(phone='923007654321', message='Approved', status='approved')
        db.session.add_all([pending, approved])
        db.session.commit()
        pending_id, approved_id = pending.id, approved.id

    response = client.get('/api/whatsapp/pending', headers=headers)

    assert response.status_code == 200
    assert [item['id'] for item in response.get_json()['items']] == [approved_id]
    with app.app_context():
        assert db.session.get(MessageQueue, pending_id).status == 'pending'
        assert db.session.get(MessageQueue, approved_id).status == 'sending'

    repeated = client.get('/api/whatsapp/pending', headers=headers)
    assert repeated.get_json()['items'] == []


def test_auto_mode_dispatches_legacy_pending_items(app, client):
    headers = bridge_headers(app)
    with app.app_context():
        settings = AutomationSettings.get()
        settings.mode = 'auto'
        item = MessageQueue(phone='923001234567', message='Automatic', status='pending')
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    response = client.get('/api/whatsapp/pending', headers=headers)

    assert [item['id'] for item in response.get_json()['items']] == [item_id]


def test_failed_recipient_reason_is_saved_and_visible(app, client, admin_client):
    headers = bridge_headers(app)
    with app.app_context():
        item = MessageQueue(
            phone='923001234567', message='Hello', status='sending',
            trigger='attendance_absent',
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    response = client.post('/api/whatsapp/update-status', headers=headers, json={
        'id': item_id,
        'status': 'failed',
        'error_message': 'Not Registered on WhatsApp',
    })

    assert response.status_code == 200
    with app.app_context():
        saved = db.session.get(MessageQueue, item_id)
        assert saved.status == 'failed'
        assert saved.error_msg == 'Not Registered on WhatsApp'

    page = admin_client.get('/automation')
    assert b'Not Registered on WhatsApp' in page.data


def test_status_updates_cannot_bypass_queue_claim(app, client):
    headers = bridge_headers(app)
    with app.app_context():
        item = MessageQueue(phone='923001234567', message='Hello', status='pending')
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    response = client.post('/api/whatsapp/update-status', headers=headers, json={
        'id': item_id,
        'status': 'sent',
    })

    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(MessageQueue, item_id).status == 'pending'


def test_switching_to_approval_revokes_in_flight_automatic_send(app, client, admin_client):
    headers = bridge_headers(app)
    with app.app_context():
        settings = AutomationSettings.get()
        settings.mode = 'auto'
        item = MessageQueue(phone='923001234567', message='Hello', status='pending')
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    claimed = client.get('/api/whatsapp/pending', headers=headers)
    assert [item['id'] for item in claimed.get_json()['items']] == [item_id]

    admin_client.post('/automation', data={
        'action': 'save_settings',
        'mode': 'approval',
        'enabled': 'on',
    })
    authorization = client.post('/api/whatsapp/authorize-send', headers=headers,
                                json={'id': item_id})

    assert authorization.status_code == 409
    with app.app_context():
        assert db.session.get(MessageQueue, item_id).status == 'pending'


def test_whatsapp_test_api_forwards_custom_recipient(app, client, monkeypatch):
    headers = bridge_headers(app)
    forwarded = {}

    class FakeResponse:
        ok = True
        headers = {'content-type': 'application/json'}

        @staticmethod
        def json():
            return {'ok': True, 'message': 'Test message sent successfully.'}

    def fake_post(url, **kwargs):
        forwarded['url'] = url
        forwarded.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr('app.routes.settings.requests.post', fake_post)
    response = client.post('/api/whatsapp/send-test', headers=headers,
                           json={'phone': '+923001234567'})

    assert response.status_code == 200
    assert forwarded['json']['phone'] == '923001234567'
    assert forwarded['url'].endswith('/send-test')


def test_whatsapp_test_api_uses_self_chat_when_recipient_is_blank(app, client, monkeypatch):
    headers = bridge_headers(app)
    forwarded = {}

    class FakeResponse:
        ok = True
        headers = {'content-type': 'application/json'}

        @staticmethod
        def json():
            return {'ok': True, 'message': 'Test message sent successfully.'}

    def fake_post(url, **kwargs):
        forwarded.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr('app.routes.settings.requests.post', fake_post)
    response = client.post('/api/whatsapp/send-test', headers=headers, json={})

    assert response.status_code == 200
    assert forwarded['json']['phone'] is None


def test_cloud_api_settings_persist_and_are_available_to_bridge(app, admin_client, client):
    headers = bridge_headers(app)
    response = admin_client.post('/automation', data={
        'action': 'save_settings',
        'mode': 'approval',
        'integration_method': 'cloud_api',
        'whatsapp_api_token': 'test-access-token',
        'whatsapp_phone_number_id': '123456789',
        'whatsapp_business_account_id': '987654321',
    })

    assert response.status_code == 302
    config_response = client.get('/api/whatsapp/integration', headers=headers)

    assert config_response.status_code == 200
    config = config_response.get_json()
    assert config['integration_method'] == 'cloud_api'
    assert config['cloud_api'] == {
        'access_token': 'test-access-token',
        'phone_number_id': '123456789',
        'business_account_id': '987654321',
    }


def test_cloud_api_settings_require_all_credentials(app, admin_client):
    response = admin_client.post('/automation', data={
        'action': 'save_settings',
        'mode': 'approval',
        'integration_method': 'cloud_api',
        'whatsapp_api_token': 'test-access-token',
        'whatsapp_phone_number_id': '123456789',
    })

    assert response.status_code == 302
    with app.app_context():
        assert AutomationSettings.get().integration_method == 'qr_scan'


def test_cloud_queue_claim_returns_selected_transport_configuration(app, client):
    headers = bridge_headers(app)
    with app.app_context():
        settings = AutomationSettings.get()
        settings.integration_method = 'cloud_api'
        settings.whatsapp_api_token = 'worker-token'
        settings.whatsapp_phone_number_id = '123456789'
        settings.whatsapp_business_account_id = '987654321'
        item = MessageQueue(phone='923001234567', message='Cloud delivery', status='approved')
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    stale_transport = client.get('/api/whatsapp/pending?integration_method=qr_scan',
                                 headers=headers)
    assert stale_transport.status_code == 409
    with app.app_context():
        assert db.session.get(MessageQueue, item_id).status == 'approved'

    response = client.get('/api/whatsapp/pending?integration_method=cloud_api',
                          headers=headers)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['integration_method'] == 'cloud_api'
    assert payload['cloud_api']['access_token'] == 'worker-token'
    assert [queued['id'] for queued in payload['items']] == [item_id]


def test_class_broadcast_personalizes_message_for_each_student(admin_client, app, seed):
    response = admin_client.post('/automation', data={
        'action': 'queue_broadcast',
        'audience': 'class',
        'class_id': seed['class_id'],
        'due_date': '2026-10-20',
        'message': 'Hello {student_name}, {school_name} fee {fee_amount} is due {due_date}.',
    })

    assert response.status_code == 302
    with app.app_context():
        queued = MessageQueue.query.filter_by(trigger='custom_broadcast').all()
        assert len(queued) == 2
        texts = [item.message for item in queued]
        assert any('Ali Khan' in text and '2,500.00' in text for text in texts)
        assert any('Sara Ali' in text and '2,000.00' in text for text in texts)
        assert all('2026-10-20' in text for text in texts)
        assert all(item.status == 'pending' for item in queued)


def test_staff_broadcast_targets_active_staff_contacts(admin_client, app):
    with app.app_context():
        db.session.add(TeacherModel(
            teacher_id_str='T-AUTO-1', teacher_name='Nadia Teacher',
            qualification='B.Ed', contact_number='03001234567',
        ))
        db.session.commit()

    response = admin_client.post('/automation', data={
        'action': 'queue_broadcast',
        'audience': 'staff',
        'message': 'Hello {staff_name} from {school_name}.',
    })

    assert response.status_code == 302
    with app.app_context():
        item = MessageQueue.query.filter_by(trigger='custom_broadcast').one()
        assert item.phone == '923001234567'
        assert item.student_id is None
        assert 'Nadia Teacher' in item.message


def test_automation_page_renders_integration_panels_and_broadcast_builder(admin_client):
    response = admin_client.get('/automation')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'qr-integration-panel' in body
    assert 'cloud-api-config' in body
    assert 'broadcast-audience' in body
    assert 'message-placeholder' in body
    assert 'testMessageModal' in body


def test_automation_hides_inactive_integration_panel(admin_client, app):
    qr_page = admin_client.get('/automation').get_data(as_text=True)
    assert 'id="qr-integration-panel"' in qr_page
    assert 'id="cloud-api-config" class="border rounded p-3 mb-3" hidden' in qr_page

    with app.app_context():
        settings = AutomationSettings.get()
        settings.integration_method = 'cloud_api'
        settings.whatsapp_api_token = 'saved-token'
        settings.whatsapp_phone_number_id = '123456789'
        settings.whatsapp_business_account_id = '987654321'
        db.session.commit()

    cloud_page = admin_client.get('/automation').get_data(as_text=True)
    assert 'id="qr-integration-panel" hidden' in cloud_page
    assert 'id="qr-status-panel" hidden' in cloud_page
    assert 'id="cloud-api-config" class="border rounded p-3 mb-3" hidden' not in cloud_page


def test_queue_is_paginated_at_ten_items_and_search_keeps_queue_tab(admin_client, app):
    with app.app_context():
        db.session.add_all([
            MessageQueue(
                phone=f'92300000{index:04d}', message=f'Pagination item {index}',
                status='sent', trigger='custom_broadcast',
            )
            for index in range(23)
        ])
        db.session.commit()

    page = admin_client.get('/automation?tab=queue&page=2')
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'Page 2 of 3 · 23 message(s)' in body
    assert body.count('<tr>') == 11
    assert 'tab-pane fade show active' in body

    filtered = admin_client.get('/automation?tab=queue&search=Pagination%20item%2022&page=2')
    filtered_body = filtered.get_data(as_text=True)
    assert 'Page 1 of 1 · 1 message(s)' in filtered_body
    assert 'Pagination item 22' in filtered_body
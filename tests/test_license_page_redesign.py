"""Software License page redesign: one status band, plain 3-step renewal,
grouped features, folded technical details."""


def _page(client):
    return client.get('/license').get_data(as_text=True)


def test_page_has_plain_header_and_status_band(admin_client):
    body = _page(admin_client)
    assert 'Software License' in body
    assert 'lc-status' in body


def test_three_step_help_and_key_box(admin_client):
    body = _page(admin_client)
    assert "Copy this computer's code" in body
    assert 'name="license_key"' in body and 'name="license_file"' in body
    assert 'id="machineCode"' in body and 'id="copyMachineCode"' in body


def test_technical_details_are_folded_away(admin_client):
    body = _page(admin_client)
    if 'Licensed to' in body:      # only present once a license is active
        assert 'Technical details' in body
        assert 'Valid until' in body


def test_features_are_grouped(admin_client):
    body = _page(admin_client)
    if 'Included features' in body and 'lc-feat-grid' in body:
        assert 'lc-group' in body


def test_activate_form_still_posts_to_same_url(admin_client):
    bad = admin_client.post('/license', data={'license_key': 'not-a-key'})
    assert bad.status_code == 400


def test_urdu_labels_exist():
    from app.services.i18n_ur import UR
    for text in ('Software License', 'Valid until', 'Included features', 'Activate'):
        assert text in UR

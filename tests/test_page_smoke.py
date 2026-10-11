"""Smoke test: the four money-facing pages must render for an admin.

Guards against the paisa-migration class of regression (template errors,
missing imports, unconverted figures) reaching a rendered page.
"""

MARKERS = {
    '/': 'Dashboard',
    '/executive': 'Executive',
    '/reports': 'Reports',
    '/financials/summary': 'Financial',
}


def test_financial_pages_render_200_for_admin(admin_client):
    for url, marker in MARKERS.items():
        response = admin_client.get(url, follow_redirects=True)
        assert response.status_code == 200, '%s returned %s' % (url,
                                                                response.status_code)
        body = response.get_data(as_text=True)
        assert body.strip(), '%s rendered an empty page' % url
        assert marker.lower() in body.lower(), \
            '%s does not look like the expected page (missing %r)' % (url, marker)

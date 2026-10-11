"""Offline assets: every template uses vendored static files, never a CDN.

An offline school must get the fully styled UI from the local ``vendor/``
folder, so the tests assert both template hygiene (no external URLs) and that
the referenced files actually exist on disk.
"""

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / 'app' / 'templates'
STATIC = Path(__file__).resolve().parent.parent / 'app' / 'static'

EXTERNAL_SRC = re.compile(
    r'(?:src|href)=["\'](?:https?:)?//[^"\']+["\']', re.IGNORECASE)

#: Outbound links a user may deliberately click (not assets the UI loads).
ALLOWED_EXTERNAL_PREFIXES = ('https://wa.me/',)

# {{ url_for('static', filename='vendor/...') }} references in templates.
STATIC_REF = re.compile(
    r"url_for\(\s*'static'\s*,\s*filename='([^']+)'\s*\)")


def test_no_external_asset_urls_in_templates():
    offenders = []
    for template in TEMPLATES.rglob('*.html'):
        for match in EXTERNAL_SRC.finditer(template.read_text(encoding='utf-8')):
            url = match.group(0)
            if any(prefix in url for prefix in ALLOWED_EXTERNAL_PREFIXES):
                continue  # outbound deep link the user clicks, not a UI asset
            offenders.append(f'{template.name}: {url}')
    assert not offenders, 'external asset URLs found:\n' + '\n'.join(offenders)


def test_every_static_reference_resolves_to_a_real_file():
    missing = []
    for template in TEMPLATES.rglob('*.html'):
        text = template.read_text(encoding='utf-8')
        for relative_path in STATIC_REF.findall(text):
            if relative_path.startswith('vendor/'):
                if not (STATIC / relative_path).is_file():
                    missing.append(f'{template.name}: {relative_path}')
    assert not missing, 'vendored files missing:\n' + '\n'.join(missing)


def test_all_core_vendor_files_shipped():
    required = [
        'vendor/bootstrap/bootstrap.min.css',
        'vendor/bootstrap/bootstrap.bundle.min.js',
        'vendor/fontawesome/css/all.min.css',
        'vendor/fontawesome/webfonts/fa-solid-900.woff2',
        'vendor/fontawesome/webfonts/fa-regular-400.woff2',
        'vendor/fontawesome/webfonts/fa-brands-400.woff2',
        'vendor/jquery/jquery-3.7.0.min.js',
        'vendor/datatables/css/dataTables.bootstrap5.min.css',
        'vendor/datatables/js/jquery.dataTables.min.js',
        'vendor/datatables/js/dataTables.bootstrap5.min.js',
        'vendor/qrcodejs/qrcode.min.js',
        'vendor/chartjs/chart.umd.min.js',
    ]
    missing = [path for path in required if not (STATIC / path).is_file()]
    assert not missing, 'run tools/fetch_vendor_assets.py; missing:\n' + '\n'.join(missing)


def test_fontawesome_webfont_urls_resolve_locally():
    css = (STATIC / 'vendor' / 'fontawesome' / 'css' / 'all.min.css').read_text(
        encoding='utf-8')
    for match in set(re.findall(r'url\(\.\./webfonts/([^)]+)\)', css)):
        assert (STATIC / 'vendor' / 'fontawesome' / 'webfonts' / match).is_file(), \
            f'Font Awesome webfont missing: {match}'


def test_rendered_pages_reference_vendor_assets(admin_client):
    body = admin_client.get('/login').get_data(as_text=True)
    assert '/static/vendor/bootstrap/bootstrap.min.css' in body
    assert 'https://cdn.jsdelivr.net' not in body
    assert 'https://cdnjs.cloudflare.com' not in body

    home = admin_client.get('/').get_data(as_text=True)
    assert '/static/vendor/bootstrap/bootstrap.bundle.min.js' in home
    assert '/static/vendor/datatables/js/jquery.dataTables.min.js' in home
    assert 'code.jquery.com' not in home

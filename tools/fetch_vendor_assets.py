"""Download the frontend libraries used by the templates into app/static/vendor.

The product must work fully offline, so every CDN reference is replaced by a
local copy.  Run this once on a machine with internet access (or whenever a
library version is bumped); the downloaded files are committed with the
project and no download is needed at install time.

Usage:
    python tools/fetch_vendor_assets.py            # download anything missing
    python tools/fetch_vendor_assets.py --force    # re-download everything
"""

import sys
import urllib.request
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / 'app' / 'static' / 'vendor'

ASSETS = [
    # Bootstrap 5.3.0 (CSS + JS bundle with Popper)
    ('bootstrap/bootstrap.min.css',
     'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'),
    ('bootstrap/bootstrap.bundle.min.js',
     'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'),
    # Font Awesome 6.4.0 (CSS + every webfont the CSS references)
    ('fontawesome/css/all.min.css',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'),
    ('fontawesome/webfonts/fa-solid-900.woff2',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2'),
    ('fontawesome/webfonts/fa-solid-900.ttf',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.ttf'),
    ('fontawesome/webfonts/fa-regular-400.woff2',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-regular-400.woff2'),
    ('fontawesome/webfonts/fa-regular-400.ttf',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-regular-400.ttf'),
    ('fontawesome/webfonts/fa-brands-400.woff2',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-brands-400.woff2'),
    ('fontawesome/webfonts/fa-brands-400.ttf',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-brands-400.ttf'),
    ('fontawesome/webfonts/fa-v4compatibility.woff2',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-v4compatibility.woff2'),
    ('fontawesome/webfonts/fa-v4compatibility.ttf',
     'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-v4compatibility.ttf'),
    # jQuery 3.7.0
    ('jquery/jquery-3.7.0.min.js',
     'https://code.jquery.com/jquery-3.7.0.min.js'),
    # DataTables 1.13.6 (Bootstrap 5 styling)
    ('datatables/css/dataTables.bootstrap5.min.css',
     'https://cdn.datatables.net/1.13.6/css/dataTables.bootstrap5.min.css'),
    ('datatables/js/jquery.dataTables.min.js',
     'https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js'),
    ('datatables/js/dataTables.bootstrap5.min.js',
     'https://cdn.datatables.net/1.13.6/js/dataTables.bootstrap5.min.js'),
    # QR code generator (WhatsApp automation page)
    ('qrcodejs/qrcode.min.js',
     'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js'),
    # Chart.js 4.4.1 (dashboard charts)
    ('chartjs/chart.umd.min.js',
     'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'),
]


def fetch(relative_path, url, force=False):
    target = STATIC / relative_path
    if target.exists() and not force:
        return 'skip'
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (asset fetcher)'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data:
        raise RuntimeError(f'empty download: {url}')
    target.write_bytes(data)
    return f'downloaded {len(data):,} bytes'


def main(argv=None):
    force = '--force' in (argv or sys.argv[1:])
    failures = 0
    for relative_path, url in ASSETS:
        try:
            print(f'{fetch(relative_path, url, force):<28} {relative_path}')
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f'FAILED ({exc})                 {relative_path}')
    if failures:
        print(f'\n{failures} download(s) failed.')
        return 1
    print('\nAll vendor assets are in place (offline-ready).')
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""School Manager - Windows launcher (the double-click entry point).

Dual-launch modes:

* **Default - desktop window**: starts the local server, waits until it
  answers, then opens the app in its own standalone window (Edge/Chrome
  ``--app`` mode with a private profile - no tabs, no address bar, looks and
  behaves like a native desktop application).  Closing that window closes
  School Manager: the launcher terminates the background server gracefully.
* **--browser**: opens School Manager in a normal browser tab instead.
* **--selftest**: boots the server, probes the core routes over HTTP, prints
  ``VERIFY-PASS``/``VERIFY-FAIL`` and exits - used by the Phase 5 build to
  verify the bundled executable.

Running the launcher again while the app is already up simply opens another
window/tab - it never starts a second server.

Data location: see ``app/user_data.py`` - the database, logs, license files and
uploads all live in one folder (``%LOCALAPPDATA%\\SchoolManager`` for the
packaged product).
"""

import argparse
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path
from urllib.error import URLError

HOST = '127.0.0.1'
READINESS_TIMEOUT_SECONDS = 60
LOG_FILE_NAME = 'school_manager.log'

#: Chromium browsers that support ``--app`` standalone windows, best first.
_BROWSER_CANDIDATES = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
]


def _log(message):
    """Print when a console exists; never crash the windowed exe."""
    try:
        print(message, flush=True)
    except (OSError, ValueError, AttributeError):
        pass


def _port_in_use(port, host=HOST):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def _app_ready(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (URLError, OSError):
        return False


def _first_free_port(start):
    """Next port at or after ``start`` that nothing is listening on."""
    port = max(1, int(start))
    for _ in range(50):
        if not _port_in_use(port):
            return port
        port += 1
    raise RuntimeError('No free port found near %s.' % start)


def find_chromium_browser():
    """Path to a Chromium browser able to run ``--app`` windows, or ``None``."""
    for candidate in _BROWSER_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    for name in ('msedge', 'chrome'):
        found = shutil.which(name)
        if found:
            return found
    return None


def _open_app_window(browser_path, url, profile_dir):
    """Open ``url`` as a standalone desktop window; return the process."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        browser_path,
        f'--app={url}',
        f'--user-data-dir={profile_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        '--window-size=1280,900',
    ]
    return subprocess.Popen(command)


def _open_browser_when_ready(launch, port, app, profile_dir):
    """Wait for readiness, then open the window/tab and monitor it.

    Closing the standalone window terminates School Manager gracefully; a
    normal browser tab stays open on its own.
    """
    url = f'http://{HOST}:{port}/'
    deadline = time.time() + READINESS_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _app_ready(f'http://{HOST}:{port}/healthz'):
            break
        time.sleep(0.25)
    else:
        _log(f'Server did not become ready at {url} within '
             f'{READINESS_TIMEOUT_SECONDS}s.')
        return

    if launch == 'window':
        browser = find_chromium_browser()
        if browser is None:
            _log('No Edge/Chrome found for desktop-window mode; opening a '
                 'browser tab instead.')
            webbrowser.open(url)
            return
        process = _open_app_window(browser, url, profile_dir)
        _log('Desktop window opened. Closing it exits School Manager.')
        process.wait()  # the window was closed by the user
        from app.graceful_exit import request_shutdown
        _log('Desktop window closed - shutting down the background server.')
        request_shutdown(app)
    else:
        webbrowser.open(url)


def _serve_with_waitress(app, host, port):
    # create_server (instead of serve) lets the /shutdown route stop the
    # accept loop cleanly, so the whole process exits gracefully.
    from waitress import create_server
    from app.graceful_exit import register_shutdown_handle

    _log(f'School Manager running at http://{host}:{port}/ (Ctrl+C to stop)')
    server = create_server(app, host=host, port=port, threads=8,
                           ident='SchoolManager')
    register_shutdown_handle(app, server)
    server.run()


def _serve_with_werkzeug(app, host, port):
    _log('School Manager running at http://%s:%s/ (waitress not installed, '
         'using the Flask development server)' % (host, port))
    app.run(host=host, port=port, debug=False, use_reloader=False)


def _redirect_streams_to_log(data_dir):
    """A windowed (.pyw / PyInstaller) exe has no stdout/stderr.

    Point them - and the application log - at a file inside the data folder
    BEFORE anything prints (config warnings, schema migrations, ...).  Must be
    called as early as possible so a boot failure leaves a diagnosable log.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / LOG_FILE_NAME
    if getattr(sys, 'stdout', None) is None or getattr(sys, 'stderr', None) is None:
        stream = open(log_path, 'a', buffering=1, encoding='utf-8')
        sys.stdout = stream
        sys.stderr = stream
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        handlers=[logging.FileHandler(log_path, encoding='utf-8')],
        force=True,
    )
    logging.getLogger('school_manager').info('Launcher starting (frozen=%s)',
                                             bool(getattr(sys, 'frozen', False)))
    return log_path


def _selftest(port, data_dir):
    """Bundled-exe smoke test: boot, probe core routes + bundled bridge, exit."""
    checks = {
        'healthz': f'http://{HOST}:{port}/healthz',
        'login': f'http://{HOST}:{port}/login',
        'vendor_css': f'http://{HOST}:{port}/static/vendor/bootstrap/bootstrap.min.css',
    }
    results = {}
    for name, url in checks.items():
        deadline = time.time() + READINESS_TIMEOUT_SECONDS
        results[name] = 'FAIL'
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    results[name] = response.status
                break
            except (URLError, OSError):
                time.sleep(0.25)
    # Licensing: a fresh install must be gated to the license page, and the
    # root must redirect there (enforcement is always on in the packaged exe).
    import http.client
    try:
        connection = http.client.HTTPConnection(HOST, port, timeout=3)
        connection.request('GET', '/')
        response = connection.getresponse()
        results['license_gate'] = ('302->' + response.getheader('Location', '')
                                   if response.status == 302 else response.status)
    except (URLError, OSError):
        results['license_gate'] = 'FAIL'

    # Bundled WhatsApp bridge: must be found (absolute paths from the install
    # directory), start, and answer its health endpoint.
    from pathlib import Path

    from app.services import whatsapp_bridge
    if whatsapp_bridge.is_installed():
        bridge = whatsapp_bridge.launch_bridge(Path(data_dir) / 'whatsapp-session',
                                               os.environ.get('WHATSAPP_BRIDGE_TOKEN', ''))
        if bridge is None:
            results['bridge'] = 'FAIL (no node runtime)'
        else:
            bridge_ok = False
            for _ in range(60):
                if bridge.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen('http://127.0.0.1:3001/health',
                                                timeout=2) as response:
                        if response.status == 200:
                            bridge_ok = True
                        break
                except (URLError, OSError):
                    time.sleep(0.5)
            results['bridge'] = 200 if bridge_ok else 'FAIL'
            bridge.terminate()
            try:
                bridge.wait(timeout=10)
            except Exception:
                bridge.kill()
    else:
        results['bridge'] = 'not installed'

    _log('SELFTEST-RESULTS: %r' % results)
    core_ok = all(value == 200 for key, value in results.items()
                  if key not in ('license_gate', 'bridge'))
    gate = results.get('license_gate', '')
    gate_ok = isinstance(gate, str) and gate.startswith('302->/license')
    bridge_ok = results.get('bridge') in (200, 'not installed')
    print('VERIFY-PASS' if core_ok and gate_ok and bridge_ok else 'VERIFY-FAIL',
          flush=True)
    sys.stdout.flush()
    os._exit(0 if core_ok and gate_ok and bridge_ok else 1)


def build_arg_parser():
    """Launcher CLI: default = desktop window; --browser = normal tab."""
    parser = argparse.ArgumentParser(description='School Manager launcher')
    parser.add_argument('--browser', action='store_true',
                        help='open in a normal browser tab instead of an '
                             'app window')
    parser.add_argument('--selftest', action='store_true',
                        help='boot the server, probe core routes, exit')
    return parser


def _new_bridge_token():
    import secrets
    return secrets.token_urlsafe(32)


def _start_core_bridge(app):
    """Start the bundled WhatsApp bridge (a mandatory core component).

    Its WhatsApp session lives in the data folder so updates and reinstalls
    never require re-pairing the school phone.  The process is terminated
    during the graceful shutdown sequence.
    """
    from pathlib import Path

    from app.services import whatsapp_bridge
    from app.graceful_exit import register_cleanup

    if not whatsapp_bridge.is_installed():
        _log('WhatsApp bridge not found next to the app - notifications '
             'disabled for this run.')
        return
    if _app_ready('http://127.0.0.1:3001/health'):
        _log('WhatsApp bridge already running on port 3001 - reusing it.')
        return

    session_dir = Path(app.config['DATA_DIR']) / 'whatsapp-session'
    token = os.environ.get('WHATSAPP_BRIDGE_TOKEN') or ''
    process = whatsapp_bridge.launch_bridge(session_dir, token)
    if process is None:
        _log('Could not start the WhatsApp bridge (missing Node runtime?).')
        return
    _log('WhatsApp bridge started (PID %s).' % process.pid)
    register_cleanup(process.terminate)


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    # Windowed exes have no console: start logging to the data folder FIRST,
    # so a boot failure is always diagnosable from school_manager.log.
    from app.user_data import data_root
    _redirect_streams_to_log(data_root())
    logging.getLogger('school_manager').info('Launch mode: %s',
                                             'selftest' if args.selftest
                                             else ('browser' if args.browser
                                                   else 'window'))

    # The bridge authenticates to the app with this token; a fresh one per
    # launch keeps the pair private to this process family.
    os.environ.setdefault('WHATSAPP_BRIDGE_TOKEN', _new_bridge_token())

    from app.config import get_config
    config = get_config()
    port = int(config.get('PORT') or 8000)

    # Already running? Just bring the window/tab up and exit.
    if _app_ready(f'http://{HOST}:{port}/healthz'):
        if args.selftest:
            print('VERIFY-PASS', flush=True)   # an instance is already serving
            return 0
        _open_running_instance_window(port, args.browser)
        return 0

    if _port_in_use(port):
        port = _first_free_port(port + 1)

    from app import create_app
    app = create_app()

    if not args.selftest:
        _start_core_bridge(app)

    if args.selftest:
        from waitress import create_server
        server = create_server(app, host=HOST, port=port, threads=4)
        threading.Thread(target=_selftest, args=(port, config['DATA_DIR']),
                         daemon=True).start()
        server.run()
        return 0

    profile_dir = data_root() / 'browser-profile'
    threading.Thread(target=_open_browser_when_ready,
                     args=('browser' if args.browser else 'window', port,
                           app, profile_dir),
                     daemon=True).start()

    try:
        _serve_with_waitress(app, HOST, port)
    except ImportError:
        _serve_with_werkzeug(app, HOST, port)
    return 0


def _open_running_instance_window(port, browser_mode):
    url = f'http://{HOST}:{port}/'
    if browser_mode:
        webbrowser.open(url)
        return
    browser = find_chromium_browser()
    if browser is None:
        webbrowser.open(url)
        return
    from app.user_data import data_root
    _open_app_window(browser, url, data_root() / 'browser-profile')


def _fatal_box(message):
    """Best-effort visible error for a silent (.pyw) launch."""
    _log(message)
    try:
        import tkinter.messagebox
        tkinter.messagebox.showerror('School Manager', message)
    except Exception:  # noqa: BLE001 - no GUI available; nothing more we can do
        pass


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a silent launcher must show why it died
        _fatal_box('School Manager failed to start:\n\n' + traceback.format_exc())
        sys.exit(1)

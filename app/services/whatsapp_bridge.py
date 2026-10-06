"""WhatsApp bridge presence detection.

The bridge ships as a mandatory core component of the Windows installer; these
detection helpers let the app tell "running" from "broken/missing" so problems
are explainable instead of silent.

The Node service (``whatsapp-service/``) is what actually talks to WhatsApp.
The application must never depend on it: without the bridge the rest of the
product works normally, queued messages simply wait, and the automation page
explains what is missing.  This module answers three questions in one place:

* **Installed?**  Does a bridge directory with ``package.json``/``server.js``
  exist (and does it carry its own ``node_modules``)?
* **Runnable?**  Is a Node runtime available (``node`` on PATH or an explicit
  ``WHATSAPP_NODE_PATH``)?
* **Reachable?**  Does the HTTP health endpoint answer?

The overall :func:`install_state` combines them:

========================  ====================================================
State                     Meaning
========================  ====================================================
``not_installed``         No bridge folder - the product runs without it.
``node_missing``          Bridge folder present but no Node runtime to run it.
``installed_stopped``     Bridge installed but its health endpoint is silent.
``running_unpaired``      Bridge process up, WhatsApp not paired yet (QR due).
``ready``                 Bridge up and WhatsApp connected.
========================  ====================================================

The installer (Phase 6) ships the bridge - together with a private Node
runtime - as an optional component, and sets ``WHATSAPP_BRIDGE_DIR`` if it
lands anywhere other than the default location next to the program.
"""

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import requests

from app.user_data import BASE_DIR

HEALTH_TIMEOUT_SECONDS = 3

#: Values returned by :func:`install_state`.
STATE_NOT_INSTALLED = 'not_installed'
STATE_NODE_MISSING = 'node_missing'
STATE_INSTALLED_STOPPED = 'installed_stopped'
STATE_RUNNING_UNPAIRED = 'running_unpaired'
STATE_READY = 'ready'

_STATE_HINTS = {
    STATE_NOT_INSTALLED:
        'The WhatsApp component is missing on this computer. Everything else '
        'keeps working; queued messages will wait here until School Manager is '
        'reinstalled with the WhatsApp component.',
    STATE_NODE_MISSING:
        'The WhatsApp bridge is installed, but no Node.js runtime was found on '
        'this computer. Install the WhatsApp component again (it bundles its own '
        'Node runtime) to enable sending.',
    STATE_INSTALLED_STOPPED:
        'The WhatsApp bridge is installed but not running. Start it (or restart '
        'the app with the WhatsApp component enabled) to send queued messages.',
    STATE_RUNNING_UNPAIRED:
        'The WhatsApp bridge is running - scan the QR code below to pair the '
        'school phone.',
    STATE_READY:
        'WhatsApp bridge is running and the school phone is paired.',
}


def _service_url():
    """Base URL of the bridge's HTTP API."""
    configured = (os.environ.get('WHATSAPP_NODE_URL')
                  or _config_value('WHATSAPP_NODE_URL')
                  or 'http://127.0.0.1:3001')
    return configured.rstrip('/')


def bridge_dir():
    """Folder the bridge lives in (``WHATSAPP_BRIDGE_DIR`` overrides the default)."""
    configured = (os.environ.get('WHATSAPP_BRIDGE_DIR')
                  or _config_value('WHATSAPP_BRIDGE_DIR'))
    if configured:
        return Path(configured)
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'whatsapp-service'
    return BASE_DIR / 'whatsapp-service'


def _config_value(key):
    try:
        from flask import current_app
        return current_app.config.get(key)
    except RuntimeError:  # outside an application context
        return None


def node_runtime_path():
    """Path to a usable ``node`` executable, or ``None``.

    The installer bundles a private Node runtime as
    ``<bridge dir>/node.exe`` — preferred over a system-wide installation.
    """
    bundled = bridge_dir() / 'node.exe'
    if bundled.is_file():
        return bundled
    explicit = (os.environ.get('WHATSAPP_NODE_PATH')
                or _config_value('WHATSAPP_NODE_PATH'))
    if explicit and Path(explicit).exists():
        return Path(explicit)
    return shutil.which('node')


def launch_bridge(session_dir, token, port=3001):
    """Start the bundled bridge as a subprocess (the product ships it as a
    mandatory core component — see installer/SchoolManager.iss).

    Returns the ``Popen`` handle, or ``None`` when the bridge is not installed,
    no Node runtime is available, or the port is already serving (then the
    running bridge is assumed to be ours).  The caller owns the process and
    must terminate it on shutdown (``graceful_exit.register_cleanup``).
    """
    import subprocess as _subprocess

    if not is_installed():
        return None
    node = node_runtime_path()
    if node is None:
        return None

    env = dict(os.environ)
    env['SESSION_PATH'] = str(session_dir)
    env['APP_PORT'] = str(port)
    if token:
        env['WHATSAPP_BRIDGE_TOKEN'] = token
    try:
        return _subprocess.Popen(
            [str(node), str(bridge_dir() / 'server.js')],
            cwd=str(bridge_dir()), env=env,
            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL,
            creationflags=_subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return None


@lru_cache(maxsize=8)
def _node_version_cached(node_path, mtime):
    try:
        result = subprocess.run([str(node_path), '--version'],
                                capture_output=True, text=True, timeout=10)
        return (result.stdout or '').strip() or 'unknown'
    except Exception:  # noqa: BLE001 - any failure means "runtime unusable"
        return None


def node_version():
    """``'v20.11.0'``-style version string, or ``None`` when Node is unusable."""
    node_path = node_runtime_path()
    if not node_path:
        return None
    marker = Path(node_path)
    try:
        mtime = marker.stat().st_mtime
    except OSError:
        return None
    return _node_version_cached(str(node_path), mtime)


def is_installed():
    """True when a bridge folder with the entry points exists."""
    directory = bridge_dir()
    return (directory / 'package.json').is_file() and (directory / 'server.js').is_file()


def is_fully_installed():
    """True when the bridge folder also carries its ``node_modules``."""
    return is_installed() and (bridge_dir() / 'node_modules').is_dir()


def health():
    """Bridge HTTP health payload (``serviceReachable`` False when silent).

    Never raises: every failure mode degrades to an unreachable report so
    callers can treat "bridge problems" as a normal state, not an error.
    """
    url = _service_url()
    try:
        response = requests.get(f'{url}/health', timeout=HEALTH_TIMEOUT_SECONDS)
    except requests.RequestException:
        return {'ok': False, 'connected': False, 'serviceReachable': False,
                'phonePaired': False, 'messageSent': False, 'status': 'offline',
                'message': 'WhatsApp service unavailable'}

    try:
        data = response.json() if response.headers.get('content-type', '').startswith(
            'application/json') else {}
    except ValueError:
        data = {}
    if not response.ok:
        return {'ok': False, 'connected': False, 'serviceReachable': False,
                'phonePaired': False, 'messageSent': False, 'status': 'offline',
                'message': 'WhatsApp service unavailable'}
    data.setdefault('serviceReachable', True)
    data.setdefault('phonePaired', bool(data.get('connected')))
    data.setdefault('messageSent', bool(data.get('messageSent')))
    if not data.get('message'):
        if data.get('lastError'):
            data['message'] = data['lastError']
        else:
            data['message'] = ('WhatsApp service is running.' if data.get('connected')
                               else 'Waiting for WhatsApp to connect.')
    return data


def install_state(health_payload=None):
    """Combine filesystem + runtime + health checks into one state label."""
    payload = health_payload if health_payload is not None else health()
    if payload.get('serviceReachable'):
        return STATE_READY if payload.get('connected') else STATE_RUNNING_UNPAIRED
    if not is_installed():
        return STATE_NOT_INSTALLED
    if node_runtime_path() is None:
        return STATE_NODE_MISSING
    return STATE_INSTALLED_STOPPED


def state_hint(state):
    """Human-readable explanation for an install state."""
    return _STATE_HINTS.get(state, '')


def install_summary(health_payload=None):
    """Everything the automation page needs about the optional bridge."""
    directory = bridge_dir()
    payload = health_payload if health_payload is not None else health()
    state = install_state(payload)
    return {
        'install_state': state,
        'hint': state_hint(state),
        'bridge_dir': str(directory),
        'installed': is_installed(),
        'node_modules_present': is_fully_installed(),
        'node_path': str(node_runtime_path()) if node_runtime_path() else None,
        'node_version': node_version(),
        'service_url': None,  # filled in by callers that know the URL
    }

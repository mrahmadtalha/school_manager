import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error


ROOT = Path(__file__).resolve().parent
FLASK_SCRIPT = ROOT / 'run.py'
NODE_SERVICE_DIR = ROOT / 'whatsapp-service'
NODE_SERVICE_SCRIPT = NODE_SERVICE_DIR / 'server.js'
SESSION_DIR = NODE_SERVICE_DIR / 'session'
FLASK_HEALTH_URL = 'http://127.0.0.1:5000/login'


def start_process(name, command, cwd):
    print(f"Starting {name} in {cwd}")
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0),
    )


def validate_required_environment():
    missing = []
    if not os.environ.get('SECRET_KEY'):
        missing.append('SECRET_KEY')

    if missing:
        print('Missing required environment variables: ' + ', '.join(missing))
        print('For local development, run:')
        print('set SECRET_KEY=your-local-secret')
        print('or in PowerShell: $env:SECRET_KEY="your-local-secret"')
        return False
    return True


def wait_for_flask_ready(timeout_seconds=30):
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(FLASK_HEALTH_URL, timeout=2) as response:
                if response.status < 500:
                    print('Flask is ready on http://127.0.0.1:5000')
                    return True
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    print(f'Flask did not become ready in time: {last_error}')
    return False


def is_port_in_use(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


def find_pids_using_port(port):
    try:
        output = subprocess.check_output(['netstat', '-ano', '-p', 'tcp'], text=True, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    pids = set()
    for line in output.splitlines():
        if str(port) not in line:
            continue
        parts = line.split()
        if len(parts) >= 5 and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return sorted(pids)


def clear_stale_port(port):
    pids = find_pids_using_port(port)
    if not pids:
        return False

    print(f'Port {port} is already in use by PID(s): {pids}. Clearing stale service...')
    for pid in pids:
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(pid), '/F'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception as exc:
            print(f'Could not stop PID {pid}: {exc}')

    deadline = time.time() + 10
    while time.time() < deadline:
        if not is_port_in_use(port):
            print(f'Port {port} is free again.')
            return True
        time.sleep(0.5)

    print(f'Port {port} still appears to be in use after cleanup.')
    return False


def terminate_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        process.terminate()
    else:
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def clear_stale_whatsapp_session(force=False):
    """Reset the WhatsApp session folder.

    IMPORTANT: this must only ever run when explicitly requested (force=True,
    driven by --reset-whatsapp-session). A saved session — creds.json,
    pre-key-*.json — is normal evidence of a SUCCESSFUL pairing, not
    corruption. Wiping it automatically just because those files exist
    deletes a working login every time this script starts, forcing a fresh
    QR scan on every launch. Genuine corruption detection already happens
    inside server.js itself, once, at Node process boot.
    """
    if not force:
        return False
    if not SESSION_DIR.exists():
        return False
    print('Resetting WhatsApp session folder (explicitly requested via --reset-whatsapp-session)...')
    shutil.rmtree(SESSION_DIR, ignore_errors=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description='Run the Flask app and WhatsApp service together.')
    parser.add_argument('--flask-only', action='store_true', help='Start only Flask app')
    parser.add_argument('--node-only', action='store_true', help='Start only WhatsApp service')
    parser.add_argument('--reset-whatsapp-session', action='store_true', help='Delete stale WhatsApp auth/session data before startup')
    args = parser.parse_args()

    processes = []
    flask_proc = None
    node_proc = None

    try:
        if not validate_required_environment():
            raise RuntimeError('Missing required environment configuration. See the instructions above.')

        if not args.node_only:
            flask_proc = start_process('Flask', [sys.executable, str(FLASK_SCRIPT)], ROOT)
            processes.append(('Flask', flask_proc))
            if not wait_for_flask_ready():
                raise RuntimeError('Flask failed to start correctly.')

        if not args.flask_only:
            if is_port_in_use(3001):
                clear_stale_port(3001)
            clear_stale_whatsapp_session(force=args.reset_whatsapp_session)
            node_proc = start_process('WhatsApp', ['node', str(NODE_SERVICE_SCRIPT)], NODE_SERVICE_DIR)
            processes.append(('WhatsApp', node_proc))

        for name, proc in processes:
            if proc.poll() is None:
                print(f"{name} process started with PID {proc.pid}")

        while True:
            time.sleep(1)
            if flask_proc is not None and flask_proc.poll() is not None:
                print(f"Flask exited with code {flask_proc.returncode}; restarting it...")
                flask_proc = start_process('Flask', [sys.executable, str(FLASK_SCRIPT)], ROOT)
                processes[0] = ('Flask', flask_proc)
            if node_proc is not None and node_proc.poll() is not None:
                print(f"WhatsApp exited with code {node_proc.returncode}; restarting it...")
                if is_port_in_use(3001):
                    clear_stale_port(3001)
                node_proc = start_process('WhatsApp', ['node', str(NODE_SERVICE_SCRIPT)], NODE_SERVICE_DIR)
                processes[-1] = ('WhatsApp', node_proc)
    except (KeyboardInterrupt, RuntimeError) as exc:
        if isinstance(exc, RuntimeError):
            print(f'Startup error: {exc}')
        print('\nStopping services...')
    finally:
        for _, proc in processes:
            terminate_process(proc)


if __name__ == '__main__':
    main()
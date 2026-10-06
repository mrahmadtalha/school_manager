"""Graceful shutdown of the local server process (the "Exit Software" action).

School Manager runs as a local server started by ``school_manager.pyw``.  When
an administrator confirms exit in the UI, ``POST /shutdown`` renders a goodbye
page and schedules the process to stop a moment later — after the response has
been delivered.

Two stop strategies, in order of preference:

1. **Waitress handle** (the product launcher registers its server object via
   :func:`register_shutdown_handle`): ``server.close()`` makes the accept loop
   return and the launcher process exits normally — browsers, sessions and the
   SQLite database are all closed cleanly.
2. **Forced exit** (fallback when no handle exists, e.g. the development
   ``run.py``): the database is committed, then ``os._exit(0)`` stops the
   process.  All data is committed first, so nothing is lost.

Under pytest (``app.config['TESTING']``) the exit is only *recorded*, never
performed, so the test suite can exercise the route without killing itself.
"""

import os
import threading
import time

EXIT_DELAY_SECONDS = 1.0

#: Callbacks run just before the process stops (e.g. terminating the bundled
#: WhatsApp bridge subprocess).  Registered by the launcher.
_cleanups = []
_cleanups_lock = threading.Lock()


def register_cleanup(callback):
    """Run ``callback()`` during the graceful shutdown sequence."""
    with _cleanups_lock:
        _cleanups.append(callback)


def register_shutdown_handle(app, server):
    """Let the shutdown route stop ``server`` (a waitress ``create_server``)."""
    app.extensions['shutdown_handle'] = server


def _perform_exit(app):
    handle = app.extensions.get('shutdown_handle')
    try:  # flush any pending session state before stopping
        from app.database import db
        db.session.commit()
    except Exception:  # noqa: BLE001 - nothing more can be done at exit
        pass
    with _cleanups_lock:
        cleanups = list(_cleanups)
    for cleanup in cleanups:  # e.g. terminate the bundled WhatsApp bridge
        try:
            cleanup()
        except Exception:
            pass
    if handle is not None:
        try:
            handle.close()          # waitress: run() returns, process exits
            return
        except Exception:
            pass
    os._exit(0)                     # development fallback: data already committed


def _shutdown_worker(app):
    if app.config.get('TESTING'):
        app.extensions['shutdown_requested'] = True
        return
    time.sleep(EXIT_DELAY_SECONDS)  # let the goodbye response reach the browser
    _perform_exit(app)


def request_shutdown(app):
    """Schedule the process to stop shortly after the current response."""
    app.extensions['shutdown_requested'] = True
    if app.config.get('TESTING'):
        return
    threading.Thread(target=_shutdown_worker, args=(app,),
                     name='school-manager-exit', daemon=True).start()

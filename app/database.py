"""Shared SQLAlchemy instance plus the session-scoping fix.

Flask-SQLAlchemy 3.1 scopes its session registry on ``id()`` of the current
app-context object (``session.py: _app_ctx_id``).  ``id()`` values are memory
addresses: once a popped context has been garbage-collected, a later context
can land on the same address and inherit the surviving registry entry — with
its stale identity-map state — from the previous context.  That bleed was
observed as pages rendering pre-commit data (the WhatsApp automation flake).

Keying the registry on the app-context OBJECT itself keeps a strong reference
in the registry until ``session.remove()`` runs at that context's teardown,
so an address can never be recycled while a session is still registered, and
a stale session can never be reached from a different context.
"""
from flask.globals import app_ctx
from flask_sqlalchemy import SQLAlchemy


def _app_context_scope():
    """Registry key for the scoped session: the app-context object itself."""
    return app_ctx._get_current_object()


db = SQLAlchemy(session_options={'scopefunc': _app_context_scope})

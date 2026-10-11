"""The scoped-session registry must key on the app-context OBJECT.

Regression guard for the WhatsApp automation flake: Flask-SQLAlchemy 3.1's
default scope is ``id(app_ctx)`` — a popped context's memory address can be
recycled by a later context, which would inherit a surviving session (and its
stale identity map).  ``app/database.py`` keys on the object itself, so a
surviving session is unreachable from any other context.
"""

from flask.globals import app_ctx

from app.database import _app_context_scope, db


def test_scope_key_is_the_app_context_object(app):
    with app.app_context():
        key = _app_context_scope()
        assert key is app_ctx._get_current_object()
        assert _app_context_scope() is key          # stable within a context

    with app.app_context():
        assert _app_context_scope() is not key      # a new context, a new key


def test_each_context_gets_its_own_session(app):
    with app.app_context() as first:
        first_session = db.session()
        assert db.session() is first_session        # same context -> same session

    with app.app_context() as second:
        second_session = db.session()
        assert second_session is not first_session
        assert _app_context_scope() is not first


def test_surviving_session_cannot_leak_across_contexts(app):
    with app.app_context():
        stale = db.session()
        stale_key = _app_context_scope()

    # Teardown removed the entry; plant it back to simulate a teardown that
    # failed to clean up.  Under the old id()-based scope a later context could
    # land on the same key and inherit ``stale``; with the object key it cannot.
    db.session.registry.registry[stale_key] = stale

    with app.app_context():
        fresh = db.session()
        assert fresh is not stale
        assert _app_context_scope() is not stale_key

    # A context entered twice (e.g. nested re-entry) still resolves to its own
    # session object, and the planted entry stayed quarantined.
    assert db.session.registry.registry.get(stale_key) is stale

    db.session.registry.registry.pop(stale_key, None)
    db.session.registry.registry.pop(_app_context_scope(), None)

"""Offline assistant for administrators (no AI service, no internet).

Two read-only GET endpoints:

* ``/assistant``      the chat page
* ``/assistant/ask``  JSON answer for ``?q=<question>`` (optionally
  ``&c=<context>``, the small memory the previous answer carried, so short
  follow-ups such as "aur kal?" work)

The questions are answered by ``app/services/assistant.py`` from the school's
own data.  Nothing here writes to the database.  GET is used on purpose so the
assistant keeps working when the license is read-only (see license_guard.py).
"""
import json

from flask import jsonify, render_template, request

from app.models import ROLE_ADMIN
from app.routes import main
from app.security import role_required
from app.services import assistant as assistant_service
from app.services import assistant_intents


@main.app_context_processor
def _assistant_widget_context():
    """What the floating assistant button (base.html) needs on every page."""
    return {'assistant_starters': assistant_intents.STARTER_QUESTIONS[:4],
            'assistant_max_length': assistant_service.MAX_QUESTION_LENGTH}


def _read_context():
    """The follow-up memory from ``?c=``; anything malformed is ignored."""
    raw = request.args.get('c') or ''
    if not raw or len(raw) > assistant_service.MAX_CONTEXT_LENGTH:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


@main.route('/assistant')
@role_required(ROLE_ADMIN)
def assistant_page():
    return render_template('assistant.html',
                           starters=assistant_intents.STARTER_QUESTIONS,
                           max_length=assistant_service.MAX_QUESTION_LENGTH)


@main.route('/assistant/ask')
@role_required(ROLE_ADMIN)
def assistant_ask():
    question = (request.args.get('q') or '').strip()
    result = assistant_service.answer(question, context=_read_context())
    response = jsonify(dict(result, ok=True))
    response.headers['Cache-Control'] = 'no-store'
    return response

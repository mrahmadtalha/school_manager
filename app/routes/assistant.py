"""Offline assistant for administrators (no AI service, no internet).

Two read-only GET endpoints:

* ``/assistant``      the chat page
* ``/assistant/ask``  JSON answer for ``?q=<question>``

The questions are answered by ``app/services/assistant.py`` from the school's
own data.  Nothing here writes to the database.  GET is used on purpose so the
assistant keeps working when the license is read-only (see license_guard.py).
"""
from flask import jsonify, render_template, request

from app.models import ROLE_ADMIN
from app.routes import main
from app.security import role_required
from app.services import assistant as assistant_service
from app.services import assistant_intents


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
    result = assistant_service.answer(question)
    response = jsonify(dict(result, ok=True))
    response.headers['Cache-Control'] = 'no-store'
    return response

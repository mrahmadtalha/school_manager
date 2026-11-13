"""Shared reply helpers: rupee formatting, links, the reply envelope and period labels."""

import json

from flask import url_for

from werkzeug.routing import BuildError
from app.services.payroll_service import month_label


def rs(value):
    return 'Rs {:,.0f}'.format(value or 0)


def _link(label, endpoint, **values):
    try:
        return {'label': label, 'url': url_for(endpoint, **values)}
    except BuildError:
        return None


def _links(*items):
    return [item for item in items if item]


def _reply(intent, text, *, table=None, links=None, suggestions=None):
    return {
        'intent': intent,
        'answer': text,
        'table': table,
        'links': links or [],
        'suggestions': suggestions or [],
    }


def _with_context(reply, context):
    reply['context'] = context
    return reply


def _period_label(ctx):
    return month_label(ctx.month)


def _json_list(value):
    try:
        data = json.loads(value or '[]')
    except (TypeError, ValueError):
        return []
    return [str(item) for item in data] if isinstance(data, list) else []

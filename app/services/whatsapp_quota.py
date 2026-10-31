"""WhatsApp message caps taken from the license (protects the school's number).

Sending too many WhatsApp messages too fast is the quickest way to get a
number banned, so each license carries a **daily** and a **monthly** cap
(``wa_daily`` / ``wa_monthly``).  A missing cap means unlimited (legacy keys).

How it is enforced
------------------
* Messages beyond the cap are never handed to the WhatsApp bridge.  They stay
  in the queue (nothing is lost) and go out automatically once the next day or
  month starts.
* Usage is the larger of two independent counts: the messages the queue shows
  as sent, and a small signed counter file.  Deleting queue rows does not reset
  it, and neither does deleting the counter file.
* Messages already handed to the bridge but not yet confirmed ("in flight")
  are reserved against the cap, so a burst cannot overshoot it.
* "Today" never moves backwards: the counter remembers the latest date it has
  seen, so setting the Windows clock back does not hand out a fresh quota.

Like the rest of licensing this is a deterrent, not DRM.
"""

import hashlib
import hmac
import json
import os
from datetime import date, datetime, time as dtime, timedelta, timezone
from app.timeutil import utcnow
from pathlib import Path

from sqlalchemy import func

from app.services.licensing import LIMIT_WA_DAILY, LIMIT_WA_MONTHLY, normalize_machine_code

USAGE_FILE = 'whatsapp_usage.state'
FEATURE_KEY = 'whatsapp'
IN_FLIGHT_MAX_AGE = timedelta(minutes=30)     # older "sending" rows are stale
KEEP_DAYS = 70
KEEP_MONTHS = 14


def _manager():
    from app.license_guard import get_manager
    return get_manager()


# -- signed counter file -------------------------------------------------

def _path():
    # Next to license.key/license.state, so it follows the school's data folder.
    return Path(_manager().state_path).parent / USAGE_FILE


def _key():
    machine = normalize_machine_code(_manager().machine_code())
    return hashlib.sha256(f'sm-wa-usage-v1|{machine}'.encode()).digest()


def _sign(seen, days, months):
    body = json.dumps({'s': seen, 'd': days, 'm': months}, sort_keys=True,
                      separators=(',', ':')).encode()
    return hmac.new(_key(), body, hashlib.sha256).hexdigest()


def _load():
    """The counter state; a missing or tampered file reads as empty."""
    empty = {'seen': None, 'days': {}, 'months': {}}
    try:
        data = json.loads(_path().read_text(encoding='utf-8'))
        seen, days, months = data.get('s'), dict(data.get('d') or {}), dict(data.get('m') or {})
        if hmac.compare_digest(_sign(seen, days, months), data.get('sig', '')):
            return {'seen': seen, 'days': days, 'months': months}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return empty


def _save(state):
    days = dict(sorted(state['days'].items())[-KEEP_DAYS:])
    months = dict(sorted(state['months'].items())[-KEEP_MONTHS:])
    body = {'s': state['seen'], 'd': days, 'm': months,
            'sig': _sign(state['seen'], days, months)}
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(body), encoding='utf-8')
        os.replace(tmp, path)
    except OSError:
        pass        # an unwritable folder must not stop the app (the queue still counts)


def _effective_today(state, today=None):
    """Local date, but never earlier than the latest date already seen."""
    today = today or date.today()
    try:
        seen = date.fromisoformat(state['seen']) if state['seen'] else None
    except ValueError:
        seen = None
    return max(today, seen) if seen else today


# -- queue-based counts ----------------------------------------------------

def _utc_start(day):
    """UTC (naive) instant at which local ``day`` begins."""
    return datetime.combine(day, dtime.min).astimezone(timezone.utc).replace(tzinfo=None)


def _db_counts(day):
    from app.database import db
    from app.models import MessageQueue

    def sent_since(start):
        return (db.session.query(func.count(MessageQueue.id))
                .filter(MessageQueue.status == 'sent', MessageQueue.sent_at >= start)
                .scalar()) or 0

    return sent_since(_utc_start(day)), sent_since(_utc_start(day.replace(day=1)))


def _in_flight():
    from app.database import db
    from app.models import MessageQueue

    cutoff = utcnow() - IN_FLIGHT_MAX_AGE
    return (db.session.query(func.count(MessageQueue.id))
            .filter(MessageQueue.status.in_(['sending', 'sending_auto']),
                    MessageQueue.updated_at >= cutoff)
            .scalar()) or 0


# -- public API --------------------------------------------------------------

def feature_enabled():
    return _manager().status().feature_enabled(FEATURE_KEY)


def summary(today=None):
    """Everything the UI and the dispatcher need to know about the caps.

    ``*_limit`` / ``*_remaining`` / ``allowance`` are ``None`` when unlimited.
    """
    status = _manager().status()
    state = _load()
    day = _effective_today(state, today)
    db_day, db_month = _db_counts(day)
    day_used = max(db_day, int(state['days'].get(day.isoformat(), 0)))
    month_used = max(db_month, int(state['months'].get(day.strftime('%Y-%m'), 0)))
    in_flight = _in_flight()

    day_limit = status.limit(LIMIT_WA_DAILY)
    month_limit = status.limit(LIMIT_WA_MONTHLY)
    day_remaining = None if day_limit is None else max(0, day_limit - day_used)
    month_remaining = None if month_limit is None else max(0, month_limit - month_used)

    enabled = status.feature_enabled(FEATURE_KEY)
    room = [value - in_flight for value in (day_remaining, month_remaining) if value is not None]
    allowance = None if not room else max(0, min(room))
    if not enabled:
        allowance = 0

    blocked_by = ''
    if not enabled:
        blocked_by = 'feature'
    elif allowance == 0:
        blocked_by = 'day' if (day_remaining is not None and day_remaining - in_flight <= 0) else 'month'

    return {
        'enabled': enabled,
        'day_used': day_used, 'day_limit': day_limit, 'day_remaining': day_remaining,
        'month_used': month_used, 'month_limit': month_limit, 'month_remaining': month_remaining,
        'in_flight': in_flight, 'allowance': allowance, 'blocked_by': blocked_by,
        'limited': day_limit is not None or month_limit is not None,
    }


def allowance():
    """How many more messages may be handed to the bridge right now (None = any)."""
    return summary()['allowance']


def block_message(info=None):
    """Human-readable reason sending is paused (empty string when it is not)."""
    info = info or summary()
    if info['blocked_by'] == 'feature':
        return 'WhatsApp automation is not included in this license.'
    if info['blocked_by'] == 'day':
        return (f"Daily WhatsApp limit reached ({info['day_used']}/{info['day_limit']}). "
                'Queued messages will go out automatically tomorrow.')
    if info['blocked_by'] == 'month':
        return (f"Monthly WhatsApp limit reached ({info['month_used']}/{info['month_limit']}). "
                'Queued messages will go out automatically next month.')
    return ''


def record_sent(count=1, today=None):
    """Count ``count`` successfully sent messages in the signed counter."""
    state = _load()
    day = _effective_today(state, today)
    day_key, month_key = day.isoformat(), day.strftime('%Y-%m')
    db_day, db_month = _db_counts(day)
    # The queue query may already include the message being recorded (the row
    # is flushed as 'sent' first), so take the larger of the two views rather
    # than adding on top.  This also heals a deleted or tampered counter file.
    state['days'][day_key] = max(int(state['days'].get(day_key, 0)) + count, db_day)
    state['months'][month_key] = max(int(state['months'].get(month_key, 0)) + count, db_month)
    state['seen'] = day_key
    _save(state)

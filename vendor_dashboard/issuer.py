"""Business rules of the dashboard: expiry maths, license status, issuing keys
and recovery tokens.  No Flask in here, so it is easy to test."""

import calendar
import time
from datetime import date, datetime, timedelta

from vendor_dashboard.core import admin_tool, features as features_mod, lic

EXPIRING_SOON_DAYS = 30
PERIODS = {'keep': None, '1m': 1, '3m': 3, '6m': 6, '1y': 12}
PERIOD_LABELS = {
    'keep': 'Keep the current expiry date',
    '1m': 'Renew +1 month', '3m': 'Renew +3 months', '6m': 'Renew +6 months',
    '1y': 'Renew +1 year', 'custom': 'Choose a date…',
}
REASONS = {
    'new': 'First key for this school',
    'renew': 'Renewal (payment received)',
    'update': 'Change features / limits',
    'move': 'Move to a new computer',
}
RECOVERY_HOURS = (1, 6, 24, 72)


class IssueError(Exception):
    """User-facing reason a key or token could not be issued."""


# -- dates -------------------------------------------------------------------

def add_months(day, months):
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def compute_expiry(period, custom_date, current_expires, today):
    """Last valid day of the new key.

    Renewals extend from the LATER of today and the day after the current
    expiry, so paying early never loses days and paying late never gives
    free ones.
    """
    if period == 'keep':
        if not current_expires:
            raise IssueError('There is no current expiry to keep - choose a renewal period or a date.')
        return current_expires
    if period == 'custom':
        if not custom_date:
            raise IssueError('Choose the expiry date.')
        return custom_date
    months = PERIODS.get(period)
    if not months:
        raise IssueError('Choose how long the key should be valid.')
    start = today
    if current_expires and current_expires + timedelta(days=1) > today:
        start = current_expires + timedelta(days=1)
    return add_months(start, months) - timedelta(days=1)


def license_status(expires_iso, grace_days, today):
    """(code, label, days_left) for a license row; ``code`` drives the colours."""
    if not expires_iso:
        return 'none', 'No license', None
    expires = date.fromisoformat(expires_iso)
    days_left = (expires - today).days
    if days_left < 0:
        grace_end = expires + timedelta(days=int(grace_days or 0))
        if today <= grace_end:
            return 'grace', 'Grace period', days_left
        return 'expired', 'Expired (read-only)', days_left
    if days_left <= EXPIRING_SOON_DAYS:
        return 'soon', 'Expiring soon', days_left
    return 'active', 'Active', days_left


def reminder_text(school_name, expires_iso, days_left):
    nice = date.fromisoformat(expires_iso).strftime('%d %b %Y')
    if days_left is not None and days_left < 0:
        timing = f'expired on {nice}'
    else:
        timing = f'expires on {nice}'
    return (f'Assalam o Alaikum! This is a reminder that the School Manager subscription for '
            f'{school_name} {timing}. Please renew to keep full access - after the grace period '
            f'the software becomes read-only. JazakAllah.')


# -- keys ----------------------------------------------------------------------

def _new_license_id(store, today):
    number = store.license_id_count() + 1
    while True:
        candidate = f'LIC-{today:%Y%m%d}-{number:04d}'
        if not store.license_id_exists(candidate):
            return candidate
        number += 1


def _optional_int(value):
    value = (value or '').strip() if isinstance(value, str) else value
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise IssueError('WhatsApp limits must be whole numbers (leave blank for unlimited).')
    if number < 0:
        raise IssueError('WhatsApp limits cannot be negative.')
    return number


def issue_key(store, private_key, school_id, *, reason, machine_code, plan, features,
              wa_daily, wa_monthly, period, custom_expires, grace_days, note, today=None):
    """Sign a new key revision for a school and record it.  Returns the row id."""
    today = today or date.today()
    school = store.school(school_id)
    if school is None:
        raise IssueError('School not found.')

    machine = lic.normalize_machine_code(machine_code)
    if len(machine) != 16:
        raise IssueError('The machine code must look like 7F3A-91BC-0D42-E8A5 (16 letters/digits).')
    machine = lic.format_machine_code(machine)

    wanted = features_mod.normalize_features(features) or []
    wa_daily, wa_monthly = _optional_int(wa_daily), _optional_int(wa_monthly)
    try:
        grace = max(0, min(lic.MAX_GRACE_DAYS, int(grace_days if grace_days not in (None, '') else lic.DEFAULT_GRACE_DAYS)))
    except (TypeError, ValueError):
        raise IssueError('Grace days must be a whole number.')

    current = store.latest_license(school_id)
    current_expires = date.fromisoformat(current['expires']) if current else None
    custom_date = None
    if custom_expires:
        try:
            custom_date = date.fromisoformat(custom_expires)
        except ValueError:
            raise IssueError('That expiry date is not valid.')
    if reason == 'new' and period == 'keep':
        raise IssueError('A first key needs a validity period or an expiry date.')
    expires = compute_expiry(period, custom_date, current_expires, today)
    if expires < today:
        raise IssueError('The expiry date is already in the past.')

    license_id = (current['license_id'] if current else school['license_id']) or _new_license_id(store, today)
    rev = (current['rev'] + 1) if current else 1

    payload = admin_tool.build_payload(
        license_id=license_id, licensee=school['name'], machine_code=machine,
        issued=today, expires=expires, grace_days=grace, rev=rev,
        plan=plan or None, features=wanted, wa_daily=wa_daily, wa_monthly=wa_monthly)
    key_text = admin_tool.sign_license(private_key, payload)

    return store.add_license(
        school_id=school_id, license_id=license_id, rev=rev, reason=reason, plan=plan or '',
        machine_code=machine, issued=today.isoformat(), expires=expires.isoformat(),
        grace_days=grace, features=wanted, wa_daily=wa_daily, wa_monthly=wa_monthly,
        key_text=key_text, note=note or '')


# -- password recovery -----------------------------------------------------------

def decode_request(store, text):
    """Decode a school's request code and match it to a registered school."""
    try:
        request_data = lic.parse_recovery_request(text)
    except lic.LicenseError as err:
        raise IssueError(err.message)
    school = store.find_school_for(request_data['license_id'], request_data['machine_code'])
    warnings = []
    if school is None:
        warnings.append('No registered school matches this request. Do not continue unless you can '
                        'confirm who is asking.')
    elif school['machine_code'] and lic.normalize_machine_code(school['machine_code']) != \
            lic.normalize_machine_code(request_data['machine_code']):
        warnings.append(f'This computer\'s machine code ({request_data["machine_code"]}) is different '
                        f'from the one registered for {school["name"]} ({school["machine_code"]}). '
                        'It may be a reinstall or a new PC - or someone else. Verify the person first.')
    if store.nonce_already_issued(request_data['nonce']):
        warnings.append('A token was already issued for this exact request code.')
    return request_data, school, warnings


def issue_recovery_token(store, private_key, request_data, school, hours, note, now=None):
    if hours not in RECOVERY_HOURS:
        raise IssueError('Choose how long the token stays valid.')
    now = int(now if now is not None else time.time())
    expires_ts = now + hours * 3600
    token = lic.sign_recovery_token(private_key, request_data['nonce'],
                                    request_data['machine_code'], now, expires_ts)
    store.add_recovery(
        school_id=school['id'] if school else None, license_id=request_data['license_id'],
        nonce=request_data['nonce'], machine_code=request_data['machine_code'],
        requested_at=request_data['requested_at'].isoformat(timespec='seconds'),
        issued_at=datetime.fromtimestamp(now).isoformat(timespec='seconds'),
        expires_at=datetime.fromtimestamp(expires_ts).isoformat(timespec='seconds'), note=note or '')
    return token, datetime.fromtimestamp(expires_ts)

"""Academic Calendar routes — add / edit / delete / archive / pin events."""

from datetime import date, datetime

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.models import ROLE_ADMIN, ROLE_OWNER
from app.models.calendar import CalendarEvent
from app.routes import main
from app.security import role_required
from app.services.audit import log_action

CATEGORIES = ['general', 'holiday', 'exam', 'meeting', 'trip', 'sport', 'other']


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_date(val, field='date'):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        flash(f'Invalid {field} format.', 'danger')
        return None


def _event_or_404(event_id):
    ev = CalendarEvent.query.get(event_id)
    if ev is None:
        abort(404)
    return ev


def _snapshot(ev):
    return {k: str(v) for k, v in ev.to_dict().items()}


# ──────────────────────────────────────────────────────────────────────────────
# List / main calendar page
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar')
@login_required
def calendar_page():
    today = date.today()
    year  = request.args.get('year',  today.year,  type=int)
    month = request.args.get('month', today.month, type=int)
    view  = request.args.get('view', 'month')   # month | list
    show_archived = request.args.get('archived', '0') == '1'
    cat_filter    = request.args.get('category', '')

    # Pinned events (always shown at top, never archived ones)
    pinned = (CalendarEvent.query
              .filter_by(is_pinned=True, is_archived=False)
              .order_by(CalendarEvent.event_date)
              .all())

    # Base query
    q = CalendarEvent.query.filter_by(is_archived=show_archived)
    if cat_filter and cat_filter in CATEGORIES:
        q = q.filter_by(category=cat_filter)

    if view == 'list':
        # Upcoming-first list (or past-first if archived)
        if show_archived:
            events = q.order_by(CalendarEvent.event_date.desc()).limit(200).all()
        else:
            events = q.filter(CalendarEvent.event_date >= today).order_by(
                CalendarEvent.event_date).all()
        month_events = None
    else:
        # Month grid
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        month_start = date(year, month, 1)
        month_end   = date(year, month, last_day)
        events = (q.filter(
            CalendarEvent.event_date <= month_end,
            db.or_(
                CalendarEvent.end_date >= month_start,
                CalendarEvent.event_date >= month_start,
            )
        ).order_by(CalendarEvent.event_date).all())
        # Build a day → [event] map for the template
        month_events = {}
        for ev in events:
            start = max(ev.event_date, month_start)
            end   = min(ev.end_date or ev.event_date, month_end)
            d = start
            while d <= end:
                month_events.setdefault(d.day, []).append(ev)
                d = date(d.year, d.month, d.day + 1) if d.day < last_day else month_end
                if d > end:
                    break
            month_events.setdefault(start.day, [])  # ensure start day always exists

        # Build grid weeks (list of lists of day numbers, 0 = padding)
        import calendar as cal_mod
        cal = cal_mod.monthcalendar(year, month)

    return render_template(
        'calendar.html',
        pinned=pinned,
        events=events,
        month_events=month_events,
        view=view,
        year=year,
        month=month,
        today=today,
        show_archived=show_archived,
        cat_filter=cat_filter,
        categories=CATEGORIES,
        cur='calendar',
        # For the month grid header
        month_name=date(year, month, 1).strftime('%B'),
        cal_weeks=cal if view == 'month' else None,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Add
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar/add', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_OWNER)
def calendar_add():
    if request.method == 'POST':
        title      = request.form.get('title', '').strip()
        desc       = request.form.get('description', '').strip()
        event_date = _parse_date(request.form.get('event_date'), 'start date')
        end_date   = _parse_date(request.form.get('end_date'), 'end date') or None
        category   = request.form.get('category', 'general')
        is_pinned  = bool(request.form.get('is_pinned'))

        if not title:
            flash('Title is required.', 'danger')
        elif not event_date:
            pass  # flash already set by _parse_date
        else:
            if end_date and end_date < event_date:
                flash('End date cannot be before start date.', 'danger')
            elif category not in CATEGORIES:
                flash('Invalid category.', 'danger')
            else:
                ev = CalendarEvent(
                    title=title, description=desc,
                    event_date=event_date, end_date=end_date,
                    category=category, is_pinned=is_pinned,
                    created_by=current_user.id,
                )
                db.session.add(ev)
                db.session.flush()
                log_action('create', entity_type='CalendarEvent', entity_id=ev.id,
                           summary=f'Added calendar event "{title}" on {event_date}',
                           after=_snapshot(ev))
                db.session.commit()
                flash(f'Event "{title}" added.', 'success')
                return redirect(url_for('main.calendar_page',
                                        year=event_date.year, month=event_date.month))

    prefill_date = request.args.get('date', date.today().isoformat())
    return render_template('calendar_form.html', event=None,
                           prefill_date=prefill_date, categories=CATEGORIES, cur='calendar')


# ──────────────────────────────────────────────────────────────────────────────
# Edit
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_OWNER)
def calendar_edit(event_id):
    ev = _event_or_404(event_id)
    if request.method == 'POST':
        title      = request.form.get('title', '').strip()
        desc       = request.form.get('description', '').strip()
        event_date = _parse_date(request.form.get('event_date'), 'start date')
        end_date   = _parse_date(request.form.get('end_date'), 'end date') or None
        category   = request.form.get('category', 'general')
        is_pinned  = bool(request.form.get('is_pinned'))

        if not title:
            flash('Title is required.', 'danger')
        elif not event_date:
            pass
        else:
            if end_date and end_date < event_date:
                flash('End date cannot be before start date.', 'danger')
            elif category not in CATEGORIES:
                flash('Invalid category.', 'danger')
            else:
                before = _snapshot(ev)
                ev.title       = title
                ev.description = desc
                ev.event_date  = event_date
                ev.end_date    = end_date
                ev.category    = category
                ev.is_pinned   = is_pinned
                ev.updated_at  = datetime.utcnow()
                log_action('update', entity_type='CalendarEvent', entity_id=ev.id,
                           summary=f'Updated calendar event "{title}"',
                           before=before, after=_snapshot(ev))
                db.session.commit()
                flash(f'Event "{title}" updated.', 'success')
                return redirect(url_for('main.calendar_page',
                                        year=event_date.year, month=event_date.month))

    return render_template('calendar_form.html', event=ev,
                           prefill_date=ev.event_date.isoformat(),
                           categories=CATEGORIES, cur='calendar')


# ──────────────────────────────────────────────────────────────────────────────
# Delete
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar/<int:event_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_OWNER)
def calendar_delete(event_id):
    ev = _event_or_404(event_id)
    before = _snapshot(ev)
    title  = ev.title
    log_action('delete', entity_type='CalendarEvent', entity_id=ev.id,
               summary=f'Deleted calendar event "{title}"', before=before)
    db.session.delete(ev)
    db.session.commit()
    flash(f'Event "{title}" deleted.', 'success')
    return redirect(request.referrer or url_for('main.calendar_page'))


# ──────────────────────────────────────────────────────────────────────────────
# Archive / unarchive
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar/<int:event_id>/archive', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_OWNER)
def calendar_archive(event_id):
    ev = _event_or_404(event_id)
    ev.is_archived = not ev.is_archived
    ev.is_pinned   = False if ev.is_archived else ev.is_pinned
    action = 'archive' if ev.is_archived else 'unarchive'
    log_action(action, entity_type='CalendarEvent', entity_id=ev.id,
               summary=f'{"Archived" if ev.is_archived else "Unarchived"} event "{ev.title}"')
    db.session.commit()
    label = 'archived' if ev.is_archived else 'restored'
    flash(f'Event "{ev.title}" {label}.', 'success')
    return redirect(request.referrer or url_for('main.calendar_page'))


# ──────────────────────────────────────────────────────────────────────────────
# Pin / unpin
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar/<int:event_id>/pin', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_OWNER)
def calendar_pin(event_id):
    ev = _event_or_404(event_id)
    if ev.is_archived:
        flash('Archived events cannot be pinned.', 'warning')
        return redirect(request.referrer or url_for('main.calendar_page'))
    ev.is_pinned = not ev.is_pinned
    action = 'pin' if ev.is_pinned else 'unpin'
    log_action(action, entity_type='CalendarEvent', entity_id=ev.id,
               summary=f'{"Pinned" if ev.is_pinned else "Unpinned"} event "{ev.title}"')
    db.session.commit()
    label = 'pinned' if ev.is_pinned else 'unpinned'
    flash(f'"{ev.title}" {label}.', 'success')
    return redirect(request.referrer or url_for('main.calendar_page'))


# ──────────────────────────────────────────────────────────────────────────────
# API: events for a given month (used by JS calendar grid)
# ──────────────────────────────────────────────────────────────────────────────

@main.route('/calendar/api/events')
@login_required
def calendar_api_events():
    year  = request.args.get('year',  date.today().year,  type=int)
    month = request.args.get('month', date.today().month, type=int)
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    month_start = date(year, month, 1)
    month_end   = date(year, month, last_day)
    events = (CalendarEvent.query
              .filter_by(is_archived=False)
              .filter(
                  CalendarEvent.event_date <= month_end,
                  db.or_(
                      CalendarEvent.end_date >= month_start,
                      CalendarEvent.event_date >= month_start,
                  )
              )
              .order_by(CalendarEvent.event_date)
              .all())
    return jsonify([e.to_dict() for e in events])

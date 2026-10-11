"""Redesigned Timetables system (the only timetable used by the app).

Two predefined templates over the same saved slot data:

* ``matrix``  - teacher-wise chart (see ``timetable1.jpg``)
* ``daygrid`` - class weekly grids

Both support one-click automatic generation from the school's own settings,
classes, subjects and teaching assignments, manual editing, saving and
loading.  The period/break structure is read from the School Settings page, so
the user never re-enters timings here.

All endpoints are administrator-only except the teacher-facing timetable views
(``main.teacher_timetables`` / ``main.teacher_timetable``), which live in
``app/routes/classes.py``.
"""

import json
import re
from collections import defaultdict

from flask import flash, redirect, render_template, request, url_for

from app.database import db
from app.models import (ClassModel, SectionModel, TeacherModel, TimetableSlot)
from app.routes import main
from app.services import timetable as tt
from app.services import timetable_conflicts
from app.services.timetable_grid import effective_entries, effective_teachers


# ================================================== redesigned hub

@main.route('/timetables')
def timetables_hub():
    """The Timetables page: pick a class, generate, then edit on the template.

    ``?class_id=`` narrows the page to one class (the simple default flow);
    ``?template_key=`` previews the other layout without saving the choice.
    """
    from app.services import timetable_redesign as redesign

    template_key = redesign.get_template_key()
    preview_key = request.args.get('template_key')
    if preview_key in redesign.REDESIGN_TEMPLATES:
        template_key = preview_key
    rows = redesign.master_rows()
    period_nos = [r['no'] for r in rows if r.get('kind') != 'break']
    days = tt.school_days()
    day_index = request.args.get('day', type=int)
    if day_index is None or day_index not in {d for d, _n in days}:
        day_index = days[0][0] if days else 0

    classes = ClassModel.query.order_by(ClassModel.name).all()
    teachers = (TeacherModel.query.filter_by(is_active=True)
                .order_by(TeacherModel.teacher_name).all())

    # One class at a time keeps the page light and easy to read: a class with
    # sections shows one grid per section, a plain class shows a single grid.
    raw_class_id = request.args.get('class_id', type=int)
    selected_class = db.session.get(ClassModel, raw_class_id) if raw_class_id else None
    shown = [selected_class] if selected_class is not None else []
    grids = []
    for klass in shown:
        sections = sorted(klass.sections, key=lambda s: s.name)
        audiences = [sec.id for sec in sections] if sections else [None]
        for section_id in audiences:
            grids.append(redesign.class_grid(klass, rows, section_id=section_id))

    entries = effective_entries()
    slot_teachers = effective_teachers([e['slot'] for e in entries
                                        if e['slot'] is not None])
    matrix = redesign.matrix_for_day(day_index, rows, entries, slot_teachers)
    chart = redesign.classes_chart(day_index, rows, entries, slot_teachers)

    # A teacher covering several classes in the same period is normal here, so
    # it is reported for information (a small badge) and never blocked.
    shared = timetable_conflicts.shared_teacher_map()
    shared_count = sum(len(at_period) for at_period in shared.values())
    return render_template('timetables.html',
                           template_key=template_key,
                           templates=redesign.REDESIGN_TEMPLATES,
                           rows=rows, period_nos=period_nos,
                           days=days, day_index=day_index,
                           classes=classes, teachers=teachers,
                           matrix=matrix,
                           chart=chart,
                           grids=grids,
                           selected_class=selected_class,
                           shared=shared,
                           shared_count=shared_count,
                           start_time=tt.school_start_time(),
                           days_names=[name for _d, name in days])


@main.route('/timetables/template', methods=['POST'])
def timetables_template():
    """Remember which of the two predefined templates the school uses."""
    from app.services import timetable_redesign as redesign
    from app.services.audit import log_action

    raw_key = request.form.get('template_key') or redesign.DEFAULT_TEMPLATE
    redesign.set_template_key(raw_key)
    key = redesign.get_template_key()
    log_action('settings_change', entity_type='TimetableMasterConfig', entity_id=1,
               summary='Timetable template set to "%s"' % key)
    db.session.commit()
    flash('Timetable layout saved: %s.' % redesign.REDESIGN_TEMPLATES[key]['label'],
          'success')
    return redirect(url_for('main.timetables_hub'))


@main.route('/timetables/generate', methods=['POST'])
def timetables_generate():
    """One-click generation from the school's own settings and class data.

    The class dropdown may carry ``all`` (every class) or one class id; the
    layout dropdown both saves the preferred template and is used for the
    redirect, so the admin lands back on the class they just generated.
    """
    from app.services import timetable_generator as gen
    from app.services import timetable_redesign as redesign
    from app.services.audit import log_action

    raw_values = [v for v in request.form.getlist('class_ids') if v]
    class_ids = []
    for raw in raw_values:
        if raw == 'all':
            class_ids = [c.id for c in ClassModel.query.order_by(ClassModel.name).all()]
            break
        try:
            class_ids.append(int(raw))
        except ValueError:
            continue
    if not class_ids:
        flash('Pick a class (or All classes) first.', 'danger')
        return redirect(url_for('main.timetables_hub'))

    # The layout dropdown doubles as the template preference.
    raw_template = request.form.get('template_key')
    if raw_template in redesign.REDESIGN_TEMPLATES:
        redesign.set_template_key(raw_template)
    template_key = redesign.get_template_key()

    rows = redesign.master_rows()
    period_nos = [r['no'] for r in rows if r.get('kind') != 'break']
    days = [d for d, _name in tt.school_days()]
    if not period_nos or not days:
        flash('No periods or teaching days set up yet — check School Settings.',
              'danger')
        return redirect(url_for('main.timetables_hub'))

    payload = gen.generate(class_ids, period_nos, days)
    rows_json = json.dumps([{k: r.get(k, '') for k in ('kind', 'start', 'end', 'label')}
                            for r in rows])
    written = redesign.write_generated_slots(payload['slots'], class_ids, rows_json)
    log_action('timetable_update', entity_type='TimetableMasterConfig', entity_id=1,
               summary='Timetable generated: %d period(s) across %d class(es)'
                       % (written, len(class_ids)))
    db.session.commit()

    for note in (payload.get('notes') or [])[:3]:
        flash(note, 'warning')
    flash('Timetable ready — %d period(s) placed for %d class(es). '
          'You can change anything below by hand.' % (written, len(class_ids)),
          'success')
    # Land on the class that was just generated (or the class list for "all").
    target = class_ids[0] if len(class_ids) == 1 else None
    return redirect(url_for('main.timetables_hub', class_id=target,
                            template_key=template_key))


@main.route('/timetables/save/<int:class_id>', methods=['POST'])
def timetables_save_class(class_id):
    """Save the edited grid(s) for a class: subjects + teachers.

    A plain class posts one grid.  A sectioned class posts one grid per section
    (the section id travels as a per-grid ``section_id_<id>`` hidden field), so
    the teacher-wise chart can save every section behind one button.

    Teacher overlap is never a reason to refuse a save: one teacher may cover
    several classes in the same period.
    """
    from app.services import timetable_redesign as redesign
    from app.services.audit import log_action

    class_obj = ClassModel.query.get_or_404(class_id)
    rows = redesign.master_rows()
    day_indices = [d for d, _name in tt.school_days()]
    active_subjects = {s.id: s for s in class_obj.subjects if s.is_active}
    all_subjects = {s.id: s for s in class_obj.subjects}

    # Which grids are on the form?  A sectioned class posts one grid per
    # section (the section id travels as a per-grid ``section_id_<id>``
    # hidden field, or a single ``section_id`` for one section's form).  A
    # form with no section info edits the whole-class grid, which every
    # section inherits until it keeps its own.
    audiences = [None]
    sections = sorted(class_obj.sections, key=lambda s: s.name)
    if sections:
        posted = [s.id for s in sections
                  if request.form.get('section_id_%d' % s.id) is not None]
        single = (request.form.get('section_id') or '').strip()
        if not posted and single:
            candidate = db.session.get(SectionModel, int(single)) \
                if single.isdigit() else None
            if candidate is None or candidate.class_id != class_obj.id:
                flash('That section does not belong to this class.', 'danger')
                return redirect(url_for('main.timetables_hub', class_id=class_id))
            posted = [candidate.id]
        audiences = posted if posted else [None]

    saved = 0
    for section_id in audiences:
        # The template builds field names as ``slot_s<id>_...`` for a section
        # grid and plain ``slot_...`` for a whole-class grid (see the
        # ``prefix`` set in timetables.html) — match it exactly.
        prefix = 'slot_s%d_' % section_id if section_id is not None else 'slot_'
        new_slots = []
        teacher_overrides = {}
        for row in rows:
            if row.get('kind') == 'break' or row.get('no') is None:
                continue
            period_no = row['no']
            for day in day_indices:
                raw_subject = (request.form.get(
                    '%s%d_%d_subject' % (prefix, day, period_no)) or '').strip()
                try:
                    subject_id = int(raw_subject) if raw_subject else None
                except ValueError:
                    subject_id = None
                if subject_id is None or subject_id not in active_subjects:
                    continue
                new_slots.append((day, period_no, subject_id))

                raw_teacher = (request.form.get(
                    '%s%d_%d_teacher' % (prefix, day, period_no)) or '').strip()
                try:
                    teacher_id = int(raw_teacher) if raw_teacher else None
                except ValueError:
                    teacher_id = None
                # Only stored when it differs from the subject's own teacher —
                # otherwise the cell inherits, so Classes-page teacher changes
                # keep propagating automatically.
                if teacher_id and teacher_id != active_subjects[subject_id].teacher_id \
                        and db.session.get(TeacherModel, teacher_id) is not None:
                    teacher_overrides[(day, period_no)] = teacher_id

        TimetableSlot.query.filter_by(class_id=class_obj.id,
                                      section_id=section_id).delete()
        db.session.flush()
        for day, period_no, subject_id in new_slots:
            override = teacher_overrides.get((day, period_no))
            if override and override == all_subjects[subject_id].teacher_id:
                override = None
            db.session.add(TimetableSlot(class_id=class_obj.id, section_id=section_id,
                                         day_of_week=day, period_no=period_no,
                                         subject_id=subject_id, teacher_id=override))
        saved += len(new_slots)

    label = class_obj.name if len(audiences) <= 1 or audiences == [None] \
        else '%s (%d section(s))' % (class_obj.name, len(audiences))
    log_action('timetable_update', entity_type='ClassModel', entity_id=class_obj.id,
               summary='Timetable saved for %s (%d period(s))' % (label, saved))
    db.session.commit()
    flash('Saved — %s now has %d lesson(s).' % (label, saved), 'success')
    return redirect(url_for('main.timetables_hub', class_id=class_obj.id))


@main.route('/timetables/save-all', methods=['POST'])
def timetables_save_all():
    """Save the all-classes chart (timetable2.jpg template) for ONE day.

    The chart shows every class in one grid, so one Save button writes it all.
    Cells posted for this day replace that day's lessons; every other day of
    the saved timetable stays untouched (a per-day merge, so editing Monday
    never disturbs Tuesday).  A teacher covering several classes in the same
    period is fine and never blocked.
    """
    from app.services import timetable_redesign as redesign
    from app.services.audit import log_action

    days = tt.school_days()
    day = request.form.get('day', type=int)
    if day is None or day not in {d for d, _n in days}:
        flash('Pick a teaching day first.', 'danger')
        return redirect(url_for('main.timetables_hub'))

    rows = redesign.master_rows()
    period_nos = {r['no'] for r in rows if r.get('kind') != 'break' and r.get('no')}
    pattern = re.compile(
        r'^cell_(\d+)_(all|s\d+)_(\d+)_(subject|teacher)$')

    # Collect the posted cells per audience: (class_id, section_id) ->
    # {period_no: {'subject_id': …, 'teacher_id': …}}.
    posted = defaultdict(dict)
    for key, value in request.form.items():
        match = pattern.match(key)
        if not match:
            continue
        class_id, section_token, raw_period, field = match.groups()
        period_no = int(raw_period)
        if period_no not in period_nos:
            continue
        section_id = int(section_token[1:]) if section_token.startswith('s') else None
        audience = (int(class_id), section_id)
        posted[audience].setdefault(period_no, {})[field] = (value or '').strip()

    written = 0
    skipped = 0
    for (class_id, section_id), cells in posted.items():
        klass = db.session.get(ClassModel, class_id)
        if klass is None:
            skipped += len(cells)
            continue
        if section_id is not None:
            section = db.session.get(SectionModel, section_id)
            if section is None or section.class_id != class_id:
                skipped += len(cells)
                continue
        subjects = {s.id: s for s in klass.subjects if s.is_active}

        # Replace only this day's slots for the audience; other days merge.
        TimetableSlot.query.filter_by(class_id=class_id, section_id=section_id,
                                      day_of_week=day).delete()
        db.session.flush()
        for period_no, cell in sorted(cells.items()):
            raw_subject = cell.get('subject') or ''
            try:
                subject_id = int(raw_subject) if raw_subject else None
            except ValueError:
                subject_id = None
            if subject_id is None or subject_id not in subjects:
                continue
            raw_teacher = cell.get('teacher') or ''
            try:
                teacher_id = int(raw_teacher) if raw_teacher else None
            except ValueError:
                teacher_id = None
            # Inherit unless the posted teacher genuinely differs from the
            # subject's own teacher (keeps Classes-page changes propagating).
            override = None
            if teacher_id and teacher_id != subjects[subject_id].teacher_id \
                    and db.session.get(TeacherModel, teacher_id) is not None:
                override = teacher_id
            db.session.add(TimetableSlot(class_id=class_id, section_id=section_id,
                                         day_of_week=day, period_no=period_no,
                                         subject_id=subject_id, teacher_id=override))
            written += 1

    day_name = dict(days).get(day, 'Day %d' % day)
    log_action('timetable_update', entity_type='TimetableMasterConfig', entity_id=1,
               summary='All-classes chart saved for %s (%d lesson(s))'
                       % (day_name, written))
    db.session.commit()
    flash('Saved — %s: %d lesson(s) written.' % (day_name, written), 'success')
    return redirect(url_for('main.timetables_hub', template_key='daygrid', day=day))

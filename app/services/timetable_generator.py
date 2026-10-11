"""Timetable generator: fills the period grid from the school's own data.

Every class's subjects (with each subject's own teacher) are spread evenly
across the teaching days and periods.  A teacher may cover several classes in
the same period — normal in a small or medium school — so teacher overlap is
never treated as a blocker; the generator simply places what the school set up.

Soft preferences only shape *where* a lesson lands: subjects spread across the
week, no back-to-back repeats, and a teacher's lessons balanced across days.
Nothing touches the live table until the admin presses Generate.
"""

import math
from collections import defaultdict

from app.models import ClassModel, SectionModel, TeachingAssignment, TimetableSlot
from app.services import timetable_conflicts


def _demand_for_class(class_obj, subjects, grid_size, days_count, notes):
    """[(subject, teacher_id, required_periods)] — every active subject of the
    class, spread evenly over the week unless a required period count is set."""
    assignments = {(a.library_id): a for a in TeachingAssignment.query
                   .filter_by(class_id=class_obj.id, is_active=True, section_id=None)
                   .all() if a.library_id}
    demand = []
    for subject in subjects:
        assignment = assignments.get(subject.library_id)
        teacher_id = (assignment.teacher_id if assignment and assignment.teacher_id
                      else subject.teacher_id)
        required = assignment.periods_per_week if assignment else None
        if required is not None:
            required = max(0, min(int(required), grid_size))
        demand.append({'subject': subject, 'teacher_id': teacher_id,
                       'required': required, 'name': subject.name,
                       'explicit': required is not None})

    set_total = sum(item['required'] or 0 for item in demand)
    unset = [item for item in demand if item['required'] is None]
    if set_total > grid_size:
        # Trim the subjects the school gave the largest requirements first, so
        # nobody silently loses their allocation.
        remaining = grid_size
        trimmed = 0
        for item in sorted(demand, key=lambda d: -(d['required'] or 0)):
            if item['required'] is None:
                continue
            keep = min(item['required'], remaining)
            trimmed += item['required'] - keep
            item['required'] = keep
            remaining -= keep
        notes.append('%s: the required periods add up to more than the week has '
                     '(%d slot(s)); %d period(s) were trimmed.'
                     % (class_obj.name, grid_size, trimmed))
    if unset:
        # Subjects without an explicit requirement share what is left.  Using
        # ceil() means a short week simply drops a subject rather than failing.
        share_total = max(0, grid_size - set_total)
        share = max(1, math.ceil(share_total / len(unset)))
        for item in unset:
            item['required'] = share
    demand = [item for item in demand if item['required'] and item['required'] > 0]
    demand.sort(key=lambda item: (0 if item['explicit'] else 1,
                                  -item['required'], item['name']))
    return demand


def generate(class_ids, period_nos, days, existing=None):
    """Build a draft timetable for the given classes.

    ``period_nos`` is the 1-based list of lesson periods; ``days`` the list of
    stored day indices (school teaching days).  Classes with several sections
    get one grid per section (each scheduled as its own audience); classes
    without sections get class-level slots.  Returns a payload dict for the
    draft table.
    """
    notes = []
    slots = []
    per_class = {}
    days = list(days)
    period_nos = list(period_nos)
    grid_size = len(days) * len(period_nos)

    # A teacher may cover several classes in the same period, so occupancy is
    # deliberately NOT loaded: the generator places exactly what the school
    # configured (its chosen classes, subjects and teachers).
    classes = ClassModel.query.filter(ClassModel.id.in_(class_ids)).all() \
        if class_ids else []
    class_map = {c.id: c for c in classes}
    sec_map = defaultdict(list)
    if class_ids:
        for sec in SectionModel.query.filter(SectionModel.class_id.in_(class_ids)).all():
            sec_map[sec.class_id].append(sec)

    for class_id in class_ids:
        class_obj = class_map.get(class_id)
        if class_obj is None:
            continue
        subjects = [s for s in class_obj.subjects if s.is_active]
        if not subjects:
            notes.append('%s has no active subjects — nothing to schedule.' % class_obj.name)
            per_class[class_id] = {'name': class_obj.name, 'sections': 0,
                                   'placed': 0, 'free': grid_size}
            continue
        demand = _demand_for_class(class_obj, subjects, grid_size, len(days), notes)

        audiences = [sec.id for sec in sec_map.get(class_id, [])] or [None]
        for section_id in audiences:
            section_label = class_obj.name if section_id is None else (
                '%s-%s' % (class_obj.name,
                           next(s.name for s in sec_map[class_id] if s.id == section_id)))
            cells = {}                       # (day, period) -> subject_id
            day_subject_count = defaultdict(lambda: defaultdict(int))
            teacher_day_load = defaultdict(int)    # teacher_id -> periods today
            placed = 0
            for item in demand:
                subject = item['subject']
                teacher_id = item['teacher_id']
                per_day_cap = max(1, math.ceil(item['required'] / len(days))) \
                    if len(days) else 1
                same_period_count = defaultdict(int)  # period_no -> times used
                got = 0
                for _n in range(item['required']):
                    candidates = []
                    for day in days:
                        for period_no in period_nos:
                            if (day, period_no) in cells:
                                continue
                            score = 0
                            if day_subject_count[day].get(subject.id, 0) >= per_day_cap:
                                score += 8
                            score += 4 * day_subject_count[day].get(subject.id, 0)
                            prev_sub = cells.get((day, period_no - 1))
                            next_sub = cells.get((day, period_no + 1))
                            if prev_sub == subject.id or next_sub == subject.id:
                                score += 10
                            score += same_period_count[period_no]
                            if teacher_id is not None:
                                score += 2 * teacher_day_load[teacher_id]
                            candidates.append((score, day, period_no))
                    if not candidates:
                        continue
                    score, day, period_no = min(candidates)
                    cells[(day, period_no)] = subject.id
                    day_subject_count[day][subject.id] = day_subject_count[day].get(subject.id, 0) + 1
                    same_period_count[period_no] += 1
                    if teacher_id is not None:
                        teacher_day_load[teacher_id] += 1
                    # Record the assigned teacher only when it differs from the
                    # subject's own teacher — NULL means "inherit", so later
                    # teacher changes on the Classes page still propagate.
                    override = teacher_id if teacher_id != subject.teacher_id else None
                    slots.append({'class_id': class_id, 'section_id': section_id,
                                  'day': day, 'period': period_no,
                                  'subject_id': subject.id, 'teacher_id': override})
                    got += 1
                    placed += 1
            per_class.setdefault(class_id, {'name': class_obj.name,
                                            'sections': len(audiences), 'placed': 0,
                                            'free': 0})
            per_class[class_id]['placed'] += placed
            per_class[class_id]['free'] += grid_size - placed

    return {'class_ids': list(class_ids), 'days': days, 'periods': period_nos,
            'slots': slots, 'notes': notes, 'per_class': per_class}


def load_master_rows():
    """(rows, period_nos) for the school timetable structure.

    The structure now lives on the School Settings page (see
    ``app.services.timetable.build_school_rows``), so every class shares the
    timings the school configured instead of a per-class preset.
    """
    from app.services import timetable as tt
    rows = tt.number_rows(tt.build_school_rows())
    period_nos = [r['no'] for r in rows if r.get('kind') != 'break']
    return rows, period_nos

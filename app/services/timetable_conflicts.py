"""Timetable reading, teacher-sharing detection and reporting.

In a small or medium school one teacher often handles two or three classes in
the same period (Period 2: Class 1 Science + Class 3 English).  That is normal
here, **not** an error: nothing is ever blocked.

This module therefore *reports* where a teacher is shared instead of refusing
it, so the school can see the arrangement at a glance:

* :func:`shared_teacher_map` — {(day, period): {teacher_id: [lesson, ...]}},
  the small "2 classes" badge shown on the template.
* :func:`all_teacher_conflicts` — the same information grouped per teacher for
  the read-only teacher views.

Detection works on slot **rows**: a class-level row (section NULL) is one
engagement for the whole class, and a section row is one for that section.  A
class-level row that every section overrides covers nobody and is ignored.
"""

from collections import namedtuple, defaultdict

from app.models import ClassModel, SectionModel, SubjectModel, TeacherModel, TimetableSlot

NewSlot = namedtuple('NewSlot', 'id class_id section_id day_of_week period_no subject_id teacher_id')
NewSlot.__new__.__defaults__ = (None, None, None, None, None, None, None)


def tt_day_name(day_index):
    """'Monday'..'Saturday' for the stored 0-based day index."""
    from app.services.timetable import DAYS
    return DAYS[day_index] if 0 <= day_index < len(DAYS) else 'Day %d' % day_index


def effective_teacher_id(row, subject):
    """Who actually teaches a slot: a manual ``row.teacher_id`` override wins,
    otherwise the subject's own teacher."""
    override = getattr(row, 'teacher_id', None)
    return override if override else (subject.teacher_id if subject is not None else None)


def _active_rows(slot_rows=None):
    """Slot rows that actually engage a teacher, with subjects resolved.

    Class-level rows fully overridden by per-section rows at the same
    (day, period) are dropped — every section has its own lesson instead.
    """
    rows = list(slot_rows) if slot_rows is not None else list(TimetableSlot.query.all())
    sections_count = defaultdict(int)
    for section in SectionModel.query.all():
        sections_count[section.class_id] += 1

    overridden = defaultdict(set)  # (class_id, day, period) -> {section_id}
    for row in rows:
        if row.section_id is not None:
            overridden[(row.class_id, row.day_of_week, row.period_no)].add(row.section_id)

    subject_ids = {row.subject_id for row in rows if row.subject_id}
    subjects = {}
    if subject_ids:
        for subject in SubjectModel.query.filter(SubjectModel.id.in_(subject_ids)).all():
            subjects[subject.id] = subject

    active = []
    for row in rows:
        if row.section_id is None and sections_count.get(row.class_id):
            covered = overridden.get((row.class_id, row.day_of_week, row.period_no), set())
            if len(covered) >= sections_count[row.class_id]:
                continue  # every section keeps its own slot at this time
        active.append((row, subjects.get(row.subject_id)))
    return active


def shared_teacher_groups(slot_rows=None):
    """[(teacher_id, teacher_name, day, period, [(row, subject), ...])] for every
    teacher teaching more than one lesson at the same day and period.

    This is a *report*, not a fault: the caller decides whether to badge it.
    """
    grouped = defaultdict(list)
    for row, subject in _active_rows(slot_rows):
        teacher_id = effective_teacher_id(row, subject)
        if subject is None or teacher_id is None:
            continue
        grouped[(teacher_id, row.day_of_week, row.period_no)].append((row, subject))
    involved_ids = {teacher_id for teacher_id, _day, _period in grouped}
    names = {t.id: t.teacher_name for t in TeacherModel.query.filter(
        TeacherModel.id.in_(involved_ids)).all()} if involved_ids else {}
    result = []
    for (teacher_id, day, period), members in grouped.items():
        if len(members) > 1:
            result.append((teacher_id, names.get(teacher_id, 'Teacher'), day, period, members))
    return sorted(result, key=lambda item: (item[2], item[3], item[1]))


def shared_teacher_map():
    """{(day, period): {teacher_id: [{'class','section','subject'}, ...]}}.

    Used to draw the small ``N classes`` badge on the editable template, so a
    teacher shared across classes is visible but never blocked.
    """
    classes = {c.id: c.name for c in ClassModel.query.all()}
    sections = {s.id: s.name for s in SectionModel.query.all()}
    result = defaultdict(lambda: defaultdict(list))
    for teacher_id, _name, day, period, members in shared_teacher_groups():
        for row, subject in members:
            result[(day, period)][teacher_id].append({
                'class': classes.get(row.class_id, 'Class'),
                'section': sections.get(row.section_id) if row.section_id else None,
                'subject': subject.name if subject else '?',
            })
    return {key: dict(value) for key, value in result.items()}


def all_teacher_conflicts():
    """Shared periods school-wide, grouped by teacher (read-only reporting).

    Returns ``{teacher_id: [(day_name, period_no, ['Class — Subject', ...])]}``.
    Empty dict when no teacher is shared.
    """
    result = defaultdict(list)
    classes = {c.id: c.name for c in ClassModel.query.all()}
    for teacher_id, _name, day, period, members in shared_teacher_groups():
        places = ['%s — %s' % (classes.get(row.class_id, 'Class'),
                               subject.name if subject else '?')
                  for row, subject in members]
        result[teacher_id].append((tt_day_name(day), period, places))
    for shared in result.values():
        shared.sort(key=lambda item: (item[0], item[1]))
    return dict(result)

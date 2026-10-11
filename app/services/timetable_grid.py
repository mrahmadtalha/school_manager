"""Section-aware timetable resolution.

Stored :class:`~app.models.class_.TimetableSlot` rows come in two flavours:
class-level (``section_id`` NULL — belongs to the whole class) and
section-level (a section's own grid entry).  A section slot overrides the
class-level slot **for that section** at the same day and period; the
class-level slot still applies to every other section.

Every consumer — conflict detection, teacher views, the master grid and the
date-wise substitution sheet — reads the school timetable through
:func:`effective_entries`, never from the raw rows.
"""

from collections import defaultdict

from app.models import ClassModel, SectionModel, TeacherModel, TimetableSlot


def effective_teachers(slot_rows):
    """{slot_id: TeacherModel or None} — who actually teaches each slot row.

    A manual ``teacher_id`` override on the slot wins; otherwise the slot's
    subject teacher is used.  Used by every read-only view so a manual
    reassignment on the Timetables page is visible school-wide immediately.
    """
    from app.models import SubjectModel

    subject_ids = {row.subject_id for row in slot_rows if row.subject_id}
    subjects = {}
    if subject_ids:
        for subject in SubjectModel.query.filter(SubjectModel.id.in_(subject_ids)).all():
            subjects[subject.id] = subject
    teacher_ids = {row.teacher_id for row in slot_rows if row.teacher_id}
    teacher_ids |= {s.teacher_id for s in subjects.values() if s.teacher_id}
    teachers = {}
    if teacher_ids:
        for teacher in TeacherModel.query.filter(TeacherModel.id.in_(teacher_ids)).all():
            teachers[teacher.id] = teacher

    result = {}
    for row in slot_rows:
        subject = subjects.get(row.subject_id)
        teacher_id = row.teacher_id or (subject.teacher_id if subject else None)
        result[row.id] = teachers.get(teacher_id)
    return result


def _load_rows(class_ids=None):
    query = TimetableSlot.query
    if class_ids is not None:
        query = query.filter(TimetableSlot.class_id.in_(class_ids))
    return query.all()


def sections_map(class_ids=None):
    """{class_id: [SectionModel, ...]} (empty list for classes without any)."""
    query = SectionModel.query
    if class_ids is not None:
        query = query.filter(SectionModel.class_id.in_(class_ids))
    result = defaultdict(list)
    for section in query.all():
        result[section.class_id].append(section)
    return result


def effective_entries(class_ids=None, slot_rows=None):
    """The resolved school timetable.

    Returns a list of dicts ``{'class', 'section_id', 'day', 'period', 'slot',
    'subject'}`` — one per (class, section or whole-class, day, period).
    ``slot_rows`` replaces the database rows (used to test hypothetical
    timetables without touching the database); ``class_ids`` narrows the load.

    ``section_id`` is the concrete section the entry applies to, or ``None``
    when the class has no sections at all.
    """
    rows = slot_rows if slot_rows is not None else _load_rows(class_ids)
    sec_map = sections_map()
    classes = {c.id: c for c in ClassModel.query.all()}

    class_level = defaultdict(dict)    # class_id -> {(day, period): slot}
    section_level = defaultdict(dict)  # (class_id, section_id) -> {(day, period): slot}
    for row in rows:
        if row.section_id is None:
            class_level[row.class_id][(row.day_of_week, row.period_no)] = row
        else:
            section_level[(row.class_id, row.section_id)][(row.day_of_week, row.period_no)] = row

    subject_ids = {row.subject_id for row in rows if row.subject_id}
    subjects = {}
    if subject_ids:
        from app.models import SubjectModel
        for subject in SubjectModel.query.filter(SubjectModel.id.in_(subject_ids)).all():
            subjects[subject.id] = subject

    entries = []

    def _emit(class_id, section_id, day, period, slot):
        class_obj = classes.get(class_id)
        if class_obj is None:
            return
        entries.append({'class': class_obj, 'section_id': section_id,
                        'day': day, 'period': period, 'slot': slot,
                        'subject': subjects.get(slot.subject_id) if slot else None})

    handled_classes = set()
    for class_id, slots in class_level.items():
        handled_classes.add(class_id)
        sections = sec_map.get(class_id, [])
        if not sections:
            for (day, period), slot in slots.items():
                _emit(class_id, None, day, period, slot)
            continue
        section_slots = {sec.id: section_level.get((class_id, sec.id), {})
                         for sec in sections}
        for (day, period), slot in slots.items():
            for sec in sections:
                if section_slots[sec.id].get((day, period)) is None:
                    _emit(class_id, sec.id, day, period, slot)
        for sec in sections:
            for (day, period), slot in section_slots[sec.id].items():
                _emit(class_id, sec.id, day, period, slot)

    # Classes that keep only section grids (no class-level rows at all).
    for (class_id, section_id), slots in section_level.items():
        if class_id in handled_classes:
            continue
        for (day, period), slot in slots.items():
            _emit(class_id, section_id, day, period, slot)

    entries.sort(key=lambda e: (e['class'].name, e['section_id'] or 0,
                                e['day'], e['period']))
    return entries

"""Redesigned Timetables hub (references: timetable1.jpg, timetable2.jpg).

Two predefined templates over the same saved slot data:

* ``matrix``  — teacher-wise chart (timetable1.jpg): teachers down the left,
  period columns across with stacked start/end times, gray vertical
  Assembly/Break columns, cells showing Subject / Class.  Shown per day.
* ``daygrid`` — all-classes chart (timetable2.jpg): every class in ONE grid —
  classes down the left, period columns across, cells showing the teacher
  name, a school-name title and a gray vertical BREAK column.  Shown per day.

Both templates read and write the same :class:`TimetableSlot` rows, so the
school can switch templates at any time without regenerating.  The one-click
generator fills the grid from the school's own settings, classes, subjects
and teaching assignments; everything stays editable afterwards.
"""

import json
from datetime import datetime

from app.database import db
from app.models import (ClassModel, SectionModel, SubjectModel, TeacherModel,
                        TimetableConfig, TimetableMasterConfig, TimetableSlot)
from app.services import timetable as tt
from app.services.timetable_grid import effective_entries, effective_teachers

# The two predefined templates (requirement 8).
REDESIGN_TEMPLATES = {
    'matrix': {'label': 'Teacher-wise Chart',
               'desc': 'Teachers down the side, periods across the top with '
                       'timings — the classic wall chart (timetable1.jpg). '
                       'Shown one day at a time.'},
    'daygrid': {'label': 'All Classes at a Time',
                'desc': 'Every class in one grid: classes down the side, '
                        'periods across the top, the teacher in each cell '
                        '(timetable2.jpg). Shown one day at a time.'},
}
DEFAULT_TEMPLATE = 'matrix'


def _template_key_config():
    """The single master-config row holding the chosen template key.

    Only ``template_key`` is used now (which of the two timed templates the
    hub shows); the period structure moved to School Settings.
    """
    return TimetableMasterConfig.query.first()


def get_template_key():
    """The template chosen on the hub ('matrix' or 'daygrid')."""
    config = _template_key_config()
    key = getattr(config, 'template_key', None) if config else None
    return key if key in REDESIGN_TEMPLATES else DEFAULT_TEMPLATE


def set_template_key(key):
    config = _template_key_config()
    if config is None:
        config = TimetableMasterConfig(id=1)
        db.session.add(config)
    config.template_key = key if key in REDESIGN_TEMPLATES else DEFAULT_TEMPLATE
    config.updated_at = datetime.utcnow()
    db.session.commit()


def master_rows():
    """Period/break rows for the whole school, from the School Settings page.

    Every class shares this structure; changing it on the Settings page changes
    the grid the hub displays and the slots the generator fills.
    """
    return tt.number_rows(tt.build_school_rows())


def write_generated_slots(slots, class_ids, rows_json):
    """Replace the timetables of ``class_ids`` with ``slots`` (generator payload).

    Writes teacher overrides, copies the shared period structure onto each
    class config, and returns how many slots were written.  Used by both the
    redesigned one-click generator and the legacy master apply flow.
    """
    written = 0
    TimetableSlot.query.filter(TimetableSlot.class_id.in_(list(class_ids))) \
        .delete(synchronize_session=False)
    db.session.flush()
    for slot in slots:
        db.session.add(TimetableSlot(class_id=slot['class_id'],
                                     section_id=slot['section_id'],
                                     day_of_week=slot['day'],
                                     period_no=slot['period'],
                                     subject_id=slot['subject_id'],
                                     teacher_id=slot.get('teacher_id')))
        written += 1
    for class_id in class_ids:
        cfg = TimetableConfig.query.filter_by(class_id=class_id).first()
        if cfg is None:
            cfg = TimetableConfig(class_id=class_id)
            db.session.add(cfg)
        cfg.rows_json = rows_json
    return written


def matrix_for_day(day_index, rows, entries, slot_teachers):
    """Teacher × period chart data for one day.

    Returns ``{'columns', 'teachers'}`` where ``columns`` mirrors ``rows``
    (each ``{'kind','start','end','label','no'}``) and ``teachers`` is
    ``[{'teacher', 'cells': {period_no: [line1, line2]}}]`` sorted by name.
    Cell line 1 is the subject, line 2 the class/section label.
    """
    day_entries = [e for e in entries if e['day'] == day_index and e['subject']]
    teacher_ids = set()
    audiences = {}   # (teacher_id, period_no) -> [(subject, label)]
    for entry in day_entries:
        teacher = slot_teachers.get(entry['slot'].id) if entry['slot'] else None
        if teacher is None:
            continue
        section = db.session.get(SectionModel, entry['section_id']) \
            if entry['section_id'] else None
        label = '%s-%s' % (entry['class'].name, section.name) if section \
            else entry['class'].name
        audiences.setdefault((teacher.id, entry['period']), []).append(
            (entry['subject'].name, label))
        teacher_ids.add(teacher.id)

    teachers = (TeacherModel.query.filter(TeacherModel.is_active.is_(True),
                                          TeacherModel.id.in_(teacher_ids or {0}))
                .order_by(TeacherModel.teacher_name).all()
                if teacher_ids else [])
    teacher_rows = []
    for teacher in teachers:
        cells = {}
        for (teacher_id, period_no), items in audiences.items():
            if teacher_id != teacher.id:
                continue
            subject_names = ' / '.join(dict.fromkeys(s for s, _l in items))
            class_labels = ', '.join(l for _s, l in items)
            cells[period_no] = [subject_names, class_labels]
        teacher_rows.append({'teacher': teacher, 'cells': cells})

    columns = [{'kind': r.get('kind'), 'start': r.get('start'), 'end': r.get('end'),
                'label': r.get('label') or ('Break' if r.get('kind') == 'break' else ''),
                'no': r.get('no')}
               for r in rows]
    return {'columns': columns, 'teachers': teacher_rows}


def classes_chart(day_index, rows, entries, slot_teachers):
    """The all-classes chart data for one day (timetable2.jpg layout).

    Returns ``{'columns', 'audiences'}`` where ``columns`` mirrors ``rows``
    and ``audiences`` is ``[{'class', 'section', 'label', 'subjects',
    'cells'}]`` — one row per class (or per section, for a sectioned class),
    ``cells`` mapping ``period_no`` to ``{'teacher_id', 'teacher_name',
    'subject_id', 'subject_name'}`` for that audience's lesson.  A section's
    own saved row wins over the class-level row (same rule as
    :func:`effective_entries`).
    """
    # Effective lesson per audience per period at this day.
    class_level = {}    # (class_id, period_no) -> info
    section_level = {}  # (class_id, section_id, period_no) -> info
    for entry in entries:
        if entry['day'] != day_index or entry['subject'] is None:
            continue
        teacher = slot_teachers.get(entry['slot'].id) if entry['slot'] else None
        info = {'teacher_id': teacher.id if teacher else None,
                'teacher_name': teacher.teacher_name if teacher else None,
                'subject_id': entry['subject'].id,
                'subject_name': entry['subject'].name}
        if entry['section_id'] is None:
            class_level[(entry['class'].id, entry['period'])] = info
        else:
            section_level[(entry['class'].id, entry['section_id'],
                           entry['period'])] = info

    def _lesson(klass, section_id, period_no):
        info = None
        if section_id is not None:
            info = section_level.get((klass.id, section_id, period_no))
        if info is None:
            info = class_level.get((klass.id, period_no))
        return dict(info) if info else None

    classes = ClassModel.query.order_by(ClassModel.name).all()
    audiences = []
    for klass in classes:
        subjects = [s for s in klass.subjects if s.is_active]
        sections = sorted(klass.sections, key=lambda s: s.name)
        if sections:
            for section in sections:
                audiences.append({'class': klass, 'section': section,
                                  'label': '%s-%s' % (klass.name, section.name),
                                  'subjects': subjects, 'cells': {}})
        else:
            audiences.append({'class': klass, 'section': None,
                              'label': klass.name,
                              'subjects': subjects, 'cells': {}})
    period_nos = [r['no'] for r in rows if r.get('kind') != 'break']
    for audience in audiences:
        section_id = audience['section'].id if audience['section'] else None
        for period_no in period_nos:
            info = _lesson(audience['class'], section_id, period_no)
            if info is not None:
                audience['cells'][period_no] = info
    return {'columns': [{'kind': r.get('kind'), 'start': r.get('start'),
                         'end': r.get('end'),
                         'label': r.get('label') or ('Break' if r.get('kind') == 'break' else ''),
                         'no': r.get('no')} for r in rows],
            'audiences': audiences}


def class_grid(class_obj, rows, section_id=None):
    """One editable weekly grid for a class (or one of its sections).

    Returns ``{'class', 'section', 'rows', 'grid', 'teacher_overrides',
    'subjects'}`` where ``grid`` maps ``(day, period_no)`` to the subject id
    and ``teacher_overrides`` maps ``(day, period_no)`` to a manually set
    teacher id (absent = the subject's own teacher applies).
    """
    subjects = [s for s in class_obj.subjects if s.is_active]
    slots = TimetableSlot.query.filter_by(class_id=class_obj.id,
                                          section_id=section_id).all()
    subject_lookup = {s.id: s for s in class_obj.subjects}
    grid = {}
    overrides = {}
    for slot in slots:
        key = (slot.day_of_week, slot.period_no)
        grid[key] = slot.subject_id
        subject = subject_lookup.get(slot.subject_id)
        if slot.teacher_id and (subject is None or slot.teacher_id != subject.teacher_id):
            overrides[key] = slot.teacher_id
    section = db.session.get(SectionModel, section_id) if section_id else None
    return {'class': class_obj, 'section': section, 'rows': rows, 'grid': grid,
            'teacher_overrides': overrides, 'subjects': subjects}

"""Redesigned Timetables system: the only timetable in the app.

Covers both predefined templates (``matrix`` = teacher-wise chart,
``daygrid`` = class weekly grid) end to end:

* rendering, one class at a time, and switching layout
* one-click automatic generation of the school timetable
* manual editing saved directly on the template, then reloaded
* a teacher covering several classes in the SAME period (allowed, badged)
* period/break structure coming from the School Settings page
* sections, roles, and that the legacy surfaces stay gone
"""

from app.database import db
from app.models import (ClassModel, SchoolSettings, SectionModel, SubjectModel,
                        SubjectLibrary, TeacherModel, TeachingAssignment,
                        TimetableConfig, TimetableMasterConfig, TimetableSlot)
from app.models.settings import (DEFAULT_TIMETABLE_STRUCTURE,
                                 get_timetable_structure, set_timetable_structure)
from app.services import timetable as tt
from app.services import timetable_conflicts
from app.services import timetable_redesign as redesign
from app.services.timetable_grid import effective_entries


# --------------------------------------------------------------- helpers

def _teacher(name):
    teacher = TeacherModel(teacher_id_str='TR%d' % (TeacherModel.query.count() + 100),
                           teacher_name=name, qualification='MSc')
    db.session.add(teacher)
    db.session.flush()
    return teacher


def _class_with_subjects(name, teacher=None):
    """A class offering Mathematics plus three more subjects."""
    base, suffix = name, 1
    while ClassModel.query.filter_by(name=name).first() is not None:
        suffix += 1
        name = '%s (%d)' % (base, suffix)
    klass = ClassModel(name=name)
    db.session.add(klass)
    db.session.flush()

    lib_math = SubjectLibrary.query.filter_by(name='Mathematics').first()
    if lib_math is None:
        lib_math = SubjectLibrary(name='Mathematics')
        db.session.add(lib_math)
        db.session.flush()
    math = SubjectModel(name='Mathematics', class_id=klass.id,
                        teacher_id=teacher.id if teacher else None,
                        library_id=lib_math.id)
    db.session.add(math)
    for subject_name in ('English', 'Urdu', 'Drawing'):
        db.session.add(SubjectModel(name=subject_name, class_id=klass.id))
    db.session.flush()
    return klass, math


def _grid_form(klass, cells, section_id=None):
    """Hub save payload for one grid.

    ``cells`` maps (day, period_no) to (subject_id, teacher_id); either may be
    None ('' means no lesson / "Auto").  Field names carry the grid's section
    prefix exactly as the page renders them.
    """
    prefix = 'slot_s%d_' % section_id if section_id is not None else 'slot_'
    data = {}
    if section_id is not None:
        data['section_id_%d' % section_id] = '1'
    for row in redesign.master_rows():
        if row.get('kind') == 'break' or row.get('no') is None:
            continue
        for day in range(6):
            subject_id, teacher_id = cells.get((day, row['no']), (None, None))
            data['%s%d_%d_subject' % (prefix, day, row['no'])] = \
                str(subject_id) if subject_id else ''
            data['%s%d_%d_teacher' % (prefix, day, row['no'])] = \
                str(teacher_id) if teacher_id else ''
    return data


def _matrix_form(klass, section_cells):
    """Combined payload for a sectioned class (the chart's single Save button).

    ``section_cells`` maps section_id -> the ``cells`` dict for that section.
    """
    data = {}
    for section_id, cells in section_cells.items():
        data.update(_grid_form(klass, cells, section_id=section_id))
    return data


def _set_structure(**overrides):
    structure = dict(DEFAULT_TIMETABLE_STRUCTURE)
    structure.update(overrides)
    set_timetable_structure(structure['periods_per_day'],
                            structure['period_minutes'],
                            structure['break_after'],
                            structure['break_minutes'],
                            structure['break_label'],
                            assembly_minutes=structure['assembly_minutes'],
                            assembly_label=structure['assembly_label'])


# ------------------------------------------------- 1. rendering / templates

def test_hub_shows_class_and_layout_pickers(admin_client, app, seed):
    response = admin_client.get('/timetables')
    assert response.status_code == 200
    html = response.data.decode()
    assert 'Which class?' in html
    assert 'Which layout?' in html
    assert 'Generate Timetable' in html
    assert 'All classes' in html
    # Both predefined layouts are offered by name.
    assert 'Teacher-wise Chart' in html
    assert 'All Classes at a Time' in html


def test_hub_loads_one_class_at_a_time(admin_client, app, seed):
    teacher = _teacher('Ms Hina')
    klass, math = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()

    response = admin_client.get('/timetables?class_id=%d' % klass.id)
    assert response.status_code == 200
    html = response.data.decode()
    # The editable grid for this class is on the page, ready to edit.
    assert 'tt-edit' in html
    assert 'Save Timetable' in html
    assert 'name="slot_0_1_subject"' in html


def test_layout_switch_keeps_the_class(admin_client, app, seed):
    teacher = _teacher('Ms Hina')
    klass, _math = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()

    response = admin_client.get('/timetables?class_id=%d&template_key=daygrid' % klass.id)
    assert response.status_code == 200
    html = response.data.decode()
    assert 'All Classes at a Time' in html
    # The class stays selected when previewing the other layout.
    assert 'value="%d" selected' % klass.id in html


def test_missing_template_key_defaults_cleanly(app, admin_client, seed):
    """A fresh install has no master-config row; the page still renders."""
    TimetableMasterConfig.query.delete()
    db.session.commit()
    assert admin_client.get('/timetables').status_code == 200
    with app.app_context():
        assert get_timetable_structure() == DEFAULT_TIMETABLE_STRUCTURE


# ------------------------------------------------------- 2. auto generation

def test_one_click_generate_for_a_single_class(admin_client, app, seed):
    teacher = _teacher('Ms Hina')
    klass, _math = _class_with_subjects('Class 1', teacher=teacher)
    other, _om = _class_with_subjects('Class 2', teacher=teacher)
    db.session.commit()

    response = admin_client.post('/timetables/generate',
                                 data={'class_ids': str(klass.id)},
                                 follow_redirects=True)
    assert response.status_code == 200
    assert 'Timetable ready' in response.data.decode()

    slots = TimetableSlot.query.filter_by(class_id=klass.id).all()
    assert slots
    # Only the chosen class was generated.
    assert TimetableSlot.query.filter_by(class_id=other.id).count() == 0
    # Teaching days come from School Settings (Mon-Fri on a fresh install).
    assert all(slot.day_of_week in (0, 1, 2, 3, 4) for slot in slots)
    # The period structure was copied onto the generated class.
    cfg = TimetableConfig.query.filter_by(class_id=klass.id).first()
    assert cfg is not None and cfg.rows_json


def test_one_click_generate_for_all_classes(admin_client, app, seed):
    teacher = _teacher('Ms Hina')
    klass1, _m1 = _class_with_subjects('Class 1', teacher=teacher)
    klass2, _m2 = _class_with_subjects('Class 2', teacher=teacher)
    db.session.commit()

    response = admin_client.post('/timetables/generate',
                                 data={'class_ids': 'all'},
                                 follow_redirects=True)
    assert response.status_code == 200
    for klass in (klass1, klass2):
        assert TimetableSlot.query.filter_by(class_id=klass.id).count() > 0


def test_generate_remembers_the_chosen_layout(admin_client, app, seed):
    teacher = _teacher('Ms Hina')
    klass, _math = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()

    admin_client.post('/timetables/generate',
                      data={'class_ids': str(klass.id), 'template_key': 'daygrid'})
    assert TimetableMasterConfig.query.first().template_key == 'daygrid'


# ------------------------------------------- 3. one teacher, several classes

def test_teacher_may_teach_two_classes_in_the_same_period(admin_client, app, seed):
    """The new requirement: sharing a period is allowed, not an error.

    Period 2: Class 1 Science + Class 3 English, same teacher.
    """
    teacher = _teacher('Maryam Iqbal')
    klass1, math1 = _class_with_subjects('Class 1', teacher=teacher)
    klass3, math3 = _class_with_subjects('Class 3', teacher=teacher)
    english1 = SubjectModel.query.filter_by(class_id=klass1.id, name='English').first()
    db.session.commit()

    # Same teacher, same day+period, two different classes and subjects.
    first = admin_client.post('/timetables/save/%d' % klass1.id,
                              data=_grid_form(klass1, {(1, 2): (english1.id, teacher.id)}),
                              follow_redirects=True)
    assert first.status_code == 200
    assert 'Saved' in first.data.decode()

    second = admin_client.post('/timetables/save/%d' % klass3.id,
                               data=_grid_form(klass3, {(1, 2): (math3.id, teacher.id)}),
                               follow_redirects=True)
    html = second.data.decode()
    # The save is accepted - no "not saved" / "double-booked" refusal anywhere.
    assert 'Saved' in html
    assert 'Not saved' not in html
    assert 'double-booked' not in html

    # Both lessons are stored for the same teacher, day and period.
    stored = TimetableSlot.query.filter(
        TimetableSlot.day_of_week == 1, TimetableSlot.period_no == 2).all()
    assert len(stored) == 2
    assert {s.class_id for s in stored} == {klass1.id, klass3.id}


def test_shared_period_is_reported_not_blocked(admin_client, app, seed):
    teacher = _teacher('Maryam Iqbal')
    klass1, math1 = _class_with_subjects('Class 1', teacher=teacher)
    klass3, math3 = _class_with_subjects('Class 3', teacher=teacher)
    db.session.commit()

    admin_client.post('/timetables/save/%d' % klass1.id,
                      data=_grid_form(klass1, {(1, 2): (math1.id, teacher.id)}))
    admin_client.post('/timetables/save/%d' % klass3.id,
                      data=_grid_form(klass3, {(1, 2): (math3.id, teacher.id)}))

    # Reported for information...
    shared = timetable_conflicts.shared_teacher_map()
    assert (1, 2) in shared
    assert teacher.id in shared[(1, 2)]
    assert len(shared[(1, 2)][teacher.id]) == 2

    # ...and surfaced on the page as a friendly note plus a cell badge.
    html = admin_client.get('/timetables?class_id=%d&day=1' % klass1.id).data.decode()
    assert 'teacher-period(s) are shared' in html
    assert 'tt-shared' in html


def test_generator_keeps_shared_teachers(admin_client, app, seed):
    """Generate must not skip lessons just because a teacher is shared."""
    teacher = _teacher('Ms Shared')
    klass1, _m1 = _class_with_subjects('Class 1', teacher=teacher)
    klass2, _m2 = _class_with_subjects('Class 2', teacher=teacher)
    db.session.commit()
    _set_structure(periods_per_day=4, break_after=2)

    admin_client.post('/timetables/generate', data={'class_ids': 'all'})
    for klass in (klass1, klass2):
        slots = TimetableSlot.query.filter_by(class_id=klass.id).all()
        assert slots, '%s got no lessons' % klass.name
    # The school's 4-period structure was respected.
    assert not TimetableSlot.query.filter(TimetableSlot.period_no > 4).count()


# ---------------------------------------------------- 4. editing and saving

def test_manual_edit_saves_and_reloads(admin_client, app, seed):
    teacher = _teacher('Ms A')
    klass, math = _class_with_subjects('Class 1', teacher=teacher)
    english = SubjectModel.query.filter_by(class_id=klass.id,
                                           name='English').first()
    db.session.commit()

    cells = {(0, 1): (math.id, None), (1, 2): (english.id, None)}
    response = admin_client.post('/timetables/save/%d' % klass.id,
                                 data=_grid_form(klass, cells),
                                 follow_redirects=True)
    assert response.status_code == 200
    assert 'Saved' in response.data.decode()

    stored = {(s.day_of_week, s.period_no): s.subject_id
              for s in TimetableSlot.query.filter_by(class_id=klass.id).all()}
    assert stored == {(0, 1): math.id, (1, 2): english.id}

    # Reload: the page shows the saved lessons in the editable grid.
    reloaded = redesign.class_grid(klass, redesign.master_rows())
    assert reloaded['grid'][(0, 1)] == math.id
    assert reloaded['grid'][(1, 2)] == english.id


def test_saved_timetable_survives_template_switch(admin_client, app, seed):
    teacher = _teacher('Ms B')
    klass, math = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()

    admin_client.post('/timetables/save/%d' % klass.id,
                      data=_grid_form(klass, {(2, 3): (math.id, None)}))
    before = {(s.day_of_week, s.period_no): s.subject_id
              for s in TimetableSlot.query.filter_by(class_id=klass.id).all()}
    assert before == {(2, 3): math.id}

    for template_key in ('daygrid', 'matrix'):
        response = admin_client.get(
            '/timetables?class_id=%d&template_key=%s' % (klass.id, template_key))
        assert response.status_code == 200
        after = {(s.day_of_week, s.period_no): s.subject_id
                 for s in TimetableSlot.query.filter_by(class_id=klass.id).all()}
        assert after == before, 'slots changed when viewing %s' % template_key


def test_teacher_override_is_stored_only_when_different(admin_client, app, seed):
    teacher_a = _teacher('Ms A')
    teacher_b = _teacher('Ms B')
    klass, math = _class_with_subjects('Class 1', teacher=teacher_a)
    db.session.commit()

    # Posting the subject's own teacher means "inherit" -> no override stored.
    admin_client.post('/timetables/save/%d' % klass.id,
                      data=_grid_form(klass, {(0, 1): (math.id, teacher_a.id)}))
    slot = TimetableSlot.query.filter_by(class_id=klass.id,
                                         day_of_week=0, period_no=1).one()
    assert slot.teacher_id is None

    # Posting a different teacher stores the override.
    admin_client.post('/timetables/save/%d' % klass.id,
                      data=_grid_form(klass, {(0, 1): (math.id, teacher_b.id)}))
    slot = TimetableSlot.query.filter_by(class_id=klass.id,
                                         day_of_week=0, period_no=1).one()
    assert slot.teacher_id == teacher_b.id


def test_sectioned_class_saves_every_section_in_one_go(admin_client, app, seed):
    """The chart's single Save button writes both section grids."""
    teacher = _teacher('Ms A')
    klass, math = _class_with_subjects('Class 1', teacher=teacher)
    section_a = SectionModel(name='A', class_id=klass.id)
    section_b = SectionModel(name='B', class_id=klass.id)
    english = SubjectModel.query.filter_by(class_id=klass.id, name='English').first()
    db.session.add_all([section_a, section_b])
    db.session.commit()

    data = _matrix_form(klass, {
        section_a.id: {(0, 1): (math.id, None)},
        section_b.id: {(0, 1): (english.id, None)},
    })
    response = admin_client.post('/timetables/save/%d' % klass.id,
                                 data=data, follow_redirects=True)
    assert response.status_code == 200
    assert 'Saved' in response.data.decode()

    stored = {(s.section_id, s.day_of_week, s.period_no): s.subject_id
              for s in TimetableSlot.query.filter_by(class_id=klass.id).all()}
    assert stored[(section_a.id, 0, 1)] == math.id
    assert stored[(section_b.id, 0, 1)] == english.id


def test_section_grid_overrides_class_grid(admin_client, app, seed):
    teacher = _teacher('Ms A')
    klass, math = _class_with_subjects('Class 1', teacher=teacher)
    section_a = SectionModel(name='A', class_id=klass.id)
    db.session.add(section_a)
    english = SubjectModel.query.filter_by(class_id=klass.id, name='English').first()
    db.session.commit()

    admin_client.post('/timetables/save/%d' % klass.id,
                      data=_grid_form(klass, {(0, 1): (math.id, None)}))
    admin_client.post('/timetables/save/%d' % klass.id,
                      data=_grid_form(klass, {(0, 1): (english.id, None)},
                                      section_id=section_a.id))

    entries = effective_entries(class_ids=[klass.id])
    at_slot = [e for e in entries if e['day'] == 0 and e['period'] == 1]
    by_section = {e['section_id']: e['subject'].id for e in at_slot}
    # The section's own grid row wins for that section.
    assert by_section[section_a.id] == english.id
    stored = {(s.section_id, s.day_of_week, s.period_no): s.subject_id
              for s in TimetableSlot.query.filter_by(class_id=klass.id).all()}
    assert stored[(None, 0, 1)] == math.id, 'class-level row is still saved'
    assert stored[(section_a.id, 0, 1)] == english.id


def test_hub_edit_grid_follows_school_days(admin_client, app, seed):
    """Default settings have Saturday off, so saved slots never land on it."""
    math1 = db.session.get(SubjectModel, seed['subject_id'])
    db.session.commit()
    admin_client.post('/timetables/save/%d' % seed['class_id'],
                      data=_grid_form(None, {(5, 1): (math1.id, None)}),
                      follow_redirects=True)
    slots = TimetableSlot.query.filter_by(class_id=seed['class_id']).all()
    assert all(slot.day_of_week != 5 for slot in slots), \
        'Saturday (default off) must stay empty'


# ------------------------------------------ 5. period/break from School Settings

def test_period_structure_comes_from_school_settings(app, seed):
    with app.app_context():
        assert get_timetable_structure() == DEFAULT_TIMETABLE_STRUCTURE
        defaults = tt.build_school_rows()
        assert sum(1 for r in defaults if r['kind'] == 'period') == 8
        assert sum(1 for r in defaults if r['kind'] == 'break') == 1
        assert defaults[0]['start'] == '08:30'

        _set_structure(periods_per_day=6, period_minutes=35, break_after=3,
                       break_minutes=15, break_label='Short Break')
        rows = tt.build_school_rows()
        assert sum(1 for r in rows if r['kind'] == 'period') == 6
        breaks = [r for r in rows if r['kind'] == 'break']
        assert len(breaks) == 1 and breaks[0]['label'] == 'Short Break'
        assert breaks[0]['start'] == '10:15' and breaks[0]['end'] == '10:30'

        _set_structure(break_after=0)
        assert all(r['kind'] == 'period' for r in tt.build_school_rows())


def test_school_settings_page_saves_period_structure(admin_client, app, seed):
    response = admin_client.post('/settings', data={
        'action': 'save_academic_settings',
        'academic_session': '2025-2026',
        'result_announcement_date': '',
        'school_start_time': '08:00',
        'school_end_time': '14:00',
        'attendance_grace_minutes': '5',
        'saturday_off': 'on',
        'sunday_off': 'on',
        'custom_off_days': '',
        'timetable_periods_per_day': '7',
        'timetable_period_minutes': '45',
        'timetable_break_after': '2',
        'timetable_break_minutes': '25',
        'timetable_break_label': 'Lunch',
    }, follow_redirects=True)
    assert response.status_code == 200

    structure = get_timetable_structure()
    assert structure['periods_per_day'] == 7
    assert structure['period_minutes'] == 45
    assert structure['break_after'] == 2
    assert structure['break_minutes'] == 25
    assert structure['break_label'] == 'Lunch'

    rows = tt.build_school_rows()
    assert rows[0]['start'] == '08:00'
    assert sum(1 for r in rows if r['kind'] == 'period') == 7
    html = admin_client.get('/settings?tab=academic').data.decode()
    assert 'Timetable Periods' in html
    assert 'name="timetable_periods_per_day"' in html
    assert 'value="Lunch"' in html


def test_generator_respects_settings_period_count(admin_client, app, seed):
    teacher = _teacher('Ms A')
    klass, _math = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()
    _set_structure(periods_per_day=4, break_after=2)

    admin_client.post('/timetables/generate', data={'class_ids': str(klass.id)})
    slots = TimetableSlot.query.filter_by(class_id=klass.id).all()
    assert slots
    assert not TimetableSlot.query.filter(TimetableSlot.period_no > 4).count()


def test_settings_link_is_reachable_from_the_hub(admin_client, app, seed):
    html = admin_client.get('/timetables').data.decode()
    assert '/settings?tab=academic' in html


# ---------------------------------------------------- 6. roles and cleanup

def test_hub_is_blocked_for_teachers_but_schedules_are_visible(teacher_client, app, seed):
    assert teacher_client.get('/timetables').status_code == 403
    assert teacher_client.get('/timetables/teachers').status_code == 200


# --------------------------------------- 7. template 2: all classes at a time

def test_all_classes_chart_renders_one_grid(admin_client, app, seed):
    """timetable2.jpg layout: every class in ONE grid with a school title."""
    teacher = _teacher('Sir Sadam')
    klass1, _m1 = _class_with_subjects('Play Group', teacher=teacher)
    klass2, _m2 = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()

    admin_client.post('/timetables/generate',
                      data={'class_ids': 'all', 'template_key': 'daygrid'})
    html = admin_client.get('/timetables?template_key=daygrid&day=0').data.decode()
    assert 'tt2-title' in html                       # school-name title
    assert 'tt-ref2' in html                         # the single grid
    # Both classes appear as rows in the same grid.
    assert ('cell_%d_all_' % klass1.id) in html
    assert ('cell_%d_all_' % klass2.id) in html
    # One Save button for the whole chart.
    assert 'Save All Classes' in html


def test_save_all_writes_one_day_and_merges_the_rest(admin_client, app, seed):
    teacher = _teacher('Ms A')
    klass1, math1 = _class_with_subjects('Class 1', teacher=teacher)
    klass2, math2 = _class_with_subjects('Class 2', teacher=teacher)
    db.session.commit()

    admin_client.post('/timetables/generate',
                      data={'class_ids': 'all', 'template_key': 'daygrid'})
    before_other_days = TimetableSlot.query.filter(
        TimetableSlot.day_of_week != 0).count()
    assert before_other_days > 0

    # Replace Monday for both classes with a single lesson each.
    response = admin_client.post('/timetables/save-all', data={
        'day': '0',
        'cell_%d_all_1_subject' % klass1.id: str(math1.id),
        'cell_%d_all_1_teacher' % klass1.id: '',
        'cell_%d_all_1_subject' % klass2.id: str(math2.id),
        'cell_%d_all_1_teacher' % klass2.id: '',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert 'Saved' in response.data.decode()

    monday = TimetableSlot.query.filter(
        TimetableSlot.day_of_week == 0,
        TimetableSlot.class_id.in_([klass1.id, klass2.id])).all()
    assert {(s.class_id, s.period_no) for s in monday} == \
        {(klass1.id, 1), (klass2.id, 1)}, 'Monday replaced by the posted cells'
    after_other_days = TimetableSlot.query.filter(
        TimetableSlot.day_of_week != 0).count()
    assert after_other_days == before_other_days, \
        'other days must stay untouched (per-day merge)'


def test_save_all_allows_shared_teacher_same_period(admin_client, app, seed):
    """One teacher, same period, two classes — saved without complaint."""
    teacher = _teacher('Maryam Iqbal')
    klass1, math1 = _class_with_subjects('Class 1', teacher=teacher)
    klass2, math2 = _class_with_subjects('Class 2', teacher=teacher)
    english1 = SubjectModel.query.filter_by(class_id=klass1.id, name='English').first()
    db.session.commit()

    response = admin_client.post('/timetables/save-all', data={
        'day': '1',
        'cell_%d_all_2_subject' % klass1.id: str(english1.id),
        'cell_%d_all_2_teacher' % klass1.id: str(teacher.id),
        'cell_%d_all_2_subject' % klass2.id: str(math2.id),
        'cell_%d_all_2_teacher' % klass2.id: str(teacher.id),
    }, follow_redirects=True)
    html = response.data.decode()
    assert response.status_code == 200
    assert 'Not saved' not in html and 'double-booked' not in html
    lessons = TimetableSlot.query.filter(
        TimetableSlot.day_of_week == 1, TimetableSlot.period_no == 2,
        TimetableSlot.class_id.in_([klass1.id, klass2.id])).all()
    assert {s.class_id for s in lessons} == {klass1.id, klass2.id}
    # Both lessons are effectively taught by Maryam Iqbal: the English row
    # stores her as an override, the Maths row inherits its own teacher.
    assert all((s.teacher_id == teacher.id) or
               (s.subject is not None and s.subject.teacher_id == teacher.id)
               for s in lessons)


# --------------------------------------------------- 8. assembly (timetable1)

def test_assembly_column_from_settings(app, seed):
    with app.app_context():
        _set_structure(assembly_minutes=10, assembly_label='Assembly')
        rows = tt.build_school_rows()
        assembly = rows[0]
        assert assembly['kind'] == 'break' and assembly['label'] == 'Assembly'
        # The first period starts AFTER the assembly slot.
        assert assembly['start'] == '08:30' and assembly['end'] == '08:40'
        assert rows[1]['kind'] == 'period' and rows[1]['start'] == '08:40'

        _set_structure(assembly_minutes=0)
        assert tt.build_school_rows()[0]['kind'] == 'period'


def test_assembly_renders_in_teacher_chart(admin_client, app, seed):
    teacher = _teacher('Ms Hina')
    klass, _math = _class_with_subjects('Class 1', teacher=teacher)
    db.session.commit()
    with app.app_context():
        _set_structure(assembly_minutes=10)

    admin_client.post('/timetables/generate',
                      data={'class_ids': str(klass.id), 'template_key': 'matrix'})
    html = admin_client.get('/timetables?class_id=%d&template_key=matrix' % klass.id) \
        .data.decode()
    assert 'tt-vertical' in html
    assert 'Assembly' in html


def test_settings_page_saves_assembly_fields(admin_client, app, seed):
    response = admin_client.post('/settings', data={
        'action': 'save_academic_settings',
        'academic_session': '2025-2026',
        'result_announcement_date': '',
        'school_start_time': '08:00',
        'school_end_time': '14:00',
        'attendance_grace_minutes': '0',
        'saturday_off': 'on',
        'sunday_off': 'on',
        'custom_off_days': '',
        'timetable_periods_per_day': '6',
        'timetable_period_minutes': '45',
        'timetable_break_after': '3',
        'timetable_break_minutes': '20',
        'timetable_break_label': 'Break',
        'timetable_assembly_minutes': '15',
        'timetable_assembly_label': 'Morning Assembly',
    }, follow_redirects=True)
    assert response.status_code == 200
    structure = get_timetable_structure()
    assert structure['assembly_minutes'] == 15
    assert structure['assembly_label'] == 'Morning Assembly'
    html = admin_client.get('/settings?tab=academic').data.decode()
    assert 'name="timetable_assembly_minutes"' in html
    assert 'value="Morning Assembly"' in html


def test_legacy_timetable_surfaces_are_gone(admin_client, app, seed):
    for url in ('/timetables/master', '/timetables/master/grid',
                '/timetables/substitutions', '/classes/%d/timetable' % seed['class_id']):
        assert admin_client.get(url).status_code == 404, url

    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    for gone in ('main.master_timetable', 'main.master_grid', 'main.substitutions',
                 'main.class_timetable', 'main.timetable_autofix',
                 'main.master_preview', 'main.master_apply', 'main.master_cancel'):
        assert gone not in endpoints, gone


def test_legacy_helpers_and_transient_table_are_removed(app, seed):
    for name in ('build_rows', 'get_config', 'save_config', 'autofill_pairs',
                 'resolve_incharge', 'build_timetable_pdf', 'build_master_grid_pdf',
                 'TEMPLATES', 'MAX_PERIODS', 'MAX_ROWS'):
        assert not hasattr(tt, name), name

    import sqlite3
    from flask import current_app
    with app.app_context():
        database = current_app.config['SQLALCHEMY_DATABASE_URI'].split('///')[-1]
        con = sqlite3.connect(database)
        names = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
    assert 'timetable_drafts' not in names
    for kept in ('timetable_slots', 'timetable_configs', 'timetable_master_configs',
                 'timetable_overrides', 'teaching_assignments'):
        assert kept in names, kept

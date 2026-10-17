"""One-page timetable sheet: columns from School Settings, rows with merged
classes, teacher cells, save/reload and the single-page PDF."""
import pytest

from app.database import db
from app.models import ClassModel, TeacherModel
from app.models.settings import set_timetable_structure
from app.services import timetable_sheet as ts


def _teacher(name, code):
    from datetime import date
    t = TeacherModel(teacher_id_str=code, teacher_name=name, qualification='BA',
                     joining_date=date(2024, 1, 1))
    db.session.add(t)
    db.session.commit()
    return t.id


def _class(name):
    c = ClassModel(name=name)
    db.session.add(c)
    db.session.commit()
    return c.id


def _structure(periods=4, minutes=40, break_after=2, break_minutes=15, assembly=0):
    set_timetable_structure(periods, minutes, break_after, break_minutes, 'Break',
                            assembly, 'Assembly')


def test_columns_follow_settings(app):
    _structure(periods=4, break_after=2, assembly=0)
    keys = [c['key'] for c in ts.build_columns()]
    assert keys == ['p1', 'p2', 'break', 'p3', 'p4']          # no assembly column

    _structure(periods=3, break_after=0, assembly=10)
    keys = [c['key'] for c in ts.build_columns()]
    assert keys == ['assembly', 'p1', 'p2', 'p3']              # assembly on, no break


def test_column_times(app):
    _structure(periods=2, minutes=45, break_after=1, break_minutes=15, assembly=15)
    cols = ts.with_times(ts.build_columns(), '07:45')
    assert [c['time'] for c in cols] == [
        '7:45 to 8:00', '8:00 to 8:45', '8:45 to 9:00', '9:00 to 9:45']


def test_save_and_reload_with_merged_classes(admin_client, app, seed):
    _structure()
    c2, c3 = _class('Class 2'), _class('Class 3')
    t1, t2 = _teacher('Ms Aisha', 'T1'), _teacher('Mr Bilal', 'T2')
    payload = {'start_time': '07:45', 'rows': [
        {'class_ids': [seed['class_id']], 'cells': {'1': t1, '2': t2}},
        {'class_ids': [c2, c3], 'cells': {'1': t2, '3': t1}},       # merged row
    ]}
    res = admin_client.post('/timetable/save', json=payload)
    assert res.status_code == 200 and res.get_json()['ok']

    sheet = ts.load_sheet()
    assert len(sheet) == 2
    assert sheet[1]['label'] == 'Class 2 + Class 3'
    assert sheet[1]['cells'] == {'1': t2, '3': t1}
    assert ts.get_start_time() == '07:45'

    page = admin_client.get('/timetable')
    assert page.status_code == 200
    assert b'Class 2' in page.data and b'Ms Aisha' in page.data

    # saving again replaces (editable later)
    payload['rows'] = payload['rows'][:1]
    assert admin_client.post('/timetable/save', json=payload).status_code == 200
    assert len(ts.load_sheet()) == 1


@pytest.mark.parametrize('bad', [
    {'start_time': '25:99', 'rows': []},
    {'start_time': '08:00', 'rows': [{'class_ids': [], 'cells': {}}]},
    {'start_time': '08:00', 'rows': [{'class_ids': [99999], 'cells': {}}]},
    {'start_time': '08:00', 'rows': 'x'},
])
def test_save_rejects_bad_data(admin_client, app, bad):
    res = admin_client.post('/timetable/save', json=bad)
    assert res.status_code == 400 and not res.get_json()['ok']


def test_class_cannot_be_in_two_rows(admin_client, app, seed):
    cid = seed['class_id']
    res = admin_client.post('/timetable/save', json={'start_time': '08:00', 'rows': [
        {'class_ids': [cid], 'cells': {}}, {'class_ids': [cid], 'cells': {}}]})
    assert res.status_code == 400 and 'more than one row' in res.get_json()['error']


def test_unknown_teacher_rejected(admin_client, app, seed):
    res = admin_client.post('/timetable/save', json={'start_time': '08:00', 'rows': [
        {'class_ids': [seed['class_id']], 'cells': {'1': 424242}}]})
    assert res.status_code == 400


def test_periods_removed_from_settings_are_ignored(admin_client, app, seed):
    _structure(periods=3)
    t1 = _teacher('Ms Aisha', 'T1')
    res = admin_client.post('/timetable/save', json={'start_time': '08:00', 'rows': [
        {'class_ids': [seed['class_id']], 'cells': {'1': t1, '9': t1}}]})
    assert res.status_code == 200
    assert ts.load_sheet()[0]['cells'] == {'1': t1}


@pytest.mark.parametrize('orientation', ['landscape', 'portrait'])
def test_pdf_is_a_single_page(admin_client, app, seed, orientation):
    _structure(periods=8, break_after=4, assembly=15)
    t1 = _teacher('Ms Aisha Khan', 'T1')
    rows = [{'class_ids': [seed['class_id']], 'cells': {str(i): t1 for i in range(1, 9)}}]
    for n in range(25):                       # many rows must still fit one page
        rows.append({'class_ids': [_class('Section %d' % n)],
                     'cells': {str(i): t1 for i in range(1, 9)}})
    assert admin_client.post('/timetable/save',
                             json={'start_time': '07:45', 'rows': rows}).status_code == 200
    res = admin_client.get('/timetable/pdf?orientation=' + orientation)
    assert res.status_code == 200
    assert res.mimetype == 'application/pdf'
    assert res.data.startswith(b'%PDF')
    assert res.data.count(b'/Type /Page\n') + res.data.count(b'/Type /Page ') == 1 \
        or res.data.count(b'/Type /Page') - res.data.count(b'/Type /Pages') == 1


def test_empty_pdf_still_renders(admin_client, app):
    assert admin_client.get('/timetable/pdf').data.startswith(b'%PDF')


def test_teachers_cannot_open_timetable(teacher_client, app):
    for path in ('/timetable', '/timetable/pdf'):
        assert teacher_client.get(path).status_code in (302, 403)
    assert teacher_client.post('/timetable/save', json={'rows': []}).status_code in (302, 403)

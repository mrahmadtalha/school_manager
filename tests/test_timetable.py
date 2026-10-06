"""Timetable: template generation, editing, teacher names and PDF export."""

import pytest

from app.database import db
from app.models import ClassModel, SubjectModel, TeacherModel, TimetableSlot
from app.models.class_ import TimetableConfig
from app.services import timetable as tt


@pytest.fixture()
def tt_data(app, seed):
    """Seeded class gets a teacher (assigned to it) on its subject, plus a 2nd subject."""
    teacher = TeacherModel(teacher_id_str='T900', teacher_name='Ms Hina',
                           qualification='MSc', assigned_class='Class 1')
    db.session.add(teacher)
    db.session.flush()
    subject = db.session.get(SubjectModel, seed['subject_id'])
    subject.teacher_id = teacher.id
    db.session.add(SubjectModel(name='English', class_id=seed['class_id']))
    db.session.commit()
    return {'class_id': seed['class_id'], 'teacher_id': teacher.id,
            'subject_id': seed['subject_id']}


def _url(class_id, query=''):
    return '/classes/%d/timetable%s' % (class_id, query)


def test_build_rows_has_timings_and_break():
    rows = tt.number_rows(tt.build_rows('standard', '08:00', 40))
    assert rows[0]['start'] == '08:00' and rows[0]['end'] == '08:40'
    assert [r['kind'] for r in rows].count('period') == 8
    assert rows[4]['kind'] == 'break' and rows[4]['start'] == '10:40'


def test_autofill_has_no_back_to_back_repeats():
    pairs = tt.autofill_pairs([1, 2, 3], 8)
    assert all(pairs[(d, p)] != pairs[(d, p + 1)] for d in range(6) for p in range(1, 8))


def test_generate_fills_subjects_and_stays_editable(admin_client, tt_data):
    cid = tt_data['class_id']
    resp = admin_client.post(_url(cid), data={
        'action': 'generate', 'template': 'primary', 'start_time': '08:00',
        'minutes': '35', 'autofill': '1'})
    assert resp.status_code == 302
    assert TimetableSlot.query.filter_by(class_id=cid).count() == 6 * 6
    page = admin_client.get(_url(cid)).get_data(as_text=True)
    assert 'Period 6' in page and '08:00' in page

    admin_client.post(_url(cid), data={
        'action': 'save', 'row_count': '2',
        'row_kind_0': 'period', 'row_start_0': '09:00', 'row_end_0': '09:45',
        'row_kind_1': 'break', 'row_start_1': '09:45', 'row_end_1': '10:00',
        'row_label_1': 'Tea', 'slot_0_0': str(tt_data['subject_id'])})
    assert TimetableSlot.query.filter_by(class_id=cid).count() == 1
    rows = tt.load_rows(cid)
    assert rows[0]['start'] == '09:00' and rows[1]['label'] == 'Tea'


def test_invalid_times_are_rejected(admin_client, tt_data):
    cid = tt_data['class_id']
    admin_client.post(_url(cid), data={
        'action': 'save', 'row_count': '1', 'row_kind_0': 'period',
        'row_start_0': '10:00', 'row_end_0': '09:00'})
    assert TimetableConfig.query.filter_by(class_id=cid).first() is None


def test_incharge_and_pdf(admin_client, tt_data):
    cid = tt_data['class_id']
    admin_client.post(_url(cid), data={'action': 'generate', 'template': 'standard',
                                       'start_time': '08:30', 'minutes': '40', 'autofill': '1'})
    # a lone teacher assigned to the class is picked up automatically
    teacher, auto = tt.resolve_incharge(db.session.get(ClassModel, cid), tt.get_config(cid))
    assert teacher.id == tt_data['teacher_id'] and auto

    # an explicit choice wins and is saved with the timetable
    admin_client.post(_url(cid), data={'action': 'save', 'row_count': '1',
                                       'row_kind_0': 'period', 'row_start_0': '08:00',
                                       'row_end_0': '08:40',
                                       'incharge_teacher_id': str(tt_data['teacher_id'])})
    teacher, auto = tt.resolve_incharge(db.session.get(ClassModel, cid), tt.get_config(cid))
    assert teacher.id == tt_data['teacher_id'] and not auto

    for query in ('?pdf=1&teachers=1', '?pdf=1'):
        pdf = admin_client.get(_url(cid, query))
        assert pdf.status_code == 200
        assert pdf.mimetype == 'application/pdf' and pdf.data.startswith(b'%PDF')


def test_teacher_role_is_read_only_but_can_download(teacher_client, tt_data):
    cid = tt_data['class_id']
    teacher_client.post(_url(cid), data={'action': 'generate', 'template': 'standard',
                                         'start_time': '08:30'})
    assert TimetableSlot.query.filter_by(class_id=cid).count() == 0
    assert teacher_client.get(_url(cid)).status_code == 200
    assert teacher_client.get(_url(cid, '?pdf=1')).data.startswith(b'%PDF')
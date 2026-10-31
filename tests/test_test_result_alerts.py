from datetime import date

import itertools

import pytest

from app import create_app
from app.database import db
from app.models import (AutomationSettings, ClassModel, MessageQueue,
                        StudentMarkModel, StudentModel, SubjectModel, TestModel)
from app.services.test_result_alerts import queue_test_result_alerts


_n = itertools.count(1)


@pytest.fixture()
def batch():
    n = next(_n)
    app = create_app()
    with app.app_context():
        cls = ClassModel(name='TR Class %d' % n)
        db.session.add(cls)
        db.session.flush()
        subs = [SubjectModel(name=n, class_id=cls.id) for n in ('Math', 'Urdu')]
        db.session.add_all(subs)
        db.session.flush()
        tests = [TestModel(test_title='Monthly', test_date=date(2026, 10, 20),
                           test_type='Monthly', class_id=cls.id, subject_id=s.id,
                           total_marks=50) for s in subs]
        db.session.add_all(tests)
        studs = []
        for i, phone in enumerate(('03001234567', '03007654321', '')):
            st = StudentModel(roll_number=9100 + n * 10 + i, student_name='TR Student %d' % i,
                              father_name='F', address='X', monthly_fee=0,
                              class_id=cls.id, guardian_phone=phone)
            db.session.add(st)
            studs.append(st)
        db.session.flush()
        for st, vals in zip(studs[:2], ((40, 45), (25, 30))):
            for t, v in zip(tests, vals):
                db.session.add(StudentMarkModel(test_id=t.id, student_id=st.id,
                                                marks_obtained=v, percentage=v * 2,
                                                grade='A'))
        s = AutomationSettings.get()
        s.enabled, s.notify_results, s.mode = True, True, 'delayed'
        db.session.commit()
        yield tests, studs


def test_summary_queued_with_mode_and_dedupe(batch):
    tests, studs = batch
    res = queue_test_result_alerts(tests, studs)
    assert res['queued'] == 2 and res['incomplete'] == 1
    msgs = MessageQueue.query.filter_by(trigger='test_result').order_by(MessageQueue.id).all()[-2:]
    assert all(m.status == 'approved' for m in msgs)      # delayed mode, no approval
    assert 'Math: 40/50 (80%)' in msgs[0].message and 'Urdu: 45/50' in msgs[0].message
    assert 'Total: *85/100*' in msgs[0].message
    again = queue_test_result_alerts(tests, studs)
    assert again['queued'] == 0 and again['duplicate'] == 2


def test_switch_off_blocks(batch):
    tests, studs = batch
    s = AutomationSettings.get()
    s.notify_results = False
    db.session.commit()
    res = queue_test_result_alerts(tests, studs)
    assert res['off_reason'] and res['queued'] == 0


def test_marks_page_save_and_send_flow(app, seed, admin_client):
    from app.models import AutomationSettings
    with app.app_context():
        s = AutomationSettings.get()
        s.enabled, s.notify_results, s.mode = True, True, 'approval'
        sub = db.session.get(SubjectModel, seed['subject_id'])
        t = TestModel(test_title='Quiz 1', test_date=date(2026, 10, 21), test_type='Quiz',
                      class_id=seed['class_id'], subject_id=sub.id, total_marks=20)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    url = '/tests/batch_marks?title=Quiz 1&date=2026-10-21&class_id=%d' % seed['class_id']
    page = admin_client.get(url)
    assert b'Save &amp; Send Results' in page.data
    resp = admin_client.post(url, data={
        'send_wa': '1',
        'marks_%d_%d' % (seed['student_id'], tid): '18',
        'marks_%d_%d' % (seed['other_student_id'], tid): '12',
    }, follow_redirects=True)
    assert b'2 WhatsApp result message(s) queued' in resp.data
    with app.app_context():
        q = MessageQueue.query.filter_by(trigger='test_result').all()
        assert len(q) == 2 and all(m.status == 'pending' for m in q)   # approval mode


def _published_exam(seed):
    from tests.test_absent_marks import _exam_setup
    exam, maths, eng = _exam_setup(seed)
    for tid in (maths.id, eng.id):
        for sid in (seed['student_id'], seed['other_student_id']):
            db.session.add(StudentMarkModel(test_id=tid, student_id=sid,
                                            marks_obtained=80, percentage=80, grade='A'))
    db.session.commit()
    return exam


def test_term_exam_publish_follows_mode(app, seed, admin_client):
    exam = _published_exam(seed)
    s = AutomationSettings.get()
    s.enabled, s.notify_results, s.mode = True, True, 'auto'
    db.session.commit()
    admin_client.post('/examinations/%d/publish' % exam.id, data={'queue_whatsapp': '1'})
    q = MessageQueue.query.filter_by(trigger='result').all()
    assert len(q) == 2 and all(m.status == 'approved' for m in q)       # auto, not pending


def test_term_exam_publish_respects_results_switch(app, seed, admin_client):
    exam = _published_exam(seed)
    s = AutomationSettings.get()
    s.enabled, s.notify_results = True, False
    db.session.commit()
    resp = admin_client.post('/examinations/%d/publish' % exam.id,
                             data={'queue_whatsapp': '1'}, follow_redirects=True)
    assert MessageQueue.query.filter_by(trigger='result').count() == 0
    assert b'switched off' in resp.data

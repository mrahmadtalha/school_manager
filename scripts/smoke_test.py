"""End-to-end HTTP smoke test for School Manager.

Starts the real application on a local port, then walks the core school
administration loop over HTTP (the same way a browser would) and prints a
pass/fail checklist.  Exits non-zero if any check fails.

Usage
-----
    python scripts/smoke_test.py
    python scripts/smoke_test.py --port 5099
"""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from app.database import db  # noqa: E402
from app.models import (  # noqa: E402
    AdminUser, AttendanceModel, AuditLog, ClassModel, FeeRecordModel,
    FeeTransaction, StudentMarkModel, StudentModel, TestModel,
)

RESULTS = []


def check(name, condition, detail=''):
    RESULTS.append((bool(condition), name, detail))
    flag = 'PASS' if condition else 'FAIL'
    print(f'[{flag}] {name}' + (f'  -> {detail}' if detail else ''))
    return bool(condition)


class Server(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self._server = make_server(host, port, app, threaded=True)

    def run(self):
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description='HTTP smoke test for School Manager.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5099)
    parser.add_argument('--password', default=None, help='password for the demo accounts')
    args = parser.parse_args(argv)

    app = create_app()
    password = args.password or app.config.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'

    server = Server(app, args.host, args.port)
    server.start()
    base = f'http://{args.host}:{args.port}'

    for _ in range(40):
        try:
            requests.get(f'{base}/healthz', timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.25)

    session = requests.Session()
    marker = f'SMOKE-{int(time.time())}'
    with app.app_context():
        roll_marker = 990000 + int(time.time()) % 9000
        while StudentModel.query.filter_by(roll_number=roll_marker).first():
            roll_marker += 1

    try:
        # --- public surface -------------------------------------------------
        health = session.get(f'{base}/healthz', timeout=5)
        check('GET /healthz returns 200 with ok=true',
              health.status_code == 200 and health.json().get('ok') is True,
              f'status={health.status_code}')

        login_page = session.get(f'{base}/login', timeout=5)
        check('GET /login renders', login_page.status_code == 200 and 'Password' in login_page.text,
              f'status={login_page.status_code}')

        anon_students = requests.get(f'{base}/students', allow_redirects=False, timeout=5)
        check('anonymous /students is redirected to the login page',
              anon_students.status_code == 302 and '/login' in anon_students.headers.get('Location', ''),
              f'status={anon_students.status_code}')

        anon_api = requests.get(f'{base}/api/whatsapp/pending', allow_redirects=False, timeout=5)
        check('anonymous /api/whatsapp/pending is rejected (was public before the fix)',
              anon_api.status_code == 403, f'status={anon_api.status_code}')

        # --- admin login ----------------------------------------------------
        auth = session.post(f'{base}/login', data={'username': 'admin', 'password': password},
                            allow_redirects=False, timeout=5)
        check('admin login succeeds', auth.status_code == 302, f'status={auth.status_code}')

        dashboard = session.get(f'{base}/', timeout=5)
        check('admin dashboard renders', dashboard.status_code == 200,
              f'status={dashboard.status_code}')

        # --- locate reference data -----------------------------------------
        with app.app_context():
            class_obj = ClassModel.query.order_by(ClassModel.id).first()
            subject = None
            if class_obj:
                from app.models import SubjectModel
                subject = SubjectModel.query.filter_by(class_id=class_obj.id).first()
            class_id = class_obj.id if class_obj else None
            subject_id = subject.id if subject else None

        if not class_id:
            check('reference data present (class + subject)', False, 'no class found - run seed_data.py first')
            return _summary()

        # --- create a student ----------------------------------------------
        students_page = session.get(f'{base}/students', timeout=5)
        check('GET /students renders for admin', students_page.status_code == 200)

        created = session.post(f'{base}/students/add', data={
            'roll_number': str(roll_marker),
            'student_name': f'Smoke Student {marker}',
            'father_name': 'Smoke Father',
            'guardian_phone': '03001239876',
            'address': 'Smoke Street 1',
            'class_id': str(class_id),
            'monthly_fee': '2000',
        }, allow_redirects=False, timeout=5)
        check('POST /students/add creates a student', created.status_code == 302,
              f'status={created.status_code}')

        with app.app_context():
            student = StudentModel.query.filter_by(roll_number=roll_marker).first()
            student_id = student.id if student else None
        check('the new student is persisted in the database', student_id is not None,
              f'student_id={student_id}')

        listing = session.get(f'{base}/students', timeout=5)
        check('the new student appears in the students list',
              f'Smoke Student {marker}' in listing.text)

        # --- attendance ------------------------------------------------------
        attendance = session.post(f'{base}/attendance/students', data={
            'class_id': str(class_id),
            'date': '2026-09-22',
            f'status_{student_id}': 'Absent',
        }, allow_redirects=False, timeout=5)
        check('POST /attendance/students saves attendance',
              attendance.status_code == 302, f'status={attendance.status_code}')

        with app.app_context():
            from datetime import date
            record = AttendanceModel.query.filter_by(target_type='student', target_id=student_id,
                                                     date=date(2026, 9, 22)).first()
            check('attendance is stored with status Absent',
                  record is not None and record.status == 'Absent',
                  f'status={record.status if record else None}')

        # --- marks -----------------------------------------------------------
        with app.app_context():
            test = TestModel(test_title=f'Smoke Test {marker}', test_date=_today(),
                             test_type='Monthly', class_id=class_id, subject_id=subject_id,
                             total_marks=100)
            db.session.add(test)
            db.session.commit()
            test_id = test.id

        marks = session.post(f'{base}/tests/batch_marks', params={
            'title': f'Smoke Test {marker}',
            'date': _today().isoformat(),
            'class_id': class_id,
        }, data={
            f'marks_{student_id}_{test_id}': '78',
        }, allow_redirects=False, timeout=5)
        check('POST /tests/batch_marks saves marks',
              marks.status_code == 302, f'status={marks.status_code}')

        with app.app_context():
            mark = StudentMarkModel.query.filter_by(test_id=test_id, student_id=student_id).first()
            check('the mark is stored with a computed grade',
                  mark is not None and mark.marks_obtained == 78.0 and mark.grade == 'A',
                  f'marks={mark.marks_obtained if mark else None} grade={mark.grade if mark else None}')

        # --- fee ledger ------------------------------------------------------
        month_year = 'September 2026'
        fees_page = session.get(f'{base}/fees?class_id={class_id}&month_year={month_year}', timeout=5)
        check('GET /fees renders', fees_page.status_code == 200)

        payment = session.post(f'{base}/fees/pay/{student_id}', data={
            'month_year': month_year,
            'amount_paid': '800',
            'amount_due_override': '2000',
            'method': 'cash',
            'reference': f'SMOKE-{marker}',
        }, allow_redirects=False, timeout=5)
        check('POST /fees/pay records a payment',
              payment.status_code == 302, f'status={payment.status_code}')

        with app.app_context():
            charged = round(sum(t.amount for t in FeeTransaction.query.filter_by(
                student_id=student_id, month_year=month_year, txn_type='charge', is_void=False).all()), 2)
            paid = round(sum(t.amount for t in FeeTransaction.query.filter_by(
                student_id=student_id, month_year=month_year, txn_type='payment', is_void=False).all()), 2)
            record = FeeRecordModel.query.filter_by(student_id=student_id, month_year=month_year).first()
            check('the fee ledger holds the charge and the payment as separate transactions',
                  charged == 2000.0 and paid == 800.0, f'charged={charged} paid={paid}')
            check('the fee summary reconciles with the ledger',
                  record is not None and record.amount_due == charged and record.amount_paid == paid
                  and record.status == 'Partial',
                  f'due={record.amount_due if record else None} paid={record.amount_paid if record else None} '
                  f'status={record.status if record else None}')

        reconciliation = session.get(f'{base}/fees/reconciliation?month_year={month_year}', timeout=5)
        check('GET /fees/reconciliation reports that ledger and summary agree',
              reconciliation.status_code == 200 and 'Ledger and summary agree' in reconciliation.text)

        receipt = session.get(f'{base}/fees/receipt/{student_id}/{month_year}', timeout=5)
        check('GET /fees/receipt/<id>/<month> renders the receipt with the ledger rows',
              receipt.status_code == 200 and 'Ledger Transactions' in receipt.text)

        # --- reports ----------------------------------------------------------
        report = session.get(f'{base}/students/{student_id}/report', timeout=5)
        check('GET /students/<id>/report renders the student report card',
              report.status_code == 200 and 'Result Card' in report.text)

        history = session.get(f'{base}/students/{student_id}/history', timeout=5)
        check('GET /students/<id>/history renders the change history',
              history.status_code == 200 and marker in history.text)

        # --- audit trail ------------------------------------------------------
        with app.app_context():
            create_rows = [r for r in AuditLog.query.filter_by(entity_type='StudentModel',
                                                               entity_id=student_id).all()
                           if r.action == 'create']
            attendance_rows = [r for r in AuditLog.query.filter_by(entity_type='AttendanceModel').all()
                               if (r.after_json or '').find(f'"target_id": {student_id}') >= 0]
            payment_rows = [r for r in AuditLog.query.filter_by(action='payment').all()]
            check('the student creation was audited with the acting user',
                  bool(create_rows) and create_rows[0].username == 'admin',
                  f'entries={len(create_rows)}')
            check('the attendance entry/correction was audited',
                  bool(attendance_rows), f'entries={len(attendance_rows)}')
            check('the fee payment was audited',
                  bool(payment_rows), f'entries={len(payment_rows)}')

        audit_page = session.get(f'{base}/audit-log', timeout=5)
        check('GET /audit-log renders', audit_page.status_code == 200)

        audit_csv = session.get(f'{base}/audit-log/export.csv', timeout=5)
        check('GET /audit-log/export.csv exports CSV',
              audit_csv.status_code == 200 and 'timestamp,username,role' in audit_csv.text)

        # --- role separation ---------------------------------------------------
        teacher_session = requests.Session()
        with app.app_context():
            has_teacher = AdminUser.query.filter_by(username='teacher1').first() is not None
            has_parent = AdminUser.query.filter_by(username='parent1').first() is not None

        if has_teacher:
            teacher_session.post(f'{base}/login', data={'username': 'teacher1', 'password': password},
                                 allow_redirects=False, timeout=5)
            allowed = teacher_session.get(f'{base}/students', timeout=5)
            blocked = teacher_session.get(f'{base}/fees', timeout=5)
            check('teacher can open /students', allowed.status_code == 200)
            check('teacher is rejected (403) from /fees', blocked.status_code == 403,
                  f'status={blocked.status_code}')
        else:
            check('teacher demo account exists', False, 'teacher1 not found - run seed_data.py')

        if has_parent:
            parent_session = requests.Session()
            parent_session.post(f'{base}/login', data={'username': 'parent1', 'password': password},
                                allow_redirects=False, timeout=5)
            portal = parent_session.get(f'{base}/portal', timeout=5)
            blocked = parent_session.get(f'{base}/students', timeout=5)
            check('parent can open the read-only /portal', portal.status_code == 200)
            check('parent is rejected (403) from /students', blocked.status_code == 403,
                  f'status={blocked.status_code}')
        else:
            check('parent demo account exists', False, 'parent1 not found - run seed_data.py')

        # --- logout -------------------------------------------------------------
        logged_out = session.get(f'{base}/logout', allow_redirects=False, timeout=5)
        after_logout = session.get(f'{base}/', allow_redirects=False, timeout=5)
        check('logout invalidates the session',
              logged_out.status_code == 302 and after_logout.status_code == 302
              and '/login' in after_logout.headers.get('Location', ''),
              f'logout={logged_out.status_code} after={after_logout.status_code}')

    finally:
        server.stop()

    return _summary()


def _today():
    from datetime import date
    return date.today()


def _summary():
    passed = sum(1 for ok, _, _ in RESULTS if ok)
    failed = [name for ok, name, _ in RESULTS if not ok]
    print('')
    print(f'Smoke test: {passed}/{len(RESULTS)} checks passed.')
    if failed:
        print('Failed checks:')
        for name in failed:
            print(f'  - {name}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

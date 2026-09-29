"""Headless browser UI check.

Loads the real application in Chromium and asserts what the *rendered* page
contains (including JavaScript-driven DataTables), and that no uncaught
JavaScript or console errors occur.  This complements the HTTP smoke test: the
smoke test proves the server responds correctly, this proves the browser renders
it correctly.

Usage
-----
    python scripts/ui_check.py
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from app.models import AdminUser, ClassModel, StudentModel, TestModel  # noqa: E402

RESULTS = []


def check(name, condition, detail=''):
    RESULTS.append((bool(condition), name, detail))
    print(f'[{"PASS" if condition else "FAIL"}] {name}' + (f'  -> {detail}' if detail else ''))


class Server(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self._server = make_server(host, port, app, threaded=True)

    def run(self):
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Headless UI check for School Manager.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5097)
    parser.add_argument('--password', default=None)
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright is not installed: pip install -r requirements-dev.txt')
        return 1

    app = create_app()
    password = args.password or app.config.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'

    with app.app_context():
        student_count = StudentModel.query.filter_by(is_active=True).count()
        class_obj = ClassModel.query.order_by(ClassModel.id).first()
        sample_student = (StudentModel.query.filter_by(is_active=True)
                          .order_by(StudentModel.id).first())
        test = TestModel.query.order_by(TestModel.id).first()
        sample_name = sample_student.student_name if sample_student else ''
        student_id = sample_student.id if sample_student else None
        class_id = class_obj.id if class_obj else None
        test_id = test.id if test else None
        has_teacher = AdminUser.query.filter_by(username='teacher1').first() is not None
        has_parent = AdminUser.query.filter_by(username='parent1').first() is not None

    server = Server(app, args.host, args.port)
    server.start()
    base = f'http://{args.host}:{args.port}'
    for _ in range(40):
        try:
            import requests
            requests.get(f'{base}/healthz', timeout=1)
            break
        except Exception:
            time.sleep(0.25)

    console_errors = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={'width': 1440, 'height': 950})
            page = context.new_page()
            page.on('console', lambda msg: console_errors.append(msg.text)
                    if msg.type == 'error' else None)
            page.on('pageerror', lambda err: console_errors.append(str(err)))

            page.goto(f'{base}/login', wait_until='networkidle')
            check('login page renders a username and password field',
                  page.locator('input[name="username"]').count() == 1
                  and page.locator('input[name="password"]').count() == 1)

            page.fill('input[name="username"]', 'admin')
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state('networkidle')

            body = page.inner_text('body')
            check('dashboard shows the seeded student count',
                  'active students' in body.lower() and str(student_count) in body,
                  f'expected count {student_count}')

            page.goto(f'{base}/students', wait_until='networkidle')
            page.wait_for_timeout(1500)
            rows = page.locator('#studentTable tbody tr').count()
            dt_info = page.locator('.dataTables_info').inner_text() if page.locator('.dataTables_info').count() else ''
            check('students table is rendered by DataTables with rows',
                  rows > 0 and 'Showing' in dt_info, f'{rows} rows visible, info="{dt_info.strip()}"')
            check('a seeded student name is visible on the students page',
                  sample_name in page.inner_text('#studentTable'), f'sample={sample_name!r}')

            page.goto(f'{base}/teachers', wait_until='networkidle')
            page.wait_for_timeout(1000)
            check('teachers page lists seeded staff',
                  page.locator('#teacherTable tbody tr').count() > 0
                  and 'T001' in page.inner_text('body'))

            page.goto(f'{base}/classes', wait_until='networkidle')
            check('classes page lists the seeded classes',
                  'Playgroup' in page.inner_text('body'))

            page.goto(f'{base}/attendance/students', wait_until='networkidle')
            check('attendance page renders the student roster',
                  page.locator('input[name^="status_"]').count() > 0
                  or page.locator('select[name^="status_"]').count() > 0)

            if test_id:
                page.goto(f'{base}/tests/marks/{test_id}', wait_until='networkidle')
                check('enter-marks page renders an input per student',
                      page.locator('input[name^="marks_"]').count() > 0)

            page.goto(f'{base}/fees?class_id={class_id}', wait_until='networkidle')
            fees_body = page.inner_text('body')
            fees_lower = fees_body.lower()
            check('fees page shows a fee ledger row with amounts and status',
                  'monthly due' in fees_lower and 'collect fee' in fees_lower
                  and 'amount paid' in fees_lower and 'pending' in fees_lower)

            page.goto(f'{base}/fees/reconciliation', wait_until='networkidle')
            recon = page.inner_text('body')
            check('reconciliation page reports that ledger and summary agree',
                  'Ledger and summary agree' in recon)
            check('reconciliation page shows a totals row',
                  'Total charged' in recon and 'Outstanding' in recon)

            if student_id:
                page.goto(f'{base}/students/{student_id}/history', wait_until='networkidle')
                check('student history page renders an audit table',
                      'Change History' in page.inner_text('body'))

            page.goto(f'{base}/audit-log', wait_until='networkidle')
            audit_body = page.inner_text('body')
            check('audit log page renders entries with actors',
                  'Audit Log' in audit_body and 'admin' in audit_body)

            page.goto(f'{base}/users', wait_until='networkidle')
            users_body = page.inner_text('body')
            check('users page lists the three roles',
                  all(name in users_body for name in ('admin', 'teacher1', 'parent1'))
                  if has_teacher and has_parent else 'admin' in users_body)

            page.goto(f'{base}/documents', wait_until='networkidle')
            documents_body = page.inner_text('body').lower()
            check('documents hub offers ID cards and certificates',
                  'id cards' in documents_body and 'certificates' in documents_body)

            if has_teacher:
                teacher_ctx = browser.new_context(viewport={'width': 1440, 'height': 950})
                teacher_page = teacher_ctx.new_page()
                teacher_page.goto(f'{base}/login', wait_until='networkidle')
                teacher_page.fill('input[name="username"]', 'teacher1')
                teacher_page.fill('input[name="password"]', password)
                teacher_page.click('button[type="submit"], input[type="submit"]')
                teacher_page.wait_for_load_state('networkidle')
                teacher_page.goto(f'{base}/fees', wait_until='networkidle')
                check('teacher sees the 403 access-denied page for /fees',
                      '403' in teacher_page.inner_text('body')
                      and 'Access denied' in teacher_page.inner_text('body'))
                teacher_page.goto(f'{base}/settings', wait_until='networkidle')
                check('teacher sees the 403 access-denied page for /settings',
                      '403' in teacher_page.inner_text('body'))
                teacher_ctx.close()

            if has_parent and sample_name:
                parent_ctx = browser.new_context(viewport={'width': 1440, 'height': 950})
                parent_page = parent_ctx.new_page()
                parent_page.goto(f'{base}/login', wait_until='networkidle')
                parent_page.fill('input[name="username"]', 'parent1')
                parent_page.fill('input[name="password"]', password)
                parent_page.click('button[type="submit"], input[type="submit"]')
                parent_page.wait_for_load_state('networkidle')
                parent_body = parent_page.inner_text('body')
                check('parent portal shows the linked child',
                      'My Child' in parent_body and sample_name in parent_body,
                      f'linked child {sample_name!r}')
                parent_page.goto(f'{base}/students', wait_until='networkidle')
                check('parent is denied the staff students page',
                      '403' in parent_page.inner_text('body'))
                parent_ctx.close()

            browser.close()
    finally:
        server.stop()

    check('no uncaught JavaScript or console errors during the run',
          not console_errors, '; '.join(console_errors[:3]))

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    print('')
    print(f'UI check: {passed}/{len(RESULTS)} checks passed.')
    failed = [name for ok, name, _ in RESULTS if not ok]
    if failed:
        print('Failed checks:')
        for name in failed:
            print(f'  - {name}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

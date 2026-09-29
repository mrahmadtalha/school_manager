"""Capture screenshots of every core screen with the seeded demo data.

Starts the real application locally, drives a headless Chromium through the
core flows as an administrator (plus a teacher 403 check and the parent portal)
and writes one PNG per screen into ``docs/screenshots/``.

Requirements
------------
    pip install -r requirements-dev.txt
    python -m playwright install chromium

Usage
-----
    python scripts/capture_screenshots.py
    python scripts/capture_screenshots.py --out docs/screenshots --port 5098
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
from app.database import db  # noqa: E402
from app.models import AdminUser, ClassModel, StudentModel, SubjectModel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Server(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self._server = make_server(host, port, app, threaded=True)

    def run(self):
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Capture School Manager screenshots.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5098)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'screenshots'))
    parser.add_argument('--password', default=None)
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright is not installed. Run: pip install -r requirements-dev.txt')
        return 1

    app = create_app()
    password = args.password or app.config.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        class_obj = ClassModel.query.order_by(ClassModel.id).first()
        subject = SubjectModel.query.filter_by(class_id=class_obj.id).first() if class_obj else None
        student = StudentModel.query.filter_by(is_active=True).order_by(StudentModel.id).first()
        tests = None
        try:
            from app.models import TestModel
            tests = TestModel.query.order_by(TestModel.id).first()
        except Exception:
            tests = None
        ids = {
            'class_id': class_obj.id if class_obj else '',
            'subject_id': subject.id if subject else '',
            'student_id': student.id if student else '',
            'test_id': tests.id if tests else '',
        }
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

    captured = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={'width': 1440, 'height': 950})
            page = context.new_page()

            def shot(name, url, wait=900):
                page.goto(url, wait_until='networkidle')
                page.wait_for_timeout(wait)
                target = out_dir / f'{name}.png'
                height = page.evaluate('document.documentElement.scrollHeight')
                # Keep images reviewable: full page only when it stays compact.
                page.screenshot(path=str(target), full_page=bool(height and height <= 2400))
                captured.append(target)
                print(f'  captured {target}  ({height}px tall)')

            shot('01-login', f'{base}/login')
            page.goto(f'{base}/login', wait_until='networkidle')
            page.fill('input[name="username"]', 'admin')
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state('networkidle')

            shot('02-dashboard', f'{base}/')
            shot('03-students', f'{base}/students')
            shot('04-teachers', f'{base}/teachers')
            shot('05-classes', f'{base}/classes')
            shot('06-attendance', f'{base}/attendance/students')
            shot('07-attendance-summary', f'{base}/attendance/summary')
            shot('08-tests', f'{base}/tests')
            if ids['test_id']:
                shot('09-enter-marks', f'{base}/tests/marks/{ids["test_id"]}')
            shot('10-class-results', f'{base}/reports/class-results')
            shot('11-reports-hub', f'{base}/reports/hub')
            shot('12-fees', f'{base}/fees')
            shot('13-fee-reconciliation', f'{base}/fees/reconciliation')
            if ids['student_id']:
                shot('14-student-report', f'{base}/students/{ids["student_id"]}/report')
                shot('15-student-history', f'{base}/students/{ids["student_id"]}/history')
                shot('16-fee-ledger', f'{base}/fees/student/{ids["student_id"]}')
            shot('17-audit-log', f'{base}/audit-log')
            shot('18-users', f'{base}/users')
            shot('19-settings', f'{base}/settings')
            shot('20-documents', f'{base}/documents')

            # Teacher: denied administrative page
            teacher_context = browser.new_context(viewport={'width': 1440, 'height': 950})
            teacher_page = teacher_context.new_page()
            teacher_page.goto(f'{base}/login', wait_until='networkidle')
            teacher_page.fill('input[name="username"]', 'teacher1')
            teacher_page.fill('input[name="password"]', password)
            teacher_page.click('button[type="submit"], input[type="submit"]')
            teacher_page.wait_for_load_state('networkidle')
            teacher_page.goto(f'{base}/fees', wait_until='networkidle')
            teacher_page.wait_for_timeout(600)
            target = out_dir / '21-teacher-blocked-403.png'
            teacher_page.screenshot(path=str(target), full_page=False)
            captured.append(target)
            print(f'  captured {target}')
            teacher_context.close()

            if has_parent:
                parent_context = browser.new_context(viewport={'width': 1440, 'height': 950})
                parent_page = parent_context.new_page()
                parent_page.goto(f'{base}/login', wait_until='networkidle')
                parent_page.fill('input[name="username"]', 'parent1')
                parent_page.fill('input[name="password"]', password)
                parent_page.click('button[type="submit"], input[type="submit"]')
                parent_page.wait_for_load_state('networkidle')
                parent_page.goto(f'{base}/portal', wait_until='networkidle')
                parent_page.wait_for_timeout(700)
                target = out_dir / '22-parent-portal.png'
                parent_page.screenshot(path=str(target), full_page=False)
                captured.append(target)
                print(f'  captured {target}')
                parent_context.close()

            browser.close()
    finally:
        server.stop()

    print('')
    print(f'{len(captured)} screenshots written to {out_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

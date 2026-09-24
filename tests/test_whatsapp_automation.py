import os
import sqlite3
import tempfile
import unittest
from datetime import date

from flask import Flask

from app import create_app
from app.bootstrap import migrate_automation_schema
from app.database import db
from app.services.whatsapp_automation import (
    build_whatsapp_message,
    get_delivery_mode_policy,
    normalize_whatsapp_number,
    queue_automation_message,
)


class WhatsAppAutomationTests(unittest.TestCase):
    def test_normalize_whatsapp_number(self):
        self.assertEqual(normalize_whatsapp_number('0300 1234567'), '923001234567')
        self.assertEqual(normalize_whatsapp_number('+923001234567'), '923001234567')

    def test_build_absent_message(self):
        msg = build_whatsapp_message('attendance_absent', {
            'student_name': 'Ali Khan',
            'date': '2026-09-22',
        })
        self.assertIn('ABSENT', msg)
        self.assertIn('Ali Khan', msg)

    def test_delay_policy(self):
        policy = get_delivery_mode_policy('approval')
        self.assertTrue(policy['requires_approval'])
        self.assertFalse(policy['send_all_at_once'])

    def test_build_result_message_uses_test_type(self):
        msg = build_whatsapp_message('result', {
            'student_name': 'Ali Khan',
            'date': '2026-09-22',
            'test_type': 'Monthly',
            'grade': 'A',
            'obtained': '90',
            'total': '100',
            'percentage': '90',
        })
        self.assertIn('Monthly', msg)
        self.assertIn('Ali Khan', msg)

    def test_queue_automation_message(self):
        app = create_app()
        with app.app_context():
            from app.models import AutomationSettings

            settings = AutomationSettings.get()
            settings.enabled = True
            settings.notify_absent = True
            settings.notify_late = True
            settings.notify_results = True
            settings.mode = 'approval'
            from app.database import db
            db.session.commit()

            class DummyStudent:
                id = 1
                guardian_phone = '0300-1234567'
                student_name = 'Ali Khan'

            student = DummyStudent()
            item = queue_automation_message(student, 'attendance_absent', {'student_name': 'Ali Khan', 'date': '2026-09-22'})
            self.assertIsNotNone(item)
            self.assertIn(item.status, {'pending', 'approved'})
            self.assertIsInstance(item.ref_date, date)
            self.assertEqual(item.ref_date.isoformat(), '2026-09-22')

    def test_result_queue_is_blocked_when_result_notifications_are_disabled(self):
        app = create_app()
        with app.app_context():
            from app.database import db
            from app.models import AutomationSettings

            settings = AutomationSettings.get()
            settings.enabled = True
            settings.notify_results = False
            settings.mode = 'approval'
            db.session.commit()

            class DummyStudent:
                id = 2
                guardian_phone = '0300-1234567'
                student_name = 'Sara Ali'

            student = DummyStudent()
            item = queue_automation_message(student, 'result', {'student_name': 'Sara Ali', 'date': '2026-09-22', 'grade': 'A', 'obtained': '90', 'total': '100', 'percentage': '90'})
            self.assertIsNone(item)

    def test_whatsapp_api_is_accessible_without_browser_login(self):
        app = create_app()
        with app.test_client() as client:
            response = client.get('/api/whatsapp/pending')
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn('items', data)

    def test_migrate_automation_schema_adds_retry_count(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, 'test_school.db')
            app = Flask(__name__)
            app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
            app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            db.init_app(app)
            with app.app_context():
                conn = sqlite3.connect(db_path)
                conn.execute('''
                    CREATE TABLE message_queue (
                        id INTEGER PRIMARY KEY,
                        phone TEXT NOT NULL,
                        message TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        "trigger" TEXT,
                        student_id INTEGER,
                        ref_date DATE,
                        created_at DATETIME,
                        updated_at DATETIME,
                        sent_at DATETIME,
                        error_msg TEXT
                    )
                ''')
                conn.commit()
                conn.close()

                migrate_automation_schema(app)

                conn = sqlite3.connect(db_path)
                columns = [row[1] for row in conn.execute('PRAGMA table_info(message_queue)').fetchall()]
                conn.close()
                self.assertIn('retry_count', columns)


if __name__ == '__main__':
    unittest.main()

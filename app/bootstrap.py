import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

from app.database import db


def register_blueprints(app):
    from app.auth import auth
    from app.routes import main

    app.register_blueprint(main)
    app.register_blueprint(auth)


def create_default_admin():
    from app.models import AdminUser

    if AdminUser.query.first():
        return

    username = os.environ.get('INITIAL_ADMIN_USERNAME') or os.environ.get('ADMIN_USERNAME')
    password = os.environ.get('INITIAL_ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD')

    if username and password:
        default = AdminUser(
            username=username,
            password_hash=generate_password_hash(password),
        )
        db.session.add(default)
        db.session.commit()
        print(f'Initial admin created — username: {username}')
        return

    print('No admin account configured. Set INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD or create one via /setup-admin.')


def migrate_attendance_schema(app):
    db_path = os.path.join(app.instance_path, 'school.db')
    if not os.path.exists(db_path):
        return

    with sqlite3.connect(db_path) as connection:
        columns = [row[1] for row in connection.execute('PRAGMA table_info(attendance)').fetchall()]

        if 'is_locked' not in columns:
            connection.execute('ALTER TABLE attendance ADD COLUMN is_locked BOOLEAN DEFAULT 0')
            print('Migration: added is_locked to attendance')

        if 'late_time' not in columns:
            connection.execute('ALTER TABLE attendance ADD COLUMN late_time VARCHAR(10)')
            print('Migration: added late_time to attendance')

        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_target_date ON attendance(target_type, target_id, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_class_date ON attendance(class_id, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_attendance_target_type_date ON attendance(target_type, date)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_students_class_active ON students(class_id, is_active)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_student_marks_test_student ON student_marks(test_id, student_id)')
        connection.commit()


def migrate_automation_schema(app):
    db_path = os.path.join(app.instance_path, 'school.db')
    if not os.path.exists(db_path):
        return

    with sqlite3.connect(db_path) as connection:
        queue_columns = [row[1] for row in connection.execute('PRAGMA table_info(message_queue)').fetchall()]
        if 'retry_count' not in queue_columns:
            connection.execute('ALTER TABLE message_queue ADD COLUMN retry_count INTEGER DEFAULT 0')
            print('Migration: added retry_count to message_queue')

        automation_columns = [row[1] for row in connection.execute('PRAGMA table_info(automation_settings)').fetchall()]
        if 'last_successful_send_at' not in automation_columns:
            connection.execute('ALTER TABLE automation_settings ADD COLUMN last_successful_send_at DATETIME')
            print('Migration: added last_successful_send_at to automation_settings')

        delivery_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_logs'"
        ).fetchone()
        if not delivery_table:
            connection.execute('''
                CREATE TABLE delivery_logs (
                    id INTEGER PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_msg TEXT,
                    details TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(message_id) REFERENCES message_queue(id)
                )
            ''')
            print('Migration: created delivery_logs table')

        connection.commit()


def migrate_teacher_schema(app):
    db_path = os.path.join(app.instance_path, 'school.db')
    if not os.path.exists(db_path):
        return

    with sqlite3.connect(db_path) as connection:
        teacher_columns = [row[1] for row in connection.execute('PRAGMA table_info(teachers)').fetchall()]
        if 'salary_type' not in teacher_columns:
            connection.execute("ALTER TABLE teachers ADD COLUMN salary_type VARCHAR(20) DEFAULT 'monthly'")
            print('Migration: added salary_type to teachers')
        if 'monthly_salary' not in teacher_columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN monthly_salary FLOAT DEFAULT 0')
            print('Migration: added monthly_salary to teachers')
        if 'hourly_rate' not in teacher_columns:
            connection.execute('ALTER TABLE teachers ADD COLUMN hourly_rate FLOAT DEFAULT 0')
            print('Migration: added hourly_rate to teachers')

        connection.commit()


def migrate_school_settings_schema(app):
    db_path = os.path.join(app.instance_path, 'school.db')
    if not os.path.exists(db_path):
        return

    with sqlite3.connect(db_path) as connection:
        settings_columns = [row[1] for row in connection.execute('PRAGMA table_info(school_settings)').fetchall()]
        if 'school_start_time' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN school_start_time VARCHAR(10) DEFAULT '08:30'")
            print('Migration: added school_start_time to school_settings')
        if 'school_end_time' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN school_end_time VARCHAR(10) DEFAULT '15:00'")
            print('Migration: added school_end_time to school_settings')
        if 'weekend_off' not in settings_columns:
            connection.execute('ALTER TABLE school_settings ADD COLUMN weekend_off BOOLEAN DEFAULT 1')
            print('Migration: added weekend_off to school_settings')
        if 'custom_off_days' not in settings_columns:
            connection.execute("ALTER TABLE school_settings ADD COLUMN custom_off_days VARCHAR(200) DEFAULT ''")
            print('Migration: added custom_off_days to school_settings')

        connection.commit()


def ensure_school_settings():
    from app.models import SchoolSettings

    if not SchoolSettings.query.first():
        db.session.add(SchoolSettings(school_name='School Manager'))
        db.session.commit()


def seed_demo_data(student_count=60, teacher_count=8, default_monthly_fee=2500.0):
    from app.models import ClassModel, SectionModel, SubjectModel, TeacherModel, StudentModel, TestTypeModel

    class_names = [
        'Playgroup', 'Nursery', 'Class 1', 'Class 2', 'Class 3',
        'Class 4', 'Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10'
    ]
    subject_names = ['English', 'Urdu', 'Mathematics', 'Science', 'Islamiyat']
    test_types = ['Daily', 'Weekly', 'Monthly', 'Mid-Term', 'Final']

    classes = []
    for class_name in class_names:
        class_obj = ClassModel.query.filter_by(name=class_name).first()
        if class_obj is None:
            class_obj = ClassModel(name=class_name)
            db.session.add(class_obj)
            db.session.flush()
        classes.append(class_obj)

        for section_name in ['A', 'B']:
            if not SectionModel.query.filter_by(class_id=class_obj.id, name=section_name).first():
                db.session.add(SectionModel(name=section_name, class_id=class_obj.id))

        for subject_name in subject_names:
            if not SubjectModel.query.filter_by(class_id=class_obj.id, name=subject_name).first():
                db.session.add(SubjectModel(name=subject_name, class_id=class_obj.id))

    for test_name in test_types:
        if not TestTypeModel.query.filter_by(name=test_name).first():
            db.session.add(TestTypeModel(name=test_name))

    teacher_total = max(0, int(teacher_count))
    if TeacherModel.query.count() == 0 and teacher_total > 0:
        teacher_names = [
            'M. Akram', 'Ayesha Bibi', 'Tariq Mahmood', 'Sana Khan', 'Usman Ali',
            'Farah Nadeem', 'Ali Raza', 'Hina Malik', 'Bilal Ahmed', 'Maryam Noor',
            'Zahid Hassan', 'Nadia Shahid', 'Kashif Aslam', 'Saima Qureshi'
        ]
        for idx in range(teacher_total):
            teacher_name = teacher_names[idx % len(teacher_names)]
            assigned_class = classes[idx % len(classes)].name
            db.session.add(TeacherModel(
                teacher_id_str=f'T{idx + 1:03d}',
                teacher_name=teacher_name,
                joining_date=datetime.utcnow().date(),
                qualification='B.Ed / M.Ed',
                salary=35000 + (idx * 1500),
                assigned_class=assigned_class,
            ))

    student_total = max(0, int(student_count))
    if StudentModel.query.count() == 0 and student_total > 0:
        first_names = ['Ali', 'Ahmed', 'Hassan', 'Hussain', 'Bilal', 'Ayesha', 'Fatima', 'Maryam', 'Hamza', 'Zain']
        last_names = ['Khan', 'Awan', 'Malik', 'Rana', 'Qureshi', 'Abbasi']
        class_list = ClassModel.query.order_by(ClassModel.id).all()
        if not class_list:
            class_list = classes

        for index in range(student_total):
            class_obj = class_list[index % len(class_list)]
            sections = SectionModel.query.filter_by(class_id=class_obj.id).order_by(SectionModel.id).all()
            section = sections[index % len(sections)] if sections else None
            first_name = first_names[index % len(first_names)]
            last_name = last_names[index % len(last_names)]
            student = StudentModel(
                roll_number=f'RN-{1000 + index + 1}',
                student_name=f'{first_name} {last_name}',
                father_name=f'Father of {first_name}',
                guardian_phone=f'+923{(300 + index) % 900:03d}{(1234567 + index) % 10000000:07d}',
                address='Main Bazaar, Sargodha',
                class_id=class_obj.id,
                section_id=section.id if section else None,
                monthly_fee=float(default_monthly_fee),
            )
            db.session.add(student)

    db.session.commit()


def inject_school_settings(app):
    from app.models import SchoolSettings

    @app.context_processor
    def inject_school():
        school = SchoolSettings.query.first()
        return {'school': school}

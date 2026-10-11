"""Roll number policy: per-class integer numbering, cascade shifts, migration."""

import io
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.models import ClassModel, StudentModel
from app.services.roll_numbers import (
    FIRST_ROLL_NUMBER,
    cascade_shift_plan,
    migrate_students_table,
    next_roll_map,
    next_roll_number,
    parse_roll_number,
    students_table_needs_migration,
)


def _make_student(app, name, roll, class_id, section_id=None, is_active=True):
    with app.app_context():
        student = StudentModel(
            roll_number=roll, student_name=name, father_name=f'{name} Father',
            guardian_phone='03000000000', address='Street', monthly_fee=1000.0,
            class_id=class_id, section_id=section_id, is_active=is_active,
        )
        db.session.add(student)
        db.session.commit()
        return student.id


def _make_class(app, name):
    with app.app_context():
        class_obj = ClassModel(name=name)
        db.session.add(class_obj)
        db.session.commit()
        return class_obj.id


# -- validation & suggestions -------------------------------------------------

def test_parse_roll_number():
    assert parse_roll_number(' 1001 ') == 1001
    for bad in ('', None, 'R-001', 'ten'):
        with pytest.raises(ValueError):
            parse_roll_number(bad)
    with pytest.raises(ValueError):
        parse_roll_number(str(FIRST_ROLL_NUMBER - 1))


def test_next_roll_number_and_map(app, seed):
    class2_id = _make_class(app, 'Class 2')
    with app.app_context():
        assert next_roll_number(seed['class_id']) == FIRST_ROLL_NUMBER + 2  # seed has 1001, 1002
        assert next_roll_number(class2_id) == FIRST_ROLL_NUMBER

        mapping = next_roll_map()
        assert mapping[seed['class_id']] == FIRST_ROLL_NUMBER + 2
        assert class2_id not in mapping  # a class without students keeps the default


def test_cascade_plan_lists_affected_students(app, seed):
    _make_student(app, 'Third', FIRST_ROLL_NUMBER + 2, seed['class_id'])
    with app.app_context():
        plan = cascade_shift_plan(seed['class_id'], FIRST_ROLL_NUMBER + 1)
        assert [(item['old'], item['new']) for item in plan] == [
            (FIRST_ROLL_NUMBER + 1, FIRST_ROLL_NUMBER + 2),
            (FIRST_ROLL_NUMBER + 2, FIRST_ROLL_NUMBER + 3),
        ]


# -- schema -------------------------------------------------------------------

def test_roll_number_is_unique_per_class_only(app, seed):
    class2_id = _make_class(app, 'Class 2')
    _make_student(app, 'Solo', FIRST_ROLL_NUMBER, class2_id)  # same number as class 1 - allowed

    with app.app_context():
        db.session.add(StudentModel(
            roll_number=FIRST_ROLL_NUMBER, student_name='Clash', father_name='F',
            guardian_phone='0300', address='a', class_id=seed['class_id']))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# -- cascade behaviour through the real routes --------------------------------

def test_add_student_prompts_before_cascade_then_shifts(admin_client, app, seed):
    payload = {
        'roll_number': str(FIRST_ROLL_NUMBER + 1),  # taken by Sara Ali
        'student_name': 'New Kid',
        'father_name': 'New Father',
        'guardian_phone': '03001112223',
        'address': 'Street 9',
        'class_id': str(seed['class_id']),
        'section_id': '',
        'monthly_fee': '1800',
    }

    preview = admin_client.post('/students/add', data=payload)
    body = preview.get_data(as_text=True)
    assert 'Shift students to make room' in body
    assert 'Sara Ali' in body
    assert 'confirm_cascade' in body
    with app.app_context():
        assert StudentModel.query.filter_by(student_name='New Kid').first() is None
        assert StudentModel.query.filter_by(roll_number=FIRST_ROLL_NUMBER + 1).one() \
            .student_name == 'Sara Ali'

    confirmed = admin_client.post('/students/add', data=dict(payload, confirm_cascade='1'),
                                  follow_redirects=True)
    assert confirmed.status_code == 200
    with app.app_context():
        new_kid = StudentModel.query.filter_by(student_name='New Kid').one()
        assert new_kid.roll_number == FIRST_ROLL_NUMBER + 1
        sara = StudentModel.query.filter_by(student_name='Sara Ali').one()
        assert sara.roll_number == FIRST_ROLL_NUMBER + 2
        rolls = sorted(student.roll_number for student in
                       StudentModel.query.filter_by(class_id=seed['class_id']).all())
        assert rolls == [FIRST_ROLL_NUMBER, FIRST_ROLL_NUMBER + 1, FIRST_ROLL_NUMBER + 2]


def test_edit_student_moves_and_shifts_with_confirmation(admin_client, app, seed):
    _make_student(app, 'Third', FIRST_ROLL_NUMBER + 2, seed['class_id'])
    with app.app_context():
        sara_id = StudentModel.query.filter_by(student_name='Sara Ali').one().id

    edit_payload = {
        'roll_number': str(FIRST_ROLL_NUMBER + 2),  # taken by Third; Sara is at 1002
        'student_name': 'Sara Ali',
        'father_name': 'Nadeem Ali',
        'guardian_phone': '03007654321',
        'address': 'Street 2',
        'class_id': str(seed['class_id']),
        'section_id': str(seed['section_id']),
        'monthly_fee': '2000',
    }

    preview = admin_client.post(f'/students/edit/{sara_id}', data=edit_payload)
    assert 'Shift students to make room' in preview.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(StudentModel, sara_id).roll_number == FIRST_ROLL_NUMBER + 1

    confirmed = admin_client.post(f'/students/edit/{sara_id}',
                                  data=dict(edit_payload, confirm_cascade='1'),
                                  follow_redirects=True)
    assert confirmed.status_code == 200
    with app.app_context():
        sara = db.session.get(StudentModel, sara_id)
        assert sara.roll_number == FIRST_ROLL_NUMBER + 2
        assert sara.section_id == seed['section_id']  # section survives the edit
        third = StudentModel.query.filter_by(student_name='Third').one()
        assert third.roll_number == FIRST_ROLL_NUMBER + 3
        ali = StudentModel.query.filter_by(student_name='Ali Khan').one()
        assert ali.roll_number == FIRST_ROLL_NUMBER


def test_students_page_renders_roll_assist_and_edit_section(admin_client):
    body = admin_client.get('/students').get_data(as_text=True)
    assert 'roll-assist-form' in body
    assert 'nextRollByClass' in body
    assert 'name="section_id"' in body


# -- imports ------------------------------------------------------------------

def test_import_checks_roll_conflicts_per_class(admin_client, app, seed):
    _make_class(app, 'Class 2')
    csv_text = (
        'Roll Number,Student Name,Father Name,Class,Section,Guardian Phone,Address\n'
        '1001,Dupe One,Father A,Class 1,,03001234567,a\n'
        '1001,Fresh Other Class,Father B,Class 2,,03001234567,b\n'
        'not-a-number,Bad Roll,Father C,Class 1,,03001234567,c\n'
    )

    response = admin_client.post('/students/import', data={
        'import_file': (io.BytesIO(csv_text.encode('utf-8')), 'students.csv'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert StudentModel.query.filter_by(student_name='Dupe One').count() == 0
        assert StudentModel.query.filter_by(student_name='Bad Roll').count() == 0
        fresh = StudentModel.query.filter_by(student_name='Fresh Other Class').one()
        assert fresh.roll_number == FIRST_ROLL_NUMBER


# -- search -------------------------------------------------------------------

def test_students_search_matches_integer_roll(admin_client):
    body = admin_client.get('/students?search=1001').get_data(as_text=True)
    assert 'Ali Khan' in body


# -- seed numbering -----------------------------------------------------------

def test_seed_generator_numbers_each_class_from_first(app, seed):
    from app.services.seed_generator import SeedConfig, run_seed

    _make_class(app, 'Class 2')
    with app.app_context():
        run_seed(SeedConfig(student_count=10, teacher_count=2, months=1,
                            include_attendance=False, include_fees=False,
                            include_expenses=False, include_class_tests=False,
                            include_term_exams=False, include_payroll=False,
                            random_seed=7))
        per_class = {}
        for student in StudentModel.query.all():
            per_class.setdefault(student.class_id, []).append(student.roll_number)
        for rolls in per_class.values():
            rolls.sort()
            assert rolls == list(range(FIRST_ROLL_NUMBER, FIRST_ROLL_NUMBER + len(rolls)))


# -- legacy migration ---------------------------------------------------------

def test_legacy_migration_rebuilds_and_renumbers(tmp_path):
    db_path = tmp_path / 'legacy.db'
    connection = sqlite3.connect(str(db_path))
    connection.executescript(
        '''
        CREATE TABLE classes (id INTEGER PRIMARY KEY, name VARCHAR(50));
        CREATE TABLE sections (id INTEGER PRIMARY KEY, name VARCHAR(10),
                               class_id INTEGER REFERENCES classes(id));
        INSERT INTO classes (id, name) VALUES (1, 'Class 1'), (2, 'Class 2');
        CREATE TABLE students (
            id INTEGER NOT NULL,
            roll_number VARCHAR(50) NOT NULL,
            student_name VARCHAR(100) NOT NULL,
            father_name VARCHAR(100) NOT NULL,
            guardian_phone VARCHAR(30) NOT NULL,
            address TEXT NOT NULL,
            monthly_fee FLOAT,
            is_active BOOLEAN,
            class_id INTEGER NOT NULL,
            section_id INTEGER,
            PRIMARY KEY (id),
            UNIQUE (roll_number),
            FOREIGN KEY(class_id) REFERENCES classes (id),
            FOREIGN KEY(section_id) REFERENCES sections (id)
        );
        CREATE INDEX idx_students_class_active ON students(class_id, is_active);
        INSERT INTO students VALUES
            (1, 'RN-1001', 'A One',   'F', '0300', 'x', 100.0, 1, 1, NULL),
            (2, 'RN-1002', 'A Two',   'F', '0300', 'x', 100.0, 1, 1, NULL),
            (3, 'RN-1003', 'B One',   'F', '0300', 'x', 100.0, 1, 2, NULL),
            (4, 'ZZZ',     'A Three', 'F', '0300', 'x', 100.0, 0, 1, NULL);
        '''
    )
    connection.commit()
    connection.close()

    pre = sqlite3.connect(str(db_path))
    try:
        assert students_table_needs_migration(pre)
    finally:
        pre.close()

    summary = migrate_students_table(str(db_path), make_backup=False)
    assert summary is not None
    assert summary['students_total'] == 4

    connection = sqlite3.connect(str(db_path))
    try:
        assert not students_table_needs_migration(connection)

        rolls = {row[0]: (row[1], row[2]) for row in connection.execute(
            'SELECT id, class_id, roll_number FROM students')}
        assert rolls[1] == (1, FIRST_ROLL_NUMBER)
        assert rolls[2] == (1, FIRST_ROLL_NUMBER + 1)
        assert rolls[4] == (1, FIRST_ROLL_NUMBER + 2)  # digit-less legacy value goes last
        assert rolls[3] == (2, FIRST_ROLL_NUMBER)

        row = connection.execute(
            'SELECT student_name, is_active FROM students WHERE id=4').fetchone()
        assert row == ('A Three', 0)  # archived rows are renumbered too, names preserved

        indexes = {row[1] for row in connection.execute("PRAGMA index_list('students')")}
        assert 'idx_students_class_active' in indexes

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO students (roll_number, student_name, father_name, "
                "guardian_phone, address, class_id) VALUES (1001, 'X', 'F', 'p', 'a', 1)")
    finally:
        connection.close()

    # Idempotent: a second run is a no-op.
    assert migrate_students_table(str(db_path), make_backup=False) is None

"""Per-class roll number policy for students.

Roll numbers are plain integers.  Every class numbers its own students from
``FIRST_ROLL_NUMBER`` (1001) upwards, and ``UNIQUE(class_id, roll_number)`` is
enforced by the database.  This module centralises:

* validation of user supplied roll numbers (:func:`parse_roll_number`),
* the "next available" suggestion used by the student forms,
* the cascade shift (+1) that makes room for a manually chosen number,
* the one-time rebuild that migrates legacy databases: the students table is
  recreated with the per-class constraint and every existing student is
  renumbered per class, starting at ``FIRST_ROLL_NUMBER``.
"""

import os
import re
import sqlite3

from app.database import db
from app.models.student import StudentModel

FIRST_ROLL_NUMBER = 1001

_TRAILING_DIGITS = re.compile(r'(\d+)\s*$')


# -- validation & suggestions -------------------------------------------------

def parse_roll_number(raw):
    """Return ``raw`` as an ``int`` roll number, or raise ``ValueError``."""
    value = str(raw if raw is not None else '').strip()
    if not value:
        raise ValueError('Roll Number is required.')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f'Roll Number "{value}" must be a whole number (for example {FIRST_ROLL_NUMBER}).'
        )
    if number < FIRST_ROLL_NUMBER:
        raise ValueError(f'Roll Numbers start at {FIRST_ROLL_NUMBER}; "{number}" is too small.')
    return number


def next_roll_number(class_id):
    """Next free roll number in ``class_id`` (highest + 1, or the first number)."""
    highest = (db.session.query(db.func.max(StudentModel.roll_number))
               .filter(StudentModel.class_id == class_id)
               .scalar())
    return int(highest) + 1 if highest is not None else FIRST_ROLL_NUMBER


def next_roll_map():
    """``{class_id: next_roll_number}`` for every class that has students."""
    rows = (db.session.query(StudentModel.class_id, db.func.max(StudentModel.roll_number))
            .group_by(StudentModel.class_id)
            .all())
    return {class_id: int(highest) + 1 for class_id, highest in rows if highest is not None}


def cascade_shift_plan(class_id, target_roll, exclude_student_id=None):
    """Students who must shift +1 so ``target_roll`` becomes free in ``class_id``.

    The list is ordered ascending by the current roll number; each entry is a
    dict with the student id/name, the current number and the number after the
    shift.  ``exclude_student_id`` skips the student being edited (that student
    is moved explicitly instead of being shifted).
    """
    query = StudentModel.query.filter(
        StudentModel.class_id == class_id,
        StudentModel.roll_number >= target_roll,
    )
    if exclude_student_id is not None:
        query = query.filter(StudentModel.id != exclude_student_id)

    return [
        {
            'id': student.id,
            'student_name': student.student_name,
            'old': int(student.roll_number),
            'new': int(student.roll_number) + 1,
            'is_active': bool(student.is_active),
        }
        for student in query.order_by(StudentModel.roll_number).all()
    ]


def apply_shift_plan(plan):
    """Apply a cascade shift plan; the caller owns the transaction.

    Rows are updated from the highest number downwards so the composite
    unique constraint is satisfied at every statement.
    """
    if not plan:
        return
    ids = [entry['id'] for entry in plan]
    students = {student.id: student
                for student in StudentModel.query.filter(StudentModel.id.in_(ids)).all()}
    for entry in sorted(plan, key=lambda item: item['old'], reverse=True):
        students[entry['id']].roll_number = entry['new']
        db.session.flush()


# -- legacy database migration ------------------------------------------------

def students_table_needs_migration(connection):
    """True when the students table predates per-class integer roll numbers."""
    table = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='students'"
    ).fetchone()
    if not table:
        return False
    columns = connection.execute("PRAGMA table_info('students')").fetchall()
    roll_type = next((column[2] for column in columns if column[1] == 'roll_number'), None)
    if roll_type is None:
        return False
    if str(roll_type).strip().upper() != 'INTEGER':
        return True
    return not _has_unique_index(connection, 'students', ['class_id', 'roll_number'])


def _has_unique_index(connection, table, columns):
    for index in connection.execute(f"PRAGMA index_list('{table}')").fetchall():
        if len(index) < 3 or not index[2]:
            continue
        indexed = [row[2] for row in
                   connection.execute(f"PRAGMA index_info('{index[1]}')").fetchall()]
        if indexed == list(columns):
            return True
    return False


def migrate_students_table(db_path, make_backup=True):
    """Rebuild ``students`` and renumber every student per class from 1001.

    Returns a summary dict, or ``None`` when the table is already migrated.
    The rebuild follows SQLite's recommended table-replacement procedure:
    foreign keys off, new table, copy, drop, rename, verify.
    """
    db_path = str(db_path)
    if not os.path.exists(db_path):
        return None

    connection = sqlite3.connect(db_path)
    connection.isolation_level = None  # explicit BEGIN/COMMIT below
    try:
        if not connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='students'"
        ).fetchone():
            return None
        if not students_table_needs_migration(connection):
            return None

        backup_path = None
        if make_backup:
            try:
                from app.services.db_backup import backup_database
                backup_path = str(backup_database(db_path))
            except Exception as exc:  # a failed backup must not block the migration
                print(f'WARNING: pre-migration backup failed ({exc}); continuing.')

        rows = connection.execute(
            'SELECT id, class_id, roll_number, student_name, father_name, guardian_phone, '
            'address, monthly_fee, is_active, section_id FROM students'
        ).fetchall()
        index_sql = [row[0] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='students' "
            "AND sql IS NOT NULL"
        ).fetchall()]

        # Deterministic order: legacy numeric roll number first, then id; rows
        # without digits (should not exist) go last.
        per_class_entries = {}
        for row in rows:
            student_id, class_id, roll = row[0], row[1], row[2]
            match = _TRAILING_DIGITS.search(str(roll or ''))
            legacy_number = int(match.group(1)) if match else None
            per_class_entries.setdefault(class_id, []).append((legacy_number, student_id, row))

        renumbered = {}
        per_class = []
        for class_id, entries in per_class_entries.items():
            entries.sort(key=lambda item: (item[0] is None, item[0] or 0, item[1]))
            for offset, (_, student_id, _) in enumerate(entries):
                renumbered[student_id] = FIRST_ROLL_NUMBER + offset
            per_class.append({
                'class_id': class_id,
                'count': len(entries),
                'first': FIRST_ROLL_NUMBER,
                'last': FIRST_ROLL_NUMBER + len(entries) - 1,
            })

        connection.execute('PRAGMA foreign_keys=OFF')
        connection.execute('BEGIN')
        try:
            connection.execute('DROP TABLE IF EXISTS students_new')
            connection.execute(
                '''
                CREATE TABLE students_new (
                    id INTEGER NOT NULL,
                    roll_number INTEGER NOT NULL,
                    student_name VARCHAR(100) NOT NULL,
                    father_name VARCHAR(100) NOT NULL,
                    guardian_phone VARCHAR(30) NOT NULL,
                    address TEXT NOT NULL,
                    monthly_fee FLOAT,
                    is_active BOOLEAN,
                    class_id INTEGER NOT NULL,
                    section_id INTEGER,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_students_class_roll UNIQUE (class_id, roll_number),
                    FOREIGN KEY(class_id) REFERENCES classes (id),
                    FOREIGN KEY(section_id) REFERENCES sections (id)
                )
                '''
            )
            connection.executemany(
                'INSERT INTO students_new (id, roll_number, student_name, father_name, '
                'guardian_phone, address, monthly_fee, is_active, class_id, section_id) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [
                    (row[0], renumbered[row[0]], row[3], row[4], row[5], row[6],
                     row[7], row[8], row[1], row[9])
                    for row in rows
                ],
            )
            connection.execute('DROP TABLE students')
            connection.execute('ALTER TABLE students_new RENAME TO students')
            for statement in index_sql:
                connection.execute(statement)
            violations = connection.execute('PRAGMA foreign_key_check').fetchall()
            if violations:
                raise RuntimeError(f'foreign_key_check reported violations: {violations[:5]}')
            connection.execute('COMMIT')
        except Exception:
            connection.execute('ROLLBACK')
            raise
        connection.execute('PRAGMA foreign_keys=ON')

        return {
            'backup_path': backup_path,
            'students_total': len(rows),
            'per_class': sorted(per_class, key=lambda item: item['class_id']),
        }
    finally:
        connection.close()

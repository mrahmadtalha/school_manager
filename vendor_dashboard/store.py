"""The vendor's own database (SQLite): schools, every key issued, payments,
password recoveries and plan presets.  Lives in ``vendor_data/vendor.db`` on
the vendor's laptop only - back it up (Settings -> Backup)."""

import csv
import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_name TEXT, phone TEXT, email TEXT, city TEXT,
    billing TEXT NOT NULL DEFAULT 'yearly',
    machine_code TEXT,
    license_id TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    license_id TEXT NOT NULL,
    rev INTEGER NOT NULL,
    reason TEXT, plan TEXT,
    machine_code TEXT NOT NULL,
    issued TEXT NOT NULL, expires TEXT NOT NULL,
    grace_days INTEGER NOT NULL,
    features TEXT NOT NULL,
    wa_daily INTEGER, wa_monthly INTEGER,
    key_text TEXT, note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    paid_on TEXT NOT NULL, amount REAL, period_note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER REFERENCES schools(id),
    license_id TEXT, nonce TEXT NOT NULL, machine_code TEXT,
    requested_at TEXT, issued_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    features TEXT NOT NULL,
    wa_daily INTEGER, wa_monthly INTEGER
);
CREATE INDEX IF NOT EXISTS idx_licenses_school ON licenses(school_id, license_id, rev);
"""


def _now():
    return datetime.now().isoformat(timespec='seconds')


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / 'vendor.db'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # -- plans ----------------------------------------------------------------
    def seed_plans(self, defaults):
        with self.conn() as c:
            if c.execute('SELECT COUNT(*) FROM plans').fetchone()[0]:
                return
            for name, plan in defaults.items():
                c.execute('INSERT INTO plans VALUES (?,?,?,?,?)',
                          (name, plan['label'], json.dumps(plan['features']),
                           plan['wa_daily'], plan['wa_monthly']))

    def plans(self):
        with self.conn() as c:
            rows = c.execute('SELECT * FROM plans ORDER BY rowid').fetchall()
        return [{'name': r['name'], 'label': r['label'], 'features': json.loads(r['features']),
                 'wa_daily': r['wa_daily'], 'wa_monthly': r['wa_monthly']} for r in rows]

    def save_plan(self, name, label, features, wa_daily, wa_monthly):
        with self.conn() as c:
            c.execute('INSERT INTO plans VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET '
                      'label=excluded.label, features=excluded.features, '
                      'wa_daily=excluded.wa_daily, wa_monthly=excluded.wa_monthly',
                      (name, label, json.dumps(features), wa_daily, wa_monthly))

    # -- schools --------------------------------------------------------------
    def create_school(self, **fields):
        with self.conn() as c:
            cursor = c.execute(
                'INSERT INTO schools (name, contact_name, phone, email, city, billing, '
                'machine_code, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (fields['name'], fields.get('contact_name'), fields.get('phone'),
                 fields.get('email'), fields.get('city'), fields.get('billing') or 'yearly',
                 fields.get('machine_code'), fields.get('notes'), _now()))
            return cursor.lastrowid

    def update_school(self, school_id, **fields):
        allowed = ('name', 'contact_name', 'phone', 'email', 'city', 'billing',
                   'machine_code', 'notes', 'active', 'license_id')
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        with self.conn() as c:
            c.execute(f'UPDATE schools SET {", ".join(f"{k}=?" for k in sets)} WHERE id=?',
                      (*sets.values(), school_id))

    def school(self, school_id):
        with self.conn() as c:
            return c.execute('SELECT * FROM schools WHERE id=?', (school_id,)).fetchone()

    def schools_with_license(self, search=None):
        """Every school with its newest license revision (or None values)."""
        query = ('SELECT s.*, l.rev AS rev, l.plan AS plan, l.expires AS expires, '
                 'l.grace_days AS grace_days, l.wa_daily AS wa_daily, l.wa_monthly AS wa_monthly, '
                 'l.features AS features FROM schools s LEFT JOIN licenses l ON l.id = ('
                 'SELECT id FROM licenses WHERE school_id = s.id AND license_id = s.license_id '
                 'ORDER BY rev DESC, id DESC LIMIT 1)')
        params = ()
        if search:
            query += ' WHERE s.name LIKE ? OR s.city LIKE ? OR s.phone LIKE ? OR s.license_id LIKE ?'
            params = (f'%{search}%',) * 4
        with self.conn() as c:
            return c.execute(query + ' ORDER BY s.name COLLATE NOCASE', params).fetchall()

    def find_school_for(self, license_id, machine_code):
        """Match a recovery request to a school: by license id, else machine code."""
        with self.conn() as c:
            row = None
            if license_id:
                row = c.execute('SELECT * FROM schools WHERE license_id=?', (license_id,)).fetchone()
            if row is None and machine_code:
                row = c.execute('SELECT * FROM schools WHERE machine_code=?',
                                (machine_code,)).fetchone()
            return row

    # -- licenses ---------------------------------------------------------------
    def latest_license(self, school_id):
        with self.conn() as c:
            return c.execute(
                'SELECT l.* FROM licenses l JOIN schools s ON s.id = l.school_id '
                'WHERE l.school_id=? AND l.license_id = s.license_id '
                'ORDER BY l.rev DESC, l.id DESC LIMIT 1', (school_id,)).fetchone()

    def licenses_for(self, school_id):
        with self.conn() as c:
            return c.execute('SELECT * FROM licenses WHERE school_id=? ORDER BY id DESC',
                             (school_id,)).fetchall()

    def license(self, row_id):
        with self.conn() as c:
            return c.execute('SELECT * FROM licenses WHERE id=?', (row_id,)).fetchone()

    def add_license(self, **f):
        with self.conn() as c:
            cursor = c.execute(
                'INSERT INTO licenses (school_id, license_id, rev, reason, plan, machine_code, '
                'issued, expires, grace_days, features, wa_daily, wa_monthly, key_text, note, '
                'created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (f['school_id'], f['license_id'], f['rev'], f.get('reason'), f.get('plan'),
                 f['machine_code'], f['issued'], f['expires'], f['grace_days'],
                 json.dumps(f['features']), f.get('wa_daily'), f.get('wa_monthly'),
                 f.get('key_text'), f.get('note'), _now()))
            c.execute('UPDATE schools SET license_id=?, machine_code=? WHERE id=?',
                      (f['license_id'], f['machine_code'], f['school_id']))
            return cursor.lastrowid

    def license_id_count(self):
        with self.conn() as c:
            return c.execute('SELECT COUNT(DISTINCT license_id) FROM licenses').fetchone()[0]

    def license_id_exists(self, license_id):
        with self.conn() as c:
            return c.execute('SELECT 1 FROM licenses WHERE license_id=?', (license_id,)).fetchone() is not None

    # -- payments / recoveries -----------------------------------------------------
    def add_payment(self, school_id, paid_on, amount, period_note):
        with self.conn() as c:
            c.execute('INSERT INTO payments (school_id, paid_on, amount, period_note, created_at) '
                      'VALUES (?,?,?,?,?)', (school_id, paid_on, amount, period_note, _now()))

    def payments_for(self, school_id):
        with self.conn() as c:
            return c.execute('SELECT * FROM payments WHERE school_id=? ORDER BY paid_on DESC, id DESC',
                             (school_id,)).fetchall()

    def add_recovery(self, **f):
        with self.conn() as c:
            c.execute('INSERT INTO recoveries (school_id, license_id, nonce, machine_code, '
                      'requested_at, issued_at, expires_at, note) VALUES (?,?,?,?,?,?,?,?)',
                      (f.get('school_id'), f.get('license_id'), f['nonce'], f.get('machine_code'),
                       f.get('requested_at'), f['issued_at'], f['expires_at'], f.get('note')))

    def recoveries(self, school_id=None, limit=30):
        query = ('SELECT r.*, s.name AS school_name FROM recoveries r '
                 'LEFT JOIN schools s ON s.id = r.school_id')
        params = []
        if school_id:
            query += ' WHERE r.school_id=?'
            params.append(school_id)
        query += ' ORDER BY r.id DESC LIMIT ?'
        params.append(limit)
        with self.conn() as c:
            return c.execute(query, params).fetchall()

    def nonce_already_issued(self, nonce):
        with self.conn() as c:
            return c.execute('SELECT 1 FROM recoveries WHERE nonce=?', (nonce,)).fetchone() is not None

    # -- import / backup -----------------------------------------------------------
    def import_ledger(self, csv_path, all_features):
        """Import the old ``issued_licenses.csv`` written by license_admin.py.

        One school per licensee name; every row becomes revision 0 (the
        schools already hold those keys, which carry no revision).  Returns
        (schools_created, licenses_added).
        """
        created = added = 0
        with Path(csv_path).open(newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        rows.sort(key=lambda r: (r.get('expires') or '', r.get('created_at') or ''))
        for row in rows:
            name = (row.get('licensee') or '').strip()
            license_id = (row.get('license_id') or '').strip()
            if not name or not license_id or self.license_id_exists(license_id):
                continue
            with self.conn() as c:
                found = c.execute('SELECT id FROM schools WHERE name = ? COLLATE NOCASE', (name,)).fetchone()
            school_id = found['id'] if found else self.create_school(
                name=name, machine_code=row.get('machine_id'), billing='yearly',
                notes='Imported from issued_licenses.csv')
            created += 0 if found else 1
            self.add_license(
                school_id=school_id, license_id=license_id, rev=0, reason='imported',
                plan='', machine_code=row.get('machine_id') or '', issued=row.get('issued') or '',
                expires=row.get('expires') or '', grace_days=int(row.get('grace_days') or 7),
                features=list(all_features), wa_daily=None, wa_monthly=None, key_text=None,
                note='Imported legacy key (no features/limits: everything on)')
            added += 1
        return created, added

    def backup_to(self, target_dir):
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        dest = target_dir / f'vendor-{stamp}.db'
        source = sqlite3.connect(self.path)
        try:
            target = sqlite3.connect(dest)
            with target:
                source.backup(target)
            target.close()
        finally:
            source.close()
        return dest

    def copy_db(self, dest):
        shutil.copy2(self.path, dest)

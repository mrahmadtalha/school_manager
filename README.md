# School Manager

A Flask + SQLite school administration system: student and staff records, classes,
attendance, exams and marks, fees with a transaction ledger, reports and ID cards,
role-based access control, a full audit trail, and optional WhatsApp notifications
through a small Node bridge.

This document is the handover guide. Every command below was executed and confirmed
on Windows with Python 3.12 before being written down.

---

## 1. What you get

| Area | Module | Entry point |
|---|---|---|
| Login, roles, sessions | `app/auth.py`, `app/security.py` | `/login`, `/setup-admin` |
| Students (create/edit/archive/import/export) | `app/routes/students.py` | `/students` |
| Teachers | `app/routes/teachers.py` | `/teachers` |
| Classes, sections, subjects | `app/routes/classes.py` | `/classes` |
| Daily attendance (students + teachers) | `app/routes/attendance.py` | `/attendance/students` |
| Attendance summaries and exports | `app/services/attendance_service.py` | `/attendance/summary` |
| Tests, marks, grades | `app/routes/examinations.py` | `/tests` |
| Fees + append-only transactions | `app/routes/fees.py`, `app/services/fee_ledger.py` | `/fees` |
| Fee reconciliation | `app/routes/fees.py` | `/fees/reconciliation` |
| Reports, result cards, exports | `app/routes/reports.py` | `/reports/hub` |
| ID cards and certificates | `app/routes/documents.py` | `/documents` |
| Audit trail | `app/routes/audit.py`, `app/services/audit.py` | `/audit-log` |
| Users and roles | `app/routes/users.py` | `/users` |
| Parent self-service portal | `app/routes/portal.py` | `/portal` |
| Optional WhatsApp automation | `app/routes/settings.py`, `whatsapp-service/` | `/automation` |

---

## 2. Prerequisites

* **Python 3.12** (3.10+ works; 3.12 is what the project was verified on).
  Verify: `python --version`
* **pip** (bundled with Python).
* Optional: **Node.js 18+** only if you want the WhatsApp bridge.

> Windows note: if `python -m venv` reports `No module named venv`, you are using a
> stripped-down Python build. Install the standard build from python.org (tick
> "Add python.exe to PATH") and retry.

---

## 3. Clean install (PowerShell)

```powershell
# 1. go to the project
cd "C:\Users\ahmad talha\Desktop\projects\New folder\school_manager-main"

# 2. create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. (optional) browser automation, only needed for screenshot capture
pip install -r requirements-dev.txt
python -m playwright install chromium

# 5. set the environment (see section 4); the app starts without a SECRET_KEY in
#    development by generating one, but it is cleaner to set one explicitly
$env:APP_ENV = "development"
```

Command Prompt users: replace `.\venv\Scripts\Activate.ps1` with
`venv\Scripts\activate.bat` and `$env:NAME="value"` with `set NAME=value`.

---

## 4. Configuration

All settings are environment variables; copy `.env.example` to `.env` for reference
(the app reads the environment, not the file).

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `production` requires an explicit `SECRET_KEY` |
| `SECRET_KEY` | generated into `instance/.secret_key` in development | Flask session signing key |
| `DATABASE_URL` | `sqlite:///<project>/instance/school.db` | database location |
| `HOST` / `PORT` | `127.0.0.1` / `5000` (dev), `8000` (prod) | bind address |
| `FLASK_DEBUG` | `0` | `1` enables the Flask debugger - local use only |
| `WHATSAPP_NODE_URL` | `http://127.0.0.1:3001` | optional Node bridge |
| `WHATSAPP_BRIDGE_TOKEN` | empty | shared secret for `/api/whatsapp/*` |
| `LOGIN_MAX_ATTEMPTS` | `5` | failed logins before a temporary lockout |
| `LOGIN_LOCKOUT_SECONDS` | `300` | lockout duration |
| `AUTO_BACKUP_ENABLED` | `1` | in-app daily backup check (`0` disables) |
| `AUTO_BACKUP_INTERVAL_HOURS` | `24` | hours between automatic backups |
| `BACKUP_RETENTION_COUNT` | `30` | automatic backups to keep (manual ones are never pruned) |
| `DEFAULT_DEMO_PASSWORD` | `School@2026` | password for seeded demo accounts |
| `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` | unset | create the first admin on startup (alternative to `/setup-admin`) |

Secrets are never hard-coded. `/api/whatsapp/*` accepts either an authenticated
administrator session or the `X-Bridge-Token` header matching `WHATSAPP_BRIDGE_TOKEN`.

---

## 5. Initialise the database

Two supported paths.

**A. First-run wizard (recommended for a new school)**

```powershell
python run.py
# open http://127.0.0.1:5000/setup-admin and fill in the form
```
Tables are created automatically on first start. The wizard creates the first
administrator (and optional demo data) and saves the school profile.

**B. Seeded demo database (recommended for evaluation)**

```powershell
python seed_data.py --reset
```

`--reset` drops and recreates every table, then populates a realistic synthetic
dataset: 12 classes with sections and subjects, 12 teachers, 60 students,
10 school days of attendance, monthly tests with graded marks, three billing months
of fee charges and payments (including partial payers and defaulters), the three
demo accounts, and the audit trail that goes with all of it.

The seed is **idempotent**: running it again without `--reset` tops up anything
missing and never duplicates records.

Useful flags: `--students N`, `--teachers N`, `--fee AMOUNT`, `--seed N`.

---

## 6. Demo accounts

| Username | Role | Password | Can do |
|---|---|---|---|
| `admin` | Administrator | `School@2026` | everything |
| `teacher1` | Teacher | `School@2026` | students, classes (view), attendance, tests/marks, reports, ID cards, own password |
| `parent1` | Parent | `School@2026` | read-only `/portal` for their own linked child only |

Change `DEFAULT_DEMO_PASSWORD` before seeding if you want different passwords.
A teacher is blocked (HTTP 403) from `/fees`, `/settings`, `/automation`, `/users`
and `/audit-log`; a parent is blocked from every staff page.

---

## 7. Run the application

```powershell
python run.py          # Flask only
python start_all.py    # app + optional WhatsApp bridge (see section 11)
```

Open <http://127.0.0.1:5000/login>.

---

## 8. Run the tests

```powershell
python -m pytest -q
```

The suite runs against an isolated temporary SQLite file, so it never touches
`instance/school.db`. Coverage includes: authentication and session handling,
role enforcement per endpoint, parent isolation, audit-trail completeness,
fee-ledger reconciliation (including a deliberately corrupted summary),
persistence across an application restart, and a backup/restore round-trip.

---

## 9. HTTP smoke test (real end-to-end evidence)

```powershell
python scripts/smoke_test.py
```

This boots the real application on port 5099 and walks the whole loop over HTTP:
health check, anonymous redirects, `/api/whatsapp/*` rejection, admin login,
student creation, attendance marking, mark entry, fee payment, reconciliation,
receipt, report card, change history, audit-log page and CSV export, teacher 403,
parent portal isolation, and logout invalidation. It prints a PASS/FAIL checklist
and exits non-zero if anything fails.

Screenshots of every core screen (seeded data visible) can be captured with:

```powershell
python scripts/capture_screenshots.py
```
Output lands in `docs/screenshots/`.

---

## 10. Backup and restore

```powershell
# back up (uses SQLite's online backup API - safe while the app is running)
python scripts/backup_db.py
# -> instance/backups/school-YYYYMMDD-HHMMSS.db

# restore; refuses to overwrite a live database unless --force is given
python scripts/restore_db.py instance/backups/school-20260928-120000.db --force
```

With `--force`, the current database is first preserved as
`school.db.pre-restore-<timestamp>` so a mistaken restore can itself be undone.
The scripts honour `DATABASE_URL` and accept `--db` / `--out` overrides.

Verify a restore by comparing row counts: `python scripts/backup_db.py` prints the
per-table counts of the file it wrote.

A rotating **automatic backup** runs inside the app: when nothing has been backed
up for ~24 hours it writes a copy to `instance/backups/auto/` and keeps the newest
30 (`AUTO_BACKUP_ENABLED`, `AUTO_BACKUP_INTERVAL_HOURS`, `BACKUP_RETENTION_COUNT`).
The same check can also run once a day as a host-level scheduled task, so
days when the server was off are caught up. `/settings` has a **Backups** section
to see every copy, download one, or take a manual backup on the spot.

---

## 11. Optional WhatsApp bridge

The Node service in `whatsapp-service/` pairs a phone over WhatsApp Web and exposes
`/health`, `/qr`, `/send-test`. To enable it:

```powershell
cd whatsapp-service
npm install
cd ..
$env:WHATSAPP_BRIDGE_TOKEN = "<a long random string>"
python start_all.py
```

Set the same token in the bridge so it can call `/api/whatsapp/*`. The Flask app
works fully without the bridge; the automation pages simply report the service as
offline.

---

## 12. Project layout

```
app/
  __init__.py        application factory, request guards, error handlers
  config.py          environment-driven configuration
  auth.py            login / logout / password change / first-run setup
  security.py        role map, role_required, login throttling, bridge guard helpers
  bootstrap.py       schema migrations, blueprint registration, first-run helpers
  database.py        SQLAlchemy instance
  models/            SQLAlchemy models (students, teachers, classes, attendance,
                     tests/marks, fees + fee transactions, users, audit log, automation)
  routes/            one module per functional area
  services/          attendance, fee_ledger, audit, reports, payroll, ID documents,
                     db_backup, WhatsApp automation
  templates/         Jinja templates (Bootstrap 5)
  static/            stylesheet and logos
scripts/             backup_db.py, restore_db.py, rebuild_fee_summaries.py,
                     smoke_test.py, capture_screenshots.py
tests/               pytest suite
seed_data.py         idempotent synthetic demo data
run.py               Flask entry point
start_all.py         app + WhatsApp bridge launcher
docs/                AUDIT_REPORT.md, BACKLOG.md, screenshots/
```

---

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `RuntimeError: SECRET_KEY is required in production` | You set `APP_ENV=production` without a `SECRET_KEY`. Set one or unset `APP_ENV`. |
| `ModuleNotFoundError: No module named 'flask_login'` | Old `requirements.txt` (pre-repair). Run `pip install -r requirements.txt`. |
| Login says "Incorrect username or password" right after setup | An older database exists. Run `python seed_data.py --reset`, or delete `instance/school.db` and create the admin through `/setup-admin`. |
| Locked out after several attempts | Wait `LOGIN_LOCKOUT_SECONDS` (default 5 minutes) or restart the app (the throttle is in-process). |
| `/api/whatsapp/*` returns 403 | Expected: it needs an admin session or the `X-Bridge-Token` header. |
| Fee totals look wrong | Open `/fees/reconciliation`, then run `python scripts/rebuild_fee_summaries.py`. |
| Port already in use | Set `PORT` to another value, or stop the process holding `3001`/`5000`. |
| Excel import fails | The importer expects the exact template from `/students/template/excel`. |

---

## 14. Known limitations

* **SQLite only.** The schema is portable, but the automatic migrations and the
  backup scripts are SQLite-specific.
* **Single-process login throttling.** `LOGIN_MAX_ATTEMPTS` is tracked in memory;
  it does not survive a restart and is not shared across worker processes.
* **No password reset by email.** Administrators reset passwords from `/users`.
* **Parents see one child.** `AdminUser.student_id` links a parent to exactly one
  student; there is no multi-child or multi-guardian account model.
* **Audit rows for create are keyed by primary key**, which is assigned after the
  ORM flush; this is handled, but a raw `INSERT` outside the ORM is not audited.
* **Bulk ORM deletes** (`Query.delete()`) bypass the per-object audit hook. The
  permanent student delete path logs an explicit audit entry instead.
* **The WhatsApp bridge is optional and best-effort.** No delivery guarantees,
  retries are manual, and the QR session is stored unencrypted in
  `whatsapp-service/session/`.
* **The UI is Bootstrap 5 loaded from a CDN**, so the pages need internet access to
  look right; functionality is unaffected.
* **No deployment automation.** There is no Dockerfile, CI pipeline, or production
  web server configuration in this repository.

---

## 15. Next steps

See `docs/BACKLOG.md` for the prioritised list of deferred work, and
`docs/AUDIT_REPORT.md` for the defect-by-defect record of this repair pass.

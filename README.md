# School Manager

**Offline-first school administration for Windows — by Ahmi software firm** (established 2020)

School Manager is a desktop school-administration product for private schools.
It runs entirely on the school's own computer: a local server, a local SQLite
database, and a desktop-style interface in the default browser window. No
cloud account, no subscription, and no internet connection is required for
daily work. Where the internet *is* available, the built-in WhatsApp bridge
sends attendance alerts, results and broadcasts to parents.

Current version: **1.0.0** (the single source of truth is
`installer/SchoolManager.iss` → `#define MyAppVersion`).

---

## 1. Project overview

School Manager started as a Flask web application and is now packaged as a
commercial Windows product:

* the Flask application is **obfuscated** (PyArmor) and **frozen** into
  `SchoolManager.exe` (PyInstaller),
* the exe starts a local Waitress server on `127.0.0.1`, waits until it is
  healthy, and opens the app in a **standalone desktop window** (Edge/Chrome
  `--app` mode with a private profile) — or a normal browser tab with
  `--browser`,
* an **Inno Setup installer** (`SchoolManager_Setup_v1.0.0.exe`, ~90 MB)
  installs the app and the WhatsApp bridge together, registers clean
  shortcuts and an uninstaller, and never touches school data on
  update/uninstall,
* every school's data (database, license, WhatsApp session, photos, backups,
  logs) lives in **one folder**: `%LOCALAPPDATA%\SchoolManager`.

---

## 2. Features

| Area | Highlights | Entry point |
|---|---|---|
| Dashboard | Per-role dashboards, executive (Principal/Owner) view with charts | `/` , `/executive` |
| Students | Admissions, profiles (photo optional), custom fields, roll-number policy with cascade shift, import/export CSV/Excel, archive & restore, change history | `/students` |
| Teachers | Records, salary types (monthly/hourly), payroll with attendance snapshots | `/teachers`, `/payroll` |
| Classes | Classes, sections, subjects, per-class standard fee, timetable | `/classes` |
| Attendance | Daily student & teacher attendance (Present/Absent/Late/Leave), late times & minutes, summaries and exports | `/attendance/students` |
| Tests & exams | Class tests, batch mark entry, grading scale, term exams with date sheets and tabulation | `/tests`, `/examinations` |
| Fees | Append-only transaction ledger (charges/payments/adjustments), explicit monthly charge generation, reconciliation, receipts, reminders, class-wide fee updates | `/fees` |
| Expenses | Categories + expense log (Cash/Bank/Cheque) | `/expenses` |
| Financials | Income/expense summaries and comparisons | `/financials` |
| Reports | Result cards, transcripts, tabulation sheets, financial reports — PDF and Excel | `/reports/hub` |
| Documents | Student & teacher ID cards (photo optional, initials placeholder otherwise), certificates, date sheets | `/documents` |
| Parent portal | Read-only portal for guardians (own children only) | `/portal` |
| Users & roles | 5 roles, per-endpoint authorisation, password change | `/users` |
| Settings | School profile, branding/logo, academic session, grading scale, holidays, custom fields, backups | `/settings` |
| Automation | WhatsApp queue with three delivery modes, message templates, QR pairing status, delivery logs | `/automation` |
| Audit trail | Every create/update/delete, login, charge, payment, void, settings change, export — with before/after JSON | `/audit-log` |
| Licensing | Offline activation, expiry warnings, grace period, read-only lockout | `/license` |

The HTTP surface is **169 routes** across 20 route modules.

---

## 3. Selling points

* **Works fully offline.** The server, database and every UI asset are local;
  the installer ships everything. No internet is needed to run the school.
* **One-time purchase, machine-licensed.** Ed25519-signed licenses, no
  subscriptions, no phone-home. Expired installations keep full *read*
  access — a school is never locked out of its own records.
* **Data belongs to the school.** Everything lives in one folder on their
  computer (`%LOCALAPPDATA%\SchoolManager`), with built-in backup/restore.
  Uninstalling never deletes it.
* **WhatsApp notifications built in.** Absent/late alerts, results and
  broadcasts to guardians — with human-approval and paced-sending modes to
  reduce ban risk. The bridge ships inside the installer with its own private
  Node runtime; schools never install Node.js.
* **Desktop-app experience.** One double-click opens a dedicated window;
  closing it (or the in-app *Exit Software* button) safely stops the
  background server.
* **Realistic evaluation in minutes.** The setup wizard and `seed_data.py`
  can generate a configurable amount of demo history (1 month → 10 years):
  students, attendance, fees, tests, results, payroll — ages, lifecycles and
  fee behaviour included.

---

## 4. Technology stack

| Layer | Technology |
|---|---|
| Web framework | Flask 3.1.0 + Flask-Login 0.6.3 (sessions, roles) |
| ORM / database | SQLAlchemy 2.1.1 / Flask-SQLAlchemy 3.1.1 over **SQLite** |
| Templates | Jinja2 3.1.6 (57 templates), Bootstrap 5.3, jQuery 3.7, DataTables 1.13.6, Font Awesome 6.4, Chart.js 4.4.1 — **all vendored locally** in `app/static/vendor/` |
| Production server | Waitress 3.0.2 (threaded, `127.0.0.1`) |
| Documents | ReportLab 4.2.5 (PDF: result cards, transcripts, ID cards, date sheets), pandas 2.2.3 + openpyxl 3.1.5 (Excel/CSV exports) |
| Licensing | `cryptography` 46.0.6 — Ed25519 signature verification |
| WhatsApp bridge | Node.js (≥18) + Express + Baileys 6.7 (unofficial WhatsApp library), private `node.exe` shipped by the installer |
| Desktop packaging | PyInstaller 6.22.3 (onedir, windowed), Inno Setup 6 (installer), PyArmor 9.2.7 (obfuscation) |
| Tests | pytest 9.1.1 — 47 test files (485 collected: **482 passed / 3 skipped**) |
| Python | 3.12 (the version the product is built and verified on) |

---

## 5. Architecture

A deliberately simple, well-bounded monolith:

```
┌──────────────────────────────  SchoolManager.exe  ──────────────────────────┐
│  school_manager launcher                                                    │
│   • parses mode (desktop window / --browser / --selftest)                   │
│   • redirects logs → <data>/school_manager.log                              │
│   • starts the bundled WhatsApp bridge (node.exe server.js)                 │
│   • starts Waitress (create_server + handle → graceful /shutdown)           │
│   • opens the desktop window; closing it exits gracefully                   │
└──────────────┬──────────────────────────────────────────┬───────────────────┘
               │  HTTP 127.0.0.1:5000 (dev) / 8000 (prod) │ loopback :3001
┌──────────────▼──────────────────────────────┐  ┌────────▼──────────────────┐
│ Flask application factory (app/__init__.py) │  │ WhatsApp bridge (Node)    │
│  before_request chain:                      │  │  Baileys session (QR)     │
│   1. license guard (read-only lockout)      │◄─┤  polls /api/whatsapp/*    │
│   2. role guard (deny-by-default RBAC)      │  │  posts delivery status    │
│   3. setup-wizard gate                      │  └───────────────────────────┘
│  blueprints: 20 route modules (169 routes)  │
│  services: 30 modules (business logic)      │
│  models: 15 modules (SQLAlchemy)            │
│  audit hooks: automatic before/after JSON   │
└──────────────┬──────────────────────────────┘
               ▼
        SQLite database (schema auto-migrated on boot)
```

Key architectural rules:

* **App factory** (`create_app`) with ordered `before_request` guards: the
  license is evaluated first, then role authorisation (deny by default),
  then first-run setup redirection.
* **The fee ledger is append-only.** `fee_transactions` is the source of
  truth; `fee_records` is a cache always rebuilt from the ledger, so the two
  can never disagree (reconciliation tooling included).
* **Enrollment history** — every class placement is a dated
  `StudentEnrollment` row (one open per student), powering transcripts and
  the promotion wizard.
* **Audit hooks** snapshot audited models automatically; the seeder suspends
  them and writes one summary entry instead of thousands.
* **Obfuscated deployment.** The product tree's `app` package is
  PyArmor-obfuscated before PyInstaller ever sees it; the build pipeline
  declares every hidden import explicitly (obfuscated module bodies hide
  their imports from static analysis).
* **Stateless license checks.** A signed "latest date seen" state file
  defeats clock rollback; a wrong far-future clock is fixed by issuing a
  replacement license key.

---

## 6. Project structure

```
app/
  __init__.py          application factory, guard ordering, template filters
  config.py            environment-driven configuration (see §8)
  auth.py              login/logout, /setup-admin wizard, /shutdown, /setup-progress
  license_guard.py     read-only lockout + always-open endpoint list
  seed_progress.py     background demo-data job for the setup wizard
  security.py          role map (deny-by-default), login throttling, public endpoints
  user_data.py         single data-folder resolution + legacy migration
  bootstrap.py         schema auto-migrations, blueprint registration, auto-backup
  graceful_exit.py     /shutdown support: commit → cleanups → stop server
  database.py          SQLAlchemy instance
  models/              15 modules: student, teacher, class_, attendance, test,
                       term_exam, fees, expense, payroll, enrollment, remarks,
                       admin (users/roles), audit, automation, settings
  routes/              20 modules: students, teachers, classes, attendance,
                       examinations, term_exams, fees, expenses, payroll,
                       financials, reports, documents, dashboard, executive,
                       portal, promotions, settings, users, audit, license
  services/            30 modules: attendance, fee_ledger, fee_reminders,
                       licensing, whatsapp_bridge, whatsapp_automation,
                       id_documents, transcripts, report_service, marks,
                       teacher_payroll, payroll_service, db_backup, data_import,
                       enrollments, roll_numbers, custom_fields, photos,
                       theme, timetable, seed_generator, ...
  templates/           57 Jinja templates
  static/              style.css, ui.js, logos + vendor/ (offline Bootstrap,
                       Font Awesome, jQuery, DataTables, qrcodejs, Chart.js)
docs/                  RELEASE_CHECKLIST.md, QUICKSTART.txt (ships in installer)
installer/             SchoolManager.iss (Inno Setup, version + branding)
scripts/               backup_db.py, restore_db.py, rebuild_fee_summaries.py,
                       smoke_test.py, capture_screenshots.py, ui_check.py
tests/                 47 pytest files + conftest (482 passed / 3 skipped)
tools/                 license_admin.py (vendor-only), fetch_vendor_assets.py,
                       build_product.py, build_exe.py, build_installer.py,
                       make_release.py
build/                 build output (git-ignored): product tree, exe, installer,
                       release folder
school_manager.pyw     Windows launcher (desktop window / --browser / --selftest)
run.py                 plain Flask entry point (development)
start_all.py           dev launcher: app + optional WhatsApp bridge
seed_data.py           advanced demo-data generator (CLI)
whatsapp-service/      Node bridge (server.js, package.json, node_modules/)
vendor_keys/           Ed25519 key pair + issued-license ledger (NEVER ship/commit)
instance/              development data folder (git-ignored)
```

---

## 7. Setup & development instructions

### 7.1 Clean development setup (PowerShell, Python 3.12)

```powershell
cd <project folder>

python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# SECRET_KEY is required (or let development mode generate one into the data folder)
setx SECRET_KEY "school-manager-local-secret-2026"

# clean slate + demo data (optional)
python seed_data.py --reset

# run
python run.py               # Flask only, http://127.0.0.1:5000
python school_manager.pyw   # product launcher (server + browser)
python start_all.py         # app + WhatsApp bridge together (development)
```

First run: open `http://127.0.0.1:5000/setup-admin` and create the
administrator. The **Load demo data** option (off by default) can generate a
configurable demo history.

### 7.2 Demo accounts (only when demo data was loaded)

| Username | Role | Password |
|---|---|---|
| `admin` | Administrator | `School@2026` |
| `teacher1` | Teacher | `School@2026` |
| `parent1` | Parent/Guardian (read-only `/portal`) | `School@2026` |

Override with the `DEFAULT_DEMO_PASSWORD` environment variable.

### 7.3 Useful commands

```powershell
python scripts/smoke_test.py            # end-to-end HTTP smoke test (32 checks)
python scripts/backup_db.py             # manual backup
python scripts/restore_db.py            # restore from a backup
python scripts/rebuild_fee_summaries.py # rebuild fee cache from the ledger
python tools/fetch_vendor_assets.py     # refresh vendored UI libraries
```

---

## 8. Configuration

Configuration is resolved at `create_app()` time. Precedence: environment
variable → generated/persisted development value → default.

| Key | Default | Purpose |
|---|---|---|
| `SECRET_KEY` / `APP_SECRET_KEY` | generated → `<data>/.secret_key` (dev only) | session signing; **required in production mode** |
| `APP_ENV` | `development` | `production` raises if no `SECRET_KEY`, switches default port to 8000 |
| `PORT` | 5000 (dev) / 8000 (prod) | server port; the launcher walks to the next free port |
| `HOST` | `127.0.0.1` | bind address (keep local — this is a desktop product) |
| `DATABASE_URL` | `<data>/school.db` | explicit SQLite/SQLAlchemy URI override |
| `SCHOOL_DATA_DIR` | per §9 | relocate the whole data folder (tests/support) |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_SECONDS` | 5 / 300 | login throttling |
| `SESSION_COOKIE_*`, `PERMANENT_SESSION_LIFETIME` | HttpOnly, Lax, 8 h | session hardening |
| `WHATSAPP_NODE_URL` | `http://127.0.0.1:3001` | bridge API base URL |
| `WHATSAPP_BRIDGE_TOKEN` | (empty) | shared secret for `/api/whatsapp/*` bridge calls |
| `WHATSAPP_BRIDGE_DIR` / `WHATSAPP_NODE_PATH` | auto-detected | non-default component locations |
| `AUTO_BACKUP_ENABLED`, `AUTO_BACKUP_INTERVAL_HOURS` | on, 1 h | automatic backups |
| `LICENSE_ENFORCEMENT`, `LICENSE_DIR` | on, `<data>` | **ignored when running the packaged exe** (enforcement is forced on) |
| `DEFAULT_DEMO_PASSWORD` | `School@2026` | demo-account password |

---

## 9. Database & data storage

* **Engine:** SQLite via SQLAlchemy. The schema is created on boot and
  *auto-migrated* by `app/bootstrap.py` (20+ idempotent migrations upgrade
  older databases — no manual migration steps).
* **One data folder per school** (resolved by `app/user_data.py`):

  | How it runs | Data folder |
  |---|---|
  | Packaged exe | `%LOCALAPPDATA%\SchoolManager` |
  | From source | `<project>\instance` |
  | Override | `SCHOOL_DATA_DIR` |

  Contents: `school.db`, `.secret_key`, `license.key`, `license.state`,
  `uploads/` (photos, logo), `backups/` (+ `backups/auto`),
  `whatsapp-session/`, `browser-profile/`, `school_manager.log`.
* **Legacy migration:** on first start, files/folders from older layouts
  (e.g. the old `app/instance` license folder) are copied in — never
  overwritten.
* **Backups:** automatic (hourly check, pruned retention) plus manual
  backup/restore from Settings and `scripts/backup_db.py` /
  `restore_db.py`. The data folder survives updates *and* uninstalls.
* **Per-Windows-user:** `%LOCALAPPDATA%` is user-scoped — two Windows
  accounts on one PC keep separate databases (see §15).

---

## 10. WhatsApp integration

The bridge is a **core component**, shipped and versioned with the product:

* **Architecture:** the Node bridge (`whatsapp-service/server.js`, Express +
  Baileys) *polls* the Flask app for approved messages
  (`/api/whatsapp/pending`) and posts delivery outcomes
  (`/api/whatsapp/update-status`). Flask calls the bridge only for
  `/health`, `/qr` and `/send-test`. If the bridge is down, nothing breaks:
  messages wait in the queue and are never marked failed.
* **Pairing:** QR code on the Automation page (WhatsApp → Linked devices).
  The session persists in `<data>/whatsapp-session`, so updates never
  require re-pairing.
* **Socket tuning** (fixes the Baileys `init queries` timeout on slow
  connections): `syncFullHistory: false`, `connectTimeoutMs: 60000`,
  `defaultQueryTimeoutMs: 60000`, `keepAliveIntervalMs: 30000`, plus
  process-level `unhandledRejection`/`uncaughtException` handlers so the
  bridge never dies on transient errors.
* **Delivery modes:** `auto` (send immediately), `approval` (human review),
  `delayed` (one-by-one, 15 s pacing) — chosen per school.
* **Lifecycle in the product:** the launcher starts the bundled bridge
  (`node.exe` from the bridge folder) at app start and terminates it during
  graceful shutdown. A fresh per-launch bridge token authenticates it.
* **Integration methods:** QR session (default) or Meta Cloud API
  (access token / phone-number ID / business-account ID).

Development: `cd whatsapp-service && npm install`, then `python start_all.py`
(generates a temporary bridge token). The bridge's port is `APP_PORT`
(default 3001); its session folder is `SESSION_PATH`.

---

## 11. Licensing

* **Format:** one line, `SM1.<base64 payload>.<base64 Ed25519 signature>`,
  carrying school name, machine code, issue/expiry dates and grace days.
* **Machine binding:** the machine code derives from the Windows
  `MachineGuid`. A license copied to another PC locks *that* PC.
* **States:** `active` → `expiring` (warning banner, last 30 days) →
  `grace` (default 7 days, writes still allowed) → **read-only lockout**
  (expired/unlicensed/invalid). Read-only blocks every write — including
  GET pages that would write — while keeping viewing, printing, exports,
  login, manual backup and license activation available.
* **Clock protection:** a signed "latest date seen" state file prevents
  rolling the clock back; a wrong far-future clock is recovered by issuing a
  replacement license key.
* **Packaged builds always enforce** (`LICENSE_ENFORCEMENT=0` works only
  from source, for developers).
* **Vendor tool** — `tools/license_admin.py` (never ships, never commits):
  `init` (create key pair once), `issue` (sign + append to
  `vendor_keys/issued_licenses.csv`), `inspect`, `machine-code`.

  ```powershell
  python tools/license_admin.py machine-code
  python tools/license_admin.py issue --machine <code> --licensee "School Name" --days 365
  ```

  **Back up `vendor_keys/license_private.key` privately** — losing it means
  every customer must be re-keyed.

---

## 12. Testing

```powershell
python -m pytest tests/ -q          # current result: 482 passed, 3 skipped, 0 failed (485 collected)
```

* 49 test files covering: authentication & sessions, per-endpoint RBAC for
  all five roles, parent-portal isolation, license lifecycle (activation,
  expiry, grace, read-only lockout, clock tampering, wrong-machine and
  forged keys), fee-ledger reconciliation (including a deliberately
  corrupted summary), attendance rules, marks/absent semantics, payroll,
  expenses, backups/restore, custom fields, imports, offline assets, user
  data-folder migration, the seed generator, and the product build rules.
* Tests run against an isolated SQLite database and never touch the
  development data folder.
* `scripts/smoke_test.py` performs a separate 32-check end-to-end HTTP
  walkthrough against a real server (run it pointed at a scratch data
  folder).

---

## 13. Build & release process

One command builds a release from a clean slate:

```powershell
python tools/make_release.py
```

Pipeline (all steps verified in-script):

1. wipe `build/`, run the full test suite (release gate),
2. **PyArmor:** obfuscate the `app` package into `build/product/`
   (trial edition leaves >32 KB modules plain and lists them in
   `BUILD-INFO.txt`; a PyArmor Basic license obfuscates everything),
3. **PyInstaller:** bundle the obfuscated tree into
   `build/exe/SchoolManager/SchoolManager.exe` (onedir, windowed) and run
   its `--selftest` (routes, offline assets, license gate, bundled bridge),
4. **Inno Setup:** compile `SchoolManager_Setup_v1.0.0.exe` — application +
   WhatsApp bridge (with private `node.exe`) + quick-start guide,
5. assemble `build/release/v<version>/` with `SHA256SUMS.txt` and
   `RELEASE-INFO.txt`.

Before handing an installer to a school, complete the manual QA matrix in
**`docs/RELEASE_CHECKLIST.md`** (clean-machine install, activation, WhatsApp
pairing, offline test, update/uninstall). Optional: code-sign the installer
to remove SmartScreen warnings.

**Maintaining this software yourself?** Follow
[`update_system_guide.md`](update_system_guide.md) — a step-by-step manual
for changing code, running tests, migrating databases, building releases,
and updating client installations (with rollback), written without
assumptions about any tooling.

---

## 14. Security

* **Passwords:** Werkzeug scrypt hashing; strength rules on change; login
  throttling (5 attempts → 5-minute lockout).
* **RBAC, deny by default:** five roles (Administrator, Teacher,
  Parent/Guardian, Principal/Owner, Accountant) mapped per endpoint; parents
  see only their linked children via `/portal`; the WhatsApp bridge
  authenticates with a per-launch token header.
* **Audit trail:** automatic before/after JSON snapshots for all audited
  models, plus business events (logins, charges, payments, voids, settings,
  exports, user administration, reminders) — exportable as CSV.
* **Licensing as anti-piracy:** signed, machine-bound, enforced in packaged
  builds; vendor private key never ships or commits (`.gitignore`d).
* **Session hardening:** HttpOnly + SameSite cookies, Secure in production,
  8-hour lifetime.
* **No network exposure:** the server binds `127.0.0.1`; nothing listens on
  the LAN.
* **Supply chain:** UI libraries vendored and pinned; the installer ships a
  private Node runtime so schools never fetch anything.
* **Obfuscation:** application code is PyArmor-obfuscated in the shipped
  product (see §15 for its limits).

---

## 15. Known limitations

* **PyArmor trial build.** The default build uses the PyArmor *trial*, which
  (a) is not licensed for commercial use and (b) leaves 7 large modules as
  readable source (`bootstrap`, `reports`, `settings`, `students`,
  `teachers`, `term_exams`, `seed_generator`). Buy PyArmor Basic before
  selling; the pipeline obfuscates everything automatically afterwards.
* **Obfuscation is a deterrent, not DRM.** A determined attacker can still
  patch a trial-obfuscated build; the threat model is casual copying.
* **Machine-bound licenses.** Reformatting Windows or replacing the
  motherboard changes the machine code → re-issue the key (ledger-assisted).
* **Unsigned installer** triggers SmartScreen until you code-sign.
* **WhatsApp via Baileys** is an unofficial library; the paired number can
  in theory be banned by WhatsApp — the paced/approval sending modes exist
  to reduce that risk.
* **Data is per Windows user.** Two Windows accounts on one PC see separate
  databases.
* **Clock rules.** Rolling the clock back does not extend licenses; a
  far-future clock needs a support-issued replacement key.
* **Single-server design.** One school per Windows user per machine; there
  is no multi-branch synchronisation.

---

## 16. Current version

**1.0.0** — defined once in `installer/SchoolManager.iss`
(`#define MyAppVersion`), consumed by the exe name, the release folder and
the release manifest.  See [`CHANGELOG.md`](CHANGELOG.md) for what changed
in each release and [`ROADMAP.md`](ROADMAP.md) for what comes next.

Release artifacts (`python tools/make_release.py` →
`build/release/v1.0.0/`):

* `SchoolManager_Setup_v1.0.0.exe` (≈ 89.5 MB)
* `SHA256SUMS.txt`, `RELEASE-INFO.txt`

---

*School Manager — Copyright © 2020-2026 Ahmi software firm. All names,
phone numbers and demo data are fabricated; no real student data is used at
any point.*

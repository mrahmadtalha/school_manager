# School Manager — Update & Maintenance System Guide

**A complete "I can maintain my software myself" manual.**
No AI, no coding agent, no memory of this project's creation required —
every command below is real and works on the project as it exists today.

*Publisher: Ahmi software firm · Applies to product version 1.0.0 and later*

---

## 0. The five golden rules

1. **Backup before you touch anything.** Copy the data folder before every
   client update; run the test suite before every build.
2. **The changelog is the law.** Every change goes into `CHANGELOG.md`
   under `[Unreleased]` the moment you make it.
3. **The version lives in one place.** `installer/SchoolManager.iss` →
   `#define MyAppVersion "1.0.0"`. Bump it only there.
4. **Migrations are additive.** When you change the database, write a
   migration that only *adds* (check-then-add). Existing client data must
   survive.
5. **Never touch the two holiest folders:** `vendor_keys/` (your signing
   keys — lose them and every client must be re-keyed) and the client's
   `%LOCALAPPDATA%\SchoolManager` (their database, license and WhatsApp
   session).

---

## 1. Know your project

Assume your project folder is `C:\SchoolManager-dev` (substitute your real
path everywhere below). Open **PowerShell** in that folder.

### 1.1 File map — where everything lives

| You want to change… | Edit this file/folder |
|---|---|
| A page's behaviour (routes/urls) | `app/routes/<module>.py` — e.g. `fees.py`, `students.py`, `attendance.py` |
| A page's look (HTML) | `app/templates/<name>.html` |
| Styling | `app/static/style.css` |
| Business rules (calculations, ledgers) | `app/services/<module>.py` — e.g. `fee_ledger.py`, `licensing.py` |
| Database tables/columns | `app/models/<module>.py` **plus** a migration in `app/bootstrap.py` (§5) |
| Access rules (who may open what) | `app/security.py` (role map) and/or `app/license_guard.py` |
| Configuration keys/defaults | `app/config.py` |
| WhatsApp bridge behaviour | `whatsapp-service/server.js` (Node.js) |
| Windows launcher behaviour | `school_manager.pyw` |
| Installer (version, publisher, files) | `installer/SchoolManager.iss` |
| Demo data generator | `app/services/seed_generator.py` (CLI: `seed_data.py`) |
| Release/QA documents | `docs/` · version history: `CHANGELOG.md` · future: `ROADMAP.md` |

### 1.2 How the app starts (mental model)

`school_manager.pyw` / `run.py` → `create_app()` in `app/__init__.py` →
auto-migrations run → routes register → Waitress serves on `127.0.0.1`.
The browser is just a viewer; **all state is in the SQLite database** inside
the data folder.

| How it runs | Data folder |
|---|---|
| Development (`python run.py`) | `<project>\instance\` |
| Installed exe | `%LOCALAPPDATA%\SchoolManager\` |
| Override (tests/support) | `SCHOOL_DATA_DIR` environment variable |

---

## 2. Run the application manually (development)

```powershell
cd C:\SchoolManager-dev

# one-time per machine: create and activate the virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# one-time per machine: a secret key for development
setx SECRET_KEY "school-manager-local-secret-2026"
# close and reopen PowerShell after setx, then:

# start the app (plain Flask, port 5000)
python run.py
```

Open **http://127.0.0.1:5000** and log in.

* Stop the app with `Ctrl+C` in the terminal.
* **After editing any `.py` or `.html` file, restart `python run.py`.**
  (Flask does not auto-reload in this configuration.)

Production-style launch (what customers get): `python school_manager.pyw`
opens a standalone desktop window on port 8000. For development, plain
`python run.py` is easier.

---

## 3. Test a change manually in the browser

1. Start the app (`python run.py`).
2. Open the exact page you changed, e.g.
   `http://127.0.0.1:5000/fees`.
3. Press **Ctrl+F5** (ignore cached files).
4. Exercise the feature with real clicks: create/edit/delete something.
5. Check the data really persisted: reopen the page, or inspect the
   database with "DB Browser for SQLite" — the file is
   `C:\SchoolManager-dev\instance\school.db`.
6. Check the audit trail at `http://127.0.0.1:5000/audit-log` — your
   change should appear there.

If the page shows a traceback: the full error is in the terminal running
`python run.py`. Fix, restart, repeat.

---

## 4. Test commands

### 4.1 Run the tests for one area (fast, do this first)

```powershell
# examples — one file per area of the app
python -m pytest tests/test_fee_ledger.py tests/test_fees_charges.py -q
python -m pytest tests/test_attendance_late.py -q
python -m pytest tests/test_build_exe.py -q
```

All test files live in `tests/` (one file per area — pick the one whose
name matches what you changed). `-q` means quiet.

### 4.2 Run the FULL suite (required before every build/release)

```powershell
python -m pytest tests/ -q --tb=line --basetemp=build/.pytest
```

Expected result: **482 passed, 3 skipped, 0 failed** (numbers rise as you
add tests). If anything fails, the output names the exact test — fix before
continuing. The `--basetemp` flag keeps pytest's scratch files inside
`build/` and makes the suite pass on any machine.

### 4.3 Run the smoke test (end-to-end website walkthrough)

The smoke test walks 32 real browser-level checks (login, attendance,
marks, fees, receipts, audit…). It must run against a **throwaway
database**, never your real one:

```powershell
# create a scratch data folder
mkdir C:\temp\smoke-data
"" | Out-File C:\temp\smoke-data\school.db

$env:SCHOOL_DATA_DIR   = "C:\temp\smoke-data"
$env:DATABASE_URL      = "sqlite:///C:/temp/smoke-data/school.db"
$env:SECRET_KEY        = "smoke-secret"
$env:LICENSE_ENFORCEMENT = "0"
$env:AUTO_BACKUP_ENABLED = "0"

python seed_data.py --students 6 --teachers 2 --months 1   # fill scratch DB
python scripts/smoke_test.py --port 5099                   # 32/32 checks

Remove-Item Env:SCHOOL_DATA_DIR, Env:DATABASE_URL, Env:SECRET_KEY, `
    Env:LICENSE_ENFORCEMENT, Env:AUTO_BACKUP_ENABLED
Remove-Item -Recurse -Force C:\temp\smoke-data
```

Expected last line: `Smoke test: 32/32 checks passed.`
(The empty `school.db` file is important — it stops the first run from
copying your development database into the scratch folder.)

---

## 5. Database changes (migrations)

**Database system: SQLite.** One file. There is no migration tool to
install — this project migrates **automatically on startup**.

### 5.1 When is a migration needed?

| You changed… | Migration needed? |
|---|---|
| A `.py` file, template, or CSS — no table/column touched | **No** |
| Added a **new column** to an existing table | **Yes** — additive migration |
| Added a **new table** | Usually no — `db.create_all()` creates new tables on boot. Migration only needed if old client databases must get it *and* you removed the model first (just leave the model in place; `create_all` handles it) |
| Removed/renamed a column, or transformed data | **Yes** — and read §5.4 twice: such migrations are the risky kind |

### 5.2 How to write one (the project's real pattern)

All schema migrations live in **`app/bootstrap.py`** and run automatically
inside `create_app()` — in development *and* in the installed exe. Copy the
existing pattern (this is the real `migrate_admin_schema` from the file):

```python
def migrate_admin_schema(app):
    """Add role/parent-link columns to an existing admin_users table."""
    db_path = _sqlite_db_path(app)
    if not db_path or not os.path.exists(db_path):
        return

    with _sqlite_connection(db_path) as connection:
        columns = _table_columns(connection, 'admin_users')
        if not columns:
            return

        additions = [
            ('full_name', 'VARCHAR(120)'),
            ('role', "VARCHAR(20) DEFAULT 'admin'"),
            ('student_id', 'INTEGER'),
            ('is_active', 'BOOLEAN DEFAULT 1'),
            ('created_at', 'DATETIME'),
            ('last_login_at', 'DATETIME'),
        ]
        for name, ddl in additions:
            if name not in columns:
                connection.execute(f'ALTER TABLE admin_users ADD COLUMN {name} {ddl}')
                print(f'Migration: added {name} to admin_users')

        connection.execute("UPDATE admin_users SET role = 'admin' WHERE role IS NULL OR role = ''")
        connection.execute("UPDATE admin_users SET is_active = 1 WHERE is_active IS NULL")
        connection.commit()
```

**Your checklist for a new migration:**

1. Add the new column to the model in `app/models/<module>.py` **and**
   write the `migrate_xxx_schema(app)` function in `app/bootstrap.py`
   following the pattern above (check `if name not in columns` — this is
   what makes it safe to run a thousand times).
2. Register it in `create_app()` (`app/__init__.py`): add it to the import
   list from `app.bootstrap` and call it alongside the others.
3. The model change is what your code uses; the migration is what old
   client databases get. **Both. Always both.**
4. Migration rule: **only ADD columns/tables, never drop or rename.** Old
   columns stay (harmless); new code reads them if present.
5. Print a `Migration: …` line — that output is how you verify on client
   machines.

### 5.3 How migrations apply to an existing client (safely)

You do **not** run migrations by hand on client machines:

1. Deliver the new installer.
2. The client installs it (their data folder is untouched).
3. The **first launch of the new version runs `create_app()`**, which runs
   every `migrate_xxx_schema()` against their `school.db` — the terminal is
   hidden, but the lines appear in
   `%LOCALAPPDATA%\SchoolManager\school_manager.log`.
4. Verify: open their `school.db` in "DB Browser for SQLite" →
   `PRAGMA table_info(students);` and confirm the new column exists.

Because every migration is check-then-add, starting the app twice does
nothing twice, and a client that skips two versions is brought fully up to
date in one boot.

### 5.4 Before touching a client's database

1. Make them close the app.
2. Copy the **whole data folder**
   `%LOCALAPPDATA%\SchoolManager` to a USB stick (or at minimum
   `school.db`). This is the rollback.
3. Only then install the update.

---

## 6. Rebuild, create the .exe, and create the installer

### 6.1 The one command that does everything

```powershell
python tools/make_release.py
```

This wipes `build/`, runs the **full test suite** (the release gate),
obfuscates the code (PyArmor), builds the Windows executable (PyInstaller),
runs the exe's self-test, compiles the **installer** (Inno Setup), and
creates the release folder. It fails loudly if any step fails.

Prerequisites (one-time per build machine): Python 3.12 venv with
`pip install -r requirements.txt` (includes PyArmor + PyInstaller),
Node.js on PATH (for staging the bridge), Inno Setup 6
(`winget install JRSoftware.InnoSetup`).

### 6.2 Step-by-step (when you want to see each stage)

```powershell
python tools/build_product.py     # 1. obfuscate app → build/product
python tools/build_exe.py         # 2. PyInstaller → build/exe/SchoolManager (selftest runs)
python tools/build_installer.py --skip-exe   # 3. Inno Setup → setup exe
```

### 6.3 Bump the version BEFORE building

Edit **`installer/SchoolManager.iss`**, line 9:

```iss
#define MyAppVersion "1.0.1"     ; was 1.0.0
```

Everything else (exe name, release folder, manifest) follows automatically.

### 6.4 Where the final installer is located

```
build\release\v<version>\SchoolManager_Setup_v<version>.exe
build\release\v<version>\SHA256SUMS.txt        ← integrity hashes
build\release\v<version>\RELEASE-INFO.txt      ← what was built, sizes
```

Example: `build\release\v1.0.1\SchoolManager_Setup_v1.0.1.exe`

The customer's quick-start guide is already inside the installer
(`docs/QUICKSTART.txt` → installed next to the exe).

---

## 7. Delivering to a client

**What to deliver:** exactly one file —
`SchoolManager_Setup_v<version>.exe` from
`build\release\v<version>\`. Optionally also `SHA256SUMS.txt`.

**Plus the license:** the client's machine code comes from
`http://127.0.0.1:PORT/license` on *their* PC (shown on the activation
page). Issue their key on YOUR build machine:

```powershell
python tools/license_admin.py machine-code          # yours; for reference
# on the client PC, read the machine code shown on their license page, then:
python tools/license_admin.py issue --machine <CLIENT-CODE> --licensee "School Name" --days 365
```

Deliver the generated `.key` file (or its text) **separately** from the
installer — never inside it. The client pastes it at
`http://127.0.0.1:<port>/license`.

**What the client receives on their PC after install:**

| Location | Content |
|---|---|
| `C:\Program Files\SchoolManager\` | the application (+ WhatsApp bridge) |
| Desktop + Start Menu | "School Manager - Ahmi software firm" shortcuts |
| `%LOCALAPPDATA%\SchoolManager\` | **their** database, license, WhatsApp session, photos, backups, logs |

---

## 8. Updating an existing client's installation

The installer is built for this: same AppId → installs **over** the old
version in place, closes the running app first, and **never touches** the
data folder.

### 8.1 Safe update procedure (do exactly this)

1. **Backup the client's data** (§8.2).
2. Copy the new `SchoolManager_Setup_v<version>.exe` to their PC.
3. Make them close School Manager (sidebar **Exit Software**, or close the
   window). The installer also closes it automatically.
4. Run the installer → Next → Install. The old version is replaced;
   shortcuts stay.
5. Start School Manager. The **first boot applies any database migrations
   automatically** (§5.3).
6. Verify (§8.4).

### 8.2 Backup client data before an update

Close the app, then copy the whole folder to a USB stick:

```powershell
Copy-Item "$env:LOCALAPPDATA\SchoolManager" "D:\Backup\SchoolManager-2026-10-05" -Recurse
```

(Inside is their `school.db`, `license.key`, `license.state`,
`whatsapp-session\`, `uploads\`, `backups\`.) Alternatively, in the app:
**Settings → Backups → Create backup** (database only).

### 8.3 Files and folders that must NEVER be overwritten or deleted

| Path | Why |
|---|---|
| `%LOCALAPPDATA%\SchoolManager\school.db` | the school's entire records |
| `%LOCALAPPDATA%\SchoolManager\license.key` + `license.state` | their paid license; deleting forces re-activation |
| `%LOCALAPPDATA%\SchoolManager\whatsapp-session\` | WhatsApp pairing — deleting forces a new QR scan on the school phone |
| `%LOCALAPPDATA%\SchoolManager\backups\` + `uploads\` | their safety net and photos |
| `vendor_keys\` (on YOUR machine) | your private signing key — losing it re-keys every client |
| Never run a "clean up" or "reset" on the data folder | that IS their data |

The installer is built so a normal install/update/uninstall cannot delete
any of these — only a manual folder delete can.

### 8.4 Verify the client installation after updating

1. Windows **Settings → Apps → Installed apps** shows
   "School Manager - Ahmi software firm" with the **new version number**.
2. Launch the app → license page does **not** appear (license intact) →
   login works → student list shows their real data.
3. **Automation page** shows the WhatsApp bridge running and still paired
   (no QR required).
4. Check `%LOCALAPPDATA%\SchoolManager\school_manager.log` for
   `Migration: added …` lines and for any errors.
5. Quick functional pass: create a test student → take attendance →
   generate charges → delete the test student.

### 8.5 Rollback to the previous version

If an update causes a problem:

1. Close the app.
2. **Backup their data folder first** (§8.2) — the new version may have
   migrated the database.
3. Uninstall: Windows Settings → Apps → *School Manager - Ahmi software
   firm* → Uninstall (data folder survives).
4. Install the **previous** `SchoolManager_Setup_v1.0.0.exe` you kept.
5. Start the app and verify their data is readable.

**Honest caveat:** this project's migrations only *add* columns/tables, so
an older version tolerates a newer database. Rollback is therefore safe for
additive migrations — but if a future migration ever *transforms* data, the
old version will not show that transformation. This is exactly why §8.2
(take the backup) is not optional.

---

## 9. Worked examples

### Example 1 — Fix a bug on the Fees page

Symptom: receipts print the wrong total.

1. **Find the file:** fees logic lives in `app\routes\fees.py`
   (pages/urls) and `app\services\fee_ledger.py` (calculations). Search
   with VS Code: `Ctrl+Shift+F` → "receipt".
2. **Edit** the code, save.
3. **Run manually:** `python run.py` → open
   `http://127.0.0.1:5000/fees` → generate charges, record a payment, open
   a receipt. Press **Ctrl+F5** after every code restart.
4. **Area tests:**
   `python -m pytest tests/test_fee_ledger.py tests/test_fees_charges.py -q`
5. **Full suite:** `python -m pytest tests/ -q --tb=line --basetemp=build\.pytest`
6. **Changelog:** add under `[Unreleased]` → `### Fixed` →
   `- Fees — receipt totals now include adjustments`.
7. **Version bump:** `.iss` → `#define MyAppVersion "1.0.1"`.
8. **Build:** `python tools/make_release.py`.
9. **Client update:** §8.1 on every client PC (backup → install → verify).

### Example 2 — Add a new feature ("Transport" module, for example)

1. **Model:** add `app/models/transport.py` (copy the style of
   `app/models/expense.py`: `db.Model`, columns, `__repr__`).
2. **Register the model** in `app/models/__init__.py`.
3. **Migration:** if you added columns to an *existing* table too, write
   `migrate_transport_schema(app)` in `app/bootstrap.py` (§5.2) and
   register it in `app/__init__.py`. A brand-new table needs no migration.
4. **Routes:** create `app/routes/transport.py` — copy the skeleton of
   `app/routes/expenses.py` (`@main.route(...)`, `role_required(...)`,
   `render_template(...)`).
5. **Register the blueprint module** in `app/routes/__init__.py` and add
   its pages to the role map in `app/security.py` (decide which roles may
   open it).
6. **Template:** create `app/templates/transport.html` (copy
   `expenses.html` as the skeleton — it extends `base.html`).
7. **Sidebar link:** add it in `app/templates/base.html` near the other
   nav items.
8. **Tests:** create `tests/test_transport.py` (copy
   `tests/test_expenses.py`-style tests using the `admin_client` fixture).
9. **Run manually:** `python run.py` → use the feature in the browser →
   check `/audit-log`.
10. **Area tests** → **full suite** (§4.2) → **changelog** (`### Added`)
    → **version bump** (MINOR: `1.1.0`) → **build** (§6) → **deliver** (§7)
    → **client update** (§8).

### Example 3 — Database change (add a column to students)

Situation: schools need a "Blood Group" note on students.

1. **Model first:** in `app/models/student.py` add
   `blood_group = db.Column(db.String(10), nullable=True)`.
2. **Use it** in `app/routes/students.py` (accept/edit/save) and
   `app/templates/students.html` (input field).
3. **Migration** (needed: existing client tables lack the column) — in
   `app/bootstrap.py`:
   ```python
   def migrate_student_blood_group(app):
       """Add the optional blood_group column to students."""
       db_path = _sqlite_db_path(app)
       if not db_path or not os.path.exists(db_path):
           return
       with _sqlite_connection(db_path) as connection:
           columns = _table_columns(connection, 'students')
           if not columns:
               return
           if 'blood_group' not in columns:
               connection.execute("ALTER TABLE students ADD COLUMN blood_group VARCHAR(10)")
               print('Migration: added blood_group to students')
               connection.commit()
   ```
   Register it in `app/__init__.py` like the others.
4. **Test locally with OLD data:** copy a client's `school.db` (or your
   oldest backup) into `instance\` temporarily, run `python run.py`, and
   confirm the `Migration:` line prints and their records are intact.
5. **Full suite** → changelog (`### Added`) → **this is data-related: bump
   PATCH or MINOR depending on visibility** → build → deliver.
6. **On the client:** backup (§8.2) → install → start once → verify the
   column exists in DB Browser → enter data normally. Old rows simply have
   an empty Blood Group until edited.

### Example 4 — WhatsApp change (edit the bridge)

Situation: improve the message text or fix bridge behaviour.

1. **Edit** `whatsapp-service\server.js` (Node.js — restart rules apply,
   not Flask's).
2. **Test on your machine without touching real sessions:**
   ```powershell
   cd whatsapp-service
   $env:APP_PORT = "3099"; $env:SESSION_PATH = "C:\temp\bridge-session"
   node server.js
   ```
   Open `http://127.0.0.1:3099/health` — expect
   `{"ok":true,...,"status":"qr_ready",...}`. Scan the QR with a test
   phone if you need to send. Stop with `Ctrl+C`.
   Your **real** development/production sessions live elsewhere
   (`SESSION_PATH` decides) and are never touched.
3. **Node tests:** `cd whatsapp-service && npm test` (the bridge's own
   suite).
4. **Python side** (if you also changed `app/services/whatsapp_bridge.py`
   or templates): `python -m pytest tests/test_whatsapp_optional.py -q`.
5. **Build & deliver:** the bridge ships inside the installer, so the
   update path is the standard one (§6 + §8). During install the old
   `whatsapp-service` files are replaced — **the WhatsApp session is NOT
   part of those files** (it lives in
   `%LOCALAPPDATA%\SchoolManager\whatsapp-session`), so the school's
   phone stays paired. No QR re-scan needed.
6. **Verify on the client after update:** Automation page → bridge shows
   running → status still *connected* (not `qr_ready`).

### Example 5 — Simple frontend/template change (fastest workflow)

Situation: the Fees page needs a clearer heading.

1. **Edit** `app\templates\fees.html` — save.
2. **Run** `python run.py` → open the Fees page → **Ctrl+F5**.
   (If the change doesn't appear, restart `python run.py` — Flask caches
   templates when not in debug mode.)
3. **Template-touching tests** (they assert page content):
   `python -m pytest tests/test_ui_polish.py tests/test_flash_messages.py -q`
4. Cosmetic-only changes don't require the full suite, but it is cheap
   insurance: `python -m pytest tests/ -q --tb=line --basetemp=build\.pytest`
5. Ship it with the next version: changelog (`### Changed`) → version
   bump → `python tools/make_release.py` → §8 client update.

---

## 10. Quick reference card

| Task | Command |
|---|---|
| Start app (development) | `python run.py` |
| Start app (product style) | `python school_manager.pyw` |
| Tests for one area | `python -m pytest tests/test_fee_ledger.py -q` |
| Full test suite | `python -m pytest tests/ -q --tb=line --basetemp=build\.pytest` |
| Smoke test (isolated) | see §4.3 |
| Manual database backup | `python scripts/backup_db.py` |
| Build release (everything) | `python tools/make_release.py` |
| Version bump | edit `installer/SchoolManager.iss` → `#define MyAppVersion` |
| Installer output | `build\release\v<version>\SchoolManager_Setup_v<version>.exe` |
| Client data folder | `%LOCALAPPDATA%\SchoolManager` |
| Client log file | `%LOCALAPPDATA%\SchoolManager\school_manager.log` |
| History of changes | `CHANGELOG.md` |
| What comes next | `ROADMAP.md` |

**Remember:** change → test in browser → area tests → full suite →
changelog → version bump → `make_release.py` → deliver →
client backup → install → verify.

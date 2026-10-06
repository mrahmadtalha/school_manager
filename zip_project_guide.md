# ZIP & Update Command Guide — School Manager

Every command below was **executed and verified** against this exact
project (`C:\Users\ahmad talha\Desktop\New folder\zip`) on Windows.
Copy-paste them into **Windows CMD** from the project folder:

```cmd
cd "C:\Users\ahmad talha\Desktop\New folder\zip"
```

The ZIP tool used is the Windows built-in bsdtar. It is called with its
full path (`C:\Windows\System32\tar.exe`) so the commands work even if
another `tar.exe` (e.g. Git Bash's GNU tar) is earlier on your PATH — GNU
tar cannot create ZIP files.

---

## 1. FULL BACKUP ZIP (everything, nothing excluded)

Run these two lines from the project folder:

```cmd
mkdir C:\SchoolManager-backups
C:\Windows\System32\tar.exe -a -c -f "C:\SchoolManager-backups\SchoolManager-full-backup.zip" .
```

* **Created at:** `C:\SchoolManager-backups\SchoolManager-full-backup.zip`
* **Contains:** the ENTIRE project — all source, `vendor_keys\` (private
  key + ledger), `instance\` (dev database), `.git\`, `build\release\`
  (the signed-off installer), `whatsapp-service\` incl. `node_modules\`,
  `screenshots\`, docs, tests, caches — nothing excluded.
* The ZIP is created **outside** the project folder, so it can never
  include itself.
* Tip: rename the file after creating it (e.g. append the date) so an
  older backup is not overwritten by the next run.

## 2. AI-SHARE ZIP (safe for Claude / ZCode / AutoClaw / ChatGPT)

Run these two lines from the project folder:

```cmd
mkdir C:\SchoolManager-backups
C:\Windows\System32\tar.exe -a -c -f "C:\SchoolManager-backups\SchoolManager-AI-share.zip" --exclude="build" --exclude="vendor_keys" --exclude="instance" --exclude=".git" --exclude="node_modules" --exclude="session" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="*.pyc" --exclude="*.log" --exclude="screenshots" --exclude=".env" .
```

* **Created at:** `C:\SchoolManager-backups\SchoolManager-AI-share.zip`
* **Excludes:** `vendor_keys\` (your private signing key + license
  ledger), `instance\` (development database + `.secret_key`), `build\`
  (build output), `.git\`, `whatsapp-service\node_modules\` (regenerable
  with `npm install`), `whatsapp-service\session\` (dev WhatsApp pairing),
  caches (`__pycache__`, `.pytest_cache`, `*.pyc`), logs, and product
  screenshots.
* **Keeps:** all application code, tests, tools, scripts, docs, installer
  configuration, `app\services\license_public_key.py` (public by design),
  and the WhatsApp bridge source — everything an AI needs to understand
  and improve the project.
* Verified contents: 271 files, zero excluded-folder leaks.

**Never send either ZIP to a client.** Client delivery is section 3.

## 3. CLIENT DELIVERY

After any change, build the release and deliver ONE file:

```cmd
python tools\make_release.py
```

**SEND THIS FILE:**
`C:\Users\ahmad talha\Desktop\New folder\zip\build\release\v1.0.0\SchoolManager_Setup_v1.0.0.exe`

**LOCATION:** the version folder mirrors
`installer\SchoolManager.iss` → `#define MyAppVersion`. After bumping to
1.0.1 the file is
`build\release\v1.0.1\SchoolManager_Setup_v1.0.1.exe`.

The client needs **only this .exe installer**. One additional file is
required separately: their **license key**, which you issue from this
project and deliver by email/WhatsApp:

```cmd
python tools\license_admin.py issue --machine <CLIENT-MACHINE-CODE> --licensee "School Name" --days 365
```

(The `<CLIENT-MACHINE-CODE>` is shown on the license page of the client's
installed app — this is the one place a value is read from their screen.)
The generated `.key` file appears in `vendor_keys\` — send that file to
the client, but **keep `vendor_keys\license_private.key` private forever**.

---

## 4. FUTURE UPDATE WORKFLOW (exact commands)

Run these from the project folder after any change. Sections 4.1–4.3 are
the same for a bug fix, a new feature, a database migration or a WhatsApp
update — only *which* files you edited differs.

### 4.0 One-time setup (per machine)

```cmd
python -m venv venv
venv\Scripts\Activate.bat
pip install -r requirements.txt
setx SECRET_KEY "school-manager-local-secret-2026"
```

(Close and reopen CMD after `setx`. `pip install` includes PyArmor and
PyInstaller, so the build commands below work immediately.)

### 4.1 Run the application manually

```cmd
python run.py
```

Open `http://127.0.0.1:5000`, press **Ctrl+F5** after code changes, and
restart `python run.py` after editing any file.

### 4.2 Run tests

```cmd
:: one area (example: fees)
python -m pytest tests\test_fee_ledger.py tests\test_fees_charges.py -q

:: the FULL suite (required before every build)
python -m pytest tests\ -q --tb=line --basetemp=build\.pytest
```

Expected full-suite result: **482 passed, 3 skipped, 0 failed**.

### 4.3 Run the smoke test (isolated, never touches your real data)

```cmd
mkdir C:\temp\smoke-data
type NUL > C:\temp\smoke-data\school.db
set SCHOOL_DATA_DIR=C:\temp\smoke-data
set DATABASE_URL=sqlite:///C:/temp/smoke-data/school.db
set SECRET_KEY=smoke-secret
set LICENSE_ENFORCEMENT=0
set AUTO_BACKUP_ENABLED=0
python seed_data.py --students 6 --teachers 2 --months 1
python scripts\smoke_test.py --port 5099
```

Expected last line: `Smoke test: 32/32 checks passed.` — then close that
CMD window (it resets the temporary variables) or clear them with
`set SCHOOL_DATA_DIR=` etc.

### 4.4 Build the release and the installer

```cmd
python tools\make_release.py
```

(Or step by step: `python tools\build_product.py`,
`python tools\build_exe.py`, `python tools\build_installer.py --skip-exe`.)

### 4.5 Where the installer lands

```cmd
build\release\v1.0.0\SchoolManager_Setup_v1.0.0.exe
```

(after a version bump in `installer\SchoolManager.iss`, the folder and
file name carry the new version automatically).

### 4.6 Update the client

1. Client closes School Manager.
2. Client copies their data folder
   `%LOCALAPPDATA%\SchoolManager` to a USB stick (backup).
3. Client runs the new
   `SchoolManager_Setup_v<version>.exe` — data, license and WhatsApp
   pairing are preserved automatically.
4. First launch applies any database migrations automatically.
5. Verify: version number in Windows Settings → Apps, login works, data
   present, Automation page shows the bridge running.

**Rollback:** client backups their data folder → uninstalls → runs the
previous version's setup exe (kept in your release archive). Their data
survives uninstall.

---

## 5. Database migrations — where they live

Migrations are **not** command-line steps. They are functions in
`app\bootstrap.py` that run automatically when any copy of the app starts.
To add one: edit `app\bootstrap.py` following the existing
`migrate_admin_schema` pattern, register it in `app\__init__.py`, and
update the matching model in `app\models\`. Full walkthrough:
`update_system_guide.md` §5 and Example 3.

---

## 6. What never goes into any ZIP sent to a client

`vendor_keys\` · `instance\` · any source folder · `build\product`,
`build\exe`, `build\pyinstaller`, `build\installer-staging` · AI-share
ZIPs. Clients receive **only** the setup exe from `build\release\`.



1. FULL BACKUP ZIP (everything, nothing excluded):

C:\Windows\System32\tar.exe -a -c -f "SchoolManager-full-backup.zip" "zip"

2. AI-SHARE ZIP (safe for Claude/ZCode/ChatGPT — secrets and junk excluded):

C:\Windows\System32\tar.exe -a -c -f "SchoolManager-AI-share.zip" --exclude="build" --exclude="vendor_keys" --exclude="instance" --exclude=".git" --exclude="node_modules" --exclude="session" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="*.pyc" --exclude="*.log" --exclude="screenshots" --exclude=".env" "zip"
# Ahmi software firm — Personal Operations Notes (School Manager)

Private working notes for maintaining and selling School Manager.
Public/customer-facing documents live in `README.md` and `docs/`.

---

## Client Delivery — Exactly What to Send

### The three delivery categories — never mix them

**Copy-paste commands for all three live in
[`zip_project_guide.md`](zip_project_guide.md) — every command there was
executed and verified against this project.** Short versions:

#### A. MY FULL BACKUP
→ Everything, nothing excluded.

Zip the **entire project folder** as-is: `app\`, `tests\`, `tools\`,
`scripts\`, `docs\`, `installer\`, `whatsapp-service\` (including
`node_modules\`), `build\release\`, `vendor_keys\` (**including the
private key**), `instance\`, `.git\`, and all root files. Disaster-
recovery copy. Store off-machine. Never sent to anyone.

Exact command (CMD, from the project folder):

```cmd
mkdir C:\SchoolManager-backups
C:\Windows\System32\tar.exe -a -c -f "C:\SchoolManager-backups\SchoolManager-full-backup.zip" .
```

Creates `C:\SchoolManager-backups\SchoolManager-full-backup.zip`
(4,475 files verified — includes `vendor_keys\`, `.git\`, `instance\`,
`build\release\`; the ZIP is outside the project so it cannot include
itself). Rename it after creating (e.g. append the date) so the next run
does not overwrite it.

#### B. AI-SHARE ZIP
→ Safe project copy for Claude / ZCode / AutoClaw / ChatGPT, with
sensitive and private data excluded.

Include: `app\`, `tests\`, `tools\`, `scripts\`, `docs\`,
`installer\`, root docs and scripts, `whatsapp-service\server.js` +
`package.json` + `package-lock.json`.
Exclude: `vendor_keys\` (private signing key + ledger), `instance\`
(dev database + `.secret_key`), `build\`, `.git\`,
`whatsapp-service
ode_modules\` (regenerable with `npm install`),
`whatsapp-service\session\`, caches, logs, screenshots.
`app\services\license_public_key.py` MAY be included (public by design).

Exact command (CMD, from the project folder):

```cmd
mkdir C:\SchoolManager-backups
C:\Windows\System32\tar.exe -a -c -f "C:\SchoolManager-backups\SchoolManager-AI-share.zip" --exclude="build" --exclude="vendor_keys" --exclude="instance" --exclude=".git" --exclude="node_modules" --exclude="session" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="*.pyc" --exclude="*.log" --exclude="screenshots" --exclude=".env" .
```

Creates `C:\SchoolManager-backups\SchoolManager-AI-share.zip`
(271 files verified — zero leaks of excluded folders).

#### C. CLIENT DELIVERY
→ Only the production installer the client needs:
`SchoolManager_Setup_v<version>.exe` from `build\release\v<version>\`.
It contains the obfuscated application, the WhatsApp bridge with its
private `node.exe`, and the quick-start guide. No source file, ZIP, or
project folder is ever sent to a client. Their license `.key` file is
delivered separately (issued with `tools\license_admin.py`).

Exact commands (CMD, from the project folder):

```cmd
python tools\make_release.py
dir build\release\v1.0.0
```

The installer appears at
`build\release\v<version>\SchoolManager_Setup_v<version>.exe`
(89.5 MB for v1.0.0; SHA-256 recorded in the same folder). Issue the
client license separately — the generated `.key` lands in
`vendor_keys\`; email that file, never the private key:

```cmd
python tools\license_admin.py issue --machine <CLIENT-MACHINE-CODE> --licensee "School Name" --days 365
```

---

## Quick reference — what goes where

| Situation | What I Send Client | What I Keep Private |
|---|---|---|
| New installation | `SchoolManager_Setup_v<version>.exe` (+ `SHA256SUMS.txt`); their license `.key` separately | `vendor_keys\` (private key + ledger), all source code, my `instance\` dev DB |
| Bug fix | New full installer `SchoolManager_Setup_v<new-patch>.exe` (data/session preserved automatically) | Same as above; pre-release source/changes |
| New feature | New full installer (MINOR version bump) | Same as above; feature source until released |
| Database update | New full installer (migration applies itself on first boot); their pre-update data-folder backup | Same as above; the migration design notes |
| WhatsApp update | New full installer (session preserved automatically) | Same as above; bridge source/changes |
| Emergency hotfix | Rebuilt PATCH installer — or, WhatsApp-only, the single `server.js` file to drop into `whatsapp-service\` | Same as above; the hotfix source |

# School Manager — Release Checklist (Ahmi software firm)

Every release follows this checklist top to bottom.  Sections A–C are
automated by `tools/make_release.py`; sections D–F are manual QA steps that
must be ticked on a clean Windows machine before the installer is given to a
school.

---

## A. Automated build & verification (no human steps)

Run from the project root on the build machine:

```powershell
python -m pytest tests/ -q                      # full test suite must be green
python tools/make_release.py                    # clean rebuild + package + manifest
```

`make_release.py` performs a **clean rebuild from scratch**:

1. deletes `build/` entirely (no stale artifacts can ship),
2. obfuscates the app (PyArmor) and assembles the product tree,
3. bundles the Windows executable (PyInstaller, `--selftest` verified),
4. stages the WhatsApp bridge with a private `node.exe`,
5. compiles `SchoolManager_Setup_v<version>.exe` (Inno Setup),
6. writes `build/release/v<version>/` with the installer + `SHA256SUMS.txt`
   + `RELEASE-INFO.txt` manifest.

Gate: the script must finish with all verifications green and the suite must
report **0 failed**.

## B. Installer QA (clean Windows 10/11 VM — no dev tools installed)

| # | Check | Expected |
|---|---|---|
| B1 | Double-click the setup exe | SmartScreen "More info → Run anyway" (unsigned), then UAC prompt |
| B2 | Install wizard | Publisher **Ahmi software firm** visible; installs to `C:\Program Files\SchoolManager` |
| B3 | Shortcuts | Desktop + Start Menu: **"School Manager - Ahmi software firm"** |
| B4 | First launch (double-click shortcut) | Standalone app window opens; **license activation page** shown first |
| B5 | License activation | Paste vendor key → activated; setup wizard appears |
| B6 | Setup wizard | Create admin, school profile; demo-data options work (period/features) |
| B7 | Data folder | `%LOCALAPPDATA%\SchoolManager` created: `school.db`, `school_manager.log`, `license.key`, `license.state`, `whatsapp-session\` |
| B8 | WhatsApp bridge | Automation page shows bridge running; **QR appears**; scan with school phone; status becomes connected |
| B9 | WhatsApp test message | Send-test to a real number delivers |
| B10 | Offline test | Disable network; full UI styled, all pages work, PDF/Excel exports work (WhatsApp sending is the only offline-limited feature) |
| B11 | Restart persistence | Close window (app exits), relaunch: license + data + WhatsApp pairing intact, no re-scan needed |
| B12 | Logo upload | Settings → upload logo: works (stored in data folder), appears in header and PDF exports |

## C. Daily-use smoke (30 minutes, on the installed copy)

- Add a class/section/subject, admit a student (photo optional), admit 5 demo students via the advanced seeder.
- Take attendance (mark absent/late/leave), check the attendance summary.
- Generate monthly fee charges, record a payment, print the receipt.
- Create a test, enter marks, generate a result card PDF.
- Issue an ID card PDF (photo shows if uploaded; initials placeholder otherwise).
- Run a backup from Settings; confirm the file in `%LOCALAPPDATA%\SchoolManager\backups`.
- Log in as `teacher`/`parent` demo roles and confirm restrictions.
- **Exit Software** from the sidebar → app exits cleanly (window + bridge close).

## D. Update & uninstall QA

| # | Check | Expected |
|---|---|---|
| D1 | Run the next version's setup over an installed copy | Updates in place (same AppId), closes the running app first |
| D2 | After update | Database, license, WhatsApp session, backups all intact; **no re-pairing** |
| D3 | Uninstall | App + shortcuts removed; **data folder survives**; "Installed apps" entry removed |

## E. Release administration (vendor)

- [ ] Version bumped in `installer/SchoolManager.iss` (`#define MyAppVersion`).
- [ ] Release notes written; installer + `SHA256SUMS.txt` archived under
      `releases/v<version>/` (off-build-machine storage).
- [ ] Optional: code-sign the installer (`signtool sign /fd SHA256 …`) to
      remove SmartScreen warnings.
- [ ] License ledger (`vendor_keys/issued_licenses.csv`) updated with the
      customer's entry; customer's license file delivered **separately** from
      the installer.
- [ ] Support playbook: machine changed → re-issue key with the new machine
      code (`tools/license_admin.py machine-code` on the customer PC);
      never share `vendor_keys/license_private.key`.

## F. Known limitations to communicate to schools

- The license is machine-bound: reformatting Windows or replacing the
  motherboard requires a re-issued key (free of charge — keep the ledger).
- WhatsApp sending requires the phone to stay paired; logging the phone out
  of WhatsApp Web/Linked devices requires a fresh QR scan.
- The clock must be set correctly; rolling it back does not extend licenses
  (signed clock state), and a far-future clock needs a support call.

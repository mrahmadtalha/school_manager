# Changelog — School Manager

All notable changes to the **School Manager** product by
**Ahmi software firm** are documented in this file.

---

## Format guide (how to maintain this file)

When you add, remove, fix or improve a feature, record it **immediately**
under the `[Unreleased]` heading using the rules below. When you cut a
release, rename `[Unreleased]` to the new version and date.

**Version numbers** follow semantic versioning, applied to the product:

| Bump | When | Example |
|---|---|---|
| **MAJOR** (1.x.x → 2.0.0) | A new major module, a data-format change that requires migration, or anything that breaks a school's workflow | "Online fee collection" |
| **MINOR** (1.0.x → 1.1.0) | A new feature or a visible improvement to an existing module | "Urdu interface", "SMS fallback" |
| **PATCH** (1.0.0 → 1.0.1) | Bug fixes, small refinements, build/signing changes — no new features | "Fixed receipt numbering gap" |

**Entry rules:**

1. Work happens under `## [Unreleased]` — move entries out only on release.
2. Use exactly these categories, in this order:
   `### Added` · `### Changed` · `### Fixed` · `### Removed` ·
   `### Deprecated` · `### Security`
3. One line per change: **`Module — what changed (for whom)`**.
   Name the module first so readers can scan.
4. Write for school owners, not developers: "Fees — receipts now show the
   class teacher" beats "refactored receipt context builder".
5. Never delete history. The newest version is always at the top.
6. On release: set the version and date, bump `#define MyAppVersion` in
   `installer/SchoolManager.iss`, run `python tools/make_release.py`,
   and note the installer's SHA-256 from `build/release/`.

**Template for a new version:**

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- Module — feature description

### Changed
- Module — behaviour change description

### Fixed
- Module — what was broken and now works

### Security
- Anything affecting data protection or access control
```

---

## [2.1.0] - 2026-10-10

Timetables — the timetable system was rebuilt around two templates, and the
old one was removed.

### Added
- Timetables — two ready-made layouts to choose from: **Teacher-wise Chart**
  (teachers down the side, periods across, breaks as grey bands) and **Class
  Weekly Grid** (one grid per class, days across). Both are views over the same
  saved timetable, so switching layout never changes the data.
- Timetables — **one-click Generate** builds a clash-free timetable for the
  ticked classes from your own classes, subjects, teachers and period
  structure. No teacher is ever booked in two places at once.
- Timetables — manual editing: change the subject or the teacher in any cell
  and save; reopening the timetable shows the latest saved version.
- Settings — **Timetable Periods** on the Academic tab: periods per day,
  minutes per period, break position and length, and the break label. The
  Timetables page reads these automatically, so timings are never re-entered.
- Timetables — a Period Settings shortcut on the hub, and the saved timetable
  is remembered per class/section.

### Changed
- Settings — the first period now starts at the **School Start Time** from
  School Settings, so timings have a single source of truth.
- Classes — the per-class "Timetable" link now opens the Timetables page
  instead of a separate per-class editor.

### Removed
- Timetables — the old timetable surfaces are gone: the Master Timetable page
  (period structure, required-periods and the preview-then-apply generator),
  the per-class timetable editor with its PDF export, the conflict auto-fix
  flow, and the date-wise daily substitutions sheet. The hub's one-click
  generation replaces them.
- Timetables — the transient `timetable_drafts` scratch table is dropped on
  upgrade. No timetable data, class, subject, teacher or school setting is
  affected.
- Timetables — teachers keep their own timetable views and conflict
  reporting; only the administrative editors above were removed.

---

## [2.0.0] - 2026-10-09

New modules since 1.0.0 — Other Income, Inventory & Sales, and the
Financial Insights page — plus advance credit and write-off switched on,
the restored period-comparison panel, and a payroll page fix.

### Added

- Insights — a plain-language "Financial Insights" page for the owner: shows how
  much was collected, how much was expected, arrears recovered, salary burden,
  the biggest expense increases and sales performance, each with a short note on
  what needs attention
- Reports — the expenses report can now be downloaded as an Excel (.xlsx) file,
  alongside the existing PDF and CSV
- Fees — the receipt now shows where the money actually went, listing each month
  the payment settled (for example "Rs 1,000 applied to August 2026") instead of
  only the month it was recorded from
- Fees — advance credit and write-off are now switched on: a payment larger than
  the outstanding dues is accepted and the extra is held as credit for the
  student, and an uncollectable balance can be written off with a reason

### Changed

- Financial Overview — the period-comparison panel is back: pick two or more
  months, whole years or sessions and see them side by side, with a difference
  column, a chart and a month-by-month breakdown

### Fixed

- Payroll — the Payroll page no longer shows "500 Unexpected error" once a
  month's payroll has been saved; recording a salary payment works and the
  message it shows quotes the right amounts

---

## [1.0.0] - 2026-10-05

First commercial release of the Windows product
(`SchoolManager_Setup_v1.0.0.exe`), built by the 7-phase product program:
offline licensing → offline assets & launcher → WhatsApp core → code
obfuscation → executable packaging → installer → release QA.

### Added

**Core school modules**

- Students — admissions, profiles with optional photos, custom fields
  (with mandatory-field support), per-class roll numbering with cascade
  shifting, Excel/CSV import with validation, exports, archive/restore,
  per-student change history
- Teachers — records with qualification, experience and salary structure
  (monthly/hourly)
- Classes — classes, sections, subjects, per-class standard fees, editable
  Monday–Saturday timetable with period timings and PDF export
- Attendance — daily student and teacher attendance (Present/Absent/Late/
  Leave) with late check-in times, whole-class quick marking, summaries
  and exports
- Fees — append-only transaction ledger (charges/payments/adjustments),
  explicit monthly charge generation, partial payments, numbered receipts,
  reconciliation with discrepancy repair, defaulter exports, WhatsApp
  reminder queue, class-wide fee updates with confirmation
- Expenses — categories, expense log, one-click "continue last month's
  expense", monthly scoped views and exports
- Tests & exams — class tests, whole-class batch mark entry with proper
  absent handling, configurable grading scale, term exams with date sheets
  and tabulation with positions
- Reports & documents — result cards, transcripts, tabulation sheets, date
  sheets, student/teacher ID cards (photo optional), certificates — as
  print-ready PDFs; Excel/CSV exports across the system
- Payroll — monthly staff payroll with attendance snapshots, deductions
  and payment tracking
- Expenses & financials — income/expense summaries and period comparisons
- Parent portal — read-only access for guardians, limited to their own
  children (multiple children supported)
- Administration — school profile with logo and brand colours, academic
  session, grading scale, holiday ranges, backups (manual + automatic
  hourly with retention), audit trail with CSV export

**WhatsApp automation (core component)**

- Node bridge shipped inside the installer with its own private Node
  runtime; schools never install Node.js
- QR-code pairing with the school's WhatsApp number; the session survives
  updates (stored in the data folder)
- Guardian notifications for absence/late/results with editable templates,
  plus class broadcasts
- Three sending modes: approval, auto, delayed (human-paced)
- Delivery status tracking and logs; message queue with retry counters
- Optional Meta Cloud API integration method
- Robust socket configuration and process-level error guards so transient
  network problems never crash the bridge

**Windows product experience**

- Desktop launcher: one double-click opens a standalone app window
  (Edge/Chrome app mode); `--browser` opens a normal tab
- "Exit Software" button (sidebar, with confirmation dialog) and
  window-close both shut the background server down gracefully
- Per-school data folder (`%LOCALAPPDATA%\SchoolManager`) holding the
  database, license, WhatsApp session, photos, backups and logs — with
  automatic migration from older layouts
- First-run setup wizard with optional demo-data generation (choose
  students/teachers, history period 1 month → 10 years, and which areas to
  include) running in the background with a live progress screen
- Boot diagnostics written to `school_manager.log`
- Automatic hourly database backups with retention

**Licensing (offline)**

- Ed25519-signed license files bound to the Windows machine code
- Expiry warning (last 30 days), grace period (default 7 days), then a
  read-only lockout that always preserves viewing, printing, exports,
  login, backups and license activation
- Signed "latest date seen" state defeating clock rollback; replacement
  keys for wrong far-future clocks
- Vendor-only CLI (`tools/license_admin.py`): key-pair init, license
  issuing with ledger, inspection, machine-code lookup

**Installer & release pipeline**

- Inno Setup installer with Ahmi software firm branding, stable AppId for
  in-place updates, desktop/start-menu shortcuts, clean uninstaller —
  school data preserved on update and uninstall
- PyArmor-obfuscated application code frozen into a windowed
  `SchoolManager.exe` (PyInstaller onedir) with an embedded `--selftest`
  (routes, offline assets, license gate, bundled bridge)
- Vendored UI libraries (Bootstrap, Font Awesome, jQuery, DataTables,
  qrcodejs, Chart.js) for a fully offline interface
- One-command release build (`tools/make_release.py`): clean rebuild, full
  test suite gate, installer compilation, SHA-256 manifest

**Security**

- Five roles (Administrator, Principal/Owner, Accountant, Teacher,
  Parent/Guardian) with deny-by-default per-endpoint authorisation
- Complete audit trail with before/after JSON snapshots and business
  events (logins, charges, payments, voids, settings changes, exports,
  user administration, reminders)
- scrypt password hashing, login throttling with lockout, HttpOnly/
  SameSite session cookies
- Server binds to `127.0.0.1` only; the WhatsApp bridge authenticates with
  a per-launch token

### Changed

- Setup wizard: the "Load demo data" option is **off by default** — schools
  start with a clean database
- Fees page: monthly charges are created via an explicit "Generate monthly
  charges" action (a page load never writes billing data), which also lets
  read-only (expired-license) schools view any month

### Fixed

- Student edit no longer fails for records without a stored sponsor CNIC
- Photo replacement on Windows no longer fails when a browser still holds
  the previous image open
- Report-card PDFs, ID documents and transcripts resolve the school logo
  from the data folder (the install directory is read-only)

---

## Format note

This changelog follows the [Keep a Changelog](https://keepachangelog.com)
structure. See also: `ROADMAP.md` (what comes next),
`docs/RELEASE_CHECKLIST.md` (how to ship), `docs/PRODUCT_OVERVIEW.md`
(what to tell schools).

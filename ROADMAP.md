# Roadmap — School Manager

Where the product goes after v1.0.0.  Maintained by **Ahmi software firm**.

> **Status of this document.**  Everything below is a *candidate or
> intention*, not a promise and not a completed feature — the changelog
> (`CHANGELOG.md`) is the only record of what actually ships.  Items move
> onto the version tracks based on customer feedback from real schools.
> The manual QA and release procedure live in
> `docs/RELEASE_CHECKLIST.md`; the product's honest boundaries live in
> `docs/PRODUCT_OVERVIEW.md` (§ Limitations).

---

## How versions work

| Bump | Meaning | Example |
|---|---|---|
| **MAJOR** | New major module, or a change that needs data migration / changes school workflow | online fee collection |
| **MINOR** | New features and visible improvements inside existing modules | a new report, an interface language |
| **PATCH** | Fixes, refinements, build/signing changes — nothing new | crash fix, installer polish |

Every change is recorded under `[Unreleased]` in `CHANGELOG.md` as it is
made and promoted to a version on release
(`installer/SchoolManager.iss` → `#define MyAppVersion` is the version's
single source of truth; `python tools/make_release.py` builds and packages
the release).

**Status labels used below:**

| Label | Meaning |
|---|---|
| 🟢 **Planned** | Committed for that version, spec exists |
| 🟡 **Considering** | Real candidate; prioritised by customer feedback |
| ⚪ **Later** | Wanted someday; not scheduled |
| ⛔ **Not for now** | Deliberately out of scope (with the reason) |

---

## v1.0.x — patch track (quality & release polish)

Focus: shipping quality, trust and professionalism — no behaviour changes
for schools.

- 🟢 **PyArmor Basic license** — remove the trial's limits so all 78
  application modules ship obfuscated (7 large modules currently ship as
  readable source) and the commercial-use restriction is lifted
- 🟢 **Code-signed installer** — Authenticode signature to remove the
  SmartScreen warning schools see on first install
- 🟡 **Proper brand icon + installer artwork** — replace the generated
  placeholder icon
- 🟡 **Silent-install QA automation** — scripted clean-VM pass of
  `docs/RELEASE_CHECKLIST.md` section B
- 🟡 **Localised installer welcome text** (first-run screens)

## v1.1 — next minor (schools' most-requested conveniences)

Candidates under consideration; final list set by customer feedback.

- 🟡 **Interface language option (Urdu/English)** — the interface is
  English-only today; an Urdu translation layer for the main screens would
  fit the target schools
- 🟡 **Backup to a chosen folder/USB** — today backups stay in the data
  folder; add "also copy every backup to this location" for off-PC safety
- 🟡 **WhatsApp result delivery on publish** — one click to queue result
  messages for a whole exam from the tabulation screen (queue + templates
  already exist; this is the workflow shortcut)
- 🟡 **Attendance register printing** — month-view printable register per
  class for schools that also keep paper records
- 🟡 **Shared data across Windows accounts** — option to place the data
  folder in a shared location so two staff Windows accounts on one PC see
  the same school (today each Windows user has separate data)

## v1.2+ — later (bigger steps, each needs its own spec)

- ⚪ **WhatsApp Cloud API as first-class** — the integration method already
  exists; deepen it (delivery receipts, template management)
- ⚪ **Online fee payment** — parents pay online; the system records it.
  Requires a payment-provider decision and connectivity assumptions that
  contradict the offline-first default, hence its own version
- ⚪ **Automatic update checker** — the product is offline; a safe pattern
  is "check for updates" + downloadable installer, keeping the stable
  AppId for in-place updates
- ⚪ **Biometric / RFID attendance import** — accept CSV/device exports
  into the daily attendance flow (device-agnostic import, not drivers)
- ⚪ **Multi-school data on one PC** — manage more than one institution
  from a single installation
- ⚪ **Data sharing across a small network** — one PC hosts the database,
  others connect (real networking changes the security model; needs its own
  design phase)

## ⛔ Not for now

- **Cloud-hosted multi-tenant SaaS** — contradicts the product's core
  promise (data on the school's own computer, offline-first, no
  subscription). Revisit only if the market demands it.
- **WhatsApp automation removal / third-party messenger swap** — WhatsApp
  is the product's main selling point.

---

## How a feature gets onto this roadmap

1. **Input** — customer request from a real school, support ticket, or a
   gap found during QA (recorded in `docs/RELEASE_CHECKLIST.md` section F).
2. **Consideration** — added here with 🟡, including why it matters and
   what it touches.
3. **Spec & phase-gated build** — significant features are implemented the
   way Phases 1–7 were: one phase, review, approval, changelog entry.
4. **Release** — version bump in `installer/SchoolManager.iss`, changelog
   promotion, `python tools/make_release.py`, manual QA per
   `docs/RELEASE_CHECKLIST.md`.

> **Rule of thumb:** nothing ships that isn't in the changelog, and nothing
> enters the changelog that a school wouldn't understand.

# School Manager — Product Overview

**Offline-first school administration software for Windows**
*Ahmi software firm — established 2020 · Version 1.0.0*

> **One sentence pitch:** School Manager replaces paper registers and scattered
> Excel files with one fast, offline desktop system that manages students,
> attendance, fees, exams and results — and keeps parents informed over
> WhatsApp.

---

## 1. Product overview

School Manager is a complete school-administration system that runs entirely
on the school's own Windows computer. It manages the full daily operation of
a private school — admissions, class lists, attendance, fee collection,
exams, results, payroll and parent communication — from a single desktop
application.

It was designed for the reality of local private schools:

* **No internet? No problem.** Everything — the software, the database, even
  the screen design — is installed on the school's computer. Daily work
  never needs a connection.
* **No IT department needed.** Installation is a single setup file. The
  program opens like a normal desktop application; closing the window shuts
  it down safely.
* **No monthly fees.** The school buys a license once, for one computer.
  The software checks the license offline — no account, no cloud, no
  phone-home.
* **Data stays at the school.** All records live in one folder on the
  school's own PC, with one-click backups. Nobody else can access them.

A built-in **WhatsApp gateway** keeps parents informed automatically —
absence alerts, monthly fee reminders, exam results and school broadcasts —
using the school's own WhatsApp number.

---

## 2. Main features

### Students
* Complete student profiles: class, section, roll number, guardian details,
  date of birth, gender, admission number and date, sponsor/CNIC information
* Student photos (optional) used on ID cards and documents
* School-defined custom fields (with mandatory-field support)
* Per-class roll numbering that prevents conflicts, with automatic shifting
* Bulk import from Excel/CSV with duplicate and error checking; export
  anytime
* Archive/restore with full change history per student

### Teachers & payroll
* Teacher records: qualification, experience, salary type (monthly or
  hourly), contacts, documents data
* Monthly payroll runs with automatic attendance-based deductions,
  bonuses/deductions, and payment tracking (Cash/Bank/Cheque)

### Classes & timetable
* Classes, sections and subjects with per-class standard fees
* Editable Monday–Saturday timetable with period timings and PDF export
* In-charge teacher assignment per class

### Attendance
* Daily attendance for students and teachers: Present, Absent, Late, Leave
* Late arrivals record the actual check-in time and minutes late
* Whole-class quick marking
* Attendance summaries and exports per student, class or period

### Fees
* Append-only fee ledger: every charge, payment and adjustment is recorded
  and can never be silently changed
* Monthly charge generation with one click (per class or whole school)
* Partial payments, multiple payment methods, receipt numbers, printable
  receipts
* Automatic reconciliation: ledger vs. summaries, with discrepancy repair
* Defaulter views and WhatsApp fee-reminder queue
* Class-wide fee updates with confirmation safeguard

### Expenses
* Expense categories and entries (Cash/Bank/Cheque), receipts, monthly view

### Tests, exams & results
* Class tests with flexible totals, batch mark entry for the whole class,
  absent handling
* Configurable grading scale (A+ … F thresholds set by the school)
* Formal term exams (Mid-Term/Final) with per-subject papers, date sheets
  and automatic tabulation with positions
* Result cards and transcripts as print-ready PDFs

### Reports & documents (PDF/Excel)
* Result cards, transcripts, tabulation sheets, date sheets
* Student and teacher ID cards (photo if available, initials badge
  otherwise)
* Fee reports, defaulter lists, financial summaries — all exportable to PDF
  and Excel

### Financial management
* Income vs. expense summaries and period comparisons
* Monthly collection tracking with Paid/Partial/Pending status

### Administration & security
* Five user roles: Administrator, Principal/Owner, Accountant, Teacher,
  Parent/Guardian — each sees only what they should
* Complete audit trail: who created, changed or deleted what, and when —
  including logins and every fee transaction
* School branding: name, logo and colors across the app; name and logo on
  printed documents
* Automatic hourly backups plus manual backup/restore

---

## 3. Key selling points & benefits for schools

| Benefit | What it means in practice |
|---|---|
| **Works without the internet** | Power cut or connection down? Attendance, fees, exams and printing keep working. Only WhatsApp sending needs a connection. |
| **One-time cost** | A single license per computer. No monthly subscription, no cloud account, no data-hosting fees. |
| **Data stays with the school** | Records live in one folder on the school's own PC. Backups are one click. Nothing is stored on anyone else's servers. |
| **Parents stay informed automatically** | Absence and late alerts, fee reminders, results and broadcasts go out over WhatsApp — no phone-call rounds at 8 AM. |
| **Nothing gets "lost"** | Every fee transaction, every mark, every change is recorded with the user and timestamp. Disputes end because the history is complete. |
| **Reports in seconds, not days** | Result cards, ID cards, defaulter lists and financial summaries are generated as print-ready PDFs/Excel at any time. |
| **Right access for the right person** | Teachers cannot see fees; parents see only their own children; the accountant sees finance, not marks. |
| **Safe to try, easy to start** | A built-in demo-data generator can fill the system with realistic sample data for evaluation, then the school starts clean. |

---

## 4. Target users

**Institutions:** private schools and academies that want their records
computerized without cloud dependency — from a single-campus school with a
few hundred students upward, running Windows 10/11.

**Who uses it day to day:**

| User | What they do in School Manager |
|---|---|
| **Principal / Owner** | Executive dashboard with charts, full oversight, school settings |
| **Administrator** | Day-to-day management: admissions, classes, users, settings, backups |
| **Accountant** | Fee ledger, charges and payments, expenses, financial reports |
| **Teacher** | Attendance, class tests and marks, class lists, own timetable |
| **Parent / Guardian** | Read-only portal: their own children's attendance, fees and results |

---

## 5. WhatsApp automation

The WhatsApp gateway is a core feature, not an add-on — it ships inside the
installer with everything it needs.

* **Automatic alerts** — when a student is marked absent or late, a message
  to the guardian can be queued automatically, using the school's own
  wording templates.
* **Result announcements** — exam results can be sent to guardians when
  published.
* **Fee reminders** — the system identifies unpaid/partial months and queues
  polite reminders for those guardians.
* **Broadcasts** — send an announcement to a whole class (e.g. holiday
  notice, due-date reminder) with due-date tracking.
* **Three sending modes** for every school's comfort level:
  * *Approval* — messages wait for a staff member to press "send"
    (safest),
  * *Auto* — approved messages go out on their own,
  * *Delayed* — one-by-one with human-paced delay between messages.
* **Delivery tracking** — every message shows its status (pending, sent,
  failed) with delivery logs; nothing is silently lost.
* **Simple pairing** — the school's WhatsApp number is linked once by
  scanning a QR code on the Automation page, exactly like WhatsApp Web.

The gateway ships inside the installer with its own bundled runtime — the
school never installs Node.js or any other dependency.

---

## 6. Offline capability

School Manager is offline-first by design:

* The software, the database and **all screen assets** are installed
  locally — pages render fully styled with the network cable unplugged.
* Attendance, fees, exams, results, ID cards, reports and printing all work
  without any connection.
* **Backups are local and one click** — the school owns its data physically.
* The license is verified **offline** — no activation servers to reach.
* The only feature that uses the internet is **sending WhatsApp messages**
  (and fetching the initial QR code for pairing). If the connection drops,
  messages stay safely queued and go out when it returns.

---

## 7. Licensing

* **One-time license, per computer.** No subscription. No renewals required
  while the license is valid.
* **Offline activation.** The school pastes the license key received from
  Ahmi software firm; the system verifies it locally.
* **Fair expiry handling.** 30 days before expiry a friendly warning
  appears. After expiry there is a grace period — and even afterward the
  school keeps **full read access** to every record: printing, exports and
  viewing never stop. Only new data entry pauses until renewal.
* **Protected against tampering.** Licenses are cryptographically signed and
  bound to the computer; copying a license file to another PC does not work,
  and changing the system clock does not extend a license.
* **Re-install friendly.** Updating to a new version, or uninstalling and
  reinstalling, never deletes school data and never requires re-pairing
  WhatsApp.

---

## 8. Module highlights

### Attendance
Mark a whole class in seconds, with per-student override. Late arrivals
store the check-in time. Summaries show each student's Present/Absent/Late/
Leave counts for any period, exportable for record-keeping.

### Fees
The fee module is built on an **append-only ledger** — the same principle
banks use. A charge, a payment, a discount or an adjustment is a permanent
ledger entry, so the books always balance against the history. Monthly
charges are generated explicitly per class or school-wide; the system
tracks Paid / Partial / Pending per student and month, prints numbered
receipts, and can queue WhatsApp reminders for defaulters.

### Students
From admission to leaving: profile, guardian and sponsor details, documents
data, photo, custom school-defined fields, class history, and complete
change tracking. Bulk import accepts Excel/CSV with validation (duplicate
roll numbers, missing fields and conflicting records are reported, not
silently skipped).

### Teachers
Records with qualification, experience and salary structure. The payroll
module prepares each month's salaries with attendance already factored in,
tracks payment status and method, and keeps a history per teacher.

### Tests & results
Create class tests, enter marks for the whole class on one screen (absent
students handled properly), and let the system compute percentages and
grades on the school's own scale. Formal term exams group per-subject
papers with a date sheet and produce tabulation sheets with positions.
Result cards and transcripts are print-ready PDFs.

### Reports & documents
Everything the school prints is generated from live data: result cards,
transcripts, ID cards, date sheets, fee reports, defaulter lists, financial
summaries — as PDF or Excel, whenever needed, in seconds.

---

## 9. Why not manual registers and Excel?

| Manual registers / Excel | School Manager |
|---|---|
| Totals and grades calculated by hand — errors are common and invisible | Grades, percentages, balances and payroll are computed automatically from the entered data |
| "Who changed this number?" — unanswerable | Every change is recorded with user and timestamp in the audit trail |
| Fee follow-up means flipping pages and making calls | The system lists defaulters instantly and queues WhatsApp reminders |
| One Excel file per staff member, merged by hand at term end | One database, five roles, everyone works on the same live records with proper access limits |
| A lost notebook or corrupted spreadsheet is a disaster | One-click local backups with automatic hourly backups; restore is guided |
| Printing a result card means re-writing marks by hand | Result cards, ID cards, transcripts and reports are generated as PDFs in seconds |
| Searching "every student who was absent more than 10 days" is practically impossible | Filtering and exports across the whole history take seconds |
| Software that needs the internet stops when the connection does | School Manager keeps working offline — attendance, fees, exams, printing |

The point is not "computers are modern". The point is **accuracy,
accountability and time**: the school's numbers agree with its history,
parents hear from the school automatically, and the principal's reports are
ready before the tea gets cold.

---

## 10. Important limitations & considerations

We state these openly — they are the honest boundaries of the current
version (1.0.0):

* **Windows only.** The product targets Windows 10/11 on the school's PC.
* **One school per computer (per Windows user).** Data is stored per
  Windows account; there is no multi-campus synchronisation.
* **WhatsApp uses the school's own number via a third-party library.**
  Sending is reliable but the number must stay paired; WhatsApp's own rules
  — not ours — govern the account. The approval/paced modes reduce messaging
  volume risks.
* **Fees are recorded, not collected online.** There is no online payment
  gateway; parents pay at the counter and the accountant records it.
* **English interface.** The UI language is English.
* **One data folder per Windows user.** If two staff share one Windows
  account they share the data; if they use separate accounts, each has
  separate data.
* **Machine-bound license.** A major hardware change or Windows
  reinstallation requires a free re-issued key from Ahmi software firm.
* **Internet is needed only for WhatsApp sending** (and initial pairing).
* **Not (yet) included:** library, transport/inventory, biometric devices,
  online admission forms, and multi-branch sync.

---

## 11. At a glance

| | |
|---|---|
| Product | School Manager 1.0.0 |
| Publisher | Ahmi software firm (est. 2020) |
| Platform | Windows 10/11 · ~160 MB installed |
| Internet | Not required for daily use (WhatsApp sending only) |
| Licensing | One-time, per computer, offline activation |
| Data | 100% local, one folder, one-click backups |
| Modules | Students · Teachers · Classes & timetable · Attendance · Fees · Expenses · Financials · Tests & exams · Reports · ID cards & certificates · Payroll · Parent portal · Audit trail · WhatsApp automation |
| Roles | Administrator · Principal/Owner · Accountant · Teacher · Parent |

*Contact Ahmi software firm for a demonstration — the software includes a
demo-data generator so you can evaluate it with realistic sample records
before entering anything real.*

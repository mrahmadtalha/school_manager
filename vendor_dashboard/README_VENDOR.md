# School Manager — License Manager Dashboard (vendor only)

Runs **only on your own laptop**. It is never part of the customer build
(`tools/build_product.py` excludes `vendor_dashboard/` and `vendor_data/`).

## Start
Double-click `vendor_dashboard\START_VENDOR_DASHBOARD.bat`
(or `python vendor_dashboard/run_dashboard.py`). It opens
<http://127.0.0.1:5055> — reachable from this laptop only.

**First run:** choose a dashboard password (10+ characters). Your signing key
from `vendor_keys/license_private.key` is imported and stored **encrypted**
(`vendor_data/license_private.enc`). After you have made a backup, go to
**Settings → Plain private key file → Erase**.

## Everyday jobs
| Job | Where |
|---|---|
| New school | Schools → Add school, then **Issue key** (reason: *First key*) |
| Renewal (payment received) | School page → reason *Renewal* → pick +1 month / +1 year → Sign & issue |
| Switch features / roles / WhatsApp limits | School page → switch features and **user roles** on or off, set limits → reason *Change features* → validity *Keep current expiry* |
| School changed computer | School page → new machine code → reason *Move to a new computer* |
| Forgot username/password | Recovery → paste their request code → verify them → issue token |
| Who needs a reminder | Home → "Needs attention" → *Reminder* copies a ready message |

Send the key (or the ready-made message) to the school; they open
**License** in School Manager, paste it, and press Activate. No internet is
needed on their side.

## Features and roles you can switch per school
* **Features** (modules): expenses, payroll, financial reports, inventory & other income, admission fees, owner dashboard, attendance, exams, ID cards & certificates, timetable, parent portal, WhatsApp, school assistant, bulk import, **data export**, **Urdu / English switch** and **audit log viewer**.
* **Roles**: teacher, accountant, principal/owner and parent can each be switched off. A switched-off role cannot be created and its existing users are signed out with a message. **Administrator is always on** so a school can never be locked out.
* **Audit log**: the log is always *recorded* on every school; the *Audit log viewer* switch only decides whether the school can open and export it. Switching the viewer off hides it but keeps the history for your own inspection.
* Keys issued before these switches existed keep everything on (nothing is taken away).

## Inspection key (view-only, short)
School page → **Inspection key** → choose 6 / 24 / 48 / 72 hours → **Issue** → send the key.
The school pastes it on *License* like a normal key. While it is valid: every module and the
audit log can be opened, **nothing can be changed**, and an *Inspection mode* banner shows.
It ends by itself, works only on that PC and with that school's license, and never replaces the
real license (the real key keeps running underneath). Command line: `python tools/license_admin.py inspection-key --machine ... --licensee ... --hours 24`.

## Notice and reminders
* **Notice** (Issue key form): a short message (max 300 characters, e.g. *Renewal due on 25 Oct*) that
  travels inside the key. The school's administrator sees it on every page until they close it
  and always on the License page. Issue the next key with the box empty to clear it.
* **Reminders** need nothing from you: the school's administrator gets a pop-up 30, 14, 7, 3 and 1 day
  before the license ends. Schools need the NEW build to see notices, reminders and inspection keys.

## Good to know
* Changes reach a school **only when it applies the new key** (the app is offline).
  Use expiry dates as the real lever: monthly payers get monthly keys.
* A newer revision of a license replaces the older one; an older key is refused.
* WhatsApp limit blank = unlimited, `0` = none. Over-limit messages stay queued
  and go out automatically the next day / month.
* Keys issued before this release keep working with everything switched on.
  Schools need the new build of the app for features/limits to take effect;
  older builds ignore those fields.
* Moving a school to a new PC does not stop the old PC until its key expires
  (inherent to offline licensing).

## Password recovery, in short
School: Login → *Forgot username / password?* → sends you the **request code**.
You: Recovery → paste it → confirm the person (call the number on file) →
**Issue reset token** → send it back. School pastes it, sees the admin
username(s), sets a new password. The token works once, only on that computer,
and expires (default 24 h). Every recovery is logged in the dashboard.

## Back up (Settings → Download backup)
`vendor.db` (schools, key history, payments) and the encrypted key. **If you
lose the signing key you cannot renew any school** (the public key inside every
shipped exe can't be replaced). Keep the backup somewhere private; it is
useless without your dashboard password.

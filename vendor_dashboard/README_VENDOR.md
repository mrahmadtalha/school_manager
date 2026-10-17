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
| Switch features / WhatsApp limits | School page → tick features, set limits → reason *Change features* → validity *Keep current expiry* |
| School changed computer | School page → new machine code → reason *Move to a new computer* |
| Forgot username/password | Recovery → paste their request code → verify them → issue token |
| Who needs a reminder | Home → "Needs attention" → *Reminder* copies a ready message |

Send the key (or the ready-made message) to the school; they open
**License** in School Manager, paste it, and press Activate. No internet is
needed on their side.

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

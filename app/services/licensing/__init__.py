"""Offline license verification.

How it works
------------
* The vendor signs a small JSON payload (licensee, machine code, issue and
  expiry dates) with an Ed25519 **private** key that never leaves the vendor's
  machine.  The application ships only the matching **public** key
  (``license_public_key.py``), so it can verify licenses but cannot create them.
* A license key is a single line of text: ``SM1.<payload>.<signature>`` (both
  parts base64url).  It is bound to one machine through the machine code.
* Nothing here needs the internet.

Lifecycle of a valid license::

    active  ->  grace  ->  expired (read-only)

``unlicensed`` (no key installed) and ``invalid`` (bad signature, wrong
machine, ...) are also read-only.  "Read-only" means the *enforcement layer*
(``app/license_guard.py``) rejects writes; this module only decides the state.

Clock protection
----------------
Rolling the Windows clock back must not revive an expired license, so the
manager keeps a signed "high-water mark" (the latest date it has seen) in a
small state file and never lets effective time go backwards.  If a wrong
far-future date was ever seen, the vendor recovers the school by issuing a
replacement key (new license id), which restarts the mark from its issue date.

Features and limits
-------------------
A key may also carry ``features`` (the modules the school has paid for),
``limits`` (daily/monthly WhatsApp message caps), ``plan`` (a label) and
``rev`` (revision number).  All are OPTIONAL and the payload version stays 1,
so keys without them (legacy) keep everything switched on and older builds of
the application simply ignore the extra fields.  A newer revision of the same
license id replaces an older one; an older revision is refused.

Honest limits: this is a deterrent against casual copying and clock tricks, not
DRM.  Someone who edits the running code, or deletes the state file *and* keeps
the clock frozen, can still get around it.  Code obfuscation (Phase 3) raises
that bar; it cannot remove it.
"""

# This package replaces the former single file ``licensing.py``.  Every name the
# rest of the application, the tests and the vendor tools used before is
# re-exported here, so ``from app.services.licensing import LicenseManager`` and
# ``licensing.verify_license_text(...)`` keep working unchanged.
#
#   constants   product names, key prefixes, states, limits
#   errors      LicenseError
#   encoding    base64url, compact JSON, public-key loading
#   machine     machine code
#   keys        license key verification (+ reminder stages)
#   inspection  view-only inspection keys
#   recovery    forgotten-password request / token
#   status      LicenseStatus
#   manager     LicenseManager (activation, clock protection, state files)

from .constants import *  # noqa: F401,F403
from .encoding import (_B64U_CHARS, _compact_json, _load_public_key,  # noqa: F401
                       b64u_decode, b64u_encode, default_public_key)
from .errors import LicenseError  # noqa: F401
from .inspection import sign_inspection, verify_inspection_text  # noqa: F401
from .keys import _parse_date, reminder_stage, verify_license_text  # noqa: F401
from .machine import (_raw_machine_id, format_machine_code,  # noqa: F401
                      get_machine_code, normalize_machine_code)
from .manager import LicenseManager, _utcnow  # noqa: F401
from .recovery import (RECOVERY_REQUEST_PREFIX, RECOVERY_SIGN_CONTEXT,  # noqa: F401
                       RECOVERY_TOKEN_PREFIX, _request_check, make_recovery_request,
                       parse_recovery_request, sign_recovery_token,
                       verify_recovery_token)
from .status import LicenseStatus  # noqa: F401

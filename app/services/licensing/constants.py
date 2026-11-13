"""License constants: product names, key prefixes, states, limits and tolerances."""

from datetime import timedelta


PRODUCT = 'school-manager'
KEY_PREFIX = 'SM1'
SIGN_CONTEXT = b'school-manager-license-v1\n'
PAYLOAD_VERSION = 1

DEFAULT_GRACE_DAYS = 7
MAX_GRACE_DAYS = 60
EXPIRING_SOON_DAYS = 30
ROLLBACK_TOLERANCE = timedelta(hours=24)
STATE_WRITE_INTERVAL = timedelta(minutes=10)

# License states
ACTIVE = 'active'
GRACE = 'grace'
EXPIRED = 'expired'
UNLICENSED = 'unlicensed'
INVALID = 'invalid'
DISABLED = 'disabled'           # enforcement switched off (development only)

READ_ONLY_STATES = {EXPIRED, UNLICENSED, INVALID}

#: Limits a key may carry (a missing limit means "unlimited"): WhatsApp caps and the school's size.
LIMIT_WA_DAILY = 'wa_daily'

# Features added after the first release; keys that pre-date them keep them switched on.
FEATURES_ADDED_LATER = ('data_export', 'language_switch', 'audit_log_view')
LIMIT_WA_MONTHLY = 'wa_monthly'
LIMIT_MAX_STUDENTS = 'max_students'     # active students the school may have
LIMIT_MAX_STAFF = 'max_staff'           # active staff logins (teacher, accountant, owner, guard)
LIMIT_NAMES = (LIMIT_WA_DAILY, LIMIT_WA_MONTHLY, LIMIT_MAX_STUDENTS, LIMIT_MAX_STAFF)

#: Days-before-expiry at which the administrator gets a reminder pop-up.
REMINDER_MILESTONES = (30, 14, 7, 3, 1)
NOTICE_MAX_LENGTH = 300

# Inspection keys: short, view-only keys the vendor sends for support / audits.
INSPECTION_PREFIX = 'SMI1'            # different prefix: an older build refuses it as "not a license key"
INSPECTION_SIGN_CONTEXT = b'school-manager-inspection-v1\n'   # never reused for licenses or recovery
INSPECTION_MAX_HOURS = 168            # a week at most, whatever the vendor types
INSPECTION_START_TOLERANCE = timedelta(days=1)    # school clock slightly behind the vendor's

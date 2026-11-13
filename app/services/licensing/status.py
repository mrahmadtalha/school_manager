"""The read-only snapshot of a license that the rest of the application looks at."""

from dataclasses import dataclass
from datetime import date, datetime

from .constants import EXPIRED, GRACE, INVALID, UNLICENSED


@dataclass(frozen=True)
class LicenseStatus:
    state: str
    read_only: bool
    level: str                    # bootstrap colour: success / warning / danger / secondary
    title: str
    message: str
    machine_code: str
    enforced: bool = True
    reason: str = ''              # machine-readable detail for invalid licenses
    licensee: str = ''
    license_id: str = ''
    issued: date = None
    expires: date = None
    grace_ends: date = None
    days_left: int = None         # negative once expired
    expiring_soon: bool = False
    clock_rollback: bool = False
    features: tuple = None        # None = legacy key / not applicable: everything on
    roles: tuple = None           # None = legacy key: every role on; 'admin' is always on
    limits: dict = None           # {'wa_daily': n, 'wa_monthly': n}; missing = unlimited
    rev: int = 0
    plan: str = ''
    notice: str = ''              # vendor's message carried by the key (e.g. "renewal due")
    reminder_stage: int = None    # 30 / 14 / 7 / 3 / 1 while an active license is near its end
    inspection: bool = False      # a view-only inspection key is in effect
    inspection_until: datetime = None    # UTC, naive
    inspection_id: str = ''

    def feature_enabled(self, key):
        """True when this license includes ``key`` (legacy keys include all)."""
        if not self.enforced or self.features is None:
            return True
        return key in self.features

    def role_enabled(self, role):
        """True when users of ``role`` may sign in (admin always may)."""
        if not self.enforced or self.roles is None or role == 'admin':
            return True
        return role in self.roles

    def limit(self, name):
        """The numeric limit called ``name``, or None when unlimited."""
        return (self.limits or {}).get(name)

    @property
    def needs_attention(self):
        return (self.state in (GRACE, EXPIRED, UNLICENSED, INVALID)
                or self.expiring_soon or self.clock_rollback or self.inspection)

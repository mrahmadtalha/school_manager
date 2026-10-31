"""One-row settings table for QR attendance (guard scanner).

The signing secret lives in the database (not in a file or in SECRET_KEY) so a
restored backup or a new computer keeps every printed ID card valid.
"""

import secrets
from datetime import datetime
from app.timeutil import utcnow

from app.database import db


AUTO_ABSENT_DEFAULTS = {
    'auto_absent_enabled': False,
    'absent_cutoff_time': '10:00',
    'absent_mode': 'approval',
    'absent_min_scan_percent': 20,
    'absent_message_delay_minutes': 30,
    'late_correction_enabled': True,
}


class QrConfig(db.Model):
    __tablename__ = 'qr_config'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    secret = db.Column(db.String(128), nullable=False)
    # Let guard phones on the same Wi-Fi reach this computer (needs a restart).
    lan_access = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    # -- Auto-absent (phase 3) --------------------------------------------
    # Off by default: nobody is marked absent unless the school switches it on.
    auto_absent_enabled = db.Column(db.Boolean, nullable=False, default=False)
    absent_cutoff_time = db.Column(db.String(5), nullable=False, default='10:00')
    # 'approval' = an admin confirms the list first | 'auto' = marked straight away
    absent_mode = db.Column(db.String(10), nullable=False, default='approval')
    # Automatic mode drops to approval when fewer than this % of students have
    # arrived by the cutoff (a dead phone, Wi-Fi or app must not mark everyone absent).
    absent_min_scan_percent = db.Column(db.Integer, nullable=False, default=20)
    # Minutes to wait before the absent message is sent (time to fix a mistake).
    absent_message_delay_minutes = db.Column(db.Integer, nullable=False, default=30)
    # Send a correction message when a student marked absent arrives afterwards.
    late_correction_enabled = db.Column(db.Boolean, nullable=False, default=True)

    @classmethod
    def get(cls):
        """Return the single settings row, creating it on first use."""
        row = cls.query.first()
        if row is None:
            row = cls(secret=secrets.token_hex(32), lan_access=False,
                      **AUTO_ABSENT_DEFAULTS)
            db.session.add(row)
            db.session.commit()
        return row


class QrAbsentRun(db.Model):
    """One auto-absent check for one school day (at most one row per date).

    status:  ``pending``  - waiting for an admin to approve / reject the list
             ``applied``  - students were marked Absent
             ``rejected`` - an admin turned the list down; nobody was marked
    mode_used is what actually happened ('auto' can fall back to 'approval').
    """
    __tablename__ = 'qr_absent_runs'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    run_date = db.Column(db.Date, nullable=False, unique=True)
    status = db.Column(db.String(12), nullable=False, default='pending')
    mode_used = db.Column(db.String(10), nullable=False, default='approval')
    reason = db.Column(db.String(200), nullable=True)
    total_students = db.Column(db.Integer, nullable=False, default=0)
    attended_count = db.Column(db.Integer, nullable=False, default=0)
    candidate_count = db.Column(db.Integer, nullable=False, default=0)
    marked_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)
    decided_at = db.Column(db.DateTime, nullable=True)
    decided_by = db.Column(db.String(80), nullable=True)

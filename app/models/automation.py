"""
Automation models — WhatsApp settings and message queue.
Ported from Project1's automation feature, adapted to Project2's model naming.
"""
from datetime import datetime
from app.database import db


class AutomationSettings(db.Model):
    """
    Single-row settings table for automation configuration.
    Use AutomationSettings.get() to always get the one row.
    """
    __tablename__ = "automation_settings"

    id              = db.Column(db.Integer, primary_key=True)

    # Master switch
    enabled         = db.Column(db.Boolean, default=False)

    # Mode: 'auto' = send immediately | 'approval' = queue for review
    mode            = db.Column(db.String(20), default="approval")

    # Which events trigger messages
    notify_absent   = db.Column(db.Boolean, default=True)
    notify_late     = db.Column(db.Boolean, default=True)
    notify_results  = db.Column(db.Boolean, default=False)

    # Message templates (editable)
    template_absent = db.Column(db.Text, default=(
        "Assalam-o-Alaikum,\n\nDear Guardian of *{student_name}*,\n\n"
        "This is to inform you that your child was *ABSENT* from school today "
        "({date}).\n\nPlease ensure regular attendance.\n\n"
        "Regards,\nSchool Management"
    ))
    template_late   = db.Column(db.Text, default=(
        "Assalam-o-Alaikum,\n\nDear Guardian of *{student_name}*,\n\n"
        "Your child arrived *LATE* to school today ({date}).\n\n"
        "Please ensure timely arrival.\n\n"
        "Regards,\nSchool Management"
    ))
    template_result = db.Column(db.Text, default=(
        "Assalam-o-Alaikum,\n\nDear Guardian of *{student_name}*,\n\n"
        "Result for *{test_type}* Test ({date}):\n"
        "Obtained: *{obtained}/{total}*\n"
        "Percentage: *{percentage}%*\n"
        "Grade: *{grade}*\n\n"
        "Regards,\nSchool Management"
    ))

    # WhatsApp session state (written by Node service)
    wa_status       = db.Column(db.String(30), default="disconnected")
    # disconnected | connecting | qr_ready | connected

    # Latest successful delivery for staff visibility
    last_successful_send_at = db.Column(db.DateTime, nullable=True)

    updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow)

    @staticmethod
    def get():
        """Get or create the single settings row."""
        s = AutomationSettings.query.first()
        if not s:
            s = AutomationSettings()
            db.session.add(s)
            db.session.commit()
        return s


class MessageQueue(db.Model):
    """
    Every outgoing WhatsApp message passes through this queue.
    Auto mode:     status goes pending -> sent (or failed)
    Approval mode: status goes pending -> approved -> sent (or failed)
    """
    __tablename__ = "message_queue"

    id          = db.Column(db.Integer, primary_key=True)
    phone       = db.Column(db.String(30),  nullable=False)   # international format
    message     = db.Column(db.Text,        nullable=False)
    status      = db.Column(db.String(20),  default="pending")
    # pending | approved | rejected | sending | sent | failed

    # Context (for display)
    trigger     = db.Column(db.String(50),  nullable=True)
    # 'attendance_absent' | 'attendance_late' | 'result'
    student_id  = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    ref_date    = db.Column(db.Date,    nullable=True)   # attendance date / test date
    retry_count = db.Column(db.Integer, default=0)

    # Timing
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow)
    sent_at     = db.Column(db.DateTime, nullable=True)

    # Error info (if failed)
    error_msg   = db.Column(db.Text, nullable=True)

    student = db.relationship("StudentModel", foreign_keys=[student_id])
    delivery_logs = db.relationship("DeliveryLog", back_populates="message", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MessageQueue id={self.id} status={self.status} phone={self.phone}>"


class DeliveryLog(db.Model):
    """Operational audit trail for each outgoing WhatsApp message."""
    __tablename__ = "delivery_logs"

    id          = db.Column(db.Integer, primary_key=True)
    message_id  = db.Column(db.Integer, db.ForeignKey("message_queue.id"), nullable=False)
    status      = db.Column(db.String(20), nullable=False)
    error_msg   = db.Column(db.Text, nullable=True)
    details     = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    message = db.relationship("MessageQueue", back_populates="delivery_logs")


MESSAGE_STATUSES = ["pending", "approved", "rejected", "sending", "sent", "failed"]

"""Academic Calendar models — school events, pins and archives."""

from datetime import date, datetime
from app.database import db


class CalendarEvent(db.Model):
    """One entry on the school's academic calendar."""

    __tablename__ = 'calendar_events'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, default='')
    event_date   = db.Column(db.Date, nullable=False, index=True)
    end_date     = db.Column(db.Date, nullable=True)       # None → single-day
    category     = db.Column(db.String(40), default='general')   # holiday/exam/meeting/general
    is_pinned    = db.Column(db.Boolean, default=False, nullable=False)
    is_archived  = db.Column(db.Boolean, default=False, nullable=False)
    created_by   = db.Column(db.Integer, db.ForeignKey('admin_users.id'), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('AdminUser', foreign_keys=[created_by], lazy='joined')

    # ------------------------------------------------------------------ helpers

    @property
    def is_multi_day(self):
        return self.end_date is not None and self.end_date != self.event_date

    @property
    def is_upcoming(self):
        return self.event_date >= date.today()

    @property
    def is_past(self):
        end = self.end_date or self.event_date
        return end < date.today()

    @property
    def category_label(self):
        return {
            'holiday': 'Holiday',
            'exam':    'Exam / Test',
            'meeting': 'Meeting',
            'general': 'General',
            'trip':    'School Trip',
            'sport':   'Sports',
            'other':   'Other',
        }.get(self.category, self.category.title())

    @property
    def category_color(self):
        return {
            'holiday': 'success',
            'exam':    'danger',
            'meeting': 'warning',
            'general': 'primary',
            'trip':    'info',
            'sport':   'secondary',
            'other':   'dark',
        }.get(self.category, 'primary')

    def to_dict(self):
        return {
            'id':          self.id,
            'title':       self.title,
            'description': self.description,
            'event_date':  self.event_date.isoformat(),
            'end_date':    self.end_date.isoformat() if self.end_date else None,
            'category':    self.category,
            'is_pinned':   self.is_pinned,
            'is_archived': self.is_archived,
        }

    def __repr__(self):
        return f'<CalendarEvent id={self.id} date={self.event_date} title={self.title!r}>'

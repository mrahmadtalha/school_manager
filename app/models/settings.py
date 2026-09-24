from app.database import db


class SystemSettingModel(db.Model):
    __tablename__ = 'system_settings'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(100), nullable=False)


class SchoolSettings(db.Model):
    __tablename__ = 'school_settings'

    id            = db.Column(db.Integer, primary_key=True)
    school_name   = db.Column(db.String(200), default='School Manager')
    tagline       = db.Column(db.String(200), default='')
    logo_filename = db.Column(db.String(200), default='')
    address       = db.Column(db.String(300), default='')
    phone         = db.Column(db.String(50),  default='')
    email         = db.Column(db.String(100), default='')
    school_start_time = db.Column(db.String(10), default='08:30')
    school_end_time   = db.Column(db.String(10), default='15:00')
    weekend_off = db.Column(db.Boolean, default=True)
    custom_off_days = db.Column(db.String(200), default='')

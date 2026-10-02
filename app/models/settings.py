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
    academic_session = db.Column(db.String(50), default='')
    result_announcement_date = db.Column(db.String(20), default='')
    school_start_time = db.Column(db.String(10), default='08:30')
    school_end_time   = db.Column(db.String(10), default='15:00')
    attendance_grace_minutes = db.Column(db.Integer, default=0)
    weekend_off = db.Column(db.Boolean, default=True)
    custom_off_days = db.Column(db.String(200), default='')
    primary_color = db.Column(db.String(20), default='#0d6efd')
    secondary_color = db.Column(db.String(20), default='#6c757d')


import json

def get_grading_scale():
    setting = SystemSettingModel.query.filter_by(key='grading_scale').first()
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except Exception:
            pass
    return [
        {'grade': 'A+', 'min': 85},
        {'grade': 'A', 'min': 70},
        {'grade': 'B', 'min': 60},
        {'grade': 'C', 'min': 50},
        {'grade': 'D', 'min': 40},
        {'grade': 'F', 'min': 0},
    ]

def set_grading_scale(scale_list):
    setting = SystemSettingModel.query.filter_by(key='grading_scale').first()
    if not setting:
        setting = SystemSettingModel(key='grading_scale')
        db.session.add(setting)
    
    scale_list = sorted(scale_list, key=lambda x: float(x.get('min', 0)), reverse=True)
    setting.value = json.dumps(scale_list)
    db.session.commit()

def calculate_grade(percentage):
    scale = get_grading_scale()
    for item in scale:
        if percentage >= float(item['min']):
            return item['grade']
    return scale[-1]['grade'] if scale else 'F'

def get_custom_fields(entity_type):
    setting = SystemSettingModel.query.filter_by(key=f'{entity_type}_custom_fields').first()
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except Exception:
            pass
    return []

def set_custom_fields(entity_type, fields_list):
    key = f'{entity_type}_custom_fields'
    setting = SystemSettingModel.query.filter_by(key=key).first()
    if not setting:
        setting = SystemSettingModel(key=key)
        db.session.add(setting)
    
    setting.value = json.dumps(fields_list)
    db.session.commit()


def get_system_value(key, default=''):
    """Value of a raw system setting, or ``default`` when unset."""
    setting = SystemSettingModel.query.filter_by(key=key).first()
    if setting and setting.value is not None:
        return setting.value
    return default


def set_system_value(key, value):
    """Store a raw system setting value (creating the row when needed)."""
    setting = SystemSettingModel.query.filter_by(key=key).first()
    if not setting:
        setting = SystemSettingModel(key=key)
        db.session.add(setting)
    setting.value = '' if value is None else str(value)
    db.session.commit()

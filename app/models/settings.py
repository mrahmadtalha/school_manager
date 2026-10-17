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
    default_admission_fee = db.Column(db.Float, nullable=True)  # School-wide admission fee (a class can override it)
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
    saturday_off = db.Column(db.Boolean, default=True)
    sunday_off = db.Column(db.Boolean, default=True)
    custom_off_days = db.Column(db.String(200), default='')
    primary_color = db.Column(db.String(20), default='#0d6efd')
    secondary_color = db.Column(db.String(20), default='#6c757d')

    @property
    def brand_palette(self):
        """CSS-ready brand colours (hex + rgb triplet), or None when unusable.

        The templates use this instead of the raw hex columns so that
        ``--bs-primary-rgb`` (which drives focus rings and the ``*-subtle``
        utilities) actually follows the colour the school chose.
        """
        from app.services.theme import brand_palette
        return brand_palette(self.primary_color, self.secondary_color)


def get_holiday_ranges():
    """Return the configured holiday/vacation date ranges as a list of dicts.

    Stored in the system_settings key-value store as JSON:
    [{"label": "Summer Vacations", "start": "2026-06-01", "end": "2026-08-15"}, ...]
    """
    setting = SystemSettingModel.query.filter_by(key='holiday_ranges').first()
    if setting and setting.value:
        try:
            parsed = json.loads(setting.value)
            if isinstance(parsed, list):
                return [
                    item for item in parsed
                    if isinstance(item, dict) and item.get('start') and item.get('end')
                ]
        except (ValueError, TypeError):
            pass
    return []


def set_holiday_ranges(ranges_list):
    """Persist holiday/vacation date ranges (list of {label,start,end} dicts)."""
    cleaned = []
    for item in ranges_list or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get('label', '') or '').strip()
        start = str(item.get('start', '') or '').strip()
        end = str(item.get('end', '') or '').strip()
        if start and end and start <= end:
            cleaned.append({'label': label, 'start': start, 'end': end})
    setting = SystemSettingModel.query.filter_by(key='holiday_ranges').first()
    if not setting:
        setting = SystemSettingModel(key='holiday_ranges')
        db.session.add(setting)
    setting.value = json.dumps(cleaned)
    db.session.commit()


def get_school_closure_days(settings=None):
    """Return (saturday_off, sunday_off, custom_off_days, holiday_ranges).

    Kept as a plain settings reader so services can honour the separate
    Saturday/Sunday toggles plus configured holiday/vacation ranges.
    """
    if settings is None:
        settings = SchoolSettings.query.first()
    saturday_off = getattr(settings, 'saturday_off', None)
    if saturday_off is None:
        saturday_off = getattr(settings, 'weekend_off', True)
    sunday_off = getattr(settings, 'sunday_off', None)
    if sunday_off is None:
        sunday_off = getattr(settings, 'weekend_off', True)
    return (
        bool(saturday_off),
        bool(sunday_off),
        getattr(settings, 'custom_off_days', '') or '',
        get_holiday_ranges(),
    )


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


#: Timetable period structure defaults (School Settings -> Academic tab).
DEFAULT_TIMETABLE_STRUCTURE = {
    'periods_per_day': 8,
    'period_minutes': 40,
    'break_after': 4,      # period number the break follows; 0 = no break
    'break_minutes': 20,
    'break_label': 'Break',
    'assembly_minutes': 0,   # short all-hands slot before period 1; 0 = none
    'assembly_label': 'Assembly',
}


def _clamp_int(value, fallback, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(low, min(number, high))


def get_timetable_structure():
    """Period/break structure saved for the school timetable (to be used later).

    Stored as JSON in the system settings key-value store (like the grading
    scale and holiday ranges) so no schema migration is needed.  Values are
    validated on read, so a corrupt entry falls back to the defaults instead
    of breaking the settings page.
    """
    structure = dict(DEFAULT_TIMETABLE_STRUCTURE)
    raw = get_system_value('timetable_structure', '')
    if raw:
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            structure.update({k: v for k, v in parsed.items() if k in structure})
    structure['periods_per_day'] = _clamp_int(
        structure['periods_per_day'], DEFAULT_TIMETABLE_STRUCTURE['periods_per_day'], 1, 20)
    structure['period_minutes'] = _clamp_int(
        structure['period_minutes'], DEFAULT_TIMETABLE_STRUCTURE['period_minutes'], 10, 120)
    structure['break_after'] = _clamp_int(
        structure['break_after'], DEFAULT_TIMETABLE_STRUCTURE['break_after'], 0, 20)
    structure['break_minutes'] = _clamp_int(
        structure['break_minutes'], DEFAULT_TIMETABLE_STRUCTURE['break_minutes'], 0, 180)
    structure['assembly_minutes'] = _clamp_int(
        structure['assembly_minutes'], DEFAULT_TIMETABLE_STRUCTURE['assembly_minutes'], 0, 60)
    label = str(structure.get('break_label') or '').strip() or DEFAULT_TIMETABLE_STRUCTURE['break_label']
    structure['break_label'] = label[:50]
    structure['assembly_label'] = (str(structure.get('assembly_label') or '').strip()
                                  or DEFAULT_TIMETABLE_STRUCTURE['assembly_label'])[:50]
    return structure


def set_timetable_structure(periods_per_day, period_minutes, break_after,
                            break_minutes, break_label,
                            assembly_minutes=None, assembly_label=None):
    """Persist the validated period/break structure."""
    previous = get_timetable_structure()
    if assembly_minutes is None:
        assembly_minutes = previous['assembly_minutes']
    if assembly_label is None:
        assembly_label = previous['assembly_label']
    structure = {
        'periods_per_day': _clamp_int(periods_per_day, 8, 1, 20),
        'period_minutes': _clamp_int(period_minutes, 40, 10, 120),
        'break_after': _clamp_int(break_after, 4, 0, 20),
        'break_minutes': _clamp_int(break_minutes, 20, 0, 180),
        'break_label': (str(break_label or '').strip() or 'Break')[:50],
        'assembly_minutes': _clamp_int(assembly_minutes, 0, 0, 60),
        'assembly_label': (str(assembly_label or '').strip() or 'Assembly')[:50],
    }
    # A break can never sit after the last period.
    structure['break_after'] = min(structure['break_after'], structure['periods_per_day'] - 1)
    set_system_value('timetable_structure', json.dumps(structure))
    return structure


def set_system_value(key, value):
    """Store a raw system setting value (creating the row when needed)."""
    setting = SystemSettingModel.query.filter_by(key=key).first()
    if not setting:
        setting = SystemSettingModel(key=key)
        db.session.add(setting)
    setting.value = '' if value is None else str(value)
    db.session.commit()

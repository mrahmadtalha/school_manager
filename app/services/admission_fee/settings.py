"""Admission fee settings: the default and per-class amounts, books/uniform sets, and saving the settings page."""

from sqlalchemy import or_

from app.database import db
from app.models import ClassModel, SchoolSettings
from app.models.fees import to_paisa, to_rupees


def _settings_row(create=False):
    row = SchoolSettings.query.first()
    if row is None and create:
        row = SchoolSettings(school_name='School Manager')
        db.session.add(row)
        db.session.flush()
    return row


def default_paisa():
    row = _settings_row()
    return to_paisa(row.default_admission_fee) if row and \
        row.default_admission_fee is not None else 0


def class_override_paisa(class_obj):
    """``None`` when the class follows the school default."""
    if class_obj is None or class_obj.admission_fee is None:
        return None
    return to_paisa(class_obj.admission_fee)


def effective_paisa(class_id):
    """Admission fee for a class: its own value, else the school default."""
    class_obj = db.session.get(ClassModel, class_id) if class_id else None
    override = class_override_paisa(class_obj)
    return default_paisa() if override is None else override


def is_enabled():
    """Opt-in switch: true once any admission fee amount has been set."""
    if default_paisa() > 0:
        return True
    return db.session.query(ClassModel.id).filter(or_(
        ClassModel.admission_fee > 0, ClassModel.books_fee > 0,
        ClassModel.uniform_fee > 0)).first() is not None


def fee_by_class():
    """``{class_id(str): rupees}`` for the student form's auto-fill."""
    default = default_paisa()
    result = {}
    for class_obj in ClassModel.query.all():
        override = class_override_paisa(class_obj)
        result[str(class_obj.id)] = to_rupees(default if override is None else override)
    return result


def class_items(class_obj):
    """``{'books', 'uniform', 'sets'}`` configured for a class (rupees / count)."""
    if class_obj is None:
        return {'books': 0.0, 'uniform': 0.0, 'sets': 1}
    return {'books': float(class_obj.books_fee or 0),
            'uniform': float(class_obj.uniform_fee or 0),
            'sets': int(class_obj.uniform_sets or 1)}


def items_by_class():
    """``{class_id(str): {admission, books, uniform, sets}}`` for the form's auto-fill."""
    default = default_paisa()
    result = {}
    for class_obj in ClassModel.query.all():
        override = class_override_paisa(class_obj)
        item = class_items(class_obj)
        item['admission'] = to_rupees(default if override is None else override)
        result[str(class_obj.id)] = item
    return result


def _inventory_set_prices(class_id):
    """Selling price (rupees) of the class's books / uniform set in Inventory, or
    ``None`` - shown next to the fee boxes so the two numbers can be matched."""
    from app.services import inventory_service, student_stock
    result = {'books': None, 'uniform': None}
    try:
        if not inventory_service.inventory_enabled():
            return result
        for kind in ('books', 'uniform'):
            target = student_stock.class_set(class_id, kind)
            if target is not None:
                price = inventory_service.set_price_paisa(target)
                result[kind] = to_rupees(price) if price else None
    except Exception:       # a hint must never break the settings page
        return {'books': None, 'uniform': None}
    return result


def settings_context():
    """Everything the Fees page settings dialog needs."""
    default = default_paisa()
    rows = []
    for class_obj in ClassModel.query.order_by(ClassModel.id).all():
        override = class_override_paisa(class_obj)
        set_prices = _inventory_set_prices(class_obj.id)
        rows.append({
            'set_books': set_prices['books'],
            'set_uniform': set_prices['uniform'],
            'id': class_obj.id,
            'name': class_obj.name,
            'override': None if override is None else to_rupees(override),
            'effective': to_rupees(default if override is None else override),
            'books': class_obj.books_fee,
            'uniform': class_obj.uniform_fee,
            'sets': class_obj.uniform_sets,
        })
    return {'default': to_rupees(default) if default else None,
            'classes': rows, 'enabled': is_enabled()}


def _parse_optional_amount(value, label):
    """'' -> None (inherit), otherwise a non-negative rupee amount."""
    text = (value or '').strip().replace(',', '')
    if text == '':
        return None
    try:
        amount = float(text)
    except ValueError:
        raise ValueError('%s must be a number.' % label)
    if amount < 0:
        raise ValueError('%s cannot be negative.' % label)
    return round(amount, 2)


def _parse_sets(value):
    """'' -> None (one set), otherwise a whole number of sets >= 1."""
    text = (value or '').strip()
    if text == '':
        return None
    try:
        sets = int(float(text))
    except ValueError:
        raise ValueError('The number of uniform sets must be a whole number.')
    if sets < 1 or sets > 20:
        raise ValueError('The number of uniform sets must be between 1 and 20.')
    return sets


def save_settings(default_value, class_values, class_items_values=None):
    """Store the universal fee and each class's own fee (blank = follow default).

    ``class_items_values`` is ``{class_id: {'books', 'uniform', 'sets'}}`` of raw
    form text; blank books / uniform means the class has none.

    Existing students are never touched: a changed fee only applies to
    students admitted afterwards.
    """
    default_amount = _parse_optional_amount(default_value, 'The school admission fee')
    parsed = {}
    for class_id, raw in class_values.items():
        parsed[class_id] = _parse_optional_amount(raw, 'The class admission fee')
    items = {}
    for class_id, raw in (class_items_values or {}).items():
        items[class_id] = {
            'books': _parse_optional_amount(raw.get('books'), 'The books fee'),
            'uniform': _parse_optional_amount(raw.get('uniform'), 'The uniform price'),
            'sets': _parse_sets(raw.get('sets')),
        }
    row = _settings_row(create=True)
    row.default_admission_fee = default_amount
    for class_obj in ClassModel.query.all():
        if class_obj.id in parsed:
            class_obj.admission_fee = parsed[class_obj.id]
        if class_obj.id in items:
            class_obj.books_fee = items[class_obj.id]['books']
            class_obj.uniform_fee = items[class_obj.id]['uniform']
            class_obj.uniform_sets = items[class_obj.id]['sets']
    return default_amount, parsed

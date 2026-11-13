"""Admission fee basics: names, allowed values, labels, the admin check and rupee/paisa conversion."""

from app.models import ROLE_ADMIN
from app.models.fees import to_rupees


CATEGORY_NAME = 'Admission Fee'


RECEIPT_PREFIX = 'ADM-'


DISCOUNT_TYPES = ('percentage', 'fixed', 'waived')


PAYMENT_METHODS = ('cash', 'bank', 'online', 'other')


STATUSES = ('pending', 'partial', 'paid', 'waived')


COMPONENT_LABELS = (('admission', 'Admission fee'), ('books', 'Books'),
                    ('uniform', 'Uniform'))


STATUS_LABELS = {
    'not_applicable': 'Not applicable',
    'pending': 'Pending',
    'partial': 'Partial',
    'paid': 'Paid',
    'waived': 'Waived',
}


def is_admin(user):
    """Same rule as app/security.py: a missing role means administrator."""
    return (getattr(user, 'role', None) or ROLE_ADMIN) == ROLE_ADMIN


def money(paisa):
    return 'Rs. {:,.0f}'.format(to_rupees(paisa)) if (paisa or 0) % 100 == 0 \
        else 'Rs. {:,.2f}'.format(to_rupees(paisa))

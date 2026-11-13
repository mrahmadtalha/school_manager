"""``app/services/admission_fee`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
admission-fee code ships obfuscated.  These tests pin what must not break: every
file stays small, and every name the routes, services and tests used before
(private helpers and ``to_rupees`` / ``to_paisa`` included) is still available from
``app.services.admission_fee``.
"""

import sys
from pathlib import Path

from app.services import admission_fee

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'admission_fee'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

NAMES = (
    'CATEGORY_NAME', 'RECEIPT_PREFIX', 'DISCOUNT_TYPES', 'PAYMENT_METHODS',
    'STATUSES', 'COMPONENT_LABELS', 'STATUS_LABELS', 'is_admin', 'money',
    '_settings_row', 'default_paisa', 'class_override_paisa', 'effective_paisa',
    'is_enabled', 'fee_by_class', 'class_items', 'items_by_class',
    '_inventory_set_prices', 'settings_context', '_parse_optional_amount',
    '_parse_sets', 'save_settings', 'compute_net', 'books_unit_paisa', 'books_qty',
    'books_paisa', 'uniform_paisa', 'extras_paisa', 'has_terms', 'total_net_paisa',
    'components', 'allocate', 'concession_paisa', 'active_payments', 'all_payments',
    'prior_paid_paisa', 'income_received_paisa', 'received_paisa', 'status_for',
    'summary', '_sets', 'set_items', 'apply_terms', 'adjust_terms', '_terms_text',
    'get_category', 'next_receipt_no', 'receive_payment', 'void_payment',
    '_form_amount', 'apply_on_admission', 'register', 'apply_on_import',
    'student_map', 'income_total', 'to_paisa', 'to_rupees',
)


def test_admission_fee_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'admission_fee.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 8
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_name_is_still_available():
    assert [name for name in NAMES if not hasattr(admission_fee, name)] == []


def test_the_original_import_lines_still_work():
    from app.services.admission_fee import (income_total, receive_payment,  # noqa: F401
                                            student_map, summary, to_rupees)
    assert receive_payment.__module__.endswith('admission_fee.receipts')

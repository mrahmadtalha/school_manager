"""``app/services/fee_ledger`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
money code ships obfuscated.  These tests pin what must not break: every file
stays small, and every name the routes, services, scripts and tests used before
(private helpers included) is still importable from ``app.services.fee_ledger``.
"""

import sys
from pathlib import Path

from app.services import fee_ledger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'fee_ledger'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

NAMES = (
    'current_month', 'advance_credit_enabled', 'payment_allocation_lines',
    'payment_allocation_summary', '_round', 'month_charge_amount', 'ensure_charge',
    'set_month_charge', 'DuplicateReferenceError', 'reference_in_use', 'next_reference',
    'generate_unique_reference', '_charge_sorted', '_student_month_keys', '_settled_paisa',
    'SETTLEABLE_TYPES', '_month_charged_paisa', '_month_settled_paisa',
    'student_month_outstanding_paisa', 'student_dues_months', '_refunded_paisa',
    'allocate_transaction', 'record_payment', 'record_adjustment', 'record_refund',
    'record_writeoff', 'void_transaction', '_recompute_months', 'ledger_totals',
    'month_written_off', 'student_outstanding_paisa', 'student_credit_paisa', '_status_for',
    'recompute_fee_record', 'transactions_for', '_month_sort_key', 'student_summary',
    'reconcile', 'repair_summaries', 'orphaned_settlements', 'repair_allocations',
)


def test_fee_ledger_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'fee_ledger.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 6
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_name_is_still_importable():
    assert [name for name in NAMES if not hasattr(fee_ledger, name)] == []


def test_the_original_import_lines_still_work():
    from app.services.fee_ledger import (_month_sort_key, allocate_transaction,  # noqa: F401
                                         ensure_charge, ledger_totals, reconcile,
                                         record_payment, repair_summaries)
    assert record_payment.__module__.endswith('fee_ledger.flows')

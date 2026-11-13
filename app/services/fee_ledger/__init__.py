"""Fee ledger service (financial v2).

``fee_transactions`` is the source of truth (append-only, voidable, never
deleted).  ``fee_records`` is a derived per-student/per-month summary that is
always recomputed from the ledger + allocations so the two can never disagree.

**Allocations** link a settling transaction (a payment or a write-off) to the
specific charges it settles.  New money settles the student's outstanding
charges **oldest month first** (the month named on the form first, then any
older arrears).  Whatever is left after every outstanding charge is settled
stays unallocated — that is the student's advance credit, applied
automatically to future charges by the next allocation run.

**Refunds** are negative cash tied to their original payment
(``related_txn_id``); creating one reduces the payment's effective amount and
the payment is re-allocated, which raises the outstanding balance back.

**Voids** never delete: a voided row is flagged with a mandatory reason and
excluded from every total; affected allocations are voided with it and the
remaining payments re-allocate.
"""

# This package replaces the former single file ``fee_ledger.py``.  Every name the
# rest of the application and the tests used before (private helpers too) is
# re-exported here, so ``from app.services.fee_ledger import ...`` keeps working.

from .common import (  # noqa: F401
    current_month, advance_credit_enabled, _round, DuplicateReferenceError,
    reference_in_use, next_reference, generate_unique_reference, _month_sort_key,
)
from .charges import (  # noqa: F401
    month_charge_amount, ensure_charge, set_month_charge,
)
from .allocation import (  # noqa: F401
    payment_allocation_lines, payment_allocation_summary, _charge_sorted,
    _student_month_keys, _settled_paisa, SETTLEABLE_TYPES, _month_charged_paisa,
    _month_settled_paisa, student_month_outstanding_paisa, student_dues_months,
    _refunded_paisa, allocate_transaction,
)
from .totals import (  # noqa: F401
    _recompute_months, ledger_totals, month_written_off, student_outstanding_paisa,
    student_credit_paisa, _status_for, recompute_fee_record, transactions_for,
    student_summary, reconcile, repair_summaries,
)
from .flows import (  # noqa: F401
    record_payment, record_adjustment, record_refund, record_writeoff,
    void_transaction,
)
from .repair import (  # noqa: F401
    orphaned_settlements, repair_allocations,
)

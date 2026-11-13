"""One-time admission fee.

How the money is kept
---------------------
* The **terms** live on the student: standard fee, optional concession and the
  agreed (net) amount, all in integer paisa.  ``admission_fee_net_paisa`` is
  NULL for every student who has no admission fee on record, which includes
  every student that existed before this feature, so nobody becomes "pending"
  and no old number changes.
* The **money received** is stored as ``OtherIncome`` rows in the "Admission
  Fee" category, linked to the student (``student_id``) and numbered
  (``receipt_no``).  Because Other Income already feeds the financial
  overview, the dashboard account book and the comparisons, admission income
  shows up there without touching any of those formulas.  A student can have
  several payments (instalments); voiding a payment re-opens the balance.
* The monthly fee ledger is NOT used: it assumes exactly one monthly charge per
  student per month, so an admission charge would break it.

The feature is opt-in: nothing admission-related is shown until the school sets
a universal or a per-class admission fee (or class books / uniform).

New-admission package
---------------------
Besides the admission fee a class can carry **books** and **uniform** (price
per set x number of sets).  They are set once per class in the settings, are
copied onto the student at admission (editable on the form) and are paid
together with the admission fee on ONE receipt.  The agreed total is
``admission net + books + uniform``; a partial payment is applied in that
order (admission, books, uniform) and the rest stays pending, exactly like the
admission fee on its own.  The concession applies to the admission fee only.
"""

# This package replaces the former single file ``admission_fee.py``.  Every name the
# rest of the application and the tests used before (private helpers too) is
# re-exported here, so ``from app.services.admission_fee import ...`` keeps working.

from .common import (  # noqa: F401
    CATEGORY_NAME, RECEIPT_PREFIX, DISCOUNT_TYPES, PAYMENT_METHODS, STATUSES,
    COMPONENT_LABELS, STATUS_LABELS, is_admin, money,
)
from .settings import (  # noqa: F401
    _settings_row, default_paisa, class_override_paisa, effective_paisa, is_enabled,
    fee_by_class, class_items, items_by_class, _inventory_set_prices,
    settings_context, _parse_optional_amount, _parse_sets, save_settings,
)
from .terms import (  # noqa: F401
    compute_net, books_unit_paisa, books_qty, books_paisa, uniform_paisa,
    extras_paisa, has_terms, total_net_paisa, components, allocate, concession_paisa,
)
from .balances import (  # noqa: F401
    active_payments, all_payments, prior_paid_paisa, income_received_paisa,
    received_paisa, status_for, summary,
)
from .edit import (  # noqa: F401
    _sets, set_items, apply_terms, adjust_terms, _terms_text,
)
from .receipts import (  # noqa: F401
    get_category, next_receipt_no, receive_payment, void_payment,
)
from .admission import (  # noqa: F401
    _form_amount, apply_on_admission, register, apply_on_import,
)
from .reporting import (  # noqa: F401
    student_map, income_total,
)

# Names re-exported from app.models because callers use them as ``admission_fee.to_rupees``.
from app.models.fees import to_paisa, to_rupees  # noqa: E402,F401

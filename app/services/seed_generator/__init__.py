"""Advanced demo/seed data generator.

One engine powers both entry points:

* the first-run setup wizard (``/setup-admin``, which runs it in a background
  thread with live progress), and
* the ``seed_data.py`` CLI script.

The generator produces a realistic *history* for a configurable period
(1 month ... 10 years): students and teachers with consistent ages and a
join/leave lifecycle, daily attendance with per-person behaviour patterns,
monthly fee charges/payments on the append-only ledger, expenses, class tests,
term exams with marks/results, payroll with real salary payments, admission fees with
receipts, inventory (sets, purchases, supplier dues, sales), canteen, other income,
issued ID cards / certificates, timetable, QR attendance, WhatsApp queue, and optional locally drawn avatar
photos.  All randomness comes from a single seeded ``random.Random`` so a run
is reproducible.

Every generated fact is fabricated.  No real person's data is used.
"""

# This package replaces the former single file ``seed_generator.py``.  Every name the
# rest of the application and the tests used before (private helpers too) is
# re-exported here, so ``from app.services.seed_generator import ...`` keeps working.

from .data import (  # noqa: F401
    CLASS_LEVELS, CLASS_NAMES, SECTION_NAMES, SUBJECT_NAMES, TEST_TYPE_NAMES,
    FIRST_NAMES_MALE, FIRST_NAMES_FEMALE, LAST_NAMES, FATHER_FIRST, STREETS, CITIES,
    QUALIFICATIONS, DESIGNATIONS, LEAVING_REASONS, TEACHER_GENDER_POOL,
    STUDENT_PROFILES, PROFILE_PICK_WEIGHTS, PAYMENT_PROFILES, PAYMENT_PICK_WEIGHTS,
    EXPENSE_AMOUNTS, EXPENSE_NOTES, AVATAR_PALETTE, _STAGE_WEIGHTS, _BULK_CHUNK,
)
from .config import (  # noqa: F401
    SeedConfig, _Progress,
)
from .helpers import (  # noqa: F401
    _shift_month, _month_end, _today, _pick, _weighted_status, _person_name, _phone,
    _cnic, _address, _session_label, _custom_field_values, _status_for,
    _ensure_library_subjects, _start_minutes, _minutes_to_time, _enrolled_on,
    _mark_row, _month_end_for_pay,
)
from .stage_structure_people import (  # noqa: F401
    _stage_structure, _stage_teachers, _stage_students,
)
from .stage_attendance_fees import (  # noqa: F401
    _stage_attendance, _stage_fees, _stage_expenses,
)
from .stage_tests_payroll import (  # noqa: F401
    _stage_class_tests, _stage_term_exams, _stage_payroll,
)
from .stage_misc import (  # noqa: F401
    _stage_photos, _stage_accounts,
)
from .stage_inventory import _stage_inventory  # noqa: F401
from .stage_admission import _stage_admission  # noqa: F401
from .stage_money import (  # noqa: F401
    _stage_other_income, _stage_canteen, _stage_documents,
)
from .stage_school_life import _stage_remarks, _stage_school_life  # noqa: F401
from .engine import (  # noqa: F401
    run_seed, estimate_records,
)

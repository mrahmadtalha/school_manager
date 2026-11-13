"""Offline admin assistant (no AI model, no internet, no API).

How it works
------------
1. The question is normalised and split into words.
2. Every word is looked up (exactly, or fuzzily for misspellings) in the
   keyword table of ``assistant_intents.INTENTS``; each intent collects a score.
3. The best-scoring intent wins.  Class, student, date and status are pulled
   out of the question separately ("entities").
4. A handler for that intent reads the numbers through the application's own
   services, so the answer always matches the rest of the software.

The assistant only READS data.  It never creates, edits or deletes anything.
"""

# This package replaces the former single file ``assistant.py``.  Every name the
# rest of the application and the tests used before (private helpers too) is
# re-exported here, so ``from app.services.assistant import ...`` keeps working.

from .constants import (  # noqa: F401
    MAX_QUESTION_LENGTH, MAX_LIST_ROWS, MAX_CONTEXT_LENGTH, AT_RISK_PERCENT,
    PAYROLL_REMINDER_DAY, log, MONTHS, PREVIOUS_WORDS, MONTH_WORDS, THIS_WORDS,
    TODAY_WORDS, YESTERDAY_WORDS, TEACHER_WORDS, MALE_WORDS, FEMALE_WORDS,
    STUDENT_WORDS, PRONOUN_WORDS, FOLLOW_WORDS, FOLLOWABLE, STUDENT_INTENTS,
)
from .nlu import (  # noqa: F401
    normalize, _VOCAB, _FUZZY_KEYS, _HOW_FUZZY, _vocab, _match_key, _has_how_marker,
    score_intents,
)
from .formatting import (  # noqa: F401
    rs, _link, _links, _reply, _with_context, _period_label, _json_list,
)
from .context import (  # noqa: F401
    Ctx, _settle_people, _clean_context, _context_out, _resolve_pronoun, _follow_up,
)
from .lookup import (  # noqa: F401
    _find_class, _name_candidates, _match_names, _find_students, _find_teachers,
    _students_by_ids, _ask_which_student, _ask_which_teacher,
)
from .handlers_core import (  # noqa: F401
    h_help, h_today_summary, h_students_count, h_teachers_count, h_class_strength,
)
from .handlers_attendance import (  # noqa: F401
    _student_attendance, h_attendance, _attendance_names, _is_working_day,
    h_low_attendance,
)
from .handlers_finance import (  # noqa: F401
    h_fees_collected, h_fees_due, h_expenses, h_profit, h_salary, _pct_change,
    h_class_fees, h_compare, h_fees_payments,
)
from .handlers_people import (  # noqa: F401
    h_student_info, h_birthdays, h_new_admissions, h_teacher_info,
)
from .handlers_misc import (  # noqa: F401
    h_attention, h_howto, HANDLERS,
)
from .engine import (  # noqa: F401
    _unknown, answer,
)

# Names re-exported from payroll_service because callers use them as ``assistant.current_month_key`` etc.
from app.services.payroll_service import (  # noqa: E402,F401
    current_month_key, month_bounds, month_label, shift_month)

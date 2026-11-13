"""``app/services/assistant`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
assistant's logic ships obfuscated.  These tests pin what must not break: every
file stays small, and every name used before (private helpers, and the month
helpers borrowed from payroll) is still available from ``app.services.assistant``.
"""

import sys
from pathlib import Path

from app.services import assistant

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'assistant'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

NAMES = (
    'MAX_QUESTION_LENGTH', 'MAX_LIST_ROWS', 'MAX_CONTEXT_LENGTH', 'AT_RISK_PERCENT',
    'PAYROLL_REMINDER_DAY', 'log', 'MONTHS', 'PREVIOUS_WORDS', 'MONTH_WORDS',
    'THIS_WORDS', 'TODAY_WORDS', 'YESTERDAY_WORDS', 'TEACHER_WORDS', 'MALE_WORDS',
    'FEMALE_WORDS', 'STUDENT_WORDS', 'PRONOUN_WORDS', 'FOLLOW_WORDS', 'FOLLOWABLE',
    'STUDENT_INTENTS', 'normalize', 'rs', '_link', '_links', '_VOCAB', '_FUZZY_KEYS',
    '_HOW_FUZZY', '_vocab', '_match_key', '_has_how_marker', 'score_intents', 'Ctx',
    '_find_class', '_name_candidates', '_match_names', '_find_students',
    '_find_teachers', '_settle_people', '_clean_context', '_context_out',
    '_resolve_pronoun', '_follow_up', '_reply', '_with_context', '_period_label',
    '_students_by_ids', 'h_help', 'h_today_summary', 'h_students_count',
    'h_teachers_count', 'h_class_strength', '_student_attendance', 'h_attendance',
    '_attendance_names', 'h_fees_collected', 'h_fees_due', '_ask_which_student',
    '_ask_which_teacher', 'h_expenses', 'h_profit', 'h_salary', 'h_student_info',
    '_pct_change', '_is_working_day', 'h_attention', 'h_birthdays',
    'h_low_attendance', 'h_class_fees', 'h_compare', 'h_new_admissions',
    'h_fees_payments', '_json_list', 'h_teacher_info', 'h_howto', 'HANDLERS',
    '_unknown', 'answer', 'month_bounds', 'month_label', 'shift_month',
    'current_month_key',
)


def test_assistant_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'assistant.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 10
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_name_is_still_available():
    assert [name for name in NAMES if not hasattr(assistant, name)] == []


def test_the_original_import_lines_still_work():
    from app.services.assistant import answer, current_month_key, score_intents  # noqa: F401
    assert answer.__module__.endswith('assistant.engine')

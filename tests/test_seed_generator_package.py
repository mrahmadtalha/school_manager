"""``app/services/seed_generator`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
demo-data generator ships obfuscated. These tests pin what must not break: every
file stays small, and every name used before (private helpers included) is still
available from ``app.services.seed_generator``.
"""

import sys
from pathlib import Path

from app.services import seed_generator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'seed_generator'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

NAMES = (
    'CLASS_LEVELS', 'CLASS_NAMES', 'SECTION_NAMES', 'SUBJECT_NAMES',
    'TEST_TYPE_NAMES', 'FIRST_NAMES_MALE', 'FIRST_NAMES_FEMALE', 'LAST_NAMES',
    'FATHER_FIRST', 'STREETS', 'CITIES', 'QUALIFICATIONS', 'DESIGNATIONS',
    'LEAVING_REASONS', 'TEACHER_GENDER_POOL', 'STUDENT_PROFILES',
    'PROFILE_PICK_WEIGHTS', 'PAYMENT_PROFILES', 'PAYMENT_PICK_WEIGHTS',
    'EXPENSE_AMOUNTS', 'EXPENSE_NOTES', 'AVATAR_PALETTE', '_STAGE_WEIGHTS',
    '_BULK_CHUNK', 'SeedConfig', '_Progress', '_shift_month', '_month_end', '_today',
    '_pick', '_weighted_status', '_person_name', '_phone', '_cnic', '_address',
    '_session_label', '_custom_field_values', '_status_for',
    '_ensure_library_subjects', '_stage_structure', '_stage_teachers',
    '_stage_students', '_stage_attendance', '_start_minutes', '_minutes_to_time',
    '_stage_fees', '_stage_expenses', '_enrolled_on', '_mark_row',
    '_stage_class_tests', '_stage_term_exams', '_stage_payroll', '_month_end_for_pay',
    '_stage_photos', '_stage_accounts', 'run_seed', 'estimate_records',
)


def test_seed_generator_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'seed_generator.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 8
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_name_is_still_available():
    assert [name for name in NAMES if not hasattr(seed_generator, name)] == []


def test_the_original_import_lines_still_work():
    from app.services.seed_generator import SeedConfig, estimate_records, run_seed  # noqa: F401
    assert run_seed.__module__.endswith('seed_generator.engine')

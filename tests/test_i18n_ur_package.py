"""``app/services/i18n_ur`` is a package of small modules, not one big file.

It was split so that every file fits under the PyArmor trial size limit and the
Urdu wording ships obfuscated. It is still the same dictionary, built the same
way as before -- a literal plus a long sequence of ``.update()`` calls -- just
spread over several files that run in order when the package is imported.
These tests pin what must not break: every file stays small, the result is
byte-for-byte the same dictionary as the original single file produced, and
every name used before is still available from ``app.services.i18n_ur``.
"""

import importlib.util
import sys
from pathlib import Path

from app.services import i18n_ur

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / 'app' / 'services' / 'i18n_ur'
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import TRIAL_BIG_SCRIPT_BYTES  # noqa: E402

#: Stay well under the build's own limit so a future edit has room to grow.
SAFE_BYTES = 28_000

PUBLIC_NAMES = (
    'UR', 'PATTERNS', 'HTML_SENTENCES', 'MONTH_UR', 'WEEKDAY_UR', 'UR_FOLDED',
)


def test_i18n_ur_is_a_package_of_small_files():
    assert not (PROJECT_ROOT / 'app' / 'services' / 'i18n_ur.py').exists()
    files = sorted(PACKAGE_DIR.glob('*.py'))
    assert len(files) >= 14
    for path in files:
        size = path.stat().st_size
        assert size < SAFE_BYTES < TRIAL_BIG_SCRIPT_BYTES, f'{path.name} is {size} bytes'


def test_every_previous_name_is_still_available():
    assert [name for name in PUBLIC_NAMES if not hasattr(i18n_ur, name)] == []


def test_the_original_import_line_still_works():
    from app.services.i18n_ur import HTML_SENTENCES, PATTERNS, UR, UR_FOLDED  # noqa: F401
    assert UR['Class'] == 'کلاس'
    assert len(UR) > 1600


def test_loading_the_package_fresh_reproduces_the_same_dictionary():
    """A second, independent load must build the identical UR / UR_FOLDED,

    proving the split preserves both the final dictionary and the point in
    the sequence where ``UR_FOLDED`` takes its snapshot of ``UR``.
    """
    spec = importlib.util.spec_from_file_location(
        'sm_test_i18n_ur_fresh', PACKAGE_DIR / '__init__.py',
        submodule_search_locations=[str(PACKAGE_DIR)])
    fresh = importlib.util.module_from_spec(spec)
    sys.modules['sm_test_i18n_ur_fresh'] = fresh
    spec.loader.exec_module(fresh)
    assert fresh.UR == i18n_ur.UR
    assert fresh.UR_FOLDED == i18n_ur.UR_FOLDED
    assert len(fresh.PATTERNS) == len(i18n_ur.PATTERNS)

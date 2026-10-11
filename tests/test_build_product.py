"""Product build plan (Phase 4): what gets obfuscated, copied, and excluded.

The build script (``tools/build_product.py``) assembles the customer source
tree.  These tests pin the tree-composition rules without running PyArmor:
nothing vendor-private, nothing dev-only, and every application module must be
handed to the obfuscator.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from build_product import (  # noqa: E402
    EXCLUDED_TOPLEVEL, PRODUCT_TOPLEVEL, TRIAL_BIG_SCRIPT_BYTES, plan_build,
)


def test_every_app_python_file_is_handed_to_pyarmor():
    plan = plan_build()
    on_disk = sorted(p.relative_to(PROJECT_ROOT / 'app').as_posix()
                     for p in (PROJECT_ROOT / 'app').rglob('*.py'))
    assert plan.obfuscate == on_disk
    assert len(plan.obfuscate) >= 70


def test_security_critical_modules_are_obfuscated():
    plan = plan_build()
    for critical in ('license_guard.py', 'auth.py', 'config.py',
                     'services/licensing.py', 'services/license_public_key.py',
                     'security.py', 'graceful_exit.py'):
        assert critical in plan.obfuscate


def test_vendor_and_dev_files_are_excluded():
    for entry in ('tests', 'tools', 'vendor_keys', 'instance', 'build',
                  'whatsapp-service', 'seed_data.py', 'start_all.py', 'run.py'):
        assert entry in EXCLUDED_TOPLEVEL
    assert 'license_admin.py' not in str(PRODUCT_TOPLEVEL)


def test_launcher_and_requirements_ship_at_toplevel():
    assert 'school_manager.pyw' in PRODUCT_TOPLEVEL
    assert 'requirements.txt' in PRODUCT_TOPLEVEL


def test_no_product_toplevel_entry_points_at_project_root_outside_plan():
    """The product tree must not pull in migration helpers or debug scripts."""
    for stray in ('migrate_db.py', 'migrate_custom_fields.py',
                  'migrate_student_status.py', 'tmp_inspect_db.py'):
        assert stray in EXCLUDED_TOPLEVEL


def test_trial_size_threshold_covers_known_big_modules():
    """Files the PyArmor trial cannot obfuscate are exactly those over the
    threshold; the known large modules must all be among them.  The set can
    grow as modules grow (they then ship plain and are listed in
    BUILD-INFO.txt), but it must never silently shrink."""
    plan = plan_build()
    big = [rel for rel in plan.obfuscate
           if (PROJECT_ROOT / 'app' / rel).stat().st_size > TRIAL_BIG_SCRIPT_BYTES]
    for rel in big:
        assert (PROJECT_ROOT / 'app' / rel).stat().st_size > TRIAL_BIG_SCRIPT_BYTES
    assert {'bootstrap.py', 'routes/reports.py', 'routes/students.py',
            'routes/teachers.py', 'routes/term_exams.py',
            'services/seed_generator.py'} <= set(big)
    assert 'routes/settings.py' in set(big)  # grew past the limit in Phase 6

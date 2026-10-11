"""Build the obfuscated product source tree (Phase 4 of the product roadmap).

Runs PyArmor over the ``app`` package and assembles a self-contained product
tree that Phase 5 (PyInstaller) will consume:

    build/product/
        school_manager.pyw        the (plain) launcher - no secrets inside
        requirements.txt
        app/                      obfuscated .py + original templates/static
        pyarmor_runtime_000000/   PyArmor runtime package
        BUILD-INFO.txt            what was obfuscated, and what could not be

Deliberately EXCLUDED from the product tree: tests/, tools/
(``license_admin.py`` must never ship), seed_data.py, start_all.py, run.py,
the WhatsApp bridge (an optional installer component, Phase 6), docs,
screenshots, vendor signing keys and any local data.

PyArmor editions: the **trial** edition cannot obfuscate large scripts, so a
handful of big modules (reports, students, seed generator, ...) are copied in
plain and listed in BUILD-INFO.txt.  Everything security-relevant (licensing,
guard, security, auth, config) is small and always obfuscated.  A PyArmor
Basic license removes the size limit; the build detects this automatically -
no configuration needed either way.

Usage:
    python tools/build_product.py                   # build + verify
    python tools/build_product.py --output build/product --no-verify
"""

import argparse
import datetime
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / 'app'

#: Source files that are never part of the customer product tree.
EXCLUDED_TOPLEVEL = [
    'tests', 'tools', 'docs', 'scripts', 'screenshots', 'instance',
    'vendor_keys', 'whatsapp-service', 'build', 'dist', '.git', '.github',
    '.zcode', 'node_modules',
    'seed_data.py', 'start_all.py', 'run.py', 'tmp_inspect_db.py',
    'migrate_db.py', 'migrate_custom_fields.py', 'migrate_student_status.py',
    'setup.txt', 'folderstru.txt',
]

#: Entries copied to the product root as-is.
PRODUCT_TOPLEVEL = ['school_manager.pyw', 'requirements.txt']

#: PyArmor trial cannot obfuscate large scripts; this source-size threshold
#: (bytes) separates "known fine" from "known to fail".  Files over it are
#: excluded up front and shipped plain; a licensed PyArmor obfuscates them.
TRIAL_BIG_SCRIPT_BYTES = 33_000


class BuildPlan:
    def __init__(self):
        self.obfuscate = []        # app-relative .py paths handed to PyArmor
        self.toplevel = list(PRODUCT_TOPLEVEL)
        self.excluded = list(EXCLUDED_TOPLEVEL)

    @property
    def app_py_files(self):
        return sorted(p.relative_to(APP_DIR).as_posix()
                      for p in APP_DIR.rglob('*.py'))


def plan_build():
    """Compute what goes into the product tree (pure; unit-tested)."""
    plan = BuildPlan()
    plan.obfuscate = plan.app_py_files
    return plan


def _run_pyarmor(args):
    result = subprocess.run(['pyarmor', 'gen', *args],
                            capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    return result


def _pyarmor_edition():
    result = subprocess.run(['pyarmor', '--version'], capture_output=True,
                            text=True)
    first = (result.stdout or '').splitlines()[0] if result.stdout else ''
    return first.strip() or 'pyarmor'


def _is_big(rel_path):
    return (APP_DIR / rel_path).stat().st_size > TRIAL_BIG_SCRIPT_BYTES


def obfuscate_app(output_root, plan):
    """Obfuscate the app package into ``output_root``.

    ``output_root/app`` must already contain the plain package (assets and
    everything); PyArmor overwrites the .py files it can obfuscate.  Files the
    edition refuses (trial big-script limit) simply stay plain and are
    reported.  Returns the list of files left plain.
    """
    big_files = [rel for rel in plan.obfuscate if _is_big(rel)]
    exclude_args = []
    for rel in big_files:
        exclude_args += ['--exclude', f'app/{rel}']

    result = _run_pyarmor(['--output', str(output_root), '-r', 'app', *exclude_args])
    if result.returncode != 0:
        raise RuntimeError(f'pyarmor gen failed:\n{result.stdout}\n{result.stderr}')

    left_plain = []
    for rel in plan.obfuscate:
        target = output_root / 'app' / rel
        if not target.is_file():
            raise RuntimeError(f'pyarmor did not produce app/{rel}')
        if b'Pyarmor' not in target.read_bytes()[:120]:
            left_plain.append(rel)
    return left_plain


def assemble(output_root, plan):
    """Create the product tree: plain assets first, then obfuscated code."""
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    app_target = output_root / 'app'
    shutil.copytree(APP_DIR, app_target,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    for entry in plan.toplevel:
        source = PROJECT_ROOT / entry
        if source.is_file():
            shutil.copy2(source, output_root / entry)

    left_plain = obfuscate_app(output_root, plan)
    return left_plain


def write_build_info(output_root, left_plain, edition):
    lines = [
        f'Product source tree built: {datetime.date.today().isoformat()}',
        f'Obfuscator: {edition}',
        f'Obfuscated modules: {len(_list_obfuscated(output_root))}',
    ]
    if left_plain:
        lines.append(f'Plain (too large for the PyArmor trial): {len(left_plain)}')
        lines += [f'  - app/{rel}' for rel in left_plain]
        lines += ['A PyArmor Basic license removes the size limit; '
                  'rebuild with the licensed edition to obfuscate these too.']
    (output_root / 'BUILD-INFO.txt').write_text('\n'.join(lines) + '\n',
                                                encoding='utf-8')


def _list_obfuscated(output_root):
    obfuscated = []
    for path in sorted((output_root / 'app').rglob('*.py')):
        if b'Pyarmor' in path.read_bytes()[:120]:
            obfuscated.append(path.relative_to(output_root).as_posix())
    return obfuscated


def verify_product(output_root, port=8799):
    """Boot the obfuscated tree in a subprocess and smoke-test it over HTTP."""
    script = (
        "import os, sys, tempfile, threading, time, urllib.request\n"
        "from pathlib import Path\n"
        f"root = Path(r'{output_root}')\n"
        "scratch = Path(tempfile.mkdtemp(prefix='p4-verify-'))\n"
        "os.environ['SCHOOL_DATA_DIR'] = str(scratch)\n"
        "os.environ['DATABASE_URL'] = 'sqlite:///' + (scratch / 'school.db').as_posix()\n"
        "os.environ['SECRET_KEY'] = 'p4-verify'\n"
        "os.environ['AUTO_BACKUP_ENABLED'] = '0'\n"
        "sys.path.insert(0, str(root))\n"
        "import app as app_pkg\n"
        "assert Path(app_pkg.__file__).resolve().is_relative_to(root.resolve()), app_pkg.__file__\n"
        "from app import create_app\n"
        "application = create_app()\n"
        "from waitress import create_server\n"
        "server = create_server(application, host='127.0.0.1', port=%d)\n"
        "threading.Thread(\n"
        "    target=lambda: (time.sleep(0.5), _probe()), daemon=True).start()\n"
        "def _probe():\n"
        "    checks = {\n"
        "        'healthz': 'http://127.0.0.1:%d/healthz',\n"
        "        'login': 'http://127.0.0.1:%d/login',\n"
        "        'vendor_css': 'http://127.0.0.1:%d/static/vendor/bootstrap/bootstrap.min.css',\n"
        "    }\n"
        "    results = {}\n"
        "    for name, url in checks.items():\n"
        "        for _ in range(40):\n"
        "            try:\n"
        "                with urllib.request.urlopen(url, timeout=3) as r:\n"
        "                    results[name] = r.status\n"
        "                break\n"
        "            except Exception:\n"
        "                time.sleep(0.25)\n"
        "        else:\n"
        "            results[name] = 'FAIL'\n"
        "    print('VERIFY-RESULTS:', results)\n"
        "    ok = all(v == 200 for v in results.values())\n"
        "    print('VERIFY-PASS' if ok else 'VERIFY-FAIL')\n"
        "    sys.stdout.flush()\n"
        "    os._exit(0 if ok else 1)\n"
        "server.run()\n" % (port, port, port, port)
    )
    result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                            text=True, timeout=180)
    print(result.stdout.strip())
    if result.returncode != 0 or 'VERIFY-PASS' not in result.stdout:
        raise RuntimeError(f'obfuscated product failed smoke test:\n{result.stderr}')
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(PROJECT_ROOT / 'build' / 'product'))
    parser.add_argument('--no-verify', action='store_true',
                        help='skip the boot smoke test of the obfuscated tree')
    args = parser.parse_args(argv)
    output_root = Path(args.output).resolve()

    plan = plan_build()
    print(f'App modules to obfuscate: {len(plan.obfuscate)}')
    left_plain = assemble(output_root, plan)
    edition = _pyarmor_edition()
    write_build_info(output_root, left_plain, edition)
    print(f'Obfuscated : {len(_list_obfuscated(output_root))} modules')
    if left_plain:
        print(f'Left plain (trial size limit): {len(left_plain)}')
        for rel in left_plain:
            print(f'  - app/{rel}')
    print(f'Product tree: {output_root}')
    if not args.no_verify:
        print('Verifying the obfuscated tree boots and serves...')
        verify_product(output_root)
        print('Smoke test passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

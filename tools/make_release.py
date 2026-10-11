"""One-command release build (Phase 7).

Performs a CLEAN rebuild from scratch and assembles the release folder:

    build/release/v<version>/
        SchoolManager_Setup_v<version>.exe   the signed* installer
        SHA256SUMS.txt                       hashes of every artifact
        RELEASE-INFO.txt                     versions, sizes, build details

(* code signing is an optional post-step; see docs/RELEASE_CHECKLIST.md)

The clean rebuild is deliberate: `build/` is wiped first, so nothing stale
can ever ship.  After packaging, the script re-runs the release tests and
prints the final checklist reminder for the manual QA steps (docs section
B-F of docs/RELEASE_CHECKLIST.md).

Usage:
    python tools/make_release.py
"""

import hashlib
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

BUILD_DIR = PROJECT_ROOT / 'build'
RELEASE_ROOT = PROJECT_ROOT / 'build' / 'release'


def release_version():
    from build_installer import read_app_version
    return read_app_version()


def run_step(command, description):
    print(f'\n=== {description} ===', flush=True)
    result = subprocess.run(command, capture_output=True, text=True,
                            cwd=str(PROJECT_ROOT))
    tail = (result.stdout or '').strip().splitlines()[-6:]
    for line in tail:
        print('  ' + line[:160])
    if result.returncode != 0:
        print((result.stderr or '')[-2000:])
        raise RuntimeError(f'{description} failed (rc={result.returncode})')


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_everything():
    # --basetemp keeps pytest's scratch files inside build/ so the suite is
    # green even on machines where the default temp root is not writable.
    # The basetemp root itself must exist (pytest does not mkdir -p it).
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    run_step([sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=line',
              '--basetemp=' + str(BUILD_DIR / '.pytest')],
             'Full test suite')
    run_step([sys.executable, 'tools/build_product.py'],
             'Phase 4: obfuscated product tree')
    run_step([sys.executable, 'tools/build_exe.py'],
             'Phase 5: Windows executable (selftest verified)')
    run_step([sys.executable, 'tools/build_installer.py', '--skip-exe'],
             'Phase 6: Inno Setup installer')


def assemble_release(version):
    from build_installer import OUTPUT_DIR
    installer = Path(OUTPUT_DIR) / f'SchoolManager_Setup_v{version}.exe'
    if not installer.is_file():
        raise RuntimeError(f'installer missing: {installer}')

    release_dir = RELEASE_ROOT / f'v{version}'
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)
    shutil.copy2(installer, release_dir / installer.name)

    product_info = PROJECT_ROOT / 'build' / 'product' / 'BUILD-INFO.txt'
    lines = [
        f'School Manager release v{version}',
        f'Built: {date.today().isoformat()} by Ahmi software firm',
        '',
        '--- Installer ------------------------------------------------',
        f'  {installer.name}  ({installer.stat().st_size / (1024 * 1024):.1f} MB)',
        '',
        '--- Obfuscation / build details (from product tree) -----------',
    ]
    if product_info.is_file():
        lines += ['  ' + line for line in
                  product_info.read_text(encoding='utf-8').splitlines()]
    (release_dir / 'RELEASE-INFO.txt').write_text('\n'.join(lines) + '\n',
                                                  encoding='utf-8')

    sums = []
    for artifact in sorted(release_dir.iterdir()):
        if artifact.name == 'SHA256SUMS.txt':
            continue
        sums.append(f'{sha256_of(artifact)}  {artifact.name}')
    (release_dir / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n',
                                                encoding='utf-8')

    print(f'\nRelease folder: {release_dir}')
    print('\n'.join('  ' + s for s in sums))
    return release_dir


def main(argv=None):
    version = release_version()
    print(f'Release version: {version} (from installer/SchoolManager.iss)')

    if BUILD_DIR.exists():
        print('Wiping build/ for a clean rebuild (stale artifacts cannot ship)...')
        shutil.rmtree(BUILD_DIR)

    build_everything()
    release_dir = assemble_release(version)

    print('\n=== Reminder: finish docs/RELEASE_CHECKLIST.md sections B-F ===')
    print('(manual QA on a clean Windows machine: install, activation,')
    print(' WhatsApp pairing, offline test, update/uninstall, signing)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

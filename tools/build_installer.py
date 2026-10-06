"""Build the Windows installer (Phase 6): Inno Setup over Phases 4+5.

Produces ``build/installer/SchoolManager_Setup_v1.0.0.exe`` containing:

* the application bundle (``build/exe/SchoolManager`` — Phase 5 output), and
* the WhatsApp bridge (``whatsapp-service/`` with ``node_modules`` and a
  private ``node.exe``) — WhatsApp is a mandatory core feature.

Publisher branding on the installer, shortcuts and the Windows "Installed
Apps" entry: **Ahmi software firm** (est. 2020).

The bridge is staged from the project's ``whatsapp-service/`` folder with the
WhatsApp ``session/`` folder and development ``test/`` folder deliberately
excluded: the session is per-school user data created inside
``%LOCALAPPDATA%\\SchoolManager\\whatsapp-session`` at runtime and must never
be shipped.

Usage:
    python tools/build_installer.py                 # build + report
    python tools/build_installer.py --skip-exe      # reuse existing Phase 5 exe
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_ROOT = PROJECT_ROOT / 'build' / 'product'
EXE_ROOT = PROJECT_ROOT / 'build' / 'exe' / 'SchoolManager'
STAGING = PROJECT_ROOT / 'build' / 'installer-staging'
OUTPUT_DIR = PROJECT_ROOT / 'build' / 'installer'
ISS_FILE = PROJECT_ROOT / 'installer' / 'SchoolManager.iss'
ICON_FILE = PROJECT_ROOT / 'installer' / 'assets' / 'SchoolManager.ico'

ISCC_CANDIDATES = [
    Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Inno Setup 6' / 'ISCC.exe',
    Path(os.environ.get('ProgramFiles(x86)', '')) / 'Inno Setup 6' / 'ISCC.exe',
    Path(os.environ.get('ProgramFiles', '')) / 'Inno Setup 6' / 'ISCC.exe',
]

#: Copied into the staged bridge; everything else under whatsapp-service/
#: (session, test, caches) is per-machine or developer-only.
BRIDGE_FILES = ['server.js', 'package.json', 'package-lock.json', 'node_modules']


def read_app_version(iss_file=ISS_FILE):
    """The single source of truth for the product version: the .iss file."""
    for line in Path(iss_file).read_text(encoding='utf-8').splitlines():
        match = re.match(r'#define MyAppVersion "(.+?)"', line.strip())
        if match:
            return match.group(1)
    raise RuntimeError(f'MyAppVersion not found in {iss_file}')


def _log(message):
    print(message, flush=True)


def find_iscc():
    for candidate in ISCC_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def ensure_phase5_output():
    if not (EXE_ROOT / 'SchoolManager.exe').is_file():
        _log('Phase 5 output missing - running tools/build_exe.py first...')
        from build_exe import main as build_exe_main
        build_exe_main([])


def stage_bridge():
    """Copy the WhatsApp bridge (with a private node.exe) into staging."""
    source = PROJECT_ROOT / 'whatsapp-service'
    target = STAGING / 'whatsapp-service'
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    for entry in BRIDGE_FILES:
        src = source / entry
        dst = target / entry
        if not src.exists():
            raise RuntimeError(f'bridge file missing: {src}')
        if src.is_dir():
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns(
                                'session', 'test', '__pycache__', '.git'))
        else:
            shutil.copy2(src, dst)

    node = shutil.which('node')
    if not node:
        raise RuntimeError('node.exe not found on PATH - the installer must '
                           'bundle a private Node runtime. Install Node.js '
                           'and rebuild.')
    shutil.copy2(node, target / 'node.exe')
    _log(f'Staged WhatsApp bridge + node.exe -> {target}')
    return target


def ensure_icon():
    """Generate the installer icon (navy rounded square, white 'SM')."""
    if ICON_FILE.is_file():
        return
    ICON_FILE.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw, ImageFont

    size = 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([12, 12, size - 12, size - 12], radius=48,
                           fill=(13, 110, 253, 255))          # brand primary
    draw.rounded_rectangle([36, 60, size - 36, 96], radius=10,
                           fill=(255, 255, 255, 230))         # 'roof' bar
    draw.rectangle([48, 96, 72, size - 44], fill=(255, 255, 255, 230))
    draw.rectangle([116, 96, 140, size - 44], fill=(255, 255, 255, 230))
    draw.rectangle([184, 96, 208, size - 44], fill=(255, 255, 255, 230))
    try:
        font = ImageFont.truetype('arialbd.ttf', 40)
        draw.text((size / 2, size - 26), 'AHMI', anchor='mm', fill='white',
                  font=font)
    except OSError:
        pass
    img.save(ICON_FILE, sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                               (128, 128), (256, 256)])
    _log(f'Generated icon: {ICON_FILE}')


def compile_installer():
    iscc = find_iscc()
    if iscc is None:
        raise RuntimeError(
            'Inno Setup 6 not found (ISCC.exe). Install it with:\n'
            '    winget install --id JRSoftware.InnoSetup -e\n'
            'or download from https://jrsoftware.org/isdl.php')

    result = subprocess.run(
        [str(iscc), str(ISS_FILE)], capture_output=True, text=True,
        cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        raise RuntimeError(f'ISCC failed:\n{result.stdout[-3000:]}\n'
                           f'{result.stderr[-1500:]}')
    output = OUTPUT_DIR / f'SchoolManager_Setup_v{read_app_version()}.exe'
    if not output.is_file():
        raise RuntimeError(f'installer missing after compile: {output}')
    size_mb = output.stat().st_size / (1024 * 1024)
    _log(f'Installer built: {output} ({size_mb:.1f} MB)')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-exe', action='store_true',
                        help='reuse the existing Phase 5 output')
    args = parser.parse_args(argv)

    if not args.skip_exe:
        ensure_phase5_output()
    elif not (EXE_ROOT / 'SchoolManager.exe').is_file():
        raise RuntimeError(f'Phase 5 output missing: {EXE_ROOT}')

    stage_bridge()
    ensure_icon()
    compile_installer()
    return 0


if __name__ == '__main__':
    sys.exit(main())

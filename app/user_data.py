"""Single user-data folder for the Windows product.

Everything the school owns lives in ONE folder so it can be backed up, moved
or migrated as a unit:

* ``school.db``            the SQLite database
* ``.secret_key``          the generated Flask secret
* ``license.key`` / ``license.state``   offline license + signed clock state
* ``uploads/``             student/teacher photos
* ``backups/``             automatic and manual DB backups

Where the folder is:

1. ``SCHOOL_DATA_DIR`` environment variable (tests and support tooling) —
   wins over everything.
2. Running from the packaged exe (PyInstaller): ``%LOCALAPPDATA%\\SchoolManager``
   so the product works under Program Files without write-permission problems.
3. Running from source (development): ``<project>/instance`` — the historical
   location, so a developer's checkout keeps working unchanged.

When the data folder differs from the legacy locations (an install that kept
data next to the exe, or the pre-Phase-2 split where license files lived in
``app/instance``), :func:`migrate_into_data_root` copies anything missing into
the new folder on first start.  Copies never overwrite: the target always wins,
so re-running the migration is harmless.
"""

import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

#: Files copied as single units during a legacy migration.
_FILE_ITEMS = ('school.db', 'school.db-wal', 'school.db-shm', '.secret_key',
               'license.key', 'license.state')
#: Folders copied recursively during a legacy migration.
_FOLDER_ITEMS = ('uploads', 'backups')


def _localappdata():
    base = os.environ.get('LOCALAPPDATA')
    return Path(base) if base else Path.home() / 'AppData' / 'Local'


def _frozen_exe_dir():
    return Path(sys.executable).resolve().parent


def data_root():
    """The folder that holds every mutable file the school owns."""
    override = (os.environ.get('SCHOOL_DATA_DIR') or '').strip()
    if override:
        return Path(override)
    if getattr(sys, 'frozen', False):
        return _localappdata() / 'SchoolManager'
    return BASE_DIR / 'instance'


def legacy_candidates():
    """Old locations that may hold data from a previous layout, best match first.

    Only returns locations that differ from the current data root, so the
    default source layout (which already IS ``<project>/instance``) only ever
    migrates the stray ``app/instance`` folder the license files used before
    the data folder was unified.
    """
    target = data_root()
    if getattr(sys, 'frozen', False):
        exe_dir = _frozen_exe_dir()
        candidates = [exe_dir / 'instance', exe_dir / 'app' / 'instance',
                      exe_dir / 'data' / 'instance']
    else:
        candidates = [BASE_DIR / 'app' / 'instance']
        if (os.environ.get('SCHOOL_DATA_DIR') or '').strip():
            # Custom data dir from source: treat the project instance/ as legacy.
            candidates.insert(0, BASE_DIR / 'instance')
    seen, unique = set(), []
    for candidate in candidates:
        if candidate != target and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def migrate_folder(source, target):
    """Copy ``source`` into ``target`` without overwriting existing files."""
    copied = 0
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            if not destination.exists():
                shutil.copytree(item, destination)
                copied += 1
            continue
        if not destination.exists():
            shutil.copy2(item, destination)
            copied += 1
    return copied


def migrate_into_data_root():
    """Pull data from legacy locations into :func:`data_root`.

    Runs once per app start (cheap no-op afterwards) and never overwrites an
    existing target file.  Returns a list of human-readable report lines.
    """
    report = []
    target = data_root()
    target.mkdir(parents=True, exist_ok=True)

    for legacy in legacy_candidates():
        if not legacy.is_dir():
            continue
        copied = 0
        for name in _FILE_ITEMS:
            source_file = legacy / name
            destination = target / name
            if source_file.is_file() and not destination.exists():
                shutil.copy2(source_file, destination)
                copied += 1
                report.append(f'migrated file {name} from {legacy}')
        for name in _FOLDER_ITEMS:
            source_folder = legacy / name
            if source_folder.is_dir():
                destination = target / name
                destination.mkdir(exist_ok=True)
                copied += migrate_folder(source_folder, destination)
                if copied:
                    report.append(f'migrated folder {name}/ from {legacy}')
        if copied == 0:
            report.append(f'legacy location {legacy} present, nothing to copy')
    return report

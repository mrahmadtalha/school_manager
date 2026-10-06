"""Release tooling (Phase 7): version sourcing, manifests, checksums.

Every assemble test runs against throwaway folders (never the real
``build/installer`` or ``build/release``), so running the suite can never
corrupt a real release, and the tests stay green after a version bump.
"""

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

import make_release  # noqa: E402
from build_installer import OUTPUT_DIR, read_app_version  # noqa: E402


def test_version_is_sourced_from_the_iss_file():
    version = read_app_version()
    assert version  # non-empty, e.g. '1.0.0'
    assert f'v{version}'.startswith('v')
    text = (PROJECT_ROOT / 'installer' / 'SchoolManager.iss').read_text(
        encoding='utf-8')
    assert f'#define MyAppVersion "{version}"' in text


def test_sha256_of_a_known_file():
    sample = PROJECT_ROOT / 'requirements.txt'
    digest = make_release.sha256_of(sample)
    assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)


def test_assemble_release_builds_manifest_in_isolation(monkeypatch):
    """The manifest is built from a fake installer in THROWAWAY folders."""
    scratch = Path(tempfile.mkdtemp(prefix='p7-release-'))
    try:
        import build_installer

        monkeypatch.setattr(build_installer, 'OUTPUT_DIR', scratch / 'installer')
        monkeypatch.setattr(make_release, 'RELEASE_ROOT', scratch / 'release')
        monkeypatch.setattr(make_release, 'BUILD_DIR', scratch / 'build')

        version = read_app_version()
        fake_output = scratch / 'installer'
        fake_output.mkdir(parents=True)
        fake_installer = fake_output / f'SchoolManager_Setup_v{version}.exe'
        fake_installer.write_bytes(b'MZ fake installer')

        release_dir = make_release.assemble_release(version)

        sums = (release_dir / 'SHA256SUMS.txt').read_text(encoding='utf-8')
        assert f'SchoolManager_Setup_v{version}.exe' in sums
        expected = hashlib.sha256(fake_installer.read_bytes()).hexdigest()
        assert expected in sums
        info = (release_dir / 'RELEASE-INFO.txt').read_text(encoding='utf-8')
        assert 'Ahmi software firm' in info
        assert f'School Manager release v{version}' in info
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

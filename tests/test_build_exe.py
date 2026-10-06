"""Phase 5: PyInstaller bundling rules and launcher dual-mode helpers.

The spec is generated (never hand-edited), so its content is pinned by tests:
the PyArmor runtime and every app module must be hidden imports (PyInstaller
cannot see imports inside encrypted module bodies), templates/static must be
bundled as data, and the exe must be windowed.

All product-tree checks run against an ISOLATED copy of ``app/`` so the suite
is green even on a clean checkout (no ``build/`` yet) and never depends on a
previous build.
"""

import importlib.machinery
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def product_root():
    """A throwaway product tree: plain app copy, no build output needed.

    ``tempfile.mkdtemp`` rather than pytest's ``tmp_path`` so the tests run
    on machines where the pytest numbered-temp root is not writable.
    """
    root = Path(tempfile.mkdtemp(prefix='p5-product-root-')) / 'product'
    try:
        shutil.copytree(PROJECT_ROOT / 'app', root / 'app',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def _load_launcher():
    # .pyw is not a registered source suffix on every platform, so the loader
    # is named explicitly instead of being derived from the file extension.
    path = PROJECT_ROOT / 'school_manager.pyw'
    loader = importlib.machinery.SourceFileLoader(
        'school_manager_launcher', str(path))
    spec = importlib.util.spec_from_loader('school_manager_launcher', loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _load_build_exe():
    spec = importlib.util.spec_from_file_location(
        'build_exe_module', PROJECT_ROOT / 'tools' / 'build_exe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_app_modules_includes_everything_and_runtime(product_root):
    build_exe = _load_build_exe()
    modules = build_exe.collect_app_modules(product_root)
    assert 'app' in modules
    assert 'app.services.licensing' in modules
    assert 'app.license_guard' in modules
    assert 'app.graceful_exit' in modules
    assert 'pyarmor_runtime_000000' in modules
    assert len([m for m in modules if m.startswith('app')]) >= 70


def test_collect_datas_bundles_templates_and_static(product_root):
    build_exe = _load_build_exe()
    datas = dict(build_exe.collect_datas(product_root))
    assert 'app/templates' in datas.values()
    assert 'app/static' in datas.values()
    for source, _ in build_exe.collect_datas(product_root):
        assert Path(source).is_dir()


def test_generated_spec_pins_the_essentials(product_root):
    build_exe = _load_build_exe()
    spec = build_exe.generate_spec(product_root)

    assert "'pyarmor_runtime_000000'" in spec          # runtime as hidden import
    assert "'app.services.licensing'" in spec          # obfuscated app modules
    assert "'flask'" in spec and "'waitress'" in spec  # encrypted third-party imports
    assert "'app/templates'" in spec and "'app/static'" in spec
    assert "console=False" in spec                     # windowed desktop exe
    assert "name='SchoolManager'" in spec
    assert "school_manager.pyw" in spec                # launcher is the entry


def test_launcher_finds_a_chromium_browser_or_none():
    launcher = _load_launcher()
    found = launcher.find_chromium_browser()
    # On this machine Edge/Chrome normally exists; either way it must be a
    # valid path or None - never a stale guess.
    if found is not None:
        assert Path(found).is_file(), found


def test_launcher_flags_parse():
    launcher = _load_launcher()
    args = launcher.build_arg_parser().parse_args([])
    assert args.browser is False and args.selftest is False
    args = launcher.build_arg_parser().parse_args(['--browser'])
    assert args.browser is True and args.selftest is False
    args = launcher.build_arg_parser().parse_args(['--selftest'])
    assert args.browser is False and args.selftest is True


def test_launcher_log_file_name_is_data_folder_relative():
    launcher = _load_launcher()
    assert launcher.LOG_FILE_NAME == 'school_manager.log'


def test_verify_never_deletes_an_existing_data_folder(monkeypatch):
    """Regression: the data-folder check must never wipe a real install."""
    build_exe = _load_build_exe()

    fake_localappdata = Path(tempfile.mkdtemp(prefix='p5-localappdata-'))
    try:
        real_data = fake_localappdata / 'SchoolManager'
        real_data.mkdir(parents=True)
        sentinel = real_data / 'school.db'
        sentinel.write_bytes(b'real school data')
        monkeypatch.setenv('LOCALAPPDATA', str(fake_localappdata))

        def _must_not_run(*args, **kwargs):
            raise AssertionError('selftest must not run when data folder exists')

        monkeypatch.setattr(build_exe, 'run_selftest', _must_not_run)
        fake_exe = Path(tempfile.mkdtemp(prefix='p5-fakeexe-')) / 'SchoolManager.exe'
        fake_exe.write_bytes(b'MZ')

        assert build_exe.verify_default_data_folder(fake_exe) is True
        assert sentinel.read_bytes() == b'real school data'
        assert real_data.is_dir()
    finally:
        shutil.rmtree(fake_localappdata, ignore_errors=True)
        shutil.rmtree(fake_exe.parent, ignore_errors=True)

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import runtime_paths as paths

DEPLOYED_F9_ROOT = paths.CE_F9_ROOT


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, '_profile', None)
    # A synthetic CE host must not create /storage on the developer/CI machine.
    # Keep the real ABI literal covered separately; exercise its filesystem
    # lifecycle in a distinct legacy-root fixture, not in the selected profile.
    monkeypatch.setattr(paths, 'CE_F9_ROOT', str(tmp_path / 'ce-f9-native/subtitle-browser'))
    real_mkdir = Path.mkdir
    def bounded_mkdir(path, *args, **kwargs):
        absolute = path.absolute()
        assert absolute == tmp_path or tmp_path in absolute.parents, 'Test escaped its filesystem fixture'
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', bounded_mkdir)


def test_deployed_f9_abi_literal_is_not_changed_by_fixture():
    assert DEPLOYED_F9_ROOT == '/storage/.kodi/userdata/addon_data/plugin.video.jacktook/subtitle-browser'


def test_current_native_root_and_other_paths_stay_in_selected_profile(tmp_path):
    paths.configure(tmp_path)
    assert os.fspath(paths.ProfilePath('subtitle-browser')) == str(tmp_path / 'subtitle-browser')
    assert os.fspath(paths.ProfilePath('assrt-token')) == str(tmp_path / 'assrt-token')
    assert json.loads((tmp_path / paths.CONFIG).read_text()) == {'schema': 1, 'subtitle_abi': 'profile'}


def test_paths_survive_fresh_kodi_interpreter_without_process_globals(tmp_path, monkeypatch):
    paths.configure(tmp_path)
    spec = importlib.util.spec_from_file_location('fresh_paths', Path(paths.__file__))
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', types.SimpleNamespace(translatePath=lambda _: str(tmp_path)))
    assert fresh._profile is None
    assert os.fspath(fresh.ProfilePath('subtitle-browser')) == str(tmp_path / 'subtitle-browser')
    assert os.fspath(fresh.ProfilePath('preparation')) == str(tmp_path / 'preparation')


def test_only_old_ce_abi_selects_exact_legacy_subtitle_root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, '_coreelec', lambda: True)
    paths.configure(tmp_path, subtitle_root=paths.CE_F9_ROOT)
    assert os.fspath(paths.ProfilePath('subtitle-browser')) == paths.CE_F9_ROOT
    assert os.fspath(paths.ProfilePath('preparation')) == str(tmp_path / 'preparation')
    # Existing importer/exporter objects are lazy and agree with the native actor.
    from bobbi_core.subtitle_export import NATIVE_ROOT
    from bobbi_core.subtitle_candidates import ROOT as CANDIDATE_ROOT
    assert os.fspath(NATIVE_ROOT) == os.fspath(CANDIDATE_ROOT) == paths.CE_F9_ROOT
    # An upgrade to a current native host explicitly resets the selector.
    paths.configure(tmp_path)
    assert os.fspath(NATIVE_ROOT) == str(tmp_path / 'subtitle-browser')


@pytest.mark.parametrize('suffix', ['elsewhere', 'subtitle-browser/other', '../other'])
def test_arbitrary_roots_rejected(tmp_path, suffix):
    with pytest.raises(ValueError, match='SUBTITLE_ROOT_NOT_ALLOWED'):
        paths.configure(tmp_path, subtitle_root=str(tmp_path / suffix))
    assert not (tmp_path / paths.CONFIG).exists()


def test_legacy_root_rejected_on_non_ce_even_if_marker_was_copied(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, '_coreelec', lambda: False)
    with pytest.raises(ValueError, match='SUBTITLE_ROOT_NOT_ALLOWED'):
        paths.configure(tmp_path, subtitle_root=paths.CE_F9_ROOT)
    paths.configure(tmp_path)
    (tmp_path / paths.CONFIG).write_text(json.dumps(dict(schema=1, subtitle_abi='ce-f9',
                                                       native_sha256=paths.CE_F9_SHA256)))
    with pytest.raises(ValueError, match='RUNTIME_PATH_CONFIG_INVALID'):
        os.fspath(paths.ProfilePath('subtitle-browser'))


@pytest.mark.parametrize('marker', [dict(schema=True, subtitle_abi='profile'),
    dict(schema=1, subtitle_abi='profile', root='/tmp/anything'),
    dict(schema=1, subtitle_abi='ce-f9', native_sha256='0' * 64), ['profile']])
def test_invalid_marker_never_expands_root(tmp_path, marker):
    paths.configure(tmp_path)
    (tmp_path / paths.CONFIG).write_text(json.dumps(marker))
    with pytest.raises(ValueError, match='RUNTIME_PATH_CONFIG_INVALID'):
        os.fspath(paths.ProfilePath('subtitle-browser'))


def test_symlink_root_rejected_without_following_it(tmp_path, monkeypatch):
    root = tmp_path / 'subtitle-browser'
    real = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == root or real(path))
    with pytest.raises(ValueError, match='RUNTIME_PATH_SYMLINK'):
        paths.configure(tmp_path)


def test_legacy_probe_requires_real_native_methods_ce_and_known_binary(tmp_path, monkeypatch):
    binary = tmp_path / 'kodi.bin'
    binary.write_bytes(b'X' * (1024 * 1024))
    monkeypatch.setattr(paths, '_coreelec', lambda: True)
    monkeypatch.setattr(paths, 'CE_F9_SHA256', hashlib.sha256(binary.read_bytes()).hexdigest())
    assert paths.native_subtitle_root({'native_contract_available': False}, binary) is None
    assert paths.native_subtitle_root({'native_contract_available': True}, binary) == paths.CE_F9_ROOT
    binary.write_bytes(b'Y' * (1024 * 1024))
    assert paths.native_subtitle_root({'native_contract_available': True}, binary) is None
    monkeypatch.setattr(paths, '_coreelec', lambda: False)
    assert paths.native_subtitle_root({'native_contract_available': True}, binary) is None


def test_default_ce_probe_reads_proc_object_not_sys_executable_or_resolved_target(tmp_path, monkeypatch):
    running, external = tmp_path / 'running-kodi.bin', tmp_path / 'external-kodi.bin'
    running.write_bytes(b'R' * (1024 * 1024))
    external.write_bytes(b'E' * (1024 * 1024))
    expected = hashlib.sha256(running.read_bytes()).hexdigest()
    monkeypatch.setattr(paths, '_coreelec', lambda: True)
    monkeypatch.setattr(paths, 'CE_F9_SHA256', expected)
    monkeypatch.setattr(sys, 'executable', str(external))
    opened = []
    real_open = Path.open
    def open_object(path, *args, **kwargs):
        opened.append(path)
        return real_open(running if path == Path('/proc/self/exe') else path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', open_object)
    monkeypatch.setattr(Path, 'resolve', lambda *a, **kw: pytest.fail('Do not resolve kernel executable references'))
    assert paths.native_subtitle_root({'native_contract_available': True}) == paths.CE_F9_ROOT
    assert opened == [Path('/proc/self/exe')]
    assert paths.native_executable_sha256(external) != expected


def test_executable_probe_uses_open_fd_and_rejects_missing_or_unbounded_files(tmp_path):
    binary = tmp_path / 'kodi.bin'
    assert paths.native_executable_sha256(binary) is None
    binary.write_bytes(b'too small')
    assert paths.native_executable_sha256(binary) is None
    binary.write_bytes(b'F' * (1024 * 1024))
    assert paths.native_executable_sha256(binary) == hashlib.sha256(binary.read_bytes()).hexdigest()


def test_reviewed_native_descendant_records_actual_binary_pin(tmp_path, monkeypatch):
    digest = 'a' * 64
    monkeypatch.setattr(paths, '_coreelec', lambda: True)
    monkeypatch.setattr(paths, 'CE_F9_REVIEWED_PATCHES', frozenset((digest,)))
    monkeypatch.setattr(paths, 'native_executable_sha256', lambda _: digest)
    abi = paths.native_subtitle_abi({'native_contract_available': True})
    assert abi == dict(root=paths.CE_F9_ROOT, sha256=digest)
    paths.configure(tmp_path, subtitle_root=abi['root'], native_sha256=abi['sha256'])
    assert json.loads((tmp_path / paths.CONFIG).read_text())['native_sha256'] == digest
    assert os.fspath(paths.ProfilePath('subtitle-browser')) == paths.CE_F9_ROOT
    assert paths.known_ce_native(paths.CE_F9_SHA256)
    assert not paths.known_ce_native('b' * 64)


def test_unreviewed_descendant_cannot_select_old_abi(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, '_coreelec', lambda: True)
    with pytest.raises(ValueError, match='NATIVE_ABI_NOT_REVIEWED'):
        paths.configure(tmp_path, subtitle_root=paths.CE_F9_ROOT, native_sha256='c' * 64)
    assert not (tmp_path / paths.CONFIG).exists()

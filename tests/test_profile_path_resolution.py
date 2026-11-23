"""Live profile observations canonicalize once, without weakening revocation."""
from collections import Counter
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import paths


@pytest.fixture
def mapping(tmp_path, monkeypatch):
    roots = {addon: tmp_path / 'A' / addon for addon in paths.ProfileBinding.ADDONS}
    for root in roots.values():
        root.mkdir(parents=True)
    calls = []
    def translate(special):
        addon = special.rsplit('/', 1)[-1]
        calls.append(addon)
        return str(roots[addon])
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=translate))
    return SimpleNamespace(roots=roots, calls=calls, translate=translate)


@pytest.fixture
def measure(monkeypatch):
    def run(operation):
        counts = Counter()
        def counted(name, function):
            def call(*args, **kwargs):
                counts[name] += 1
                return function(*args, **kwargs)
            return call
        with monkeypatch.context() as scope:
            scope.setattr(Path, 'resolve', counted('resolve', Path.resolve))
            for name in ('stat', 'lstat', 'readlink'):
                scope.setattr(os, name, counted(name, getattr(os, name)))
            # Windows resolves through this native OS boundary, not lstat.
            if hasattr(os.path, '_getfinalpathname'):
                scope.setattr(os.path, '_getfinalpathname',
                    counted('finalpath', os.path._getfinalpathname))
            result = operation()
        return result, counts
    return run


def test_default_capture_and_live_checks_halve_real_resolution_work(mapping, measure, record_testsuite_property):
    binding, capture = measure(paths.ProfileBinding)
    assert mapping.calls == list(paths.ProfileBinding.ADDONS) * 2
    assert capture['resolve'] == 4
    # Explicitly supplying the public canonical resolver reproduces the old
    # default's two real resolve passes; no filesystem operation is stubbed.
    legacy, legacy_capture = measure(lambda: paths.ProfileBinding(paths.profile_root))
    assert binding._roots == legacy._roots
    assert legacy_capture['resolve'] == 8
    for name, owner in (('single_pass', binding), ('legacy_double_pass', legacy)):
        mapping.calls.clear()
        result, counts = measure(lambda: [owner.is_current() for _ in range(3)])
        assert result == [True] * 3
        assert mapping.calls == list(paths.ProfileBinding.ADDONS) * 3
        record_testsuite_property(name, json.dumps(dict(counts), sort_keys=True))
        if name == 'single_pass':
            single = counts
        else:
            double = counts
    assert single['resolve'] == 6 and double['resolve'] == 12
    # Count calls at real OS filesystem boundaries as well as Path.resolve.
    assert 0 < sum(single[key] for key in single if key != 'resolve') < sum(
        double[key] for key in double if key != 'resolve')
    if single['stat']:
        assert double['stat'] == single['stat'] * 2


def test_public_profile_root_stays_canonical_and_read_only(mapping, tmp_path, measure):
    addon = paths.ProfileBinding.ADDONS[0]
    parent = tmp_path / 'existing'
    parent.mkdir()
    mapping.roots[addon] = parent / '..' / 'not-created' / addon
    result, counts = measure(paths.profile_root)
    assert result == tmp_path / 'not-created' / addon
    assert counts['resolve'] == 1 and not (tmp_path / 'not-created').exists()
    binding = paths.ProfileBinding()
    assert binding.root() == result and binding.is_current()
    assert not (tmp_path / 'not-created').exists()


@pytest.mark.parametrize('addon', paths.ProfileBinding.ADDONS)
def test_default_binding_rechecks_each_mapping_and_never_revives(mapping, tmp_path, addon):
    binding = paths.ProfileBinding()
    first = mapping.roots[addon]
    mapping.roots[addon] = tmp_path / 'B' / addon
    assert not binding.is_current()
    mapping.roots[addon] = first
    assert not binding.is_current()
    with pytest.raises(ValueError, match='^PROFILE_CHANGED$'):
        binding.require_current()
    assert paths.ProfileBinding().is_current()


@pytest.mark.parametrize('failure', ['relative', 'unresolved', 'error'])
def test_default_mapping_failure_permanently_revokes(mapping, monkeypatch, failure):
    binding = paths.ProfileBinding()
    def broken(special):
        if failure == 'error':
            raise OSError('Fixture mapping unavailable')
        return 'relative/path' if failure == 'relative' else special
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=broken))
    assert not binding.is_current()
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=mapping.translate))
    assert not binding.is_current()


def symlink(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip('Real directory symlink unavailable on this host: ' + str(error))


@pytest.mark.parametrize('addon', paths.ProfileBinding.ADDONS)
@pytest.mark.parametrize('injected', [False, True])
def test_unchanged_mapping_observes_real_symlink_retarget_and_sticky_aba(mapping, tmp_path, addon, injected):
    first = mapping.roots[addon]
    second = tmp_path / 'B' / addon
    second.mkdir(parents=True)
    link = tmp_path / 'active-root'
    symlink(link, first)
    mapping.roots[addon] = link
    resolver = (lambda value: mapping.roots[value]) if injected else None
    binding = paths.ProfileBinding(resolver)
    assert binding.root(addon) == first
    assert paths.profile_root(addon) == first
    assert binding.is_current()
    link.unlink()
    symlink(link, second)
    assert mapping.roots[addon] == link  # Translation text did not change.
    assert paths.profile_root(addon) == second
    assert not binding.is_current()
    link.unlink()
    symlink(link, first)
    assert not binding.is_current()
    assert paths.ProfileBinding(resolver).is_current()


def test_capture_spanning_real_symlink_change_is_rejected(mapping, tmp_path, monkeypatch):
    addon = paths.ProfileBinding.ADDONS[0]
    first = mapping.roots[addon]
    second = tmp_path / 'B' / addon
    second.mkdir(parents=True)
    link = tmp_path / 'active-root'
    symlink(link, first)
    mapping.roots[addon] = link
    def translate(special):
        if len(mapping.calls) == 2:
            link.unlink()
            symlink(link, second)
        return mapping.translate(special)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=translate))
    with pytest.raises(ValueError, match='^PROFILE_CHANGED$'):
        paths.ProfileBinding()


def test_different_live_alias_of_same_canonical_root_does_not_false_revoke(mapping, tmp_path):
    addon = paths.ProfileBinding.ADDONS[0]
    target = mapping.roots[addon]
    first, second = tmp_path / 'first-alias', tmp_path / 'second-alias'
    symlink(first, target)
    symlink(second, target)
    mapping.roots[addon] = first
    binding = paths.ProfileBinding()
    mapping.roots[addon] = second
    assert binding.is_current() and binding.root() == target


def test_real_symlink_resolution_failure_permanently_revokes(mapping, tmp_path):
    addon = paths.ProfileBinding.ADDONS[0]
    target = mapping.roots[addon]
    link = tmp_path / 'active-root'
    symlink(link, target)
    mapping.roots[addon] = link
    binding = paths.ProfileBinding()
    link.unlink()
    symlink(link, link)
    assert not binding.is_current()
    link.unlink()
    symlink(link, target)
    assert not binding.is_current()

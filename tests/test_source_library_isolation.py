"""Cross-module ownership controls; core tests need no Kodi module stubs."""
import builtins
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_core import sharelib_api, sharelib_catalog, source_library
from bobbi_platform.paths import ProfileBinding
from bobbi_platform import source_libraries, runtime


def binding(root, selected):
    return ProfileBinding(lambda addon: root / selected[0] / addon)


def test_core_store_client_and_catalog_search_do_not_import_kodi_or_platform(tmp_path, monkeypatch):
    original = builtins.__import__

    def imported(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Core reached back into environment: ' + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', imported)
    store = source_library.Store(tmp_path)
    source = store.save('https://catalog.example.invalid')
    client = source.client(opener=object())
    assert client.root == source.root and client.base == source.endpoint
    assert source.profile == tmp_path and source.settings == tmp_path / 'source-library.json'
    result = sharelib_catalog.search(dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Movie']),
        time.monotonic() + 2, lambda: False, state=source.root,
        client=SimpleNamespace(get=lambda *args: dict(items=[])))
    assert not result and result.completion.succeeded == 1


def test_profile_a_b_a_never_revives_source_client_or_old_store(tmp_path):
    selected = ['a']
    store_a = source_libraries.capture(binding(tmp_path, selected))
    source_a = store_a.save('https://catalog.example.invalid')
    client_a = source_a.client(opener=object())
    assert not client_a.cancelled()
    selected[0] = 'b'
    store_b = source_libraries.capture(binding(tmp_path, selected))
    source_b = store_b.save(source_a.endpoint)
    assert source_a.root != source_b.root
    assert client_a.cancelled()
    selected[0] = 'a'
    assert client_a.cancelled() and store_a.current() is None
    with pytest.raises(source_library.SourceLibraryError, match='SOURCE_CHANGED'):
        store_a.save('https://replacement.example.invalid')
    with pytest.raises(sharelib_api.ShareLibError, match='SOURCE_CHANGED'):
        source_a.client(opener=object())
    fresh_a = source_libraries.capture(binding(tmp_path, selected)).current()
    assert fresh_a.endpoint == source_a.endpoint and fresh_a.generation == source_a.generation
    assert store_b.current() is None


def test_remove_readd_revokes_even_previously_checked_generation(tmp_path):
    store = source_library.Store(tmp_path)
    before = store.save('https://catalog.example.invalid')
    client = before.client(opener=object())
    assert not client.cancelled()
    store.remove()
    after = store.save(before.endpoint)
    assert before.root == after.root and before.generation != after.generation
    assert client.cancelled()
    assert not after.client(opener=object()).cancelled()


def test_legacy_global_endpoint_and_relative_or_missing_state_never_enable_client(tmp_path, monkeypatch):
    monkeypatch.setattr(sharelib_api, 'BASE', 'https://ignored.example.invalid')
    monkeypatch.setattr(sharelib_api, 'build_opener', lambda *args: pytest.fail('No transport should be built'))
    with pytest.raises(sharelib_api.ShareLibError, match='CATALOGUE_DISABLED'):
        sharelib_api.Client(state=tmp_path)
    for state in (None, Path('relative-cache')):
        with pytest.raises(sharelib_api.ShareLibError, match='STATE_REQUIRED'):
            sharelib_api.Client(state=state, endpoint='https://catalog.example.invalid')
    with pytest.raises(ValueError, match='Absolute source-library profile required'):
        source_library.Store('relative-profile')


def test_reader_is_profile_bound_read_only_and_a_b_a_irrevocable(tmp_path):
    selected, calls = ['a'], []
    owner = binding(tmp_path, selected)
    reader = source_libraries.ShareReader(owner,
        lambda action, body, timeout: calls.append((action, body, timeout)) or {})
    reader.account_scope(timeout=.1)
    reader.known_failures({'account': {}, 'proofs': []}, timeout=.1)
    assert [row[0] for row in calls] == ['account_status', 'share_known_failures']
    selected[0] = 'b'
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        reader.account_scope(timeout=.1)
    selected[0] = 'a'
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        reader.known_failures({}, timeout=.1)
    assert len(calls) == 2


def test_reader_cannot_adopt_a_restarted_host_or_recover_failed_capture(tmp_path, monkeypatch):
    selected = ['a']
    owner = binding(tmp_path, selected)
    path = owner.root() / 'runtime.json'
    assert source_libraries.capture_reader(owner) is None
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(port=8081, token='a' * 64)))
    reader = source_libraries.capture_reader(owner)
    assert reader is not None
    path.write_text(json.dumps(dict(port=8081, token='b' * 64)))
    monkeypatch.setattr(runtime, 'build_opener', lambda *args: pytest.fail('Must not contact replacement Host'))
    with pytest.raises(OSError, match='RUNTIME_INSTANCE_CHANGED'):
        reader.account_scope(timeout=.1)
    path.write_text(json.dumps(dict(port=8081, token='a' * 64)))
    with pytest.raises(OSError, match='RUNTIME_INSTANCE_CHANGED'):
        reader.account_scope(timeout=.1)


def test_queued_provider_uses_captured_source_and_never_recaptures_after_revocation(tmp_path, monkeypatch):
    path = ROOT / 'addons/plugin.video.bobbi/lib/clients/sharelib_provider.py'
    spec = importlib.util.spec_from_file_location('isolated_sharelib_provider', path)
    provider = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provider)
    store = source_library.Store(tmp_path)
    before = store.save('https://catalog.example.invalid')
    check = source_library.cancellation(before)
    check.source, check.share_reader = before, None
    assert not check()
    store.remove()
    store.save(before.endpoint)
    monkeypatch.setattr(provider, '_query_cancelled', lambda *args: pytest.fail('Queued work must not recapture'))
    monkeypatch.setattr(provider, 'enabled', lambda: pytest.fail('Queued work must not inspect new profile'))
    result = provider.find_sources(dict(tmdb_id=101), 'movies', None, None, 2024,
        ['Audit Movie'], None, time.monotonic() + 2, lambda: False, source_check=check)
    assert not result and result.completion.skipped == 1


def test_document_probe_cancellation_on_profile_switch_keeps_old_endpoint(tmp_path, monkeypatch):
    active = [True]
    store = source_library.Store(tmp_path, active=lambda: active[0])
    before = store.save('https://original.example.invalid')

    def reply(*args, **kwargs):
        active[0] = False
        return dict(items=[])

    monkeypatch.setattr(sharelib_api.Client, 'get', reply)
    with pytest.raises(sharelib_api.ShareLibError, match='CANCELLED'):
        store.check('https://candidate.example.invalid', time.monotonic() + 2)
    active[0] = True
    assert store.current() is None
    assert source_library.Store(tmp_path).current().generation == before.generation

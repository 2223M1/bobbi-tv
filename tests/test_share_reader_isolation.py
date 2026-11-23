"""Share presentation only consumes captured readers, never global account IO."""
import builtins
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.catalog/lib'))
from bobbi_catalog import catalog as qq
from bobbi_core import share_failure as failure
from bobbi_core.source_list_session import SourceListSession
from bobbi_platform.paths import ProfileBinding
from bobbi_platform.source_libraries import ShareReader, CatalogContext


SCOPE = dict(account_id='115:fixture', epoch=3, authenticated=True)
IDENTITY = dict(locator='am6bqqdocs://A1/123', guid='qqdocs:A1:123',
                title='Audit Fixture.2024.1080p.mkv', size=1024, media='movies:101:0:0')
SPEC = dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Fixture'], media_key=IDENTITY['media'])


def card():
    return SimpleNamespace(url=IDENTITY['locator'], guid=IDENTITY['guid'], title=IDENTITY['title'],
        size=IDENTITY['size'], type='Direct', indexer='115', verifiedShareFile=False,
        shareFailure='share_revoked', shareState=failure.resolution_state(IDENTITY, SCOPE, 'share_revoked', 1))


def test_missing_reader_never_imports_environment_or_clears_observed_failure(monkeypatch):
    original = builtins.__import__
    def imported(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Share rules queried a global environment: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', imported)
    session = SourceListSession({}, lambda rows: rows)
    row = card()
    session.publish(session.epoch, '115', [row])
    before = session.revision
    assert failure.account_scope(include_signed_out=True) is None
    session.status()
    assert session.revision == before
    assert session.entries[session.key(row)].shareFailure == 'share_revoked'
    assert failure.read_failure(row, dict(_account=SCOPE), {}) is None


def test_profile_change_or_host_unavailability_cannot_clear_existing_failure(tmp_path):
    chosen, offline, calls = ['a'], [False], []
    binding = ProfileBinding(lambda addon: tmp_path / chosen[0] / addon)
    def read(action, body, timeout):
        calls.append(action)
        if offline[0]:
            raise OSError('fixture unavailable')
        return SCOPE
    reader = ShareReader(binding, read)
    session = SourceListSession({}, lambda rows: rows, share_reader=reader)
    row = card()
    session.publish(session.epoch, '115', [row])
    session.status()
    for profile, unavailable in [('a', True), ('b', False), ('a', False)]:
        chosen[0], offline[0] = profile, unavailable
        session.share_scope_polled = 0
        session.status()
        assert session.entries[session.key(row)].shareFailure == 'share_revoked'
    assert calls == ['account_status', 'account_status']


def test_only_explicit_new_epoch_reader_can_clear_account_annotation():
    current = [SCOPE]
    reader = SimpleNamespace(account_scope=lambda timeout: current[0])
    session = SourceListSession({}, lambda rows: rows, share_reader=reader)
    row = card()
    session.publish(session.epoch, '115', [row])
    session.status()
    current[0] = dict(SCOPE, epoch=4, account_id='115:other')
    session.share_scope_polled = 0
    session.status()
    assert session.entries[session.key(row)].shareFailure == ''
    session.publish(session.epoch, 'late-old-account', [row])
    assert session.entries[session.key(row)].shareFailure == ''


def test_qq_explicit_cache_is_required_before_any_credential_factory_or_network(tmp_path, monkeypatch):
    factory = lambda: pytest.fail('Missing cache must not read credentials')
    monkeypatch.setattr(qq, 'Client', factory)
    for path in (None, Path('relative.sqlite')):
        with pytest.raises(ValueError, match='CATALOG_CACHE_REQUIRED'):
            qq.search(SPEC, time.monotonic() + 1, None, cache_path=path, client_factory=factory)
        with pytest.raises(ValueError, match='CATALOG_CACHE_REQUIRED'):
            qq.resolve(**IDENTITY, cache_path=path)
    assert not list(tmp_path.iterdir())


def test_qq_no_matching_public_route_does_not_read_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(qq, 'routes', lambda *args, **kwargs: [])
    assert qq.search(SPEC, time.monotonic() + 1, None, cache_path=tmp_path / 'cache.sqlite',
        client_factory=lambda: pytest.fail('No route needs no credentials')) == []
    assert not list(tmp_path.iterdir())


def test_real_qq_cached_failure_uses_supplied_reader_without_platform_lookup(tmp_path, monkeypatch):
    catalogue, cache_path = tmp_path / 'public.sqlite', tmp_path / 'cache.sqlite'
    with closing(sqlite3.connect(catalogue)) as db:
        db.executescript('CREATE TABLE entries(id INTEGER,text TEXT,norm TEXT,group_key TEXT,origin TEXT);'
            'CREATE TABLE terms(entry_id INTEGER,term TEXT); CREATE TABLE term_counts(term TEXT,n INTEGER);'
            'CREATE TABLE shares(cell TEXT,group_key TEXT,code TEXT,password TEXT);')
        db.execute('INSERT INTO entries VALUES(1,?,?,?,?)',
                   ('Audit Fixture 2024', qq.normalized('Audit Fixture 2024'), 'g', 'fixture'))
        for term in qq.terms('Audit Fixture'):
            db.execute('INSERT INTO terms VALUES(1,?)', (term,))
            db.execute('INSERT INTO term_counts VALUES(?,1)', (term,))
        db.execute("INSERT INTO shares VALUES('A1','g','sfixture','')")
        db.commit()
    calls = []
    client = SimpleNamespace(search=lambda *args: calls.append('remote') or
        [dict(fid='123', name=IDENTITY['title'], size=1024)])
    reader = SimpleNamespace(account_scope=lambda timeout: SCOPE)
    original = builtins.__import__
    def imported(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Catalogue queried a global environment: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', imported)
    def search(reader):
        return qq.search(SPEC, time.monotonic() + 2, None, catalogue=catalogue,
                         cache_path=cache_path, client=client, share_reader=reader)
    assert len(search(reader)) == 1
    with closing(qq.Cache(cache_path)) as cache:
        failure.record_result(cache.db, IDENTITY, SCOPE, time.time(), 'share_revoked')
    assert search(reader)[0]['shareFailure'] == 'share_revoked'
    assert not search(None)[0].get('shareFailure')  # Unknown scope cannot expose another account's overlay.
    assert calls == ['remote']


def test_diagnostic_query_is_bound_and_cannot_recapture_after_profile_change(tmp_path):
    chosen, calls = ['a'], []
    binding = ProfileBinding(lambda addon: tmp_path / chosen[0] / addon)
    owner = dict(boot_id='a' * 32, epoch=1, request_id='b' * 32, file_identity='exact',
                 native_instance='fixture', url_sha256='c' * 64)
    item = dict(_account=SCOPE, ids={'tmdb_id': 101}, mode='movies')
    def read(action, body, timeout):
        calls.append((action, timeout))
        return dict(matched=True, account=SCOPE, owner=owner, tuple_sha256=failure.tuple_hash(IDENTITY),
            failure=dict(code='share_revoked', http_status=403, api_code=4100010, invalidation_failed=False))
    reader = ShareReader(binding, read)
    assert failure.read_failure(card(), item, owner, reader)['code'] == 'share_revoked'
    chosen[0] = 'b'
    assert failure.read_failure(card(), item, owner, reader) is None
    chosen[0] = 'a'
    assert failure.read_failure(card(), item, owner, reader) is None
    assert calls == [('share_failure', .3)]


def test_failed_or_revoked_catalog_capture_never_submits_against_new_profile(tmp_path, monkeypatch):
    path = ROOT / 'addons/plugin.video.bobbi/lib/clients/catalog_providers.py'
    spec = importlib.util.spec_from_file_location('isolated_catalog_submit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from bobbi_platform import source_libraries
    monkeypatch.setattr(source_libraries, 'capture_context', lambda: pytest.fail('No recapture allowed'))
    monkeypatch.setattr(module, '_adapter', lambda name: pytest.fail('No provider may start'))
    manager = SimpleNamespace(cancelled=lambda: False, deadline=time.monotonic() + 2,
                              submit_task=lambda *args, **kwargs: pytest.fail('No submit allowed'))
    chosen = ['a']
    binding = ProfileBinding(lambda addon: tmp_path / chosen[0] / addon)
    context = CatalogContext(binding, None, None, tmp_path / 'cache', tmp_path / 'credential')
    chosen[0] = 'b'
    assert not binding.is_current()
    chosen[0] = 'a'
    for captured in (None, context):
        module.submit_catalogs(manager, {}, 'movies', 0, 0, 2024, ['Fixture'], None, context=captured)

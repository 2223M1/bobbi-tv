"""Local catalog IO must not block picker construction or outlive its owner."""
from threading import Event, current_thread
from time import monotonic

import pytest

from test_ce2089_shared_search import shared


def build(shared, scoped='', jackgram=False, budget=30):
    return shared.search._create_source_search({}, 'Fixture', {'tmdb_id': 123},
        'tv', 'tv', {'season': 1, 'episode': 1}, False, scoped, 'default',
        'localized_first', 2020, jackgram, {}, [], budget=budget)


def join(pump):
    pump.thread.join(3)
    assert not pump.thread.is_alive()


def local_source():
    from lib.domain.torrent import TorrentStream
    return TorrentStream(title='Fixture S01E01 1080p', type='Direct',
        guid='mdsub:fixture', url='https://pan.mdsub.top/api/raw?path=fixture',
        catalogIdentity={'tmdb_id': '123', 'mode': 'tv', 'season': 1, 'episode': 1})


def test_construction_registers_local_providers_without_loading_them(shared, monkeypatch):
    from lib.clients import mdsub_provider, bobi_library
    calls = []
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a: calls.append('mdsub') or [])
    monkeypatch.setattr(bobi_library, 'load_index', lambda: calls.append('cloud') or {})
    session, pump = build(shared)
    try:
        assert calls == []
        assert {k: v['state'] for k, v in session.status()['providers'].items()} == {
            '漫迪 MDsub': 'PENDING', '115-local-index': 'PENDING'}
    finally:
        pump.cancel()


def test_local_load_runs_off_caller_and_late_result_after_close_is_rejected(shared, monkeypatch):
    from lib.clients import mdsub_provider, bobi_library
    started, release = Event(), Event()
    worker_names, cloud_calls = [], []
    def load(*args):
        worker_names.append(current_thread().name)
        started.set()
        assert release.wait(3)
        return [local_source()]
    # Build first so this test cannot hang on the old synchronous constructor.
    session, pump = build(shared)
    monkeypatch.setattr(mdsub_provider, 'find_sources', load)
    monkeypatch.setattr(bobi_library, 'load_index', lambda: cloud_calls.append(True) or {})
    pump.start()
    try:
        assert started.wait(1)
        assert worker_names == ['BobiSourceCoordinator']
        pump.cancel()
    finally:
        release.set()
        join(pump)
        pump.cancel()
    assert session.snapshot()['entries'] == []
    assert cloud_calls == []
    assert shared.calls == []
    assert session.status()['providers']['漫迪 MDsub']['state'] == 'CANCELLED'


def test_local_identity_rows_are_published_before_remote_setup_and_not_transformed(shared, monkeypatch):
    from lib.clients import mdsub_provider
    from lib.clients.tmdb.utils import utils as tmdb
    source = local_source()
    session, pump = build(shared)
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a: [source])
    observed = []
    def details(*args):
        observed.extend(session.snapshot()['entries'])
        return {}
    monkeypatch.setattr(tmdb, 'get_tmdb_media_details', details)
    pump.start()
    try:
        join(pump)
        assert len(observed) == 1
        key, row = observed[0]
        assert key == session.key(source)
        assert row.catalogIdentity == source.catalogIdentity
        assert row.url == source.url
        assert session.status()['providers']['漫迪 MDsub']['state'] == 'COMPLETE'
        assert not any(not value for value in shared.processed)
    finally:
        pump.cancel()


def test_deadline_during_local_load_does_not_publish_late_card_or_start_remote(shared, monkeypatch):
    from lib.clients import mdsub_provider, bobi_library
    session, pump = build(shared)
    clouds = []
    def load(*args):
        pump.deadline = monotonic() - 1
        return [local_source()]
    monkeypatch.setattr(mdsub_provider, 'find_sources', load)
    monkeypatch.setattr(bobi_library, 'load_index', lambda: clouds.append(True) or {})
    pump.start()
    try:
        join(pump)
        assert session.snapshot()['entries'] == []
        assert clouds == [] and shared.calls == []
        assert all(session.status()['providers'][key]['state'] == 'TIMEOUT'
                   for key in ('漫迪 MDsub', '115-local-index'))
    finally:
        pump.cancel()


@pytest.mark.parametrize('scoped,jackgram', [('plugin://fixture', False), ('', True)])
def test_restricted_search_does_not_register_or_read_local_catalogs(shared, monkeypatch, scoped, jackgram):
    from lib.clients import mdsub_provider, bobi_library
    def forbidden(*args):
        pytest.fail('Restricted search must not read local catalogues')
    monkeypatch.setattr(mdsub_provider, 'find_sources', forbidden)
    monkeypatch.setattr(bobi_library, 'load_index', forbidden)
    session, pump = build(shared, scoped, jackgram)
    try:
        assert '漫迪 MDsub' not in session.status()['providers']
        assert '115-local-index' not in session.status()['providers']
    finally:
        pump.cancel()


def test_retry_failed_network_provider_does_not_rescan_successful_local_catalogues(shared, monkeypatch):
    from lib.clients import mdsub_provider
    calls = []
    monkeypatch.setattr(mdsub_provider, 'find_sources', lambda *a: calls.append(True) or [local_source()])
    session, pump = build(shared)
    pump.start()
    try:
        join(pump)
        shared.failed[0] = False
        assert pump.retry_failed()
        join(pump)
        assert calls == [True]
        assert session.status()['providers']['漫迪 MDsub']['state'] == 'COMPLETE'
        assert shared.calls == ['Q1', 'Q2', 'Q2']
    finally:
        pump.cancel()

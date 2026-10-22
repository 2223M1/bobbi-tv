"""Real Session regression: transient cloud failure must not lose live BT proof."""
from concurrent.futures import Future
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.catalog_identity import Catalog
from bobbi_core.cd2 import CD2
from bobbi_core.preparation_host import Lease, Session
from bobbi_core import torrent_metadata
from test_accounts import logged_in


def intent(identifier='a' * 32):
    return dict(request_id=identifier, purpose='current', media=dict(
        tmdb_id=1, kind='movie', season=0, episode=0, anime=False,
        title='Fixture', release_title='Fixture.2025'), selected=dict(
        source_info_hash='b' * 40, torrent_file_id=1,
        torrent_path='Fixture.2025.mkv', torrent_file_bytes=1000))


@pytest.fixture
def offline_session(tmp_path, monkeypatch):
    accounts, scope = logged_in(tmp_path)
    token = tmp_path / 'token'
    token.write_text('fixture-token')
    key = tmp_path / 'key'
    key.write_text('fixture-key')
    config = dict(account='a' * 64, destination='/115open/fixture',
        cd2_endpoint='http://127.0.0.1:19798', torrserver_endpoint='http://127.0.0.1:8090',
        cd2_token_file=str(token), tmdb_api_key_file=str(key),
        ffprobe='not-executed', download_capability='GetDownloadUrlPath')
    reads, provider_calls, reports = [], [], []
    def unavailable(*args, **kwargs):
        provider_calls.append('rpc')
        raise ConnectionError('private-provider-detail-must-not-leak')
    monkeypatch.setattr(CD2, 'rpc', unavailable)
    def metadata(*args, **kwargs):
        reads.append('registered_metadata')
        return dict(hash='b' * 40, title='Fixture.2025',
                    file_stats=[dict(id=1, path='Fixture.2025.mkv', length=1000)])
    monkeypatch.setattr(torrent_metadata, 'registered_metadata', metadata)
    monkeypatch.setattr(Catalog, 'lookup', lambda self, media: dict(
        provider='tmdb', id=1, kind='movie', aliases=['Fixture'], year=2025,
        ambiguous=False, response_sha256='f' * 64, runtime_seconds=6000))
    session = Session(tmp_path, config, Lease(accounts, scope), lambda: True, reports.append)
    session.readiness.begin()
    session.readiness.complete(error=ConnectionError('offline'))
    monkeypatch.setattr(session.worker, 'next_action', lambda *args: pytest.fail('cloud lane must remain gated'))
    monkeypatch.setattr(session.direct_queue, 'next_action', lambda *args: pytest.fail('direct cloud lane must remain gated'))
    try:
        yield session, reads, provider_calls, accounts, scope, reports
    finally:
        session.close()


def complete_intent(session, body):
    session.dispatch('prepare', body)
    until = time.monotonic() + 1
    while time.monotonic() < until:
        session.next_work = 0
        session.tick()
        result = session.dispatch('status', {'request_id': body['request_id']})
        if result['state'] in ('accepted', 'failed'):
            return result
        time.sleep(.005)
    return result


@pytest.mark.parametrize('health', ['DEPENDENCY_UNAVAILABLE', 'ACCOUNT_MISMATCH'])
def test_offline_cloud_still_captures_valid_source_without_provider_mutation(offline_session, health):
    session, reads, provider_calls, _, _, _ = offline_session
    session.readiness.state = health
    result = complete_intent(session, intent())
    assert result['state'] == 'accepted'
    assert reads == ['registered_metadata'] and provider_calls == []
    assert session.metadata_cache.load('b' * 40)['file_stats'][0]['length'] == 1000
    assert session.queue.db.execute('SELECT state FROM tasks').fetchall()[0][0] == 'queued'
    assert session.dispatch('resolve', {})['reason'] == 'cloud_dependency_not_ready'
    assert not session.snapshot_path.exists()


def test_new_current_intent_can_use_proved_cache_after_live_torrent_retires(offline_session, monkeypatch):
    session, reads, _, _, _, _ = offline_session
    assert complete_intent(session, intent())['state'] == 'accepted'
    monkeypatch.setattr(torrent_metadata, 'registered_metadata',
                        lambda *a, **k: pytest.fail('retired torrent must not be re-added'))
    assert complete_intent(session, intent('c' * 32))['state'] == 'accepted'
    assert len(reads) == 1
    assert session.queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1


def test_wrong_exact_file_is_never_cached_or_enqueued(offline_session):
    session, _, provider_calls, _, _, _ = offline_session
    body = intent()
    body['selected']['torrent_file_bytes'] += 1
    result = complete_intent(session, body)
    assert result['state'] == 'failed'
    assert result['result']['stage'] == 'identity'
    assert session.metadata_cache.load('b' * 40) is None
    assert session.queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0
    assert provider_calls == []


def test_metadata_failure_has_fixed_stage_without_raw_exception(offline_session, monkeypatch):
    session, _, _, _, _, reports = offline_session
    def broken(*args, **kwargs):
        raise ValueError('private?token=never-log-this')
    monkeypatch.setattr(torrent_metadata, 'registered_metadata', broken)
    result = complete_intent(session, intent())
    assert result['state'] == 'failed'
    assert result['result'] == dict(error='ValueError', stage='metadata', reason='validation_failed')
    assert 'private' not in repr(result) + repr(reports)


def test_revoked_source_result_never_publishes_or_mutates_cloud(offline_session):
    session, _, _, accounts, scope, _ = offline_session
    body = intent()
    session.dispatch('prepare', body)
    taken = session.intake.take()
    result = session._validate(taken)
    future = Future()
    future.set_result(result)
    session.future, session.owner = future, ('intent', taken)
    accounts.logout(scope)
    with pytest.raises(RuntimeError, match='REVOKED'):
        session.tick()
    assert session.queue.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0
    assert not session.snapshot_path.exists()

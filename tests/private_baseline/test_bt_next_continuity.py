from copy import deepcopy
from types import SimpleNamespace

import pytest

from bobbi_core import preparation_client
from bobbi_core.video_context import video_identity
from lib.utils.player import bt_continuity
from lib.utils.player.discovery_gate import DiscoveryGate


@pytest.fixture
def proved(monkeypatch):
    account = dict(account_id='115:' + 'a' * 64, epoch=2, authenticated=True)
    def video(episode):
        return video_identity('tmdb:tv:1:s1:e' + str(episode), 'b' * 64,
            dict(source_info_hash='c' * 40, torrent_file_id=episode * 7,
                 torrent_path='Series S01E{:02} [Group].mkv'.format(episode), torrent_file_bytes=1000))
    anchor, following = video(1), video(2)
    current = dict(request_id='d' * 32, mode='tv', ids={'tmdb_id': 1}, tv_data={'season': 1, 'episode': 1},
        title='Series', source_title=anchor['selected']['torrent_path'], selection_policy='exact', is_torrent=True,
        info_hash='c' * 40, _account=account, _bt_current_selected=anchor['selected'],
        progress=99, subtitles_path=['/old.ass'], stream_subtitles=['old'], resume=120,
        cinema_continuity=True)
    proof = dict(request_id=current['request_id'], anchor=anchor, account='legacy',
        next=dict(video_context=following, source_title=following['selected']['torrent_path'], account='legacy'))
    status = dict(request_id=current['request_id'], state='accepted', result={'source_proof': proof})
    calls = []
    def call(method, body, **kwargs):
        calls.append((method, body, kwargs))
        assert kwargs['expected_account'] == account
        return deepcopy(status)
    monkeypatch.setattr(preparation_client, 'call', call)
    entry = dict(key='e' * 64, state='qualified', season=1, episode=2, title=following['selected']['torrent_path'],
        prepared_version_key='b' * 64, prepared_source_info_hash='c' * 40, prepared_account='legacy',
        prepared_file_id='cloud-file', prepared_qualification='f' * 64, bytes=1000,
        path='/115open/inbox/' + following['selected']['torrent_path'], video_context=following)
    index = dict(account='legacy', generation=2, mount_root=bt_continuity_root(),
                 titles=[dict(kind='tv', tmdb_id=1, sources=[entry])])
    return SimpleNamespace(current=current, proof=proof, status=status, calls=calls, index=index, entry=entry)


def bt_continuity_root():
    return '/storage/videos/Clouddrive/CloudDrive'


def test_service_proved_exact_bt_is_available_before_cloud_and_drops_old_episode_state(proved):
    result = bt_continuity.choose_next(proved.current, {'titles': []}, fresh=True)
    assert result['_bt_next_selected'] == proved.proof['next']['video_context']['selected']
    assert result['tv_data'] == {'season': 1, 'episode': 2}
    assert result['is_torrent'] and result['_next_transport'] == 'bt'
    assert result['_account'] == proved.current['_account']
    assert not {'progress', 'resume', 'subtitles_path', 'stream_subtitles'} & set(result)
    assert result['request_id'] != proved.current['request_id']
    assert proved.calls[0][0] == 'status'


@pytest.mark.parametrize('fresh', [False, True])
def test_ready_115_wins_over_exact_bt_and_final_check_is_bounded(proved, monkeypatch, fresh):
    reads = []
    def resolve(data, index, entry, cancelled, budget, pending_on_timeout):
        reads.append((data, budget))
        assert pending_on_timeout
        assert data['_account'] == proved.current['_account']
        return entry
    monkeypatch.setattr(preparation_client, 'resolve_entry', resolve)
    result = bt_continuity.choose_next(proved.current, proved.index, fresh=fresh)
    assert result['_next_transport'] == '115'
    assert result['prepared_resource_id'] == proved.entry['key']
    assert '_bt_next_selected' not in result
    assert len(reads) == int(fresh)
    if reads:
        assert reads[0][1] == 1.0


def test_cloud_deleted_after_projection_uses_only_service_proved_bt(proved, monkeypatch):
    monkeypatch.setattr(preparation_client, 'resolve_entry', lambda *a, **kw: None)
    result = bt_continuity.choose_next(proved.current, proved.index, fresh=True)
    assert result['_next_transport'] == 'bt'
    proved.status['result'] = {}
    assert bt_continuity.choose_next(proved.current, proved.index, fresh=True) is None


def test_slow_115_verification_is_pending_not_a_reason_to_fall_back_to_bt(proved, monkeypatch):
    clock = [100.]
    monkeypatch.setattr(preparation_client.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(preparation_client.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    old_call = preparation_client.call
    def call(method, body, **kwargs):
        if method in ('status', 'ping'):
            return old_call(method, body, **kwargs)
        assert method == 'resolve'
        # Model a ready cloud whose fresh verification needs 1.2 seconds,
        # beyond the native reservation's optional IO slice.
        clock[0] += .3
        return {'state': 'pending'}
    monkeypatch.setattr(preparation_client, 'call', call)
    result = bt_continuity.choose_next(proved.current, proved.index, fresh=True)
    assert result['_next_transport'] == '115'
    assert result['_next_cloud_pending'] is True
    assert not result.get('_next_cloud_verified')
    assert '_bt_next_selected' not in result
    assert clock[0] >= 101.


@pytest.mark.parametrize('change', ['hash', 'id', 'path', 'bytes', 'episode', 'request', 'version'])
def test_unbound_status_or_wrong_file_never_becomes_bt_fallback(proved, change):
    if change == 'episode':
        following = proved.proof['next']['video_context']
        proved.proof['next']['video_context'] = video_identity('tmdb:tv:1:s1:e3', following['release_key'], following['selected'])
    elif change == 'request': proved.status['request_id'] = '1' * 32
    elif change == 'version':
        following = proved.proof['next']['video_context']
        proved.proof['next']['video_context'] = video_identity(following['media_id'], '9' * 64, following['selected'])
    else:
        fields = {'hash': ('source_info_hash', '9' * 40), 'id': ('torrent_file_id', 99),
                  'path': ('torrent_path', 'Other S01E01.mkv'), 'bytes': ('torrent_file_bytes', 999)}
        key, value = fields[change]
        proved.current['_bt_current_selected'] = dict(proved.current['_bt_current_selected'], **{key: value})
    assert bt_continuity.choose_next(proved.current, {'titles': []}, fresh=True) is None


@pytest.mark.parametrize('moment', ['status', 'resolve'])
def test_cancellation_or_account_switch_during_lookup_cannot_publish_old_next(proved, monkeypatch, moment):
    cancelled = [False]
    def status(*a, **kw):
        cancelled[0] = True
        return proved.status
    def resolve(*a, **kw):
        cancelled[0] = True
        return proved.entry
    if moment == 'status': monkeypatch.setattr(preparation_client, 'call', status)
    else: monkeypatch.setattr(preparation_client, 'resolve_entry', resolve)
    assert bt_continuity.choose_next(proved.current, proved.index, lambda: cancelled[0], fresh=True) is None


def test_bt_candidate_does_not_latch_discovery_before_cloud_generation_changes():
    gate = DiscoveryGate()
    published = []
    token = gate.begin(0)
    assert gate.finish(token, True, 0, lambda: published.append('bt'), provisional=True)
    assert gate.begin(1) is None
    token = gate.begin(2)
    assert token is not None
    assert gate.finish(token, True, 2, lambda: published.append('115'))
    assert gate.begin(100) is None
    assert published == ['bt', '115']


def test_generation_change_rejects_late_provisional_discovery():
    gate = DiscoveryGate()
    old = gate.begin(0)
    gate.wake('new-account:epoch:2')
    assert not gate.finish(old, True, 1, lambda: pytest.fail('old publish'), provisional=True)
    assert gate.begin(1) is not None


@pytest.mark.parametrize('change', ['none', 'hash', 'id', 'path', 'bytes'])
def test_standard_bt_resolution_requires_same_real_tuple_without_ui(proved, change):
    data = bt_continuity.choose_next(proved.current, {'titles': []})
    selected = data['_bt_next_selected']
    actual = dict(id=selected['torrent_file_id'], path=selected['torrent_path'], size=selected['torrent_file_bytes'])
    if change in actual: actual[change] = actual[change] + 1 if change != 'path' else 'other.mkv'
    if change == 'bytes': actual['size'] += 1
    file = SimpleNamespace(**actual)
    def resolve(info_hash, magnet, choose_file, cancelled, budget):
        assert info_hash == selected['source_info_hash'] and budget == 8.0
        assert not cancelled()
        chosen = choose_file([file])
        if chosen is None:
            raise ValueError('Exact file unavailable')
        return dict(info_hash='9' * 40 if change == 'hash' else info_hash, file_id=file.id,
                    file_path=file.path, size=file.size, url='http://127.0.0.1:8090/exact')
    if change == 'none':
        result = bt_continuity.resolve_standard(data, lambda: False, SimpleNamespace(select_source=resolve))
        assert not result['is_torrent'] and 'magnet' not in result
        assert result['video_context'] == data['video_context']
    else:
        with pytest.raises(ValueError):
            bt_continuity.resolve_standard(data, lambda: False, SimpleNamespace(select_source=resolve))

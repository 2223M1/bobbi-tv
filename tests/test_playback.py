import pytest
from bobbi_platform.playback import Handoff, selected_identity, UnsupportedPlayback


def new_handoff(handle=-1):
    calls = []
    identity = selected_identity('user-selected-release')
    handoff = Handoff(identity, handle,
        lambda *args: calls.append(('resolved', args)),
        lambda *args: calls.append(('play', args)), lambda url, data: {'path': url})
    return handoff, identity, calls


@pytest.mark.parametrize('handle,method', [(-1, 'play'), (4, 'resolved'), (0, 'resolved')])
def test_one_open_only_without_native_or_global_commands(handle, method):
    handoff, identity, calls = new_handoff(handle)
    result = handoff.submit(identity, {'url': 'https://example.org/movie.mkv'})
    assert result['evidence'] == 'standard-kodi-handoff-only'
    assert result['status'] == 'submitted'
    assert handoff.submit(identity, {'url': 'https://example.org/movie.mkv'})['opened'] is False
    assert [x[0] for x in calls] == [method]
    assert not handoff.cancel()


def test_cancellation_before_handoff_never_opens():
    handoff, identity, calls = new_handoff()
    assert handoff.cancel()
    assert not handoff.submit(identity, {'url': 'https://example.org/movie.mkv'})['opened']
    assert calls == []


def test_selected_release_cannot_be_substituted():
    handoff, identity, calls = new_handoff()
    with pytest.raises(ValueError):
        handoff.submit(selected_identity('another-release'), {'url': 'https://example.org/movie.mkv'})
    assert calls == []


@pytest.mark.parametrize('data', [
    {'url': 'magnet:?xt=urn:btih:test'}, {'url': 'plugin://unrelated/'},
    {'url': 'https://example.org/a.mkv', 'is_torrent': True},
    {'url': 'https://example.org/a.mkv', 'is_pack': True},
    {'url': 'https://example.org/a.mkv', 'require_catalog_episode_binding': True},
    {'url': 'https://example.org/a.mkv', 'direct_cloud_required': True},
])
def test_unsupported_backend_does_not_bypass_identity(data):
    handoff, identity, calls = new_handoff()
    with pytest.raises(UnsupportedPlayback):
        handoff.submit(identity, data)
    assert calls == []


def test_lost_reply_never_retries_open():
    handoff, identity, calls = new_handoff()
    def fail(*args):
        calls.append('sent')
        raise OSError('reply lost')
    handoff.play = fail
    with pytest.raises(OSError):
        handoff.submit(identity, {'url': 'https://example.org/a.mkv'})
    assert handoff.state == 'submission_unknown'
    assert not handoff.submit(identity, {'url': 'https://example.org/a.mkv'})['opened']
    assert calls == ['sent']


def test_stale_resolution_fails_final_admission_after_listitem():
    handoff, identity, calls = new_handoff()
    handoff.ready = lambda: False
    assert handoff.submit(identity, {'url': 'https://example.org/a.mkv'})['status'] == 'cancelled'
    assert calls == []

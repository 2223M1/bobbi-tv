from copy import deepcopy
import sys
from types import SimpleNamespace

import pytest

from lib.utils.player.direct_continuity import episode_data, resolve_direct

ACCOUNT = {'account_id': 'fixture', 'epoch': 2, 'authenticated': True}


def next_data(provider='qqdocs'):
    return dict(mode='tv', ids={'tmdb_id': 1}, tv_data={'season': 1, 'episode': 4},
                _account=deepcopy(ACCOUNT), source_title='Show.S01E04.1080p.Group.mkv', size=100,
                direct_source=dict(provider=provider, locator='fixture://next', guid='next',
                                   title='Show.S01E04.1080p.Group.mkv', size=100))


def test_only_account_not_previous_file_subtitles_survives_episode_clone():
    current = next_data()
    current.update(_share={'media': 'old'}, subtitles_path=['old.ass'], progress=90,
                   stream_subtitles=['old'], playback_session_id='old')
    cloned = episode_data(current, 1, 5)
    assert cloned['_account'] == ACCOUNT
    assert cloned['_account'] is not current['_account']
    assert not set(('_share', 'subtitles_path', 'stream_subtitles', 'progress', 'playback_session_id')) & set(cloned)


def install(monkeypatch, accounts, resolver):
    monkeypatch.setitem(sys.modules, 'bobbi_platform.runtime', SimpleNamespace(call=lambda *a: accounts.pop(0)))
    monkeypatch.setitem(sys.modules, 'lib.clients.qqdocs_provider', SimpleNamespace(enabled=lambda: True))
    monkeypatch.setitem(sys.modules, 'bobbi_catalog.stream', SimpleNamespace(resolve=resolver))


def test_resolved_next_file_gets_new_subtitle_identity_with_original_epoch(monkeypatch):
    captured = []
    def resolve(*args, **kwargs):
        captured.append((args, kwargs))
        return 'http://127.0.0.1:1234/next'
    install(monkeypatch, [ACCOUNT, ACCOUNT], resolve)
    data = next_data()
    data['_share'] = {'media': 'old'}
    assert resolve_direct(data, lambda: False).endswith('/next')
    assert captured[0][1] == {'account': ACCOUNT}
    assert data['_share'] == dict(account=ACCOUNT, guid='next', locator='fixture://next',
        title=data['source_title'], size=100, media='tv:1:1:4')


@pytest.mark.parametrize('before', [True, False])
def test_account_switch_never_launders_continuation_into_new_account(monkeypatch, before):
    newer = dict(ACCOUNT, epoch=3)
    install(monkeypatch, [newer] if before else [ACCOUNT, newer], lambda *a, **k: 'next')
    data = next_data()
    with pytest.raises(RuntimeError, match='ACCOUNT_SCOPE_CHANGED'):
        resolve_direct(data, lambda: False)
    assert '_share' not in data

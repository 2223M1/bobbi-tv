from types import SimpleNamespace
from urllib.parse import urlencode
import json
from unittest.mock import MagicMock

import pytest

from lib.services import navigation_warmer as warmer


def test_url_plan_retains_only_public_identity_not_credentials_or_locator():
    data = dict(ids={'tmdb_id': 42}, mode='tv', tv_data={'season': 3, 'episode': 2},
                url='https://private.invalid/signed', cookie='private')
    url = 'plugin://plugin.video.bobbi/?' + urlencode(dict(action='play_media',
        continue_watching='true', data=json.dumps(data)))
    assert warmer.target_from_url(url) == ('tv', 42, 3)
    assert warmer.target_from_url(url.replace('plugin.video.bobbi', 'untrusted')) is None
    assert warmer.target_from_url(url.replace('play_media', 'transfer')) is None
    assert warmer.target_from_url('plugin://[bad') is None


@pytest.mark.parametrize('value', [None, {}, {'id': True, 'mode': 'tv'},
    {'id': -1, 'mode': 'movies'}, {'id': '42', 'mode': 'unknown'},
    {'id': '42', 'mode': 'tv', 'ids': 'invalid'}])
def test_invalid_speculation_identity_is_rejected(value):
    assert warmer.target(value) is None


def test_future_seasons_not_dropped_and_request_scope_is_account_neutral():
    from lib.clients.tmdb.navigation import regular_seasons
    assert regular_seasons(dict(seasons=[{'season_number': 1}, {'season_number': 2,
        'episode_count': 0, 'air_date': '2030-01-01'}, {'season_number': 0}])) == [1, 2]
    assert regular_seasons({}) == []


def test_focus_debounce_recent_limit_and_cancel_do_not_refresh_or_play(monkeypatch):
    import xbmc
    from lib.db.cached import cache
    clock, focus, busy, jobs = [100.0], [('tv', 42, 2)], [False], []
    monkeypatch.setattr(warmer.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(warmer, 'focused_target', lambda: focus[0])
    monkeypatch.setattr(warmer, 'ready', lambda p: not busy[0])
    monkeypatch.setattr(cache, 'get', lambda *a: None)
    monkeypatch.setattr(xbmc, 'getGlobalIdleTime', lambda: 20)
    monkeypatch.setattr(xbmc, 'executebuiltin', lambda *a: pytest.fail('No UI/player effects'))
    monkeypatch.setattr(warmer, 'recent_targets', lambda: [('movies', 55, None)])
    def warm(value, deadline, cancelled):
        jobs.append(value)
        assert deadline == clock[0] + 8 and not cancelled()
        busy[0] = True
        assert cancelled()  # video/audio/dialog takeover cancels this same task
        busy[0] = False
        return True
    monkeypatch.setattr(warmer, 'warm', warm)
    worker = warmer.NavigationWarmer()
    monitor = SimpleNamespace(abortRequested=lambda: False)
    assert not worker.tick(monitor, None)
    clock[0] += 1
    assert not worker.tick(monitor, None)
    clock[0] += 2
    assert not worker.tick(monitor, None)  # preempted after IO began
    assert jobs == [('tv', 42, 2)]
    assert not worker.tick(monitor, None)
    assert jobs == [('tv', 42, 2), ('movies', 55, None)]
    assert not worker.tick(monitor, None)


@pytest.mark.parametrize('audio,modal', [(True, False), (False, True)])
def test_any_playback_and_modal_work_preempt_background(monkeypatch, audio, modal):
    import xbmc
    monkeypatch.setattr(xbmc, 'getCondVisibility', lambda key: modal if key == 'System.HasModalDialog' else True)
    monkeypatch.setattr(warmer, 'resources_available', lambda: True)
    assert not warmer.ready(SimpleNamespace(isPlaying=lambda: audio))


def test_cancelled_optional_fetch_does_not_poison_foreground_retry(monkeypatch):
    from lib.clients.tmdb import detail_cache
    from bobbi_core.metadata_transport import request_budget
    import time
    cancelled, data = [False], {}
    cache = SimpleNamespace(get=lambda key: data.get(key),
        set=lambda key, data, expires: pytest.fail('Cancelled work cannot write a cooldown'))
    def fetch(_):
        cancelled[0] = True
        raise OSError('cancel')
    with request_budget(time.monotonic() + 5, lambda: cancelled[0], quiet=True):
        assert detail_cache.get('tv_details', {'id': 984212}, 'zh-CN', cache, fetch) is None


def test_explicit_cache_clear_invalidates_completed_work_cooldown(monkeypatch):
    import xbmc
    from lib.db.cached import cache
    now,epoch,jobs=[100.0],[None],[]
    monkeypatch.setattr(warmer.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(warmer,'ready',lambda p:True)
    monkeypatch.setattr(warmer,'focused_target',lambda:('movies',42,None))
    monkeypatch.setattr(xbmc,'getGlobalIdleTime',lambda:0)
    monkeypatch.setattr(cache,'get',lambda *a:epoch[0])
    monkeypatch.setattr(warmer,'warm',lambda *a:(jobs.append(a[0]),True)[1])
    worker=warmer.NavigationWarmer();monitor=SimpleNamespace(abortRequested=lambda:False)
    assert not worker.tick(monitor,None)
    now[0]+=3
    assert worker.tick(monitor,None)
    assert not worker.tick(monitor,None)
    epoch[0]='new-explicit-clear'
    assert worker.tick(monitor,None)
    assert len(jobs)==2

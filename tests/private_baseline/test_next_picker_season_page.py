"""The season browser already owns a lean, validated catalogue page.

At EOF the old unqualified details key refetched artwork/credits even when the
episode directory had previously proved the exact adjacent aired episode.
"""
from types import SimpleNamespace

import pytest

from lib.clients.tmdb.utils import utils as tmdb
from lib.utils.player.next_source_picker import target_episode
from lib.utils.views import shows


@pytest.mark.parametrize('as_dict', [False, True])
def test_eof_can_reuse_a_page_populated_by_the_episode_browser(monkeypatch, as_dict):
    def record(**fields):
        return fields if as_dict else SimpleNamespace(**fields)

    pages = {}
    def browse(kind, args):
        page = record(episodes=[record(episode_number=i, name='Episode', air_date='2020-05-12')
                                for i in (1, 2)])
        pages[(kind, tuple(sorted(args.items())))] = page
        return page
    monkeypatch.setattr(shows, 'tmdb_get', browse)
    shows._fetch_localized_season_pages(123, 1)

    attempts = []
    def offline(kind, args):
        key = (kind, tuple(sorted(args.items())))
        attempts.append(key)
        return pages.get(key)  # New metadata requests cannot reach the network.
    monkeypatch.setattr(tmdb, 'tmdb_get', offline)
    current = dict(mode='tv', ids={'tmdb_id':123}, tv_data=dict(season=1, episode=1),
                   title='Series', url='parent-file', selection_policy='exact')
    next_item = target_episode(current, lambda: False)
    assert next_item is not None
    assert next_item['tv_data'] == dict(season=1, episode=2, name='Episode')
    assert next_item['autoplay'] is False and 'url' not in next_item
    assert len(attempts) == 1 and attempts[0] in pages


@pytest.mark.parametrize('after', ['allow', 'revoked', 'unavailable', 'bad_scope'])
def test_eof_picker_rechecks_only_the_original_read_after_transport_loss(monkeypatch, after):
    from copy import deepcopy
    from lib.utils.player import next_source_picker as picker
    from types import SimpleNamespace
    monkeypatch.setattr(picker, 'picker_note', lambda reason: None)
    calls = []
    scope = {'account_id':'115:'+'a'*64, 'epoch':7, 'authenticated':True}
    owner = dict(boot_id='boot', epoch=12, request_id='d'*32)
    snapshot = {'epoch':12,'desired':{'request_id':'d'*32}}
    def read(message):
        calls.append(deepcopy(message))
        if len(calls)==1 and after=='bad_scope':
            raise ValueError('stale binding')
        if len(calls)==1 or after=='unavailable':
            raise OSError('read unavailable')
        return dict(allowed=after=='allow', snapshot=snapshot)
    result = picker.picker_status(dict(_next_picker_context=owner, _account=scope),
                                  playback_client=SimpleNamespace(call=read))
    assert (result == snapshot) if after=='allow' else (result is None)
    assert calls == [dict(owner,operation='next_picker_status',account_scope=scope)] * (1 if after=='bad_scope' else 2)


def test_eof_picker_never_retries_a_confirmed_denial(monkeypatch):
    from lib.utils.player import next_source_picker as picker
    monkeypatch.setattr(picker, 'picker_note', lambda reason: None)
    calls=[]
    def read(message):
        calls.append(message)
        return dict(allowed=False, snapshot={'epoch': 7})
    assert picker.picker_status({'_next_picker_context':{}}, playback_client=SimpleNamespace(call=read)) is None
    assert len(calls)==1

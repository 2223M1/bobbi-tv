import time
from types import SimpleNamespace
import pytest

from lib.clients.tmdb import subtitle_scope
from lib.api.tmdbv3api import tmdb
from lib.db.cached import cache
from bobbi_core.subtitle_episode import SingleSeason


@pytest.mark.parametrize('age,identifier,number,expected',[
    (60,60811,1,True),(6*86400,60811,1,True),(8*86400,60811,1,False),
    (-100,60811,1,False),(60,999,1,False),(60,60811,2,False)])
def test_cache_only_scope_is_id_and_age_bound(monkeypatch,age,identifier,number,expected):
    monkeypatch.setattr(tmdb,'TMDb',lambda:SimpleNamespace(language='zh-CN'))
    data=dict(id=identifier,name='Example',number_of_seasons=number,
              seasons=[dict(season_number=1,episode_count=11)])
    monkeypatch.setattr(cache,'get',lambda **kw:dict(fetched=time.time()-age,data=data))
    assert (subtitle_scope.cached_scope(60811)==SingleSeason(60811,11)) is expected


def test_missing_cache_never_creates_network_fallback(monkeypatch):
    monkeypatch.setattr(tmdb,'TMDb',lambda:SimpleNamespace(language='zh-CN'))
    monkeypatch.setattr(cache,'get',lambda **kw:None)
    assert subtitle_scope.cached_scope(60811) is None

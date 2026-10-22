"""Reviewer-owned cache conflict and title-scope edge cases; no network."""
from pathlib import Path
import sys

import pytest

WORK=Path('D:/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021')
sys.path.insert(0,str(WORK/'tests'))
sys.path.insert(0,str(WORK/'addons/script.module.bobbi.core/lib'))
from test_subtitle_alias_recall import cache_reader, tv_detail, CONTEXT, EXACT, titles, provider
from bobbi_core import subtitle_candidates as subtitles


@pytest.mark.parametrize('same_time',[False,True])
def test_richer_title_cache_cannot_override_fresher_multiseason_numbering(cache_reader,same_time):
    cache_reader.save(208891,fetched=999990,detail=tv_detail())
    multi=tv_detail(alternative_titles=None,number_of_seasons=2,
                    seasons=[dict(season_number=1,episode_count=13),dict(season_number=2,episode_count=12)])
    cache_reader.save('208891',fetched=999990 if same_time else 999999,detail=multi)
    evidence=cache_reader.module.cached_identity(208891)
    assert evidence is not None  # Valid title aliases can remain useful.
    assert evidence['scope'] is None
    row=dict(EXACT,native_name='天国大魔境',filename='天国大魔境 EP01.srt')
    context=dict(CONTEXT,_subtitle_titles=evidence['titles'],_subtitle_single_season=evidence['scope'])
    assert subtitles.rank(row,context) is None


@pytest.mark.parametrize('stamp',[10**400,-10**400,float('nan'),float('inf'),float('-inf'),True,'999999'])
def test_bad_timestamp_never_escapes_optional_cached_identity(cache_reader,stamp,monkeypatch):
    monkeypatch.setattr(cache_reader.module.time,'time',lambda:1000000.0)
    cache_reader.save(208891,fetched=stamp)
    assert cache_reader.module.cached_identity(208891) is None


@pytest.mark.parametrize('stamp',[10**400,-10**400])
def test_one_broken_cache_key_does_not_hide_other_valid_key(cache_reader,stamp,monkeypatch):
    monkeypatch.setattr(cache_reader.module.time,'time',lambda:1000000.0)
    cache_reader.save(208891,fetched=stamp)
    cache_reader.save('208891',fetched=999999)
    evidence=cache_reader.module.cached_identity(208891)
    assert evidence is not None and evidence['scope'].tmdb == CONTEXT['tmdb']
    assert '天国大魔境' in evidence['titles'].titles


def test_duplicate_alias_ids_across_precise_queries_do_not_redetail(tmp_path):
    incomplete=dict(id=111111,native_name='天国大魔境',subtype='Subrip(srt)')
    p=provider(tmp_path,lambda query:[incomplete],detail=lambda ident:[dict(EXACT,id=ident,
        filelist=[dict(f='天国大魔境 S01E01.chs.srt',url='https://assrt.net/offline/sub.srt')])])
    result=p.run(dict(CONTEXT,_subtitle_titles=titles()))
    assert result['origin']=='assrt:111111'
    assert sum(kind=='detail' for kind,_ in p.calls)==1


def test_fullwidth_alias_normalization_does_not_drop_episode_conflict():
    evidence=subtitles.titles_from_catalog('tv',dict(tmdb_id=208891,aliases=['Ｔｅｎｇｏｋｕ Ｄａｉｍａｋｙｏ','天国大魔境']))
    assert evidence.titles[0]=='Tengoku Daimakyo'
    context=dict(CONTEXT,_subtitle_titles=evidence)
    assert subtitles.rank(dict(EXACT,videoname='Tengoku Daimakyo S02E01'),context) is None

"""Real reported filename forms, guarded by canonical season evidence."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))
from bobbi_core.subtitle_episode import from_details,SingleSeason
from bobbi_core.subtitle_candidates import rank


def context():
    return dict(title='Ping Pong The Animation',mode='series',season=1,episode=1,tmdb=60811,
                year=2014,release='Vodes 1080p HEVC',_subtitle_single_season=SingleSeason(60811,11))


def row(filename):
    return dict(videoname='Ping Pong The Animation 2014 [BD 1920x1080 HEVC FLAC] - LittleBakas!',
                lang={'langlist':{'langchs':True}},filename=filename)


@pytest.mark.parametrize('filename',[
    'Ping Pong The Animation 2014 - EP01 [BD 1920x1080 HEVC-yuv444p10 FLACx2 PGSx2 Chap] - LittleBakas!.ass',
    '[GTX-Raws] ピンポン THE ANIMATION 第01話 (1920x1080 AVC Hi10P AAC).ass',
    '[Group] Ping Pong [01].chs.ass', 'Ping Pong S01E01.ass'])
def test_exact_episode_forms_accepted(filename):
    assert rank(row(filename),context()) is not None


@pytest.mark.parametrize('filename',[
    'Ping Pong EP02.ass','Ping Pong 第02話.ass','Ping Pong S02E01.ass','Ping Pong EP01-EP02.ass',
    'Ping Pong [01-02].ass','Ping Pong 第01話-第02話.ass','Ping Pong 1080p 2014.ass',
    '[01] Group Ping Pong.ass','Ping Pong EP01 EP02.ass'])
def test_wrong_or_ambiguous_file_rejected(filename):
    assert rank(row(filename),context()) is None


@pytest.mark.parametrize('scope',[None,{'tmdb':60811,'episodes':11},SingleSeason(999,11),SingleSeason(60811,0)])
def test_unproven_or_wrong_scope_rejected(scope):
    assert rank(row('Ping Pong EP01.ass'),dict(context(),_subtitle_single_season=scope)) is None


def test_explicit_package_season_works_without_single_season_exception():
    r=row('Ping Pong EP01.ass');r['videoname']+=' S02'
    assert rank(r,dict(context(),season=2,_subtitle_single_season=None)) is not None
    assert rank(r,context()) is None


def test_details_require_only_canonical_first_season_and_exact_id():
    data=dict(id=60811,name='Ping Pong',number_of_seasons=1,seasons=[dict(season_number=0,episode_count=2),dict(season_number=1,episode_count=11)])
    assert from_details(data,60811)==SingleSeason(60811,11)
    assert from_details(data,999) is None
    assert from_details(dict(data,number_of_seasons=2),60811) is None
    assert from_details(dict(data,seasons=data['seasons']+[dict(season_number=2,episode_count=11)]),60811) is None
    assert from_details(dict(data,seasons=[dict(season_number=1,episode_count=True)]),60811) is None

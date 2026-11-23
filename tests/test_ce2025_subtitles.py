import pytest
from test_ce2023_subtitle_episodes import context, row
from bobbi_core.subtitle_candidates import rank


@pytest.mark.parametrize('tag', ['EP01,02','EP01、02','第01話、02話','EP01;02','EP01，02',
    'EP01；02','[01],02','EP01v2,02','S01E01,02','S01E01、E02'])
def test_ambiguous_file_never_means_single_episode(tag):
    assert rank(row('Ping Pong '+tag+'.chs.ass'),context()) is None


@pytest.mark.parametrize('tag',['第2季 EP01','第二季 第01話','2nd Season EP01','OVA EP01','Specials EP01','番外篇 EP01'])
@pytest.mark.parametrize('field', ['filename','native_name','videoname','title'])
def test_explicit_conflict_in_any_metadata_field(tag,field):
    data=row('Ping Pong EP01.chs.ass')
    data[field]='Ping Pong The Animation '+tag+'.chs.ass'
    assert rank(data,context()) is None


@pytest.mark.parametrize('title',['Special','The Second Season','第二季','OVA Story'])
def test_canonical_title_is_not_a_special_or_season_declaration(title):
    active=dict(context(),title=title)
    assert rank(dict(videoname=title,filename=title+' EP01.chs.ass',lang={'langlist':{'langchs':True}}),active) is not None


@pytest.mark.parametrize('tag',['第1季','第一季','1st Season','S01','Season 1'])
def test_matching_season_authorizes_unseasoned_file(tag):
    data=row('Ping Pong EP01.chs.ass');data['videoname']+=' '+tag
    assert rank(data,dict(context(),_subtitle_single_season=None)) is not None

"""Regressions from CE2195's 27 November viewing session."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from bobbi_core import anime_range_candidates as anime
from bobbi_core.episode_identity import bind_catalog_range_episode, check_transport_episode_file, resolve_episode_binding
from bobbi_core.subtitle_candidates import inspect_text

ROOT = Path(__file__).resolve().parents[1]
TITLES = ['[DBD-Raws][永生之酒/为酒而狂/Baccano!][01-16TV全集][1080P][BDRip][HEVC-10bit][简繁外挂][FLACx2][MKV](バッカーノ!)',
          '【诸神片源组】[永生之酒/为酒而狂][01-16合集][1080P][外挂DMZJ简繁+英日文字幕][BD-MKV]★高清收藏版',
          '[异域-11番小队][永生之酒BACCANO][BDRIP][1-16+SP]']


def test_real_ranges_and_selected_file_not_foreign_work_or_bonus():
    scope = anime.context(dict(id=34121, name='永生之酒', original_name='バッカーノ！',
        alternative_titles={'results':[{'title':'Baccano!'}]}, first_air_date='2007-07-27',
        genres=[{'id':16}]), 34121, 1, 1, 1)
    assert all(anime.eligible(title, scope, 1, 1) for title in TITLES)
    assert not anime.eligible(TITLES[0].replace('01-16', '02-16'), scope, 1, 1)
    assert not anime.eligible(TITLES[1].replace('永生之酒','其他作品'), scope, 1, 1)
    h, request = 'a'*40, 'b'*32
    proof = json.dumps(bind_catalog_range_episode({'tmdb_id':34121}, {'season':1,'episode':1},
        request,'bt:'+h,'',h,catalog=scope['catalog']))
    assert json.loads(resolve_episode_binding(proof,request,'bt:'+h,h,1,1))['absolute_episode']==1
    filename = '[DBD-Raws][Baccano!][01][1080P][BDRip][HEVC-10bit][FLACx2].mkv'
    dirname = '[DBD-Raws][永生之酒][01-16TV全集][1080P][BDRip][HEVC-10bit][简繁外挂][FLACx2][MKV]'
    check_transport_episode_file(proof, dirname+'/'+filename, TITLES[:1])
    for path in ('SP/'+filename,dirname+'/'+filename.replace('Baccano!', 'Another Show')):
        with pytest.raises(ValueError):
            check_transport_episode_file(proof, path, TITLES[:1])


@pytest.mark.parametrize('template', ['source_select.xml', 'source_select_direct.xml'])
def test_each_rendered_source_row_has_visible_provenance_and_subtitles(template):
    file = ROOT/'addons/plugin.video.bobbi/resources/skins/Default/1080i'/template
    source = ET.parse(file).find(".//control[@id='1000']")
    for layout in ('itemlayout','focusedlayout'):
        row=source.find(layout)
        for label in row.findall("control[@type='label']"):
            x,y = (int(label.findtext(k,'0')) for k in ('left','top'))
            assert 0 <= x < int(row.get('width')) and 0 <= y < int(row.get('height'))
        metadata=[c for c in row.findall("control[@type='label']") if 'Property(size)' in c.findtext('label','')]
        assert metadata and all(all('Property('+key+')' in c.findtext('label')
            for key in ('type_plain','chinese_subtitles','seeders')) for c in metadata)


def test_real_style_first_ass_is_readable_without_losing_styles_or_accepting_garbage():
    text = ('[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n[Events]\n'
            'Format: Layer, Start, End, Style, Text\nDialogue: 0,0:00:02.00,0:00:04.00,Default,你好\\Nhello\n')
    out,bilingual=inspect_text(text.encode('utf-8-sig'),'.ass')
    assert out.startswith(b'[Script Info]') and out.endswith(text.encode()) and bilingual
    with pytest.raises(ValueError):
        inspect_text(b'[V4+ Styles]\n[Events]\nDialogue: broken', '.ass')



def test_unmapped_ended_anime_demands_explicit_transport_episode():
    details = dict(id=130996, name='四叠半时光机蓝调', original_name='Tatami Time Machine Blues',
        first_air_date='2022-09-14', genres=[{'id':16}], status='Ended', number_of_seasons=1,
        number_of_episodes=6, seasons=[{'season_number':1, 'episode_count':6}])
    h, request = 'a'*40, 'b'*32
    ctx = anime.context(details, 130996, 1, 1, 1, mappings={})
    title = '[Group][Tatami Time Machine Blues][01-06][1080P]'
    assert anime.eligible(title, ctx, 1, 1)
    assert anime.context(dict(details,status='Returning Series'), 130996, 1, 1, 1, mappings={}) is None
    assert anime.context(dict(details,number_of_seasons=2), 130996, 1, 1, 1, mappings={}) is None
    raw = json.dumps(bind_catalog_range_episode({'tmdb_id':130996},{'season':1,'episode':1},
        request,'bt:'+h,'',h,catalog=ctx['catalog'],mappings={}))
    assert resolve_episode_binding(raw,request,'bt:'+h,h,1,1,mappings={}) == ''
    check_transport_episode_file(raw,'Tatami Time Machine Blues S01E01 [1080P].mkv',[title])
    for name in ('Tatami Time Machine Blues [01].mkv', 'Another Show S01E01.mkv',
                 'SP/Tatami Time Machine Blues S01E01.mkv', 'Tatami Time Machine Blues S02E01.mkv'):
        with pytest.raises(ValueError):
            check_transport_episode_file(raw,name,[title])


def test_confirming_unmapped_file_accepts_same_group_crc_but_never_a_bonus_or_different_group():
    details = dict(id=61389,name='Saint Seiya: The Lost Canvas',first_air_date='2009-06-24',
        genres=[{'id':16}],status='Ended',number_of_seasons=1,number_of_episodes=26,
        seasons=[{'season_number':1,'episode_count':26}])
    scope = anime.context(details,61389,1,1,1,mappings={})
    release='[F-R] Saint Seiya The Lost Canvas (BD 1080p JP+EN) 01-26'
    assert anime.eligible(release,scope,1,1)
    h='a'*40
    raw=json.dumps(bind_catalog_range_episode({'tmdb_id':61389},{'season':1,'episode':1},'b'*32,
        'bt:'+h,'',h,mappings={},catalog=scope['catalog']))
    name='Saint Seiya The Lost Canvas - 01 (1080p BD JP+EN) [F-R][49783f1a].mkv'
    check_transport_episode_file(raw,name,[release],require_work=False)
    for filename in (name.replace('[F-R]', '[Other-Group]'),name.replace('[F-R]','[OVA]'),'SP/'+name):
        with pytest.raises(ValueError):
            check_transport_episode_file(raw,filename,[release],require_work=False)
    with pytest.raises(ValueError):
        check_transport_episode_file(raw,name,[release],require_work=True)


def test_real_pack_one_eligible_file_needs_no_dialog_or_mapping():
    from test_bobbi_torrent_adapter import Clock, FakeOwner, Session, Response, request, config, HASH, RID
    from bobbi_torrent.backend import Backend
    from bobbi_torrent.resolver import Resolver
    details = dict(id=61389,name='Saint Seiya: The Lost Canvas',first_air_date='2009-06-24',
        genres=[{'id':16}],status='Ended',number_of_seasons=1,number_of_episodes=26,
        seasons=[{'season_number':1,'episode_count':26}])
    catalog = anime.context(details,61389,1,1,1,mappings={})['catalog']
    raw = json.dumps(bind_catalog_range_episode({'tmdb_id':61389},{'season':1,'episode':1},RID,
        'bt:'+HASH,'',HASH,mappings={},catalog=catalog))
    root = '[F-R] Saint Seiya The Lost Canvas (BD 1080p JP+EN)'
    title = root+' 01-26'
    rows = [dict(id=n,path=f'{root}/Saint Seiya The Lost Canvas - {n:02} (1080p BD JP+EN) [F-R][49783f1a].mkv',
                 length=1255184472) for n in range(1,27)]
    info = dict(hash=HASH,name=root,title=title,file_stats=rows[::-1],preload_size=100,preloaded_bytes=100)
    clock = Clock()
    owner = FakeOwner(clock)
    owner.choose_file = lambda *args: pytest.fail('There is no choice to make')
    owner.prepared_source_ready = lambda *args: pytest.fail('No verified numbering or preparation authority')
    import time
    owner.wait = lambda _: time.sleep(.005)
    session = Session([Response(b'MatriX.147'),Response({'hash':HASH})]+[Response(info)]*10)
    media = Session([])
    media.files = {row['id']:row['length'] for row in rows}
    result = Resolver(Backend(config(),session,clock,media_session_factory=lambda:media),owner,Session([]),clock).resolve(
        request(episode_binding=raw,release_title=title))
    assert result['file'] == rows[0] and result['file_evidence'] == 'SOLE_ELIGIBLE_FILE'
    assert not owner.targets


@pytest.mark.parametrize('when', ['before_preload','before_open'])
def test_single_file_must_still_be_the_only_eligible_file_when_rechecked(when):
    from test_bobbi_torrent_adapter import Clock, FakeOwner, Session, Response, request, config, status, HASH
    from bobbi_torrent.backend import Backend, BackendError
    from bobbi_torrent.resolver import Resolver
    row = dict(id=1,path='video.mkv',length=1000000)
    info = status(row)
    changed = dict(info,file_stats=[row,dict(row,id=2,path='main.mkv')])
    clock = Clock()
    owner = FakeOwner(clock)
    owner.choose_file = lambda *args: pytest.fail('A changing file list must not open the old choice')
    replies = [Response(b'MatriX.147'),Response({'hash':HASH}),Response(info)]
    if when == 'before_open':
        replies.extend([Response(info),Response(b'')])
    session = Session(replies+[Response(changed)])
    with pytest.raises(BackendError,match='SELECTED_FILE_CHANGED'):
        Resolver(Backend(config(),session,clock),owner,Session([]),clock).resolve(request())
    assert not owner.bindings and not owner.targets

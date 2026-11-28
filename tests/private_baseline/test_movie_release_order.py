"""Release names reproduced from ordinary movie/TV naming, on the real ranking/UI path."""
import pytest

from bobbi_core.source_list_session import SourceListSession
from lib.domain.torrent import TorrentStream
from lib.utils.general.cinema_source_rank import rank_sources, source_preference
from test_ce2015_list_binding import QueuedControl
from test_source_incremental_ui import window


def row(tags, **fields):
    return TorrentStream(title='Example.2024.' + tags, type='Torrent', seeders=fields.pop('seeders', 5),
                         guid=tags, **fields)


def order(rows, context):
    return [s.title for s in rank_sources(rows, context)]


@pytest.mark.parametrize('mode', ['movies', 'tv'])
def test_video_priority_across_origins_and_labels(mode):
    tags = ['2160p.UHD.BluRay.DoVi.P7.iso', '2160p.UHD.BluRay.REMUX.DV.HDR10.mkv',
            '2160p.UHD.BluRay.REMUX.HDR10Plus.mkv', '2160p.UHD.BluRay.REMUX.DoVi.mkv',
            '2160p.UHD.BluRay.REMUX.SDR.简中.mkv', '2160p.BluRay.x265.HDR10.mkv',
            '2160p.WEB-DL.DV.P8.1.mkv', '2160p.WEB-DL.HDR10+.mkv',
            '2160p.WEB-DL.DV.P5.mkv', '2160p.WEB-DL.SDR.[简中外挂].mkv',
            '2160p.WEBRip.SDR.mkv', '1080p.BluRay.REMUX.DV.HDR10.mkv',
            '2160p.HDCAM.HDR10.mkv']
    ctx = {'mode': mode, 'title': 'Example'}
    rows = list(map(row, tags))
    keys = [source_preference(s, ctx)['key'] for s in rows]
    assert keys[0] == keys[1]  # Full Blu-ray and remux with equivalent claimed video.
    assert all(a > b for a,b in zip(keys[1:], keys[2:]))
    assert order(rows[2:][::-1] + rows[:2], ctx) == [s.title for s in rows]


@pytest.mark.parametrize('a,b', [
    ('WEB-DL.X264.TrueHD.Atmos.mkv', 'WEB-DL.HEVC.AAC.mp4'),
    ('WEB-DL.Main10.mkv', 'WEB-DL.x264.mp4'),
    ('WEB-DL.HDR10Plus', 'WEB-DL.HDR10'), ('WEB-DL.HDR10+', 'WEB-DL.HDR10'),
    ('WEB-DL.REMUX', 'WEB-DL'), ('DVDRemux', 'DVD'),
    ('Dolby.Atmos.iso', 'plain.mp4'), ('WEB-DL.DV.dvhe.08.06', 'WEB-DL.DoVi'),
    ('WEB-DL.DV.P5.HDR10', 'WEB-DL.DV.P5'), ('WEB-DL.w/o HDR fallback.DV', 'WEB-DL.DV.P5'),
    ('WEB-DL.HYBRID.DV.P8.1', 'WEB-DL.DV.HDR10'),
    ('WEB-DL.SDR.to.HDR', 'WEB-DL.SDR'),
])
def test_no_unearned_video_advantage(a, b):
    ctx = {'mode':'movies'}
    left,right = [row('2160p.'+tag) for tag in (a,b)]
    left.size, right.size = 3*1024**3, 48*1024**3
    assert source_preference(left,ctx)['key'] == source_preference(right,ctx)['key']


def test_same_film_language_and_seeders_only_break_picture_ties():
    ctx = {'mode':'movies'}
    plain = row('2160p.WEB-DL.HDR10',seeders=300)
    localized = row('2160p.WEB-DL.HDR10.[简中外挂]',seeders=1)
    assert order([plain,localized],ctx)[0] == localized.title
    name = row('2160p.WEB-DL.HDR10.mkv'); name.title='Cam.2018.2160p.WEB-DL.HDR10.mkv'
    assert not source_preference(name,{'mode':'movies','title':'Cam'})['caution']


@pytest.mark.parametrize('ctx', [{'mode':'anime'}, {'mode':'tv','genre_ids':[16]},
                                 {'mode':'movies','media_kind':'anime_movie'}])
def test_animation_and_unscoped_cloud_retain_subtitle_and_group_policy(ctx):
    subs, high = row('2160p.WEBRip.[简中外挂]'), row('2160p.BluRay.REMUX.DV.HDR10')
    group = row('1080p.[VCB-Studio]')
    assert order([high,subs,group],ctx) == [group.title,subs.title,high.title]
    for s in (subs, high): s.type='Direct'
    assert order([high,subs],ctx) == [subs.title,high.title]


def test_confirmed_failure_and_unavailable_torrent_stay_below_playable():
    ctx = {'mode':'movies', 'title':'Example', 'ids':{'tmdb_id':123}}
    good = row('1080p.WEBRip')
    failed = row('2160p.BDREMUX.DV.HDR10',shareFailure='share_revoked')
    dead = row('2160p.BDREMUX.HDR10',seeders=0)
    wrong = row('2160p.BDREMUX',catalogIdentity={'mode':'movies','tmdb_id':234})
    assert rank_sources([failed,dead,wrong,good],ctx)[0] is good
    assert rank_sources([good,failed,wrong,dead],ctx)[-1] is failed


@pytest.mark.parametrize('eager', [False,True])
def test_late_premium_release_moves_to_top_without_changing_selected_file(window,eager):
    ctx = window.item_information = {'mode':'movies','title':'Example'}
    control = window.display_list = QueuedControl(eager)
    session = window.source_session = SourceListSession({}, lambda rs:rank_sources(rs,ctx),limit=2)
    first,selected,premium = [row(tag) for tag in ('1080p.WEB-DL','720p.WEBRip','2160p.BluRay.REMUX.DV.HDR10')]
    def refresh():
        window.sources=[s for _,s in session.snapshot(full=True,pin_focus=False)['entries']]
        window.populate_sources_list(incremental=bool(getattr(window,'_rendered_keys',[])))
        control.dispatch()
    session.publish(session.epoch,'a',[first,selected],state='RUNNING')
    refresh();control.selectItem(1);control.dispatch()
    item=control.getSelectedItem();session.focus(item.getProperty('source_key'),1)
    session.publish(session.epoch,'b',[premium]);refresh()
    assert [o.getLabel() for o in control.gui_items]==[premium.title,selected.title]
    assert '蓝光 REMUX' in control.gui_items[0].getProperty('badges_plain')
    assert '杜比视界 + HDR10' in control.gui_items[0].getProperty('badges_plain')
    assert control.getSelectedItem() is item
    assert session.capture(session.epoch,item.getProperty('source_key')).guid==selected.guid
    binds=control.binds
    refresh();assert control.binds==binds

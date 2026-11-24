"""Unit and Host-RPC tests for R08 owned_playback foundation (PB-01)."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from bobbi_core.library_contract import Source, vfs_source
from bobbi_core.playback_request import Client as PlaybackClient, SelectionChanged
from bobbi_platform.host import Host
from bobbi_platform.libraries import Registry
from bobbi_platform.owned_playback import (
    emby_source_scope,
    library_source_scope,
    reserve_playback,
)
from bobbi_platform.standard_session import StandardSession

ROOT = Path(__file__).resolve().parents[1]


class _FakeInfoTag:
    def __init__(self):
        self.title = None
        self.season = None
        self.episode = None
        self.unique = {}

    def setTitle(self, value):
        self.title = value

    def setSeason(self, value):
        self.season = value

    def setEpisode(self, value):
        self.episode = value

    def setUniqueID(self, value, kind):
        self.unique[kind] = value


class _FakeListItem:
    def __init__(self, label='', path=''):
        self.label = label
        self.path = path
        self.properties = {}
        self.info = {}
        self.art = {}
        self.subtitles = []
        self.mime = None
        self.content_lookup = True
        self.tag = _FakeInfoTag()

    def setProperty(self, k, v):
        self.properties[k] = v

    def setInfo(self, kind, info):
        self.info[kind] = dict(info)

    def setArt(self, art):
        self.art.update(art)

    def setSubtitles(self, subs):
        self.subtitles = list(subs)

    def setMimeType(self, mime):
        self.mime = mime

    def setContentLookup(self, flag):
        self.content_lookup = flag

    def getVideoInfoTag(self):
        return self.tag


def _make_standard_transport(host: Host):
    events = []
    paused = [False]
    clock = [100.0]
    session = StandardSession(
        host.playback_accounts,
        clock=lambda: clock[0],
        paused=lambda: paused[0],
        observer=events.append,
    )
    host.bind_owner(session.dispatch)

    def direct_host_call(action, body, timeout=3):
        if action in ('playback', 'standard_playback'):
            return session.dispatch(body)
        return host.dispatch(action, body)

    binding = SimpleNamespace(is_current=lambda: True, require_current=lambda: None)
    client = PlaybackClient(lambda msg, timeout=0.3: direct_host_call('playback', msg, timeout=timeout))
    return (binding, client, direct_host_call), session, events, paused, clock


def test_owned_playback_has_zero_reverse_imports_into_plugin():
    mod_path = ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/owned_playback.py'
    tree = ast.parse(mod_path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith('lib') for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith('lib')


def test_r08_01_02_07_resume_900s_start_over_and_infotag_handoff(tmp_path, monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'xbmcgui', SimpleNamespace(ListItem=_FakeListItem))
    store = Registry(tmp_path / 'libraries.sqlite3')
    src = Source(
        'a' * 32,
        'LivingRoom Emby',
        'media_server',
        'http://192.168.1.10:8096',
        password='synthetic-token',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srv1', 'user_id': 'usr1'},
    )
    store.save(src)
    _, gen = store.source_snapshot(src.id)
    store.close()

    host = Host(tmp_path)
    host.start()
    try:
        transport, session, events, paused, clock = _make_standard_transport(host)
        scope = emby_source_scope(source_id=src.id, generation=gen, server_id='srv1', user_id='usr1')

        resolved_items = []
        with reserve_playback('emby://srv1/usr1/ep10', scope, transport=transport) as res:
            out = res.submit(
                11,
                'http://192.168.1.10:8096/Videos/ep10/stream?Static=true&MediaSourceId=ms1|redirect-limit=0',
                title='Episode 10',
                source_meta={
                    'provider': 'emby',
                    'server_id': 'srv1',
                    'user_id': 'usr1',
                    'source_id': src.id,
                    'source_generation': gen,
                    'item_id': 'ep10',
                    'media_source_id': 'ms1',
                    'play_session_id': 'ps-900',
                },
                info={'mediatype': 'episode', 'season': 1, 'episode': 10, 'plot': 'Pilot', 'duration': 2400},
                art={'poster': 'http://127.0.0.1:9999/poster.jpg'},
                mime='video/x-matroska',
                resume_offset=900,
                resolve_fn=lambda h, ok, li: resolved_items.append((h, ok, li)),
                play_fn=lambda *a: None,
            )
        assert out['opened'] is True
        _, ok, li = resolved_items[-1]
        assert ok is True
        assert li.properties['StartOffset'] == '900.0'
        assert li.properties['bobbi.standard.request'] == out['request_id']
        assert li.mime == 'video/x-matroska' and li.content_lookup is False
        assert li.tag.season == 1 and li.tag.episode == 10
        assert li.info['video']['plot'] == 'Pilot'

        # Observe actual AV-start (e.g. player started at 900.2s), backward seek, pause, and natural EOF
        url_no_opts = 'http://192.168.1.10:8096/Videos/ep10/stream?Static=true&MediaSourceId=ms1'
        assert session.observe(out['request_id'], url_no_opts, 900.2, 2400.0)
        assert events[-1]['event'] == 'AV_START' and events[-1]['position'] == 900.2

        # Backward seek to 120s emits immediate TimeUpdate with real position 120.0 (never max())
        clock[0] += 1.0
        assert session.observe(out['request_id'], url_no_opts, 120.0, 2400.0)
        assert events[-1]['event'] == 'PROGRESS' and events[-1]['position'] == 120.0

        # Pause emits immediate Pause trigger
        paused[0] = True
        clock[0] += 0.5
        assert session.observe(out['request_id'], url_no_opts, 120.0, 2400.0)
        assert events[-1]['event'] == 'PROGRESS' and events[-1]['trigger'] == 'Pause' and events[-1]['paused'] is True

        # Start Over explicitly sets StartOffset='0'
        with reserve_playback('emby://srv1/usr1/ep10', scope, transport=transport) as res2:
            res2.submit(
                12,
                url_no_opts + '|redirect-limit=0',
                title='Episode 10',
                resume_offset=900,
                start_over=True,
                resolve_fn=lambda h, ok, li: resolved_items.append((h, ok, li)),
                play_fn=lambda *a: None,
            )
        assert resolved_items[-1][2].properties['StartOffset'] == '0'
    finally:
        host.close()


def test_r08_04_05_late_a_cannot_preempt_b_and_source_revocation_is_scoped(tmp_path, monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'xbmcgui', SimpleNamespace(ListItem=_FakeListItem))
    store = Registry(tmp_path / 'libraries.sqlite3')
    src_a = vfs_source('Source A', str(tmp_path))
    src_b = vfs_source('Source B', str(tmp_path))
    store.save(src_a)
    store.save(src_b)
    _, gen_a = store.source_snapshot(src_a.id)
    _, gen_b = store.source_snapshot(src_b.id)
    store.close()

    host = Host(tmp_path)
    host.start()
    try:
        transport, session, events, _, _ = _make_standard_transport(host)
        scope_a = library_source_scope(src_a.id, gen_a)
        scope_b = library_source_scope(src_b.id, gen_b)

        # User clicks A (reserved before slow PlaybackInfo/stream_open)
        res_a = reserve_playback('strm://a/movieA.strm', scope_a, transport=transport)
        # While A is still resolving, user picks B!
        res_b = reserve_playback('strm://b/movieB.strm', scope_b, transport=transport)

        resolved = []
        res_b.submit(
            21,
            'http://127.0.0.1:41000/stream/' + 'b' * 32 + '/video.mkv',
            title='Movie B',
            resolve_fn=lambda h, ok, li: resolved.append(('B', h, ok, li)),
            play_fn=lambda *a: None,
        )
        assert session.observe(res_b.request_id, 'http://127.0.0.1:41000/stream/' + 'b' * 32 + '/video.mkv', 5.0, 600.0)

        # Now slow A finishes resolution and tries to submit -> rejected, B remains untouched!
        with pytest.raises(SelectionChanged):
            res_a.submit(
                20,
                'http://127.0.0.1:41000/stream/' + 'a' * 32 + '/video.mkv',
                title='Movie A',
                resolve_fn=lambda h, ok, li: resolved.append(('A', h, ok, li)),
                play_fn=lambda *a: None,
            )
        assert [tag for tag, *_ in resolved] == ['B']
        assert session.current['request_id'] == res_b.request_id and session.current['state'] == 'playing'

        # Removing source A does NOT stop B; removing source B retires ONLY B with ACCOUNT_CHANGED!
        s = Registry(tmp_path / 'libraries.sqlite3')
        s.remove(src_a.id)
        s.close()
        session.tick(playing=True)
        assert session.current['state'] == 'playing'

        s = Registry(tmp_path / 'libraries.sqlite3')
        s.remove(src_b.id)
        s.close()
        session.tick(playing=True)
        assert session.current['state'] == 'retired'
        assert events[-1]['event'] == 'TERMINAL' and events[-1]['reason'] == 'ACCOUNT_CHANGED'
    finally:
        host.close()

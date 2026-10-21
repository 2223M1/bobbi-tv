"""Real standard adapter -> ListItem -> callback -> exact continuation chain.

Kodi/player and provider IO are test doubles, not a second hardware certificate.
All player policy, request binding and handoff code are the product modules.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def product(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi'))
    monkeypatch.syspath_prepend(str(ROOT / 'addons/script.module.bobbi.core/lib'))
    state = SimpleNamespace(playing=False, item=None, url='', position=0., total=100.,
                            opened=[], subtitles=[], props={}, saved=[], reports=[])
    class Tag:
        def __init__(self): self.ids = {}
        def setUniqueID(self, value, key): self.ids[key] = value
        def getUniqueID(self, key): return self.ids.get(key, '')
        def setTitle(self, value): pass
        def setSeason(self, value): pass
        def setEpisode(self, value): pass
    class Item:
        def __init__(self, label='', path=''):
            self.path, self.props, self.tag, self.subs = path, {}, Tag(), []
        def setProperty(self, k, v): self.props[k] = v
        def getProperty(self, k): return self.props.get(k, '')
        def getVideoInfoTag(self): return self.tag
        def setSubtitles(self, values): self.subs = values
        def setArt(self, values): pass
    class Player:
        def isPlaying(self): return state.playing
        def isPlayingVideo(self): return state.playing
        def getPlayingFile(self): return state.url
        def getPlayingItem(self): return state.item
        def getVideoInfoTag(self): return state.item.tag
        def getTime(self): return state.position
        def getTotalTime(self): return state.total
        def setSubtitles(self, value): state.subtitles.append(value)
        def play(self, url, item): state.opened.append((url, item))
    window = SimpleNamespace(getProperty=lambda k: state.props.get(k, ''),
        setProperty=lambda k, v: state.props.update({k: v}), clearProperty=lambda k: state.props.pop(k, None))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Player=Player))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=Item, Window=lambda _: window))
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(
        setResolvedUrl=lambda handle, success, item: state.opened.append((item.path, item))))
    spec = importlib.util.spec_from_file_location('standard_product',
        ROOT / 'addons/plugin.video.bobbi/lib/services/standard_playback.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'HistoryWriter', lambda report: SimpleNamespace(
        save=lambda data: state.saved.append(data), close=lambda: None))
    account = {'account_id': '', 'authenticated': False, 'epoch': 0}
    def require(value, authenticated=False):
        if value != account: raise ValueError('STALE_ACCOUNT')
    host = SimpleNamespace(accounts=SimpleNamespace(require_current=require, is_current=lambda v: v == account),
        report=state.reports.append, bind_owner=lambda fn: None, sidecar_candidate=None, stopping=Event())
    actor = module.StandardPlayback(host)
    clock = [100.]
    actor.session.clock = lambda: clock[0]
    monkeypatch.setattr(module, 'discover', lambda *args: {'file': '/profile/Chinese.ass'})
    yield SimpleNamespace(state=state, actor=actor, module=module, account=account, clock=clock)
    actor.close()


def selected(product, letter='a'):
    data = dict(request_id=letter*32, _account=deepcopy(product.account), selection_policy='exact',
        url='https://media.example/'+letter+'.mkv', title='Series', tv_data={'season': 1, 'episode': 1},
        mode='tv', file_evidence='AUTO_VERIFIED_FILE')
    product.actor.dispatch(dict(operation='select', request_id=data['request_id'], account=data['_account']))
    return data


def handoff(product, data):
    from bobbi_platform.kodi import standard_handoff
    from bobbi_platform.playback import selected_identity
    result = product.actor.dispatch(dict(operation='register', request_id=data['request_id'], data=data))
    assert result['accepted']
    data['subtitles_path'] = result['subtitles_path']
    identity = selected_identity(data['url'])
    standard_handoff(identity, 12).submit(identity, data)
    url, item = product.state.opened[-1]
    product.state.url, product.state.item, product.state.playing = url, item, True
    product.actor.tick()
    return item


def test_actual_item_binds_subtitle_then_observed_eof_opens_exact_next(product, monkeypatch):
    data = selected(product)
    product.actor.dispatch(dict(operation='subtitle_start', request_id=data['request_id'], data=data))
    product.actor.subtitle_worker.join(1)
    next_data = dict(data, request_id='b'*32, url='https://media.example/b.mkv', tv_data={'season': 1, 'episode': 2})
    monkeypatch.setattr(product.module, 'next_data', lambda current, cancelled: deepcopy(next_data))
    item = handoff(product, data)
    assert item.subs == ['/profile/Chinese.ass']
    assert product.state.saved[-1]['terminal_reason'] == 'STARTED'
    assert 'native_instance' not in product.state.saved[-1]
    product.actor.session.worker.join(1)
    product.state.position = 99
    product.actor.tick()
    product.state.playing = False
    product.actor.player.onPlayBackEnded()
    product.actor.tick()
    product.clock[0] += .3
    product.actor.tick()
    assert product.state.opened[-1][0] == next_data['url']
    assert product.state.opened[-1][1].subs == ['/profile/Chinese.ass']
    assert len(product.state.opened) == 2
    assert product.state.saved[-1]['completed']


@pytest.mark.parametrize('action', ['off', 'selection', 'account'])
def test_late_subtitle_never_auto_applies_over_user_intent(product, monkeypatch, action):
    event = Event()
    def slow(*args):
        event.wait(2)
        return {'file': '/profile/late.ass'}
    monkeypatch.setattr(product.module, 'discover', slow)
    product.actor.session.next_loader = None
    data = selected(product)
    product.actor.dispatch(dict(operation='subtitle_start', request_id=data['request_id'], data=data))
    item = handoff(product, data)
    assert item.subs == []
    if action == 'selection': selected(product, 'b')
    if action == 'account': product.account['epoch'] += 1
    event.set()
    product.actor.subtitle_worker.join(1)
    product.actor.tick()
    assert product.state.subtitles == []
    reply = product.actor.dispatch(dict(operation='subtitle_candidate', request_id=data['request_id']))
    assert bool(reply) is (action == 'off')


@pytest.mark.parametrize('kind', ['onPlayBackStopped', 'onPlayBackError'])
def test_actual_callback_stop_or_error_does_not_continue(product, kind):
    product.actor.session.next_loader = None
    handoff(product, selected(product))
    product.state.position = 99
    product.actor.tick()
    product.state.playing = False
    getattr(product.actor.player, kind)()
    product.actor.tick()
    product.actor.player.onPlayBackEnded()
    product.clock[0] += 1
    product.actor.tick()
    assert len(product.state.opened) == 1
    assert not product.state.saved[-1]['completed']


def test_history_disk_failure_cannot_stop_observation(product):
    def failed(data): raise OSError('disk')
    product.actor.session.history = failed
    product.actor.session.next_loader = None
    handoff(product, selected(product))
    assert product.actor.session.current['state'] == 'playing'
    assert product.actor.session.current['history_error']


@pytest.mark.parametrize('version,expected', [('1'*64, True), ('2'*64, False)])
def test_product_next_loader_uses_shared_exact_cloud_policy(product, monkeypatch, version, expected):
    # Only the storage/network boundary is a double. The resident loader uses
    # production next_cloud_data and cannot turn another release into next.
    data = selected(product)
    data.update(ids={'tmdb_id': 1087}, prepared_version_key='1'*64,
                prepared_source_info_hash='a'*40, prepared_resource_id='c'*64)
    row = dict(key='d'*64, season=1, episode=2, state='qualified', title='Release S01E02',
        path='/Series/E02.mkv', prepared_version_key=version, prepared_source_info_hash='a'*40)
    index = dict(mount_root='/media', titles=[dict(kind='tv', tmdb_id=1087, sources=[row])])
    monkeypatch.setitem(sys.modules, 'lib.clients.bobi_library', SimpleNamespace(
        load_prepared_index=lambda: index, local_path=lambda root, path: root+path))
    monkeypatch.setattr(product.module, 'resolve_selected', lambda data, cancelled: data)
    result = product.module.next_data(data, lambda: False)
    assert bool(result) == expected
    if expected:
        assert result['tv_data'] == {'season': 1, 'episode': 2}
        assert result['prepared_resource_id'] == 'd'*64
        assert result['url'] == '/media/Series/E02.mkv'
        assert result['request_id'] != data['request_id']
        assert result['_account'] == data['_account']


def ended_with_next(product):
    product.actor.session.next_loader = None
    data = selected(product)
    handoff(product, data)
    product.state.position = 99
    product.actor.tick()
    successor = dict(data, request_id='b'*32, url='https://media.example/b.mkv')
    product.actor.session.current['next_data'] = successor
    product.state.playing = False
    product.actor.player.onPlayBackEnded()
    product.actor.tick()
    return data, successor


def test_foreign_video_then_stop_never_resurrects_old_episode(product):
    data, successor = ended_with_next(product)
    product.clock[0] += .1
    product.state.item.props.clear()
    product.state.item.tag.ids.clear()
    product.state.url = 'https://media.example/external.mkv'
    product.state.playing = True
    product.actor.tick()
    assert product.actor.session.current['state'] == 'retired'
    assert product.actor.session.current['next_data'] is None
    product.clock[0] += 60
    product.state.playing = False
    product.actor.player.onPlayBackStopped()
    product.actor.tick()
    assert len(product.state.opened) == 1


@pytest.mark.parametrize('gap', ['read_failure', 'empty_path', 'missing_request'])
def test_seek_observation_gap_is_not_foreign_takeover(product, monkeypatch, gap):
    product.actor.session.next_loader = None
    data = selected(product)
    handoff(product, data)
    if gap == 'read_failure':
        def failed(): raise RuntimeError('seek/open transient')
        monkeypatch.setattr(product.actor.player, 'getTime', failed)
    elif gap == 'empty_path': product.state.url = ''
    else:
        product.state.item.props.clear()
        product.state.item.tag.ids.clear()
    product.actor.tick()
    assert product.actor.session.current_request(data['request_id'])
    assert product.actor.session.current['state'] == 'playing'


@pytest.mark.parametrize('boundary,status', [('item', 'before_submission_failed'),
    ('play', 'submission_unknown')])
def test_successor_exception_stays_in_request_and_host_keeps_running(product, monkeypatch, boundary, status):
    import bobbi_platform.kodi as kodi
    from lib import portable_runtime
    data, successor = ended_with_next(product)
    product.clock[0] += .3
    if boundary == 'play':
        original = sys.modules['xbmc'].Player.play
        def fail(player, url, item):
            original(player, url, item)
            raise RuntimeError('API failed after command may have been sent')
        monkeypatch.setattr(sys.modules['xbmc'].Player, 'play', fail)
    else:
        def fail(*args, **kwargs): raise RuntimeError('ListItem failed before send')
        monkeypatch.setattr(sys.modules['xbmcgui'], 'ListItem', fail)
    # Run the actual resident main/finally; only host IO and monitor are fake.
    state = SimpleNamespace(ticks=0, closed=False, abort=False)
    host = product.actor.host
    host.start = lambda: None
    host.configure_preparation = lambda *a: None
    host.configure_catalog_refresh = lambda *a: None
    def tick(): state.ticks += 1
    def close(): state.closed = True
    host.tick, host.close = tick, close
    def wait(seconds):
        state.abort = state.ticks >= 4
        return state.abort
    monkeypatch.setitem(sys.modules, 'bobbi_platform.host', SimpleNamespace(Host=lambda *a, **kw: host))
    monkeypatch.setitem(sys.modules, 'bobbi_platform.paths', SimpleNamespace(profile=lambda *a, **kw: '/test-profile'))
    monkeypatch.setitem(sys.modules, 'bobbi_core.runtime_paths', SimpleNamespace(
        configure=lambda *a, **kw: None, native_subtitle_abi=lambda *a: None))
    monkeypatch.setattr(sys.modules['xbmc'], 'Monitor', lambda: SimpleNamespace(waitForAbort=wait), raising=False)
    monkeypatch.setitem(sys.modules, 'lib.services.standard_playback', SimpleNamespace(StandardPlayback=lambda h: product.actor))
    portable_runtime.main({'native_contract_available': False})
    assert state.abort and state.ticks == 4 and state.closed
    assert product.actor.last_handoff == dict(request_id=successor['request_id'], status=status)
    assert len(product.state.opened) == (2 if boundary == 'play' else 1)
    assert product.state.reports[-1] == 'STANDARD_NEXT_' + status.upper()

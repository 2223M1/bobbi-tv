"""Actual independent entry constructors keep one account-free playback client."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/plugin.video.bobbi.torrent/lib'))
sys.path.insert(0, str(ROOT / 'tools'))

from bobbi_core import playback_request
from bobbi_core.playback_owner import PlaybackOwner
from bobbi_platform import playback_client, prepared_sessions
from bobbi_torrent import entry
from bobbi_torrent.backend import BackendError
from bobbi_torrent.owner import Owner
import ce_115_direct_kodi as diagnostic

RID = 'a' * 32
HASH = '1' * 40
MAGNET = 'magnet:?xt=urn:btih:' + HASH
FILE = dict(id=1, path='Fixture.mkv', length=1000000)


class Wire:
    """Real owner state and real Client algorithms, with local protocol replies."""
    def __init__(self, selected=None):
        self.owner = PlaybackOwner()
        if selected is not None:
            self.owner.select(self.owner.boot_id, 0, RID, selected)
        self.calls = []
        self.bound_url = None

    def __call__(self, message, timeout=.3):
        assert 0 < timeout <= .3
        self.calls.append(deepcopy(message))
        operation = message['operation']
        if operation == 'snapshot':
            return self.owner.snapshot()
        args = tuple(message[key] for key in ('boot_id', 'epoch', 'request_id'))
        if operation == 'select':
            return self.owner.select(*args, message['selection_identity'])
        if operation == 'bind_file':
            self.bound_url = message['url_sha256']
            return dict(bound=self.owner.bind_file(*args, message['selection_identity'],
                message['file_identity'], message['file_evidence']))
        if operation == 'claim_start':
            assert self.owner.claim_start(*args, message['route'])
            receipt = dict(message)
            receipt.pop('operation')
            receipt.update(file_identity=self.owner.desired['file_identity'], url_sha256=self.bound_url)
            return dict(status='CLAIMED', receipt=receipt)
        if operation == 'resolver_failed':
            return dict(recorded=self.owner.resolver_failed(*args, message['category']))
        if operation == 'cancel':
            return dict(cancelled=self.owner.cancel(*args))
        assert operation == 'torrent_subtitle_context'
        return dict(recorded=True)


class Item:
    def __init__(self, **kwargs):
        self.properties = {}

    def setProperty(self, key, value):
        self.properties[key] = value

    def setMimeType(self, mime): self.mime = mime
    def setContentLookup(self, value): self.lookup = value

    def getVideoInfoTag(self):
        return SimpleNamespace(setTitle=lambda value: None, setPlot=lambda value: None)


@pytest.fixture
def surface(monkeypatch):
    state = SimpleNamespace(properties={'bobbi_active_player_session': RID}, answers=[],
        backend_started=[], closed=[], prepared_captures=[])
    state.window = SimpleNamespace(getProperty=lambda key: state.properties.get(key, ''),
        setProperty=lambda key, value: state.properties.__setitem__(key, value))
    state.monitor = SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda seconds: False)
    def rpc(raw):
        method = json.loads(raw)['method']
        assert method in ('Player.BobiState', 'Player.GetActivePlayers')
        return json.dumps(dict(result={'playback': None} if method == 'Player.BobiState' else []))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: state.monitor,
        executeJSONRPC=rpc, log=lambda *args: None, LOGINFO=1, LOGWARNING=2))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda ident: state.window, ListItem=Item))
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(setResolvedUrl=lambda *args: state.answers.append(args)))
    monkeypatch.setitem(sys.modules, 'requests', SimpleNamespace(Session=lambda: SimpleNamespace(
        close=lambda: state.closed.append('download'))))
    monkeypatch.setattr(entry, 'load_config', lambda: {})
    def backend(config):
        state.backend_started.append(True)
        return SimpleNamespace(close=lambda: state.closed.append('backend'))
    monkeypatch.setattr(entry, 'Backend', backend)
    monkeypatch.setattr(prepared_sessions, 'capture',
        lambda: state.prepared_captures.append(True))  # Explicit optional None.
    monkeypatch.setattr(playback_request, 'call',
        lambda *a, **kw: pytest.fail('No ambient core playback transport'))
    # Runtime deliberately adds its installed addon paths; restore that process
    # list after the test instead of leaking device paths to unrelated tests.
    monkeypatch.setattr(sys, 'path', list(sys.path))
    return state


def argv():
    return ['plugin://plugin.video.bobbi.torrent/play_magnet', '7', '?' + urlencode(
        dict(selection_policy='exact', request_id=RID, magnet=MAGNET, title='Fixture'))]


def bind_capture(monkeypatch, client):
    calls = []
    def capture():
        calls.append(True)
        assert len(calls) == 1, 'An entry must never recapture from a later Host'
        return client
    monkeypatch.setattr(playback_client, 'capture', capture)
    return calls


def test_real_torrent_entry_captures_once_and_opens_without_prepared_session(surface, monkeypatch):
    wire = Wire('bt:' + HASH)
    client = playback_request.Client(wire)
    captures = bind_capture(monkeypatch, client)
    owners = []
    def resolve(resolver, request):
        owners.append(resolver.owner)
        assert resolver.owner.protocol is client and resolver.owner.prepared_session is None
        resolution = client.resolve_torrent(RID, MAGNET, HASH, HASH)
        return dict(info_hash=HASH, file=FILE, url='http://127.0.0.1/fixture', resolution=resolution)
    monkeypatch.setattr(entry.Resolver, 'resolve', resolve)

    entry.main(argv())

    assert captures == [True] and surface.prepared_captures == [True]
    assert len(owners) == 1 and isinstance(owners[0], Owner)
    assert [(handle, success) for handle, success, _ in surface.answers] == [(7, True)]
    item = surface.answers[0][2]
    assert item.mime == 'video/x-matroska' and item.lookup is False
    assert item.properties['bobitv.request_id'] == RID
    assert item.properties['bobitv.file_identity'] == client.torrent_file_identity(
        HASH, FILE['id'], FILE['path'], FILE['length'])
    operations = [row['operation'] for row in wire.calls]
    assert 'select' not in operations
    assert operations.count('bind_file') == operations.count('claim_start') == 1
    assert surface.closed == ['backend', 'download']


@pytest.mark.parametrize('change', ['request', 'cancelled', 'source'])
def test_torrent_entry_still_validates_original_request_and_selected_hash(surface, monkeypatch, change):
    wire = Wire('bt:' + ('2' * 40 if change == 'source' else HASH))
    if change == 'request':
        wire.owner.select(wire.owner.boot_id, wire.owner.epoch, 'b' * 32, 'bt:' + HASH)
    elif change == 'cancelled':
        wire.owner.cancel(wire.owner.boot_id, wire.owner.epoch, RID)
    captures = bind_capture(monkeypatch, playback_request.Client(wire))
    def resolve(resolver, request):
        resolver.owner.protocol.resolve_torrent(RID, MAGNET, HASH, HASH)
        pytest.fail('Mismatched selection cannot reach video admission')
    monkeypatch.setattr(entry.Resolver, 'resolve', resolve)

    entry.main(argv())

    assert captures == [True]
    assert [(handle, success) for handle, success, _ in surface.answers] == [(7, False)]
    assert not any(row['operation'] in ('select', 'bind_file', 'claim_start') for row in wire.calls)
    if change != 'source':
        assert not surface.backend_started
        assert all(row['operation'] == 'snapshot' for row in wire.calls)


def test_torrent_failed_entry_capture_does_not_discover_later_client(surface, monkeypatch):
    failed = playback_request.unavailable()
    captures = bind_capture(monkeypatch, failed)
    entry.main(argv())
    assert captures == [True] and not surface.backend_started
    assert [(handle, success) for handle, success, _ in surface.answers] == [(7, False)]

    # Owner's default is an explicit unavailable client, not another capture.
    monkeypatch.setattr(playback_client, 'capture', lambda: pytest.fail('Owner cannot discover a replacement'))
    owner = Owner(RID, window=surface.window, monitor=surface.monitor)
    for _ in range(2):
        with pytest.raises(BackendError, match='TORRENT_OWNER_UNAVAILABLE'):
            owner.active()
    assert owner.failure('metadata_timeout') is False
    assert owner.failure('metadata_timeout') is False


def test_real_diagnostic_constructor_reuses_one_client_for_view_select_bind_cancel(surface, monkeypatch, tmp_path):
    wire = Wire()
    client = playback_request.Client(wire)
    captures = bind_capture(monkeypatch, client)
    monkeypatch.setattr(prepared_sessions, 'capture', lambda: pytest.fail('Diagnostic playback needs no preparation account'))
    runtime = diagnostic.Runtime(tmp_path)
    assert runtime.protocol is client
    account = dict(account_id='115:' + 'c' * 64, epoch=3, authenticated=True)
    snapshot, native, players = runtime.view()
    selected = runtime.select(snapshot, RID, 'bt:' + HASH, account)
    identity = 'bt:' + HASH + '|diagnostic:file'
    context = runtime.bind(RID, identity, 'http://127.0.0.1/fixture')
    assert context == dict(boot_id=selected['boot_id'], epoch=selected['epoch'], request_id=RID, file_identity=identity)
    assert runtime.cancel_pending(dict(request_id='d' * 32)) == {'performed': False}
    assert runtime.cancel_pending(dict(request_id=RID)) == dict(performed=True, acknowledged=True)
    assert runtime.view()[0]['desired']['cancelled'] is True
    assert native == {'playback': None} and players == []
    assert captures == [True] and surface.prepared_captures == []
    operations = [row['operation'] for row in wire.calls]
    assert operations.count('select') == operations.count('bind_file') == operations.count('claim_start') == operations.count('cancel') == 1
    assert next(row for row in wire.calls if row['operation'] == 'select')['account_scope'] == account


def test_diagnostic_failed_capture_stays_unavailable_for_later_operations(surface, monkeypatch, tmp_path):
    captures = bind_capture(monkeypatch, playback_request.unavailable())
    runtime = diagnostic.Runtime(tmp_path)
    monkeypatch.setattr(playback_client, 'capture', lambda: pytest.fail('Failed entry cannot recapture'))
    for operation in (runtime.view,
            lambda: runtime.select(dict(boot_id='boot', epoch=0), RID, 'bt:' + HASH, {}),
            lambda: runtime.bind(RID, 'bt:' + HASH + '|file', 'http://127.0.0.1/fixture'),
            lambda: runtime.cancel_pending(dict(request_id=RID))):
        # bind_and_claim retains its existing bounded retry/deadline error;
        # neither that timeout nor the direct calls may reacquire a client.
        with pytest.raises(OSError):
            operation()
    assert captures == [True] and surface.prepared_captures == []

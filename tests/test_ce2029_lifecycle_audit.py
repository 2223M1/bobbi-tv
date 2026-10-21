"""Independent account-generation audit through the native preparation client.

Only Kodi method importing and the IPC transport/owner queue are substituted.
AccountManager, Host admission, client scope selection, Session, Intake and
DirectQueue are production implementations. No device or network is used.
"""
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import time
from threading import Event
from types import MethodType, ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))

from bobbi_core import preparation_client, direct_cloud, direct_cloud_client
from bobbi_core.account_readiness import AccountReadiness
from bobbi_core.capabilities import descriptor
from bobbi_core.ledger import Ledger
from bobbi_core.playback_owner import PlaybackOwner
from bobbi_core.preparation_host import Lease, Session
from bobbi_core.preparation_intake import Intake
from bobbi_platform.host import Host
from bobbi_platform.account_manager import AccountError
import bobbi_platform.runtime as runtime
from test_accounts import credential, logged_in


@pytest.fixture
def native_prepare(tmp_path, monkeypatch):
    accounts, initial = logged_in(tmp_path)
    clock, notices, logs, calls = [100.], [], [], []
    host = Host(tmp_path / 'host')
    host.accounts = accounts
    native = PlaybackOwner(boot_id='fixture-native')
    request = 'a' * 32
    snapshot = native.select(native.boot_id, 0, request, 'bt:' + 'b' * 40)
    native.bind_file(native.boot_id, snapshot['epoch'], request,
                     'bt:' + 'b' * 40, 'bt:' + 'b' * 40 + '|file')
    # Bypass only actor queue scheduling, retaining actual native owner state.
    host._owner_request = lambda body: native.snapshot()
    accounts.subscribe(host._account_changed)
    ledgers, queues = [], []
    sessions = {}

    def session_for(scope):
        key = (scope['account_id'], scope['epoch'])
        if key not in sessions:
            suffix = str(len(sessions))
            ledger = Ledger(tmp_path / ('ledger-' + suffix + '.sqlite'))
            ledgers.append(ledger)
            session = object.__new__(Session)
            session.lease = Lease(accounts, scope)
            session.intake = Intake(ledger)
            session.readiness = AccountReadiness('fixture')
            queue = direct_cloud.DirectQueue(tmp_path / ('direct-' + suffix + '.sqlite'),
                tmp_path / ('direct-' + suffix + '.json'), scope['account_id'],
                '/115open/fixture', SimpleNamespace(perform=lambda *a: pytest.fail('no cloud IO')),
                account_scope=scope)
            queues.append(queue)
            session.direct_queue = queue
            sessions[key] = session
        return sessions[key]

    def request_preparation(method, body, scope):
        accounts.require_current(scope)
        calls.append((method, deepcopy(scope)))
        return dict(ok=True, component=descriptor(), **session_for(scope).dispatch(method, body))

    host.preparation = SimpleNamespace(request=request_preparation)
    lost = [True]

    def transport(action, body, **kwargs):
        result = host.dispatch(action, body)
        if action == 'preparation' and body['method'] in ('prepare', 'catalog_prepare') and lost[0]:
            lost[0] = False
            raise OSError('fixture reply lost AFTER durable intake')
        return result

    monkeypatch.setattr(runtime, 'call', transport)
    # The installed catalogue can independently validate this exact fixture;
    # no directory listing, live provider or cloud operation is represented.
    monkeypatch.setattr(direct_cloud, 'validate_catalog', lambda body: direct_cloud.checked(body)[0])
    for name in ('lib', 'lib.cinema'):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, 'lib.cinema.preparation_client', preparation_client)
    path = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    source = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    names = {'start_cinema_preparation', 'start_direct_preparation', '_preparation_diagnostic'}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    data = dict(request_id=request, selection_policy='exact', is_torrent=True, mode='movie',
                ids={'tmdb_id': 1}, title='Fixture', source_title='Fixture.2025',
                info_hash='b' * 40)
    target = dict(request_id=request, session=request, source_info_hash='b' * 40,
                  torrent_file_id=1, torrent_path='Fixture.2025.mkv', torrent_file_bytes=16384)

    class InlineThread:
        def __init__(self, target, **kwargs): self.target = target
        def start(self): self.target()

    env = dict(monotonic=lambda: clock[0], loads=json.loads, re=re, Thread=InlineThread,
        get_property=lambda key: json.dumps(target) if key == 'bobbi_cinema_target' else '',
        kodilog=lambda value, **kwargs: logs.append(value),
        notification=lambda value, **kwargs: notices.append(value),
        xbmc=SimpleNamespace(LOGINFO=1, LOGWARNING=2))
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), env)
    player = SimpleNamespace(data=data, playback_session_id=request, _cinema_cancel=Event())
    player._owns_playback_session = lambda: not native.snapshot()['desired']['cancelled']
    for name in names:
        setattr(player, name, MethodType(env[name], player))
    state = SimpleNamespace(accounts=accounts, initial=initial, host=host, native=native,
        player=player, clock=clock, calls=calls, session_for=session_for, logs=logs)
    try:
        yield state
    finally:
        for queue in queues: queue.close()
        for ledger in ledgers: ledger.close()


@pytest.mark.parametrize('kind', ['bt', 'mdsub'])
@pytest.mark.parametrize('transition', ['renewal', 'switch', 'logout_return'])
def test_lost_intake_retry_cannot_transfer_old_playback_work_to_new_account(native_prepare, kind, transition):
    p = native_prepare
    if kind == 'mdsub':
        p.player.data.update(is_torrent=False, direct_source=dict(provider='mdsub',
            guid='mdsub:' + 'c' * 64, locator='https://pan.mdsub.top/api/raw?fixture',
            title='Fixture.2025.mkv', size=16384))
    p.player.start_cinema_preparation()
    method = 'catalog_prepare' if kind == 'mdsub' else 'prepare'
    assert p.calls == [(method, p.initial)]
    assert not getattr(p.player, '_direct_prepare_sent' if kind == 'mdsub' else '_cinema_prepare_sent', False)
    if transition == 'renewal':
        after = p.accounts.install(credential(suffix='new-session'), p.initial)
        assert after == p.initial
    elif transition == 'switch':
        after = p.accounts.install(credential('456'), p.initial)
    else:
        p.accounts.logout(p.initial)
        after = p.accounts.install(credential(), p.accounts.snapshot())
        assert after['account_id'] == p.initial['account_id'] and after != p.initial
    p.clock[0] = getattr(p.player, '_direct_prepare_due' if kind == 'mdsub' else '_cinema_prepare_due')
    p.player.start_cinema_preparation()
    # Changing the cloud account is not a user Stop for the independent BT or
    # public HTTP playback. Only its old cloud side work must lose admission.
    assert not p.player._cinema_cancel.is_set()
    assert p.player._owns_playback_session()
    if transition == 'renewal':
        assert [m for m, _ in p.calls].count(method) == 1
        assert getattr(p.player, '_direct_prepare_sent' if kind == 'mdsub' else '_cinema_prepare_sent')
    else:
        assert not [(m, scope) for m, scope in p.calls if scope == after], (
            'old playback background work was rebound to a new account generation', p.calls)


@pytest.mark.parametrize('kind', ['bt', 'mdsub'])
@pytest.mark.parametrize('scope_state', ['selected', 'unknown', 'legacy_retry'])
def test_existing_or_unknown_playback_scope_never_adopts_new_account(native_prepare, kind, scope_state):
    p = native_prepare
    if kind == 'mdsub':
        p.player.data.update(is_torrent=False, direct_source=dict(provider='mdsub',
            guid='mdsub:' + 'c' * 64, locator='https://pan.mdsub.top/api/raw?fixture',
            title='Fixture.2025.mkv', size=16384))
    if scope_state == 'selected':
        p.player.data['_account'] = deepcopy(p.initial)
    elif scope_state == 'unknown':
        p.player.data['_account'] = None
    else:
        setattr(p.player, '_direct_prepare_attempts' if kind == 'mdsub' else '_cinema_prepare_attempts', 1)
    p.accounts.install(credential('456'), p.initial)
    p.player.start_cinema_preparation()
    assert not p.calls
    assert not p.player._cinema_cancel.is_set()
    assert p.player._owns_playback_session()


def test_failed_initial_capture_is_retained_not_replaced_by_later_login(native_prepare, monkeypatch):
    p, calls = native_prepare, []
    original = runtime.call
    def unavailable(action, body, **kwargs):
        calls.append(action)
        if action == 'account_status':
            raise OSError('fixture status transport unavailable')
        return original(action, body, **kwargs)
    monkeypatch.setattr(runtime, 'call', unavailable)
    p.player.start_cinema_preparation()
    assert p.player.data['_account'] is None
    monkeypatch.setattr(runtime, 'call', original)
    p.accounts.install(credential('456'), p.initial)
    p.clock[0] = p.player._cinema_prepare_due
    p.player.start_cinema_preparation()
    assert calls == ['account_status'] and not p.calls
    assert not p.player._cinema_cancel.is_set()


@pytest.mark.parametrize('method', ['prepare', 'advance', 'status', 'resolve', 'font_preflight',
                                    'catalog_prepare', 'catalog_status', 'catalog_resolve'])
def test_explicit_client_scope_is_not_replaced_even_before_first_host_call(native_prepare, method):
    p = native_prepare
    p.accounts.install(credential('456'), p.initial)
    with pytest.raises(AccountError, match='ACCOUNT_CHANGED'):
        preparation_client.call(method, {}, expected_account=p.initial)
    assert not p.calls


def test_capture_returns_copies_without_importing_current_account(native_prepare, monkeypatch):
    p = native_prepare
    data = {'_account': deepcopy(p.initial)}
    def forbidden(*args, **kwargs):
        pytest.fail('existing scope must not query current account')
    monkeypatch.setattr(runtime, 'call', forbidden)
    captured = preparation_client.capture_account(data)
    assert captured == data['_account'] == p.initial
    assert captured is not data['_account']
    captured['epoch'] += 1
    assert data['_account'] == p.initial


@pytest.mark.parametrize('scope', [None, {}, {'epoch': 1}])
def test_invalid_explicit_scope_never_becomes_default_account(native_prepare, scope):
    with pytest.raises(AccountError, match='ACCOUNT_SCOPE_INVALID'):
        preparation_client.call('status', {}, expected_account=scope)
    assert not native_prepare.calls


def test_explicit_scope_cannot_fall_back_to_unscoped_legacy_socket(native_prepare):
    with pytest.raises(ValueError, match='Account-scoped'):
        preparation_client.call('status', {}, socket_path='fixture-unused.sock',
                                expected_account=native_prepare.initial)
    assert not native_prepare.calls


@pytest.mark.parametrize('operation', ['resolve', 'catalog_resolve', 'font_preflight'])
@pytest.mark.parametrize('transition', ['renewal', 'switch', 'logout_return'])
def test_retrying_read_clients_keep_original_scope_through_real_host(native_prepare, monkeypatch,
                                                                    operation, transition):
    p = native_prepare
    data = p.player.data
    entry = dict(key='c' * 64, state='ready', prepared_source_info_hash='b' * 40,
        prepared_file_id='123', path='/Fixture.mkv', bytes=16384, prepared_version_key='d' * 64,
        proof='fixture-proof', source={'size': 16384}, file={'path': '/Fixture.mkv'})
    data.update(prepared_resource_id=entry['key'], prepared_source_info_hash='b' * 40)
    snapshot = dict(generation=1, account='fixture-legacy-account')
    session = p.session_for(p.initial)
    session.readiness = SimpleNamespace(ready=True)
    count = [0]
    def request(body):
        count[0] += 1
        if count[0] == 1:
            if transition == 'renewal':
                p.accounts.install(credential(suffix='new-session'), p.initial)
            elif transition == 'switch':
                p.accounts.install(credential('456'), p.initial)
            else:
                p.accounts.logout(p.initial)
                p.accounts.install(credential(), p.accounts.snapshot())
            return dict(state='pending')
        if operation == 'resolve':
            return dict(body, state='ready', file_id=entry['prepared_file_id'], path=entry['path'],
                        bytes=entry['bytes'], version_key=entry['prepared_version_key'])
        if operation == 'catalog_resolve':
            return dict(body, state='ready', proof=entry['proof'], bytes=entry['bytes'],
                        path=direct_cloud.MOUNT + entry['path'])
        return dict(body, state='ready')
    session.resolve_lane = session.direct_resolve = session.font_preflight = SimpleNamespace(request=request)
    session.font_cache = True
    monkeypatch.setattr(direct_cloud_client, 'entry', lambda data: entry)
    if operation == 'resolve':
        invoke = lambda: preparation_client.resolve_entry(data, snapshot, entry)
    elif operation == 'catalog_resolve':
        invoke = lambda: direct_cloud_client.resolve(data)
    else:
        invoke = lambda: preparation_client.prepare_fonts(data, {'request_id': data['request_id']})
    if transition != 'renewal' and operation != 'font_preflight':
        with pytest.raises(AccountError, match='ACCOUNT_CHANGED'):
            invoke()
    else:
        result = invoke()
        if transition == 'renewal':
            assert result == entry if operation == 'resolve' else result['state'] == 'ready'
        else:
            assert result['state'] == 'unavailable'
    assert data['_account'] == p.initial
    assert count[0] == (2 if transition == 'renewal' else 1)
    assert p.calls == [(operation, p.initial)] * count[0]


def source_functions(relative, names, namespace):
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('representation', ['pending_direct', 'prepared_mirror', 'prepared_bt'])
def test_same_account_next_episode_preserves_scope_into_real_prepare_or_resolve(native_prepare, monkeypatch,
                                                                              representation):
    p = native_prepare
    current = dict(p.player.data, mode='tv', tv_data={'season': 1, 'episode': 1}, is_torrent=False,
        _account=deepcopy(p.initial), source_title='Fixture.S01E01.Group.mkv',
        prepared_version_key='d' * 64, prepared_source_info_hash='b' * 40,
        direct_source={'provider': 'mdsub'}, url='/115open/Fixture.S01E01.Group.mkv')
    fields = dict(guid='mdsub:' + 'c' * 64, url='https://pan.mdsub.top/api/raw?fixture',
                  title='Fixture.S01E02.Group.mkv', size=16384, indexer='fixture')
    following = dict(key='e' * 64, title=fields['title'], bytes=fields['size'], season=1, episode=2,
        state='qualified', prepared_qualification='f' * 64, prepared_source_info_hash='b' * 40,
        prepared_version_key='d' * 64, prepared_file_id='123', path='/Fixture.S01E02.Group.mkv')
    index = dict(mount_root='/115open', generation=1, account='fixture-legacy',
        titles=[] if representation == 'pending_direct' else
        [dict(kind='tv', tmdb_id=1, sources=[following])])
    namespace = source_functions('addons/plugin.video.bobbi/lib/utils/player/direct_continuity.py',
        {'episode_data', '_identity', 'next_direct_data'},
        dict(deepcopy=deepcopy, uuid4=uuid4, time=time))
    # Catalogue matching is separately tested; this probe starts with its
    # successful exact-next-file receipt and follows production payload clones.
    namespace['_mdsub'] = lambda *args: (dict(fields), 'INDEXED_DIRECT_SAME_RELEASE')
    for name in ('lib.clients', 'lib.utils', 'lib.utils.player', 'lib.utils.general'):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, ModuleType(name))
    library = ModuleType('lib.clients.bobi_library')
    library.local_path = lambda root, path: root + path
    monkeypatch.setitem(sys.modules, library.__name__, library)
    if representation == 'prepared_bt':
        direct = ModuleType('lib.utils.player.direct_continuity')
        direct.episode_data = namespace['episode_data']
        monkeypatch.setitem(sys.modules, direct.__name__, direct)
        dedupe = ModuleType('lib.utils.general.cinema_source_dedupe')
        dedupe._normalized_btih = lambda value: value
        monkeypatch.setitem(sys.modules, dedupe.__name__, dedupe)
        cloud = source_functions('addons/plugin.video.bobbi/lib/utils/player/continuity.py',
            {'next_cloud_data'}, dict(re=re, uuid4=uuid4))
        prepared = cloud['next_cloud_data'](current, index)
    else:
        prepared, _ = namespace['next_direct_data'](current, index)
    assert prepared['_account'] == p.initial and prepared['_account'] is not current['_account']
    assert preparation_client.capture_account(prepared, allow_capture=False) == p.initial
    assert p.accounts.install(credential(suffix='renewed'), p.initial) == p.initial
    monkeypatch.setattr(runtime, 'call', lambda action, body, **kwargs: p.host.dispatch(action, body))
    if representation == 'pending_direct':
        result = direct_cloud_client.prepare(prepared)
        assert result['state'] == 'queued'
        assert p.calls == [('catalog_prepare', p.initial)]
    else:
        session = p.session_for(p.initial)
        session.readiness = SimpleNamespace(ready=True)
        session.resolve_lane = SimpleNamespace(request=lambda body: dict(body, state='ready',
            file_id=following['prepared_file_id'], path=following['path'], bytes=following['bytes'],
            version_key=following['prepared_version_key']))
        assert preparation_client.resolve_entry(prepared, index, following) == following
        assert p.calls == [('resolve', p.initial)]


@pytest.mark.parametrize('url', ['https://public.example.invalid/movie.mkv',
                               'plugin://plugin.video.bobbi.torrent/play'])
@pytest.mark.parametrize('continuation', [False, True])
def test_failed_scope_capture_does_not_block_independent_native_video_entry(native_prepare, monkeypatch, url,
                                                                          continuation):
    p = native_prepare
    path = ROOT / 'addons/plugin.video.bobbi/lib/native_player.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    played = []
    env = dict(kodilog=lambda *a, **k: None, xbmc=SimpleNamespace(LOGWARNING=2),
               close_busy_dialog=lambda: None, make_listing=lambda data: dict(data))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), env)
    player = SimpleNamespace(_cinema_cancel=Event(), _was_superseded=False)
    def constants(data):
        player.data = dict(data)
        player.url = data['url']
    player.set_constants = constants
    player._activate_playback_session = lambda: True
    player._cinema_phase = lambda phase: None
    player.clear_playback_properties = lambda: None
    player._is_trakt_tracking_excluded = lambda: True
    player._drain_nextep_queue = lambda: False
    player.play_video = lambda item: played.append(item['url'])
    player.run_error = lambda error: pytest.fail('independent video failed: ' + type(error).__name__)
    requests = []
    def unavailable(*args, **kwargs):
        requests.append(args)
        raise OSError('fixture account status unavailable')
    monkeypatch.setattr(runtime, 'call', unavailable)
    env['run'](player, dict(selection_policy='exact', url=url, mode='movie', playnext_context=continuation))
    assert played == [url]
    assert player.data['_account'] is None
    assert not player._cinema_cancel.is_set()
    assert len(requests) == (0 if continuation else 1)

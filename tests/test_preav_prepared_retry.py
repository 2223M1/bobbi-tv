"""Exact pre-AV preference and real child/parent closure ordering, no device IO."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
from threading import Event, Thread
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit, urlencode

import pytest

from test_bobbi_torrent_adapter import (
    ROOT, RID, HASH, MAGNET, FILE, Clock, Session, Response, Item, FakeOwner,
    config, request, status, Backend, BackendError, Resolver)

sys.path.insert(0, str(ROOT / 'addons/plugin.video.bobbi'))
sys.path.insert(0, str(ROOT / 'tests/private_baseline'))
from bobbi_core import prepared_retry as retry, preparation_client as client, playback_ipc, playback_request
from bobbi_core.ledger import Ledger
from bobbi_core.preparation import PreparationQueue
from bobbi_core.prepared_index import document
from bobbi_core.prepared_resolver import PreparedResolver
from bobbi_core.resolve_lane import ResolveLane
from bobbi_core.playback_owner import PlaybackOwner
from bobbi_platform.account_manager import AccountManager, AccountError
from bobbi_torrent import entry
from bobbi_torrent.owner import Owner


def credentials(uid='123'):
    return dict(app='os_linux', cookies=dict(UID=uid + '_fixture', CID='fixture', SEID='fixture'))


@pytest.fixture
def ready(tmp_path, monkeypatch):
    accounts = AccountManager(tmp_path/'account.json')
    account = accounts.install(credentials(), accounts.snapshot())
    owner = PlaybackOwner()
    owner.select(owner.boot_id, 0, RID, 'bt:' + HASH)
    data = dict(request_id=RID, selection_policy='exact', is_torrent=True, info_hash=HASH,
        mode='tv', ids={'tmdb_id': '1'}, tv_data={'season': 1, 'episode': 1}, _account=account)
    selected = dict(source_info_hash=HASH, torrent_file_id=FILE['id'], torrent_path=FILE['path'],
                    torrent_file_bytes=FILE['length'])
    state = SimpleNamespace(account=account, accounts=accounts, owner=owner, data=data,
        intent=dict(request_id=RID, selected=selected), calls=[], provider_calls=0,
        hold=None, owner_reads=0)
    with Ledger(tmp_path/'ledger.db') as ledger:
        q = PreparationQueue(ledger)
        body = dict(provider='115', account=account['account_id'], destination='/115open/inbox',
            source_info_hash=HASH, media_id='tmdb:tv:1:s1:e1', version_key='b' * 64,
            bytes_required=FILE['length'], purpose='current')
        selection = dict(file=FILE, title='Series', release_title=FILE['path'], anime=False,
            request_id=RID, metadata_sha256='c' * 64, work_identity={'provider': 'tmdb'})
        task = q.request(body, selection)['task_id']
        q.begin_submission(task, 10000000, 9000000)
        q.submitted(task, True)
        q.observe(task, dict(account=account['account_id'], destination='/115open/inbox',
            source_info_hash=HASH, state='finished', file_id='root', parent_id='dest'))
        cloud = dict(provider='115', account=account['account_id'], file_id='cloud-file',
            cloud_path='/115open/inbox/' + FILE['path'], bytes=FILE['length'], kind='video',
            media_id=body['media_id'], version_key=body['version_key'])
        resource = ledger.register(cloud, managed=True, identity_verified=True)
        ledger.mark_ready(resource, dict(file_id='cloud-file', bytes=FILE['length'],
            version_key=body['version_key'], source_binding=True, read_bytes=500,
            probe_sha256='d' * 64, duration=1400, video_codec='hevc'))
        q.publish(task, resource, dict(source_info_hash=HASH, cloud_root_id='root',
            cloud_file_id='cloud-file', cloud_path=cloud['cloud_path'],
            torrent_path=FILE['path'], torrent_file_id=FILE['id'], bytes=FILE['length']))
        state.projection = dict(document(q, account['account_id']), account_scope=account)
        class Provider:
            def account_scope(self): return state.accounts.snapshot()['account_id']
            def identified_files(self, path):
                state.provider_calls += 1
                if state.hold is not None:
                    assert state.hold.wait(2)
                return [dict(file_id=cloud['file_id'], path=cloud['cloud_path'], bytes=FILE['length'],
                             directory=False, forbidden=False)]
        state.lane = ResolveLane(PreparedResolver(q, account['account_id'], Provider()))
        def service(method, body, timeout=.3, expected_account=None, **kwargs):
            assert method == 'resolve' and 0 < timeout <= .3
            state.accounts.require_current(expected_account)
            state.calls.append(deepcopy(body))
            state.lane.tick()
            result = state.lane.request(body)
            state.lane.tick()
            return result
        monkeypatch.setattr(client, 'call', service)
        monkeypatch.setattr(playback_ipc, 'call', lambda message, **kwargs: owner.snapshot())
        monkeypatch.setattr(retry, 'load_index', lambda: deepcopy(state.projection))
        try:
            yield state
        finally:
            if state.hold is not None:
                state.hold.set()
            state.lane.close()


def test_real_qualified_ledger_and_fresh_identity_resolver_produce_same_file_only(ready):
    result = retry.verified_entry(ready.data, None, ready.intent)
    assert result and result[1]['video_context']['selected'] == ready.intent['selected']
    assert ready.provider_calls == 1 and len({x['verification_id'] for x in ready.calls}) == 1
    assert ready.owner.snapshot()['desired']['start_claimed'] is False
    assert ready.owner.snapshot()['terminal'] is None


@pytest.mark.parametrize('change', ['file_id', 'path', 'bytes', 'hash', 'account_epoch', 'qualification',
                                   'claimed', 'observed', 'cancelled', 'new_request', 'no_scope'])
def test_not_exact_or_not_preav_never_authorizes_preference(ready, change):
    if change in ('file_id', 'path', 'bytes', 'hash'):
        key = dict(file_id='torrent_file_id', path='torrent_path', bytes='torrent_file_bytes', hash='source_info_hash')[change]
        ready.intent['selected'][key] = 'wrong' if change in ('path', 'hash') else 99
    elif change == 'account_epoch': ready.projection['account_scope'] = dict(ready.account, epoch=999)
    elif change == 'qualification': ready.projection['titles'][0]['sources'][0].pop('prepared_qualification')
    elif change == 'claimed': ready.owner.desired['start_claimed'] = True
    elif change == 'observed': ready.owner.observed = {'request_id': 'other'}
    elif change == 'cancelled': ready.owner.desired['cancelled'] = True
    elif change == 'new_request': ready.owner.desired['request_id'] = 'f' * 32
    else: ready.data.pop('_account')
    assert retry.verified_entry(ready.data, None, ready.intent) is None
    assert not ready.calls and ready.provider_calls == 0


@pytest.mark.parametrize('mutation', ['logout', 'switch', 'logout_login'])
def test_original_account_epoch_cannot_be_recaptured_by_poll(ready, mutation):
    if mutation == 'switch': ready.accounts.install(credentials('456'), ready.account)
    else:
        out = ready.accounts.logout(ready.account)
        if mutation == 'logout_login': ready.accounts.install(credentials(), out)
    assert retry.verified_entry(ready.data, None, ready.intent) is None
    assert ready.data['_account'] == ready.account and not ready.calls


def test_pending_real_resolve_job_reuses_nonce_and_completes_next_small_poll(ready):
    clock = Clock()
    probe = retry.ReadyProbe(ready.data, clock)
    ready.hold = Event()
    assert probe.poll(HASH, FILE, lambda: False, 90) is False
    first = probe.nonce
    assert first and ready.provider_calls == 1
    ready.hold.set()
    clock.now = .5
    assert probe.poll(HASH, FILE, lambda: False, 90) is True
    assert {row['verification_id'] for row in ready.calls} == {first}
    assert ready.provider_calls == 1 and clock.now < 90


@pytest.mark.parametrize('change', ['generation', 'qualification', 'account', 'path'])
def test_pending_nonce_is_not_retargeted_when_candidate_changes(ready, change):
    clock = Clock()
    probe = retry.ReadyProbe(ready.data, clock)
    ready.hold = Event()
    assert probe.poll(HASH, FILE, lambda: False, 90) is False
    count = len(ready.calls)
    if change == 'generation': ready.projection['generation'] += 1
    elif change == 'account': ready.projection['account_scope'] = dict(ready.account, epoch=999)
    elif change == 'path': ready.projection['titles'][0]['sources'][0]['path'] += '.other'
    else: ready.projection['titles'][0]['sources'][0]['prepared_qualification'] = 'f' * 64
    clock.now = .5
    assert probe.poll(HASH, FILE, lambda: False, 90) is False
    assert len(ready.calls) == count and probe.nonce is None


def test_late_owner_change_or_cancel_cannot_consume_ready_result(ready, monkeypatch):
    original = client.call
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if result.get('state') == 'ready':
            ready.owner.desired['start_claimed'] = True
        return result
    monkeypatch.setattr(client, 'call', changed)
    assert retry.verified_entry(ready.data, None, ready.intent) is None


def test_optional_context_is_bounded_account_scoped_and_request_specific(ready):
    url = 'plugin://plugin.video.bobbi.torrent/play_magnet?' + urlencode(
        dict(request_id=RID, selection_policy='exact', magnet=MAGNET))
    attached = retry.attach_context(url, ready.data)
    raw = parse_qs(urlsplit(attached).query)['ready_context'][0]
    context = retry.decode_context(raw, RID)
    assert context['_account'] == ready.account and len(raw.encode()) <= 1024
    assert not {'cookies', 'UID', 'CID', 'SEID'} & set(context)
    with pytest.raises(ValueError): retry.decode_context(raw, 'f' * 32)
    with pytest.raises(ValueError): retry.decode_context(' ' * 1025, RID)
    request_value = entry.parse_request(['plugin://plugin.video.bobbi.torrent/play_magnet', '7',
                                        '?' + urlsplit(attached).query])
    assert request_value['ready_context'] == raw
    assert retry.attach_context(url, dict(ready.data, _account=None)) == url


def test_resolver_ready_exit_is_before_preload_and_does_not_claim_or_delete():
    clock = Clock()
    owner = FakeOwner(clock)
    owner.prepared_source_ready = lambda *args: True
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status())])
    backend = Backend(config(), session, clock)
    with pytest.raises(BackendError) as error:
        Resolver(backend, owner, Session([]), clock).resolve(request())
    assert error.value.category == 'prepared_ready' and not backend.preload_attempted
    assert not owner.bindings and not owner.failures and clock.now == 0
    assert all(call[2].get('json', {}).get('action') not in ('drop', 'rem', 'set') for call in session.calls)


def test_pending_probe_does_not_extend_original_bt_buffer_deadline():
    clock = Clock()
    owner = FakeOwner(clock)
    deadlines = []
    def pending(req, source_hash, file, deadline):
        deadlines.append(deadline)
        clock.now += .3
        return False
    owner.prepared_source_ready = pending
    owner.wait_for_buffer = lambda detail: False
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status()), Response(b'')]
                      + [Response(status(ready=False)) for _ in range(10)])
    with pytest.raises(BackendError) as error:
        Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert error.value.category == 'buffer_timeout'
    assert len(set(deadlines)) == 1 and deadlines[0] == 2
    assert clock.now < 2.8  # No new 90-second budget or 30-second wait added by a probe.


def test_user_confirmed_file_never_enters_auto_ready_lane():
    file = dict(id=4, path='video.mkv', length=1000000)
    info, clock = status(file), Clock()
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: files[0]
    owner.prepared_source_ready = lambda *args: pytest.fail('A manual file is not automatic provenance')
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(info),
                       Response(info), Response(b''), Response(info)])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert result['file_evidence'] == 'USER_CONFIRMED_FILE' and not owner.targets


@pytest.mark.parametrize('failure', ['pending', 'unavailable', 'exception'])
def test_optional_lookup_failure_preserves_ordinary_bt_open(ready, monkeypatch, failure):
    clock = Clock()
    owner = FakeOwner(clock)
    probe = retry.ReadyProbe(ready.data, clock)
    def lookup(*args, **kwargs):
        if failure == 'pending': raise TimeoutError('synthetic pending')
        return None
    monkeypatch.setattr(retry, 'verified_entry', lookup)
    owner.prepared_source_ready = lambda req, source_hash, file, deadline: probe.poll(
        source_hash, file, lambda: False, deadline)
    if failure == 'exception':
        # The real Owner catches an unavailable optional dependency, not the Resolver.
        real = Owner(RID, protocol=SimpleNamespace(owned_state=lambda rid: ready.owner.snapshot()),
            window=SimpleNamespace(getProperty=lambda key: RID if key == 'bobbi_active_player_session' else ''),
            monitor=SimpleNamespace(abortRequested=lambda: False))
        context = dict(schema=1, **{k: ready.data[k] for k in
            ('request_id', 'info_hash', 'mode', 'ids', 'tv_data', '_account')})
        def unavailable(*args, **kwargs): raise RuntimeError('optional unavailable')
        monkeypatch.setattr(retry.ReadyProbe, 'poll', unavailable)
        owner.prepared_source_ready = lambda req, source_hash, file, deadline: real.prepared_source_ready(
            dict(req, ready_context=json.dumps(context)), source_hash, file, deadline)
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status()),
                       Response(b''), Response(status())])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(request())
    assert result['file'] == FILE and result['file_evidence'] == 'AUTO_VERIFIED_FILE'
    assert not owner.failures


def actual_parent(monkeypatch, owner, props, events):
    """Actual startup waiter and scoped cancellation; no invented return logic."""
    tree = ast.parse((ROOT/'addons/plugin.video.bobbi/lib/native_player.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JacktookPLayer')
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in {'_wait_for_video_start', 'cancel_playback', 'monitor'}]
    module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Parent', bases=[], keywords=[],
        body=methods, decorator_list=[])], type_ignores=[]))
    env = dict(monotonic=time.monotonic, sleep=lambda ms: time.sleep(ms/1000),
        get_property=lambda key: props.get(key, ''), set_property=lambda key, value: props.__setitem__(key, value),
        loads=json.loads, kodilog=lambda *args, **kwargs: None,
        xbmc=SimpleNamespace(LOGINFO=1, LOGWARNING=2, LOGERROR=3))
    exec(compile(module, 'actual-parent-waiter', 'exec'), env)
    parent = env['Parent']()
    parent.data = dict(selection_policy='exact', is_torrent=True)
    parent.playback_session_id = RID
    parent._cinema_cancel = Event()
    parent._startup_timeout_seconds = lambda: 3.0
    parent._owns_playback_session = lambda: bool(owner.desired and owner.desired['request_id'] == RID
                                                and not owner.desired['cancelled'])
    parent.kodi_monitor = SimpleNamespace(abortRequested=lambda: False)
    parent.isPlayingVideo = lambda: False
    parent.start_cinema_preparation = lambda **kwargs: None
    parent._read_startup_failure = lambda: None
    parent.on_error = lambda: events.append('parent_error_callback')
    parent._cleanup_playback_session = lambda: events.append('parent_cleanup')
    parent._owner_context = playback_request.context(owner.snapshot(), RID)
    parent._resolution_answered = True
    parent.clear_playback_properties = lambda: events.append('clear_properties')
    parent._release_playback_session = lambda: events.append('release_session')
    parent._cinema_phase = lambda phase: events.append(phase)
    return parent


@pytest.fixture
def pipeline(monkeypatch):
    """Real entry.main -> execute -> Resolver -> Owner, with a ready IO fixture."""
    owner = PlaybackOwner()
    owner.select(owner.boot_id, 0, RID, 'bt:' + HASH)
    events, props = [], {'bobbi_active_player_session': RID}
    state = SimpleNamespace(owner=owner, events=events, props=props, gates={}, throws=set(), child_errors=[])
    def dispatch(message, **kwargs):
        operation = message['operation']
        if operation == 'snapshot': return owner.snapshot()
        args = (message['boot_id'], message['epoch'], message['request_id'])
        if operation == 'resolver_failed':
            events.append('publish_' + message['category'])
            return {'recorded': owner.resolver_failed(*args, message['category'])}
        if operation == 'cancel': return {'cancelled': owner.cancel(*args)}
        raise AssertionError(operation)
    monkeypatch.setattr(playback_request, 'call', dispatch)
    monkeypatch.setattr(playback_ipc, 'call', dispatch)
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', playback_request)
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_ipc', playback_ipc)
    def checkpoint(name):
        events.append(name + '_entered')
        if name in state.gates:
            entered, release = state.gates[name]
            entered.set()
            assert release.wait(2)
        if name in state.throws:
            raise RuntimeError('synthetic uncertain operation')
        events.append(name + '_returned')
    window = SimpleNamespace(getProperty=lambda key: props.get(key, ''),
        setProperty=lambda key, value: props.__setitem__(key, value))
    monitor = SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda seconds: False)
    child_owner = Owner(RID, protocol=playback_request, window=window, monitor=monitor)
    monkeypatch.setattr(entry, 'Owner', lambda request_id: child_owner)
    bt_session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}), Response(status())])
    bt_session.close = lambda: checkpoint('backend_close')
    download_session = SimpleNamespace(close=lambda: checkpoint('download_close'))
    monkeypatch.setattr(entry, 'load_config', lambda: config())
    monkeypatch.setattr(entry, 'Backend', lambda settings: Backend(settings, bt_session))
    monkeypatch.setattr(retry.ReadyProbe, 'poll', lambda self, *args: True)
    monkeypatch.setitem(sys.modules, 'requests', SimpleNamespace(Session=lambda: download_session))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(log=lambda *args: None, LOGINFO=1, LOGWARNING=2))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=Item))
    def answer(handle, success, item):
        assert handle == 7 and success is False
        checkpoint('answer_false')
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(setResolvedUrl=answer))
    account = dict(account_id='115:' + 'a' * 64, epoch=3, authenticated=True)
    context = dict(schema=1, request_id=RID, info_hash=HASH, mode='tv', ids={'tmdb_id': '1'},
                   tv_data={'season': 1, 'episode': 1}, _account=account)
    args = request(ready_context=json.dumps(context))
    args.pop('action')
    state.argv = ['plugin://plugin.video.bobbi.torrent/play_magnet', '7', '?' + urlencode(args)]
    def run():
        try: entry.main(state.argv)
        except Exception as error: state.child_errors.append(error)
    state.run = run
    state.parent = actual_parent(monkeypatch, owner, props, events)
    return state


def test_actual_parent_never_reselects_before_real_handle_and_both_sessions_close(pipeline):
    state = pipeline
    for name in ('answer_false', 'backend_close', 'download_close'):
        state.gates[name] = (Event(), Event())
    parent_done, outcome = Event(), []
    def wait_parent():
        outcome.append(state.parent._wait_for_video_start())
        parent_done.set()
    child, parent = Thread(target=state.run), Thread(target=wait_parent)
    parent.start()
    child.start()
    try:
        for name in ('answer_false', 'backend_close', 'download_close'):
            entered, release = state.gates[name]
            assert entered.wait(1)
            assert state.owner.desired['resolver_failure'] is None and not parent_done.is_set()
            release.set()
        child.join(1)
        assert parent_done.wait(1)
        parent.join(1)
    finally:
        for _, release in state.gates.values(): release.set()
        child.join(2)
        parent.join(4)
    assert outcome == [False] and not state.child_errors
    assert state.parent._startup_failure_category == 'prepared_ready'
    assert state.events.index('download_close_returned') < state.events.index('publish_prepared_ready')
    assert state.events.index('publish_prepared_ready') < state.events.index('parent_error_callback')
    assert state.owner.desired['start_claimed'] is False and state.owner.observed is None
    assert state.owner.terminal is None
    assert state.owner.desired['cancelled'] is False and not state.parent._cinema_cancel.is_set()
    assert state.props.get('bobbi_cinema_cancel') != RID


def test_actual_monitor_finally_does_not_turn_ready_handoff_into_cancel(pipeline):
    pipeline.run()
    pipeline.parent.monitor()
    before = pipeline.owner.snapshot()
    assert before['desired']['cancelled'] is False and not pipeline.parent._cinema_cancel.is_set()
    assert pipeline.props.get('bobbi_cinema_cancel') != RID
    assert pipeline.parent._startup_failure_category == 'prepared_ready'
    pipeline.owner.cancel(pipeline.owner.boot_id, pipeline.owner.epoch, RID)
    after = pipeline.owner.snapshot()
    assert not retry.unchanged(before, after)
    data = dict(request_id=RID, info_hash=HASH, is_torrent=True, selection_policy='exact')
    assert not retry.eligible(after, data, 'prepared_ready')


@pytest.mark.parametrize('signal', ['event', 'property', 'abort'])
@pytest.mark.parametrize('when', ['before', 'during_ui_close', 'before_finally'])
def test_user_cancel_or_abort_wins_same_tick_as_ready(pipeline, signal, when):
    pipeline.run()
    state = pipeline
    def cancel():
        if signal == 'event': state.parent._cinema_cancel.set()
        elif signal == 'property': state.props['bobbi_cinema_cancel'] = RID
        else: state.parent.kodi_monitor.abortRequested = lambda: True
    if when == 'before': cancel()
    elif when == 'during_ui_close': state.parent.on_error = cancel
    else:
        actual_wait = state.parent._wait_for_video_start
        def wait_then_cancel():
            result = actual_wait()
            cancel()
            return result
        state.parent._wait_for_video_start = wait_then_cancel
    state.parent.monitor()
    assert state.owner.desired['cancelled'] is True and state.parent._cinema_cancel.is_set()
    assert state.parent._startup_failure_category == ('aborted' if signal == 'abort' else 'cancelled')
    assert state.parent._startup_failed_for_reselect is False
    assert not retry.eligible(state.owner.snapshot(), dict(request_id=RID, info_hash=HASH,
        is_torrent=True, selection_policy='exact'), 'prepared_ready')


@pytest.mark.parametrize('category', ['buffer_timeout', 'preload_error'])
def test_old_buffer_failure_keeps_its_existing_cancellation_and_retry_behavior(pipeline, category):
    assert pipeline.owner.resolver_failed(pipeline.owner.boot_id, pipeline.owner.epoch, RID, category)
    pipeline.parent.monitor()
    assert pipeline.owner.desired['cancelled'] is True and pipeline.parent._cinema_cancel.is_set()
    assert pipeline.props['bobbi_cinema_cancel'] == RID
    assert retry.eligible(pipeline.owner.snapshot(), dict(request_id=RID, info_hash=HASH,
        is_torrent=True, selection_policy='exact'), category)


@pytest.mark.parametrize('throws', ['answer_false', 'backend_close', 'download_close'])
def test_unknown_answer_or_close_never_publishes_ready_receipt_or_answers_twice(pipeline, throws):
    pipeline.throws.add(throws)
    pipeline.run()
    assert pipeline.events.count('answer_false_entered') == 1
    assert 'publish_prepared_ready' not in pipeline.events
    assert pipeline.owner.desired['resolver_failure'] is None
    assert pipeline.owner.desired['start_claimed'] is False
    assert 'download_close_entered' in pipeline.events


@pytest.mark.parametrize('change', ['claimed', 'observed', 'cancelled', 'new_request'])
def test_ready_closed_publication_cannot_override_new_or_claimed_owner(pipeline, change):
    if change == 'claimed': pipeline.owner.desired['start_claimed'] = True
    elif change == 'observed': pipeline.owner.observed = {'request_id': 'other'}
    elif change == 'cancelled': pipeline.owner.desired['cancelled'] = True
    else: pipeline.owner.select(pipeline.owner.boot_id, pipeline.owner.epoch, 'b' * 32, 'other')
    pipeline.run()
    assert (pipeline.owner.desired['resolver_failure'] or {}).get('category') != 'prepared_ready'


@pytest.mark.parametrize('mutation', ['none', 'logout', 'switch', 'logout_login'])
def test_fresh_retry_cas_uses_real_account_generation_lock(tmp_path, monkeypatch, mutation):
    from test_playback_authority import Native, PlaybackAuthority
    native, accounts = Native(), AccountManager(tmp_path/'accounts.json')
    account = accounts.install(credentials(), accounts.snapshot())
    authority = PlaybackAuthority(native)
    authority.configure_accounts(accounts)
    monkeypatch.setattr(playback_request, 'call', authority.dispatch)
    before = authority.dispatch({'operation': 'snapshot'})
    if mutation == 'switch': accounts.install(credentials('456'), account)
    elif mutation != 'none':
        out = accounts.logout(account)
        if mutation == 'logout_login': accounts.install(credentials(), out)
    if mutation != 'none':
        with pytest.raises(AccountError):
            playback_request.select(before, RID, 'prepared:exact', account_scope=account)
        assert authority.owner.desired is None and native.epoch == 0
    else:
        playback_request.select(before, RID, 'prepared:exact', account_scope=account)
        assert authority.selection_account == account and authority.owner.desired['request_id'] == RID


def test_actual_source_selection_passes_frozen_account_only_for_automatic_retry(monkeypatch):
    tree = ast.parse((ROOT/'addons/plugin.video.bobbi/lib/gui/source_select.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SourceSelect')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_resolve_item')
    # Annotations are irrelevant to execution and avoid importing the GUI graph.
    for arg in method.args.args: arg.annotation = None
    method.returns = None
    module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Selector', bases=[], keywords=[],
        body=[method], decorator_list=[])], type_ignores=[]))
    calls = []
    monkeypatch.setitem(sys.modules, 'lib.cinema.playback_request', SimpleNamespace(
        select=lambda *args, **kwargs: calls.append((args, kwargs)) or dict(
            boot_id=args[0]['boot_id'], epoch=args[0]['epoch'] + 1,
            desired=dict(request_id=args[1], cancelled=False)),
        context=playback_request.context, source_identity=lambda source: 'prepared:exact'))
    from uuid import uuid4
    env = dict(uuid4=uuid4, set_property=lambda *args: None)
    exec(compile(module, 'actual-source-selection', 'exec'), env)
    obj = env['Selector']()
    obj._native_owner, obj._selection_locked = True, False
    account = dict(account_id='115:' + 'a' * 64, epoch=3, authenticated=True)
    owner = PlaybackOwner()
    owner.select(owner.boot_id, 0, RID, 'bt:' + HASH)
    owner.resolver_failed(owner.boot_id, owner.epoch, RID, 'prepared_ready')
    obj.item_information, obj._control_snapshot = {'_account': {'stale': True}}, owner.snapshot()
    obj.setProperty, obj.close = lambda *args: None, lambda: None
    obj._resolve_item(object(), retry_account=account)
    assert calls[-1][1] == dict(account_scope=account, retry_from=dict(request_id=RID,
        selection_identity='bt:' + HASH, category='prepared_ready'))
    assert obj.item_information['_account'] == account
    obj._selection_locked = False
    obj._resolve_item(object())
    assert calls[-1][1] == {} and '_account' not in obj.item_information
    obj._selection_locked = False
    before = len(calls)
    obj._resolve_item(object(), retry_account=account, retry_cancelled=lambda: True)
    assert len(calls) == before and obj._selection_locked is False


@pytest.fixture
def admission(tmp_path):
    from test_playback_authority import Native, PlaybackAuthority
    native, accounts = Native(), AccountManager(tmp_path/'guard-account.json')
    scope = accounts.install(credentials(), accounts.snapshot())
    authority = PlaybackAuthority(native)
    authority.configure_accounts(accounts)
    before = authority.dispatch({'operation': 'snapshot'})
    initial = dict(operation='select', boot_id=before['boot_id'], epoch=before['epoch'],
                   request_id=RID, selection_identity='bt:' + HASH)
    authority.dispatch(initial)
    context = dict(boot_id=authority.owner.boot_id, epoch=authority.owner.epoch, request_id=RID)
    assert authority.dispatch(dict(context, operation='resolver_failed', category='prepared_ready'))['recorded']
    command = dict(operation='select', boot_id=context['boot_id'], epoch=context['epoch'],
        request_id='c' * 32, selection_identity='prepared:' + 'd' * 64, account_scope=scope,
        retry_from=dict(request_id=RID, selection_identity='bt:' + HASH, category='prepared_ready'))
    return SimpleNamespace(authority=authority, native=native, accounts=accounts, scope=scope,
                           context=context, command=command)


def test_service_guard_admits_closed_ready_once_without_native_stop(admission):
    state = admission.authority.dispatch(admission.command)
    assert state['desired']['request_id'] == 'c' * 32 and state['epoch'] == admission.context['epoch'] + 1
    assert admission.authority.selection_account == admission.scope and admission.native.commands == []
    epoch = admission.native.epoch
    with pytest.raises(ValueError): admission.authority.dispatch(admission.command)
    assert admission.native.epoch == epoch


@pytest.mark.parametrize('change', ['stop', 'claimed', 'observed_once', 'observed', 'new_request',
                                   'wrong_category', 'wrong_selection', 'epoch', 'boot', 'account'])
def test_service_guard_rejects_changes_after_last_client_snapshot_without_new_native_intent(admission, change):
    authority, native = admission.authority, admission.native
    if change == 'stop': authority.dispatch(dict(admission.context, operation='cancel'))
    elif change == 'claimed': authority.owner.desired['start_claimed'] = True
    elif change == 'observed_once': authority.owner.desired['observed_once'] = True
    elif change == 'observed':
        from test_playback_authority import row
        native.current = row('f' * 32, 'other-file')
        authority.refresh()
    elif change == 'new_request':
        authority.dispatch(dict(admission.command, request_id='e' * 32, retry_from=admission.command['retry_from']))
    elif change == 'wrong_category': authority.owner.desired['resolver_failure']['category'] = 'buffer_timeout'
    elif change == 'wrong_selection': authority.owner.desired['selection_identity'] = 'bt:' + 'f' * 40
    elif change == 'epoch': admission.command['epoch'] += 1
    elif change == 'boot': admission.command['boot_id'] = 'old'
    else: admission.accounts.logout(admission.scope)
    before, epoch = authority.owner.snapshot(), native.epoch
    with pytest.raises((ValueError, RuntimeError)):
        authority.dispatch(admission.command)
    assert authority.owner.snapshot() == before and native.epoch == epoch


@pytest.mark.parametrize('change', ['none', 'empty', 'extra', 'request', 'selection', 'category',
                                   'category_object', 'same_request', 'non_prepared', 'no_account'])
def test_service_guard_rejects_malformed_or_downgraded_automatic_commands(admission, change):
    command = deepcopy(admission.command)
    if change == 'none': command['retry_from'] = None
    elif change == 'empty': command['retry_from'] = {}
    elif change == 'extra': command['retry_from']['trusted'] = True
    elif change == 'request': command['retry_from']['request_id'] = 'bad'
    elif change == 'selection': command['retry_from']['selection_identity'] = 'transport:' + 'f' * 64
    elif change == 'category': command['retry_from']['category'] = 'NATURAL_EOF'
    elif change == 'category_object': command['retry_from']['category'] = {}
    elif change == 'same_request': command['request_id'] = RID
    elif change == 'non_prepared': command['selection_identity'] = 'bt:' + HASH
    else: command.pop('account_scope')
    before, epoch = admission.authority.owner.snapshot(), admission.native.epoch
    with pytest.raises((ValueError, RuntimeError)): admission.authority.dispatch(command)
    assert admission.authority.owner.snapshot() == before and admission.native.epoch == epoch


def test_manual_select_after_user_stop_still_is_a_fresh_explicit_choice(admission):
    admission.authority.dispatch(dict(admission.context, operation='cancel'))
    command = dict(admission.command)
    command.pop('retry_from')
    command.pop('account_scope')
    state = admission.authority.dispatch(command)
    assert state['desired']['request_id'] == command['request_id'] and not state['desired']['cancelled']


@pytest.mark.parametrize('category', ['buffer_timeout', 'preload_error'])
def test_old_closed_buffer_retry_retains_legacy_internal_cancel_semantics(admission, category):
    admission.authority.owner.desired['resolver_failure']['category'] = category
    admission.authority.dispatch(dict(admission.context, operation='cancel'))
    admission.command['retry_from']['category'] = category
    state = admission.authority.dispatch(admission.command)
    assert state['desired']['request_id'] == admission.command['request_id']

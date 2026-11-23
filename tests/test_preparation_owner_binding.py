"""Real resident actor/account-lock controls; no device or provider IO."""
from copy import deepcopy
import hashlib
import inspect
import json
from queue import Queue
import struct
from threading import Event, Thread, get_ident
import time
from types import SimpleNamespace

import pytest

from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_core.preparation_host import Lease, Session
from bobbi_core.prepared_index import MOUNT_ROOT
from bobbi_platform import runtime
from bobbi_platform.host import Host
from bobbi_platform.instance_lock import InstanceLock
from test_preparation_composition import setup

FILE_PATH = '/115open/fixture/Fixture.mkv'
URL_HASH = hashlib.sha256((MOUNT_ROOT + FILE_PATH).encode()).hexdigest()
FILE_IDENTITY = 'bt:' + 'd' * 40 + '|transport:' + URL_HASH


class NativeIdle:
    def __init__(self):
        self.epoch = 0
        self.commands = []

    def state(self):
        return dict(protocol=1, selection_epoch=self.epoch, playback=None,
                    gui_generation=0, gui_user_intent=0, fullscreen_instance='')

    def intent(self, body):
        assert body['expected_epoch'] == self.epoch
        self.epoch += 1
        return dict(reserved=True, selection_epoch=self.epoch)

    def control(self, body):
        self.commands.append(deepcopy(body))
        return dict(queued=True, command_id=body['command_id'])


class RecordedQueue(Queue):
    def __init__(self):
        super().__init__(maxsize=32)
        self.jobs = []

    def put_nowait(self, job):
        self.jobs.append(job)
        super().put_nowait(job)


@pytest.fixture
def account_font_actor(setup, tmp_path, monkeypatch):
    host = Host(tmp_path / 'platform', plugin_root=setup.root)
    host.accounts = setup.accounts
    host.calls = RecordedQueue()
    host.engine_check = float('inf')
    ready, stop = Event(), Event()
    cas_entered, cas_completed = Event(), Event()
    state = SimpleNamespace(errors=[], native=NativeIdle(), guard_results=[],
                            observing=False, actor_ident=None)
    original_commit = setup.accounts.run_if_current

    def observed_commit(scope, operation, authenticated=True):
        observed = state.observing and get_ident() == state.actor_ident
        if observed:
            cas_entered.set()
        result = original_commit(scope, operation, authenticated=authenticated)
        if observed:
            cas_completed.set()
        return result

    # Observe the real AccountManager CAS; its lock, validation and operation
    # remain untouched. In particular, do not bypass authority.dispatch.
    monkeypatch.setattr(setup.accounts, 'run_if_current', observed_commit)

    def actor():
        try:
            state.actor_ident = get_ident()
            authority = PlaybackAuthority(state.native)
            authority.configure_accounts(setup.accounts)
            args = dict(boot_id=authority.owner.boot_id, epoch=0, request_id='a' * 32)
            selected = authority.dispatch(dict(args, operation='select',
                selection_identity='fixture-selection', account_scope=setup.scope))
            args['epoch'] = selected['epoch']
            assert authority.dispatch(dict(args, operation='bind_file',
                selection_identity='fixture-selection', file_identity=FILE_IDENTITY,
                url_sha256=URL_HASH)) == dict(bound=True)
            assert authority.dispatch(dict(args, operation='claim_start',
                route='resolved_url')) == dict(status='CLAIMED')
            state.body = dict(args, file_identity=FILE_IDENTITY,
                              resource_id='c' * 64, source_info_hash='d' * 40)
            state.authority = authority

            def dispatch(body):
                result = authority.dispatch(body)
                if body.get('operation') == 'font_preflight_guard':
                    state.guard_results.append(result)
                    if hasattr(state, 'after_guard'):
                        state.after_guard()
                return result

            host.bind_owner(dispatch)
            state.observing = True
            ready.set()
            while not stop.wait(.001):
                host.tick()
        except BaseException as error:
            state.errors.append(error)
            ready.set()

    worker = Thread(target=actor, name='fixture-real-playback-actor', daemon=True)
    worker.start()
    session = None
    try:
        assert ready.wait(2) and not state.errors
        # Substitute only the transport, retaining the actual Host queue and
        # the actual account-scoped PlaybackAuthority dispatch on its thread.
        monkeypatch.setattr(runtime, 'call',
            lambda action, body, timeout=.3: host.dispatch(action, body))
        config = dict(setup.config, font_tool='not-executed',
                      font_native_directory=str(tmp_path / 'native-fonts'))
        # Retain the diagnostic controls on the original source as well as B.
        ports = (dict(owner_call=lambda body: host.dispatch('playback', body))
                 if 'owner_call' in inspect.signature(Session).parameters else {})
        if 'subtitle_exporter' in inspect.signature(Session).parameters:
            ports['subtitle_exporter'] = host.export_subtitle
        session = Session(setup.root, config, Lease(setup.accounts, setup.scope),
            lambda: False, lambda _: None, lock_factory=InstanceLock, **ports)
        state.session, state.host = session, host
        state.cas_entered, state.cas_completed = cas_entered, cas_completed
        yield state
    finally:
        if session is not None:
            session.close()
        stop.set()
        worker.join(2)
        assert not worker.is_alive() and not state.errors
        host.close()


def test_account_scoped_font_guard_succeeds_through_real_queue_without_outer_account_lock(account_font_actor):
    p = account_font_actor
    assert p.session.font_preflight.worker.allowed(p.body) is True
    assert p.cas_entered.is_set() and p.cas_completed.is_set()
    assert p.guard_results == [dict(allowed=True)]
    assert p.authority.selection_account == p.session.lease.scope
    assert p.actor_ident != get_ident()
    assert p.host.calls.jobs[-1].value['operation'] == 'font_preflight_guard'
    assert not p.native.commands


def test_current_session_font_lane_outer_account_lock_forces_guard_timeout(account_font_actor):
    p = account_font_actor
    assert p.session.font_preflight.request(p.body)['state'] == 'pending'
    began = time.monotonic()
    # This was the production expression before B: the real lane calls
    # the real Session font guard while Lease.commit owns AccountManager.lock.
    p.session.lease.commit(p.session.font_preflight.tick)
    elapsed = time.monotonic() - began
    assert p.cas_entered.is_set()
    assert p.session.font_preflight.request(p.body) == dict(state='stale')
    assert .20 <= elapsed < 1.0
    job = p.host.calls.jobs[-1]
    assert job.value['operation'] == 'font_preflight_guard' and job.cancelled
    # Releasing the preparation-side CAS finally lets the native actor enter
    # its own genuine CAS. The caller has already lost the same valid guard.
    assert p.cas_completed.wait(1) and job.done.wait(1)
    assert p.guard_results == [dict(allowed=True)]
    assert not p.native.commands


def font_bytes(family):
    text = family.encode('utf-16-be')
    name = struct.pack('>HHH', 0, 1, 18) + struct.pack('>HHHHHH', 3, 1, 0x409, 1, len(text), 0) + text
    os2 = bytearray(64)
    struct.pack_into('>H', os2, 4, 400)
    return (b'\0\1\0\0' + struct.pack('>HHHH', 2, 0, 0, 0)
        + struct.pack('>4sIII', b'name', 0, 44, len(name))
        + struct.pack('>4sIII', b'OS/2', 0, 44 + len(name), len(os2)) + name + bytes(os2))


def ass_bytes(family):
    return ('[Script Info]\n[V4+ Styles]\nFormat: Name,Fontname,Bold,Italic\n'
        'Style: Default,' + family + ',0,0\n[Events]\nFormat: Start,End,Style,Text\n'
        'Dialogue: 0:00:01.00,0:00:04.00,Default,真实中文对白\n').encode()


@pytest.fixture
def prepared_fonts(account_font_actor, tmp_path, monkeypatch):
    from bobbi_core.subtitle_binding import prepared_video
    from bobbi_core.subtitle_export import export
    p = account_font_actor
    session, body = p.session, p.body
    ledger, queue, cache = session.ledger, session.queue, session.font_cache
    request = dict(provider='115', account=session.config['account'], destination='/115open/fixture',
        source_info_hash=body['source_info_hash'], media_id='tmdb:movie:1', version_key='e' * 64,
        bytes_required=1000, purpose='current')
    selected = dict(file=dict(id=7, path='Fixture.mkv', length=1000), title='Fixture',
        release_title='Fixture', anime=False, request_id=body['request_id'],
        metadata_sha256='f' * 64, work_identity={'provider': 'tmdb'})
    task = queue.request(request, selected)['task_id']
    queue.begin_submission(task, 100000, 90000)
    queue.submitted(task, True)
    queue.observe(task, dict(account=request['account'], destination=request['destination'],
        source_info_hash=request['source_info_hash'], state='finished', file_id='root', parent_id='dest'))
    file = dict(provider='115', account=request['account'], file_id='fixture-cloud-file',
        cloud_path=FILE_PATH, bytes=1000, kind='video', media_id=request['media_id'], version_key=request['version_key'])
    rid = ledger.register(file, managed=True, identity_verified=True)
    ledger.mark_ready(rid, dict(file_id=file['file_id'], bytes=1000, version_key=file['version_key'],
        source_binding=True, read_bytes=500, probe_sha256='1' * 64, duration=1200, video_codec='hevc'))
    queue.publish(task, rid, dict(source_info_hash=request['source_info_hash'], cloud_root_id='root',
        cloud_file_id=file['file_id'], cloud_path=FILE_PATH, torrent_path='Fixture.mkv', torrent_file_id=7, bytes=1000))
    body['resource_id'] = rid
    session.resolve_lane.resolver.protection.arm(dict(body=body, file=ledger.get(rid)))
    video = prepared_video(queue, rid, body['source_info_hash'])
    old = cache.import_font(font_bytes('Previous Font'), 'local_exact', 'previous-release')
    old_binding = cache.bind('previous-release', ass_bytes('Previous Font'), [old['sha256']])
    cache.activate('previous-release', old_binding['subtitle_sha256'], 'previous-owner', lambda: True)
    current = cache.import_font(font_bytes('Current Font'), 'same_release_pack', video['release_key'])
    raw = ass_bytes('Current Font')
    fonts = cache.bind(video['release_key'], raw, [current['sha256']])
    record = session.subtitles.store.put(video, raw, '.ass', 'zh', True, False,
        dict(kind='provider', id='fixture-fonts'), font_result=fonts)
    session.subtitles._record(rid, video['key'], record['state'], 1,
        dict(binding_key=record['key'], subtitle_sha256=record['subtitle_sha256']))
    session.font_preflight.worker.exporter = lambda store, row: export(store, row, root=tmp_path / 'subtitle-export')
    # Run real Session.tick, but never start the unrelated provider health lane.
    monkeypatch.setattr(session.readiness, 'begin', lambda: False)
    session.next_work = session.next_fonts = float('inf')
    p.font_record, p.video = record, video
    p.old_digest, p.new_digest = old['sha256'], current['sha256']
    return p


def activation_state(p):
    db = p.session.ledger.db
    return dict(
        links=sorted((path.name, path.read_bytes()) for path in p.session.font_cache.native.iterdir()),
        native_rows=[tuple(row) for row in db.execute('SELECT * FROM font_native_links ORDER BY sha256')],
        leases=[tuple(row) for row in db.execute('SELECT * FROM font_leases ORDER BY owner')],
        readiness=[tuple(row) for row in db.execute('SELECT * FROM subtitle_preparation ORDER BY resource')],
        activations=[tuple(row) for row in db.execute("SELECT * FROM audit WHERE action='font_activate' ORDER BY seq")])


def start_font_check(p):
    assert p.session.font_preflight.request(p.body)['state'] == 'pending'
    p.session.tick()
    lane = p.session.font_preflight
    assert lane.future is not None, lane.request(p.body)
    lane.future.result(timeout=2)


def test_real_session_tick_activates_account_scoped_fonts_without_lock_inversion(prepared_fonts):
    p = prepared_fonts
    owner = get_ident()
    stages = []
    p.session.font_preflight.worker.observer = lambda row: stages.append((row['phase'], get_ident()))
    start_font_check(p)
    p.session.tick()
    result = p.session.font_preflight.request(p.body)
    assert result['state'] == 'ready' and result['font_hashes'] == [p.new_digest]
    assert p.session.font_cache.owns_activation(p.video['release_key'], p.font_record['subtitle_sha256'],
        p.body['request_id'], result['font_hashes'])
    detail = json.loads(p.session.ledger.db.execute('SELECT detail FROM subtitle_preparation').fetchone()[0])
    assert detail['font_activation']['font_hashes'] == [p.new_digest]
    assert len(p.guard_results) >= 6 and all(row == dict(allowed=True) for row in p.guard_results)
    assert all(thread == owner for stage, thread in stages if stage in ('owner_plan', 'owner_commit'))
    assert any(thread != owner for stage, thread in stages if stage == 'immutable_io')
    assert not p.native.commands


@pytest.mark.parametrize('stage', ['before', 'during_links', 'final_commit'])
def test_font_revoke_before_commit_rolls_back_links_and_all_readiness(prepared_fonts, monkeypatch, stage):
    import bobbi_core.font_cache as cache_module
    p = prepared_fonts
    before = activation_state(p)
    start_font_check(p)
    def revoke():
        completed = Event()
        def logout():
            p.session.lease.accounts.logout(p.session.lease.scope)
            completed.set()
        worker = Thread(target=logout, daemon=True)
        worker.start()
        assert completed.wait(1), 'Font observation held the account CAS against revocation'
        worker.join(1)
    if stage == 'before':
        revoke()
    elif stage == 'during_links':
        original = cache_module.os.link
        def link(source, destination, *args, **kwargs):
            value = original(source, destination, *args, **kwargs)
            if p.new_digest in str(destination):
                revoke()
            return value
        monkeypatch.setattr(cache_module.os, 'link', link)
    else:
        original = p.session.font_preflight.worker.commit
        def commit(operation):
            revoke()
            return original(operation)
        p.session.font_preflight.worker.commit = commit
    with pytest.raises(RuntimeError, match='REVOKED'):
        p.session.tick()
    assert p.session.font_preflight.request(p.body)['state'] != 'ready'
    assert activation_state(p) == before
    assert not p.session.ledger.db.in_transaction


@pytest.mark.parametrize('change', ['account', 'profile'])
def test_postcommit_invalidation_never_returns_font_ready(prepared_fonts, change):
    p = prepared_fonts
    start_font_check(p)
    original = p.session.font_preflight.worker.commit
    def commit(operation):
        value = original(operation)
        if change == 'account':
            p.session.lease.accounts.logout(p.session.lease.scope)
        else:
            p.host.profile_current = lambda: False
        return value
    p.session.font_preflight.worker.commit = commit
    if change == 'account':
        with pytest.raises(RuntimeError, match='REVOKED'):
            p.session.tick()
    else:
        p.session.tick()
    assert p.session.font_preflight.request(p.body)['state'] == 'stale'
    # This transaction really committed before invalidation; do not invent a
    # rollback or grant a ready result merely because its working set exists.
    assert [row[0] for row in p.session.ledger.db.execute('SELECT sha256 FROM font_native_links')] == [p.new_digest]


def test_close_drains_font_io_before_sqlite_and_epoch_lock_without_account_cas(prepared_fonts):
    import sqlite3
    p = prepared_fonts
    before = activation_state(p)
    entered, release, closing = Event(), Event(), Event()
    original = p.session.font_preflight.worker.perform
    shutdown = p.session.font_preflight.executor.shutdown
    def shutdown_during_close(*args, **kwargs):
        closing.set()
        return shutdown(*args, **kwargs)
    p.session.font_preflight.executor.shutdown = shutdown_during_close
    def perform(plan):
        entered.set()
        assert release.wait(4)
        return original(plan)
    p.session.font_preflight.worker.perform = perform
    p.session.font_preflight.request(p.body)
    p.session.tick()
    assert entered.wait(1)
    path = p.session.ledger.path.parent / 'owner.lock'
    checks, errors = [], []
    def inspect_during_close():
        try:
            assert closing.wait(2)
            # Another thread can observe account revocation while close owns
            # and drains the font future. The epoch lock must still be held.
            assert p.session.lease.accounts.snapshot() == p.session.lease.scope
            with pytest.raises(OSError):
                InstanceLock(path).acquire()
            checks.append('account_unlocked_epoch_locked')
        except BaseException as error:
            errors.append(error)
        finally:
            release.set()
    observer = Thread(target=inspect_during_close, daemon=True)
    observer.start()
    p.session.close()
    observer.join(2)
    assert not observer.is_alive() and not errors
    assert checks == ['account_unlocked_epoch_locked']
    assert p.session.font_preflight.records == {}
    with pytest.raises(sqlite3.ProgrammingError):
        p.session.ledger.db.execute('SELECT 1')
    replacement = InstanceLock(path)
    replacement.acquire()
    replacement.close()
    # Draining successful immutable IO never performs the owner commit.
    assert sorted((path.name, path.read_bytes()) for path in p.session.font_cache.native.iterdir()) == before['links']


def test_injected_core_font_and_resource_reads_do_not_import_environment(prepared_fonts, monkeypatch):
    import builtins
    p = prepared_fonts
    imported = builtins.__import__
    def checked(name, *args, **kwargs):
        if name.startswith(('bobbi_platform', 'xbmc')):
            pytest.fail('Core owner read rediscovered environment: ' + name)
        return imported(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', checked)
    assert p.session._owner_read({'operation': 'resource_snapshot'}) == dict(protocol=1, playback=None)
    start_font_check(p)
    p.session.tick()
    assert p.session.font_preflight.request(p.body)['state'] == 'ready'


@pytest.mark.parametrize('owner_call', [None, False, object()])
def test_missing_owner_binding_rejected_before_any_resource(tmp_path, owner_call):
    untouched = tmp_path / 'untouched'
    with pytest.raises(ValueError, match='OWNER_CALL_REQUIRED'):
        Session(untouched, {}, None, lambda: False, lambda _: None,
                lock_factory=InstanceLock, owner_call=owner_call)
    assert not untouched.exists()


@pytest.mark.parametrize('failure', [None, 'raise'])
def test_missing_resource_read_remains_unknown_not_idle(account_font_actor, failure):
    p = account_font_actor
    def unavailable(body):
        if failure == 'raise':
            raise OSError('fixture missing actor')
        return None
    p.session.owner_call = unavailable
    lane = p.session.protection_lane
    lane.tick()
    try:
        lane.future.result(timeout=1)
    except OSError:
        assert failure == 'raise'
    lane.tick()
    assert p.session.ledger.playback_observation()['known'] is False
    assert p.session.font_preflight.worker.allowed(p.body) is False


@pytest.fixture
def actual_composition_binding(account_font_actor, monkeypatch):
    from bobbi_core import preparation_host
    from bobbi_platform import android_engine, native_engine
    p = account_font_actor
    class DeferredThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass
        def join(self):
            pass
    monkeypatch.setattr(preparation_host, 'Thread', DeferredThread)
    monkeypatch.setattr(preparation_host, 'configuration', lambda _: p.session.config)
    monkeypatch.setattr(android_engine, 'available', lambda: False)
    monkeypatch.setattr(native_engine, 'architecture', lambda: 'fixture-architecture')
    p.host.root.mkdir()
    (p.host.root / 'preparation.json').write_text('fixture-only')
    p.host.configure_preparation(p.host.plugin_root)
    p.host._tick_preparation()
    assert isinstance(p.host.preparation, preparation_host.PreparationHost)
    p.session.owner_call = p.host.preparation.factory.keywords['owner_call']
    monkeypatch.setattr(runtime, 'call', lambda *a, **kw: pytest.fail('Resident composition used runtime locator'))
    return p


def test_actual_host_factory_binds_owner_queue_without_runtime_locator(actual_composition_binding):
    p = actual_composition_binding
    assert p.session.font_preflight.worker.allowed(p.body) is True
    assert p.guard_results == [dict(allowed=True)]


@pytest.mark.parametrize('change', ['account', 'profile', 'stopping'])
def test_real_binding_rechecks_after_actor_result(actual_composition_binding, change):
    p = actual_composition_binding
    def invalidate():
        if change == 'account':
            p.session.lease.accounts.logout(p.session.lease.scope)
        elif change == 'profile':
            p.host.profile_current = lambda: False
        else:
            p.host.stopping.set()
    p.after_guard = invalidate
    assert p.session.font_preflight.worker.allowed(p.body) is False
    assert p.guard_results == [dict(allowed=True)]


def test_profile_return_cannot_revive_resident_owner_binding(actual_composition_binding):
    p = actual_composition_binding
    p.host.profile_current = lambda: False
    assert p.session.font_preflight.worker.allowed(p.body) is False
    p.host.profile_current = lambda: True
    assert p.session.font_preflight.worker.allowed(p.body) is False
    assert not p.guard_results

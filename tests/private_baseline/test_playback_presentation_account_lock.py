"""Real account/stream fences with controlled native IO, not device timing proof."""
from contextlib import contextmanager
from copy import deepcopy
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_core.share_stream import Binding, Handler
from bobbi_platform.account_manager import AccountError, AccountManager
from bobbi_platform.host import Host
from bobbi_platform.paths import ProfileBinding
from bobbi_platform.playback_accounts import PlaybackAccounts
from test_playback_authority import Native, bind, row


def credential(user='123', suffix='A1_fixture'):
    return dict(app='os_linux', cookies=dict(UID=user + '_' + suffix, CID='fixture', SEID='fixture'))


@pytest.fixture
def account(tmp_path):
    manager = AccountManager(tmp_path / 'account.json')
    scope = manager.install(credential(), manager.snapshot())
    return manager, scope


def scene(manager, scope, current=lambda: True):
    native = Native()
    owner = PlaybackAuthority(native, profile_current=current)
    # Exercise the same routing adapter supplied by the resident host.
    owner.configure_accounts(PlaybackAccounts(manager, lambda: None))
    initial = owner.dispatch(dict(operation='snapshot'))
    args = dict(boot_id=initial['boot_id'], epoch=initial['epoch'], request_id='b' * 32)
    selected = owner.dispatch(dict(args, operation='select', selection_identity='release-a',
                                   account_scope=scope))
    args['epoch'] = selected['epoch']
    bind(owner, args)
    assert owner.dispatch(dict(args, operation='claim_start', route='resolved_url')) == {'status': 'CLAIMED'}
    native.current = row(args['request_id'], 'file-a', audio_intent=0,
                         open_epoch=native.epoch, control_protocol=1)
    owner.refresh(reconcile_windows=False)
    native.subtitles = lambda: dict(status='READY', control_protocol=1, receipt=deepcopy(native.current),
        selection_epoch=native.epoch, position_ms=2000, duration_ms=100000, can_seek=True,
        visible=True, audio_index=0, current_index=-1, streams=[], chapters=[],
        audio_streams=[dict(index=0, stream_key='c' * 64, name='Original', language='fr')])
    native.subtitle_status = lambda captured: 'fixture'
    native.publications = []
    native.publish_playback_presentation = lambda *args: native.publications.append(deepcopy(args))
    return owner, native, args


def observer_state(owner, native):
    return deepcopy(dict(owner=owner.owner.snapshot(), history=owner.history.items,
        commands=owner.playback_commands, native_commands=native.commands, gui_commands=native.gui_commands,
        publications=native.publications,
        last_native=owner.last_native, native_epoch=owner.native_epoch,
        reservation_epoch=owner.reservation_epoch, native_windows=owner.native_windows))


@contextmanager
def held_read(account, method='state', operation='playback_presentation', scope_source='explicit',
              current=lambda: True, failure=None):
    """Construct and dispatch on the actual authority-owning thread."""
    manager, scope = account
    entered, release = Event(), Event()
    value = dict(caller=deepcopy(scope))

    def run():
        try:
            owner, native, args = scene(manager, scope, current)
            if operation == 'select':
                message = dict(operation=operation, boot_id=args['boot_id'], epoch=args['epoch'],
                    request_id='d' * 32, selection_identity='next', account_scope=value['caller'])
            elif operation == 'playback_receipt':
                expected = owner.dispatch(dict(operation='playback_presentation'))['expected']
                command = dict(expected=expected, command_id='e' * 32,
                               action='seek', params=dict(position_ms=10000))
                assert owner.dispatch(dict(operation='playback_command', command=command))['status'] == 'queued'
                message = dict(operation=operation, expected=expected, command_id=command['command_id'])
            else:
                message = dict(operation=operation, include_owner=True)
                if scope_source == 'explicit':
                    message['account_scope'] = value['caller']
                else:
                    message.update(args)  # Derive original selection scope, never caller rebinding.
            original = getattr(native, method)

            def blocked(*args, **kwargs):
                entered.set()
                assert release.wait(5), 'Native fixture was not released'
                if failure is not None:
                    raise failure('fixture native failure')
                return original(*args, **kwargs)

            setattr(native, method, blocked)
            value['before'] = observer_state(owner, native)
            try:
                value['result'] = owner.dispatch(message)
            finally:
                value['after'] = observer_state(owner, native)
        except BaseException as error:
            value['error'] = error
            entered.set()

    actor = Thread(target=run)
    actor.start()
    try:
        assert entered.wait(3), value
        assert 'error' not in value, value
        yield value
    finally:
        release.set()
        actor.join(3)
        assert not actor.is_alive(), value


def stream_handler(manager, scope):
    entry = Binding(dict(request_id='a' * 32, locator='fixture', guid='fixture',
        title='fixture.mkv', size=1024), lambda *args: None, lambda _: True,
        account=manager, scope=scope)
    handler = Handler.__new__(Handler)
    handler.entry = entry
    handler.server = SimpleNamespace(owner=SimpleNamespace(stopping=Event()))
    handler.disconnected = False
    handler.probe_socket = lambda: False  # No socket or external service in these tests.
    return handler


def start_worker(operation):
    started, done = Event(), Event()
    value = {}

    def run():
        started.set()
        try:
            value['result'] = operation()
        except BaseException as error:
            value['error'] = error
        finally:
            done.set()

    worker = Thread(target=run)
    worker.start()
    assert started.wait(1)
    return worker, done, value


@pytest.mark.parametrize('method', ['state', 'subtitles', 'subtitle_status'])
@pytest.mark.parametrize('scope_source', ['explicit', 'selection'])
def test_scoped_presentation_native_read_does_not_block_real_stream_guard(account, method, scope_source):
    handler = stream_handler(*account)
    with held_read(account, method, scope_source=scope_source) as read:
        worker, done, guard = start_worker(handler.cancelled)
        completed_during_read = done.wait(1)
    worker.join(2)
    assert not worker.is_alive() and guard == {'result': False}
    assert completed_during_read, 'Presentation native IO retained the stream account lock'
    assert 'error' not in read and read['result']['available'] and read['result']['mode'] == 'managed'
    assert read['before'] == read['after']


@pytest.mark.parametrize('method', ['state', 'subtitles', 'subtitle_status'])
@pytest.mark.parametrize('transition', ['switch', 'aba', 'logout', 'renew'])
def test_account_changes_during_read_complete_and_old_scope_cannot_publish(account, method, transition):
    manager, scope = account
    with held_read(account, method) as read:
        def change():
            if transition == 'logout':
                latest = manager.logout(scope)
            elif transition == 'renew':
                latest = manager.install(credential(suffix='A2_renewed'), scope)
            else:
                latest = manager.install(credential('456'), scope)
                if transition == 'aba':
                    latest = manager.install(credential(), latest)
            # Mutable caller data must not retarget the original publication fence.
            read['caller'].update(latest)
            return latest
        worker, done, changed = start_worker(change)
        completed_during_read = done.wait(1)
    worker.join(2)
    assert not worker.is_alive() and 'error' not in changed
    assert completed_during_read, 'Account change was blocked by presentation IO'
    if transition == 'renew':
        assert changed['result'] == scope
        assert 'error' not in read and read['result']['available']
    else:
        assert isinstance(read.get('error'), AccountError) and str(read['error']) == 'ACCOUNT_CHANGED'
        assert 'result' not in read
        if transition == 'aba':
            assert changed['result']['account_id'] == scope['account_id']
            assert changed['result']['epoch'] != scope['epoch']
    assert read['before'] == read['after']


@pytest.mark.parametrize('method', ['state', 'subtitles', 'subtitle_status'])
@pytest.mark.parametrize('transition', ['switch', 'aba', 'resolver_failure'])
def test_profile_revocation_during_read_rejects_even_a_valid_native_view(account, tmp_path, method, transition):
    active = ['A']
    def resolve(addon):
        if active[0] == 'failure':
            raise OSError('fixture mapping unavailable')
        return tmp_path / active[0] / addon
    binding = ProfileBinding(resolve)
    host = Host(binding.root(), profile_current=binding.is_current)
    with held_read(account, method, current=host.check_profile) as read:
        active[0] = 'failure' if transition == 'resolver_failure' else 'B'
        assert host.check_profile() is False
        if transition == 'aba':
            active[0] = 'A'
    assert isinstance(read.get('error'), OSError) and str(read['error']) == 'PROFILE_CHANGED'
    assert 'result' not in read and read['before'] == read['after']
    assert host.profile_revoked and host.stopping.is_set() and not binding.is_current()


@pytest.mark.parametrize('method', ['state', 'subtitles', 'subtitle_status'])
@pytest.mark.parametrize('failure', [OSError, RuntimeError, ValueError, TypeError, AttributeError])
def test_native_read_errors_stay_unavailable_without_blocking_stream(account, method, failure):
    handler = stream_handler(*account)
    with held_read(account, method, failure=failure) as read:
        worker, done, guard = start_worker(handler.cancelled)
        completed_during_read = done.wait(1)
    worker.join(2)
    assert not worker.is_alive() and guard == {'result': False} and completed_during_read
    assert 'error' not in read
    assert read['result'] == dict(available=False, mode='unavailable', reason='SCOPED_CONTROL_UNAVAILABLE')
    assert read['before'] == read['after']


@pytest.mark.parametrize('operation,method', [('select', 'intent'), ('playback_receipt', 'state'),
                                            ('playback_receipt', 'subtitles')])
def test_mutation_and_ledger_recovery_still_hold_original_account_cas(account, operation, method):
    handler = stream_handler(*account)
    with held_read(account, method, operation=operation) as read:
        worker, done, guard = start_worker(handler.cancelled)
        completed_during_read = done.wait(.1)
    worker.join(2)
    assert not worker.is_alive() and guard == {'result': False}
    assert not completed_during_read, 'Mutation/receipt must retain its original account CAS'
    assert 'error' not in read


@pytest.mark.parametrize('invalid', ['stale', 'malformed', 'unauthenticated', 'selection_mismatch',
                                    'owner_missing', 'include_owner', 'profile'])
def test_invalid_presentation_admission_never_reads_native(account, invalid):
    manager, scope = account
    owner, native, _ = scene(manager, scope)
    supplied = deepcopy(scope)
    message = dict(operation='playback_presentation', account_scope=supplied)
    expected = AccountError
    if invalid == 'stale':
        manager.logout(scope)
    elif invalid == 'malformed':
        supplied['epoch'] = True
    elif invalid == 'unauthenticated':
        message['account_scope'] = manager.logout(scope)
    elif invalid == 'selection_mismatch':
        owner.selection_account = dict(scope, epoch=scope['epoch'] + 1)
    elif invalid == 'owner_missing':
        owner.accounts = None
        expected = RuntimeError
    elif invalid == 'include_owner':
        message['include_owner'] = 'true'
        expected = ValueError
    else:
        owner.profile_current = lambda: False
        expected = OSError
    native.state = lambda: pytest.fail('Rejected read reached native')
    if invalid == 'selection_mismatch':
        assert owner.dispatch(message) == dict(available=False, status='rejected', reason='PLAYBACK_SCOPE_CHANGED')
    else:
        with pytest.raises(expected):
            owner.dispatch(message)


def test_final_publication_rechecks_original_scope_in_short_cas(account):
    manager, scope = account
    owner, native, _ = scene(manager, scope)
    original, calls = manager.run_if_current, []
    def fenced(expected, operation, authenticated=True):
        calls.append(deepcopy(expected))
        if len(calls) == 2:
            manager.logout(scope)  # Between the completed native read and final CAS.
        return original(expected, operation, authenticated=authenticated)
    manager.run_if_current = fenced
    with pytest.raises(AccountError, match='ACCOUNT_CHANGED'):
        owner.dispatch(dict(operation='playback_presentation', account_scope=scope))
    assert calls == [scope, scope] and not native.commands


@pytest.mark.parametrize('change', ['revoked', 'exception'])
def test_profile_is_rechecked_after_waiting_for_final_account_cas(account, tmp_path, change):
    manager, _ = account
    profile = ['active']
    def current():
        if profile[0] == 'exception':
            raise OSError('fixture profile mapping unavailable')
        return profile[0] == 'active'
    host = Host(tmp_path / 'profile', profile_current=current)
    waiting, locked = Event(), Event()
    original = manager.run_if_current
    with held_read(account, current=host.check_profile) as read:
        # Admission has completed. Observe the actual subsequent publication
        # CAS attempt, then revoke while another thread owns its real lock.
        def publication(expected, operation, authenticated=True):
            waiting.set()
            return original(expected, operation, authenticated=authenticated)
        manager.run_if_current = publication
        def revoke():
            with manager.lock:
                locked.set()
                assert waiting.wait(2), 'Final publication CAS was not reached'
                profile[0] = change
                assert host.check_profile() is False
        worker, done, changed = start_worker(revoke)
        assert locked.wait(1)
    worker.join(2)
    assert not worker.is_alive() and done.is_set() and 'error' not in changed
    assert isinstance(read.get('error'), OSError) and str(read['error']) == 'PROFILE_CHANGED'
    assert 'result' not in read and read['before'] == read['after']
    assert host.profile_revoked and host.stopping.is_set()


@pytest.mark.parametrize('method,reply', [('state', None), ('state', {'protocol': True}),
                                        ('subtitles', None), ('subtitles', {'status': 'READY'})])
def test_malformed_native_observation_is_still_unavailable(account, method, reply):
    manager, scope = account
    owner, native, _ = scene(manager, scope)
    setattr(native, method, lambda: reply)
    before = observer_state(owner, native)
    assert owner.dispatch(dict(operation='playback_presentation', account_scope=scope,
        include_owner=True)) == dict(available=False, mode='unavailable', reason='SCOPED_CONTROL_UNAVAILABLE')
    assert observer_state(owner, native) == before

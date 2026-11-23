"""Personal-file entry holds one real profile and loopback Runtime binding."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
from threading import Event, Thread

import pytest

from bobbi_platform import paths, playback_client, runtime
from test_ce2096_pan_playback import entry

REAL_CAPTURE = playback_client.capture_transport


@pytest.fixture
def bound(entry, tmp_path, monkeypatch):
    state = SimpleNamespace(profile='A', captures=[], action_hook=None, replacement_calls=[], bindings=[], observed_b=Event())
    original_call = entry.module.call
    native_client = entry.client
    def dispatch(action, body):
        if state.action_hook:
            state.action_hook(action, body)
        if action == 'playback':
            return native_client.call(body)
        return original_call(action, body)
    first = runtime.Runtime(dispatch, tmp_path/'A/script.module.bobbi.platform/runtime.json')
    second = runtime.Runtime(lambda action, body: state.replacement_calls.append((action, deepcopy(body))) or {},
                             tmp_path/'B/script.module.bobbi.platform/runtime.json')
    first.start()
    second.start()
    real_binding = paths.ProfileBinding
    def resolve(addon):
        if state.profile == 'B':
            state.observed_b.set()
        return tmp_path/state.profile/addon
    def binding():
        captured = real_binding(resolver=resolve)
        state.bindings.append(captured)
        return captured
    def capture():
        state.captures.append(True)
        profile, client, call = REAL_CAPTURE()
        entry.client = client
        return profile, client, call
    monkeypatch.setattr(paths, 'ProfileBinding', binding)
    monkeypatch.setattr(playback_client, 'capture_transport', capture)
    monkeypatch.setattr(sys.modules['lib.native_support'], 'available',
                        lambda: pytest.fail('Adapter must come from the bound Host'))
    state.first, state.second, state.entry = first, second, entry
    try:
        yield state
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('native', [False, True])
def test_manual_file_uses_bound_adapter_and_one_host_for_claim_open_and_player(bound, native):
    entry = bound.entry
    entry.native = native
    entry.module.play({'ticket': entry.ticket})
    assert len(bound.captures) == 1 and len(entry.played) == 1 and not entry.errors
    assert [action for action, _ in entry.calls].count('status') == 1
    assert not bound.replacement_calls


@pytest.mark.parametrize('phase', ['pan_claim_play', 'pan_open_stream'])
@pytest.mark.parametrize('change', ['profile', 'runtime'])
def test_late_reply_cannot_rebind_player_or_cleanup_to_replacement(bound, monkeypatch, phase, change):
    entry = bound.entry
    registration = bound.first.path.read_bytes()
    def change_binding(action, body):
        if action == phase:
            if change == 'profile':
                bound.profile = 'B'
            else:
                bound.first.path.write_bytes(bound.second.path.read_bytes())
    bound.action_hook = change_binding
    def error(*args):
        entry.errors.append(args)
        # Even A -> B -> A cannot resurrect the capture after the failed read.
        bound.profile = 'A'
        bound.first.path.write_bytes(registration)
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: SimpleNamespace(ok=error))
    entry.module.play({'ticket': entry.ticket})
    assert entry.errors and not entry.played and len(bound.captures) == 1
    assert not bound.replacement_calls
    assert not any(action in ('pan_close_stream', 'pan_cancel_operation') for action, _ in entry.calls)


def test_explicit_unavailable_inherited_transport_never_captures(entry, monkeypatch):
    monkeypatch.setattr(playback_client, 'capture_transport', lambda: pytest.fail('late capture'))
    entry.module.play({'ticket': entry.ticket}, transport=None, playback_adapter='standard')
    assert entry.errors and not entry.played and not entry.calls


@pytest.mark.parametrize('operation', ['pan_open_stream', 'pan_prepare_history_play', 'catalog_prepare_play'])
def test_inflight_profile_aba_is_observed_during_each_wait(bound, monkeypatch, operation):
    from bobbi_core.file_ref import from_selected
    entry = bound.entry
    entered, release, finished = Event(), Event(), Event()
    errors = []
    ref = from_selected(entry.expected, entry.file, '0')
    monkeypatch.setattr(entry.module, '_history_record', lambda *args: dict(
        file_ref=ref, position=0, completion_reason='STOP'))
    monkeypatch.setitem(sys.modules, 'lib.utils.views.personal_catalog', SimpleNamespace(
        account_for=lambda params, accounts: entry.expected))
    original = entry.module.call
    def provider(action, body, **kw):
        if action == 'pan_status':
            return dict(providers=[dict(provider='quark', account=entry.expected)])
        if action in ('pan_prepare_history_play', 'catalog_prepare_play'):
            return dict(ticket=body['request_id'])
        return original(action, body, **kw)
    # Bound Runtime dispatch captured the original callback; routing provider
    # replies here remains behind the same actual runtime/profile fences.
    def hook(action, body):
        if action == operation:
            entered.set()
            assert release.wait(4)
    bound.action_hook = hook
    # The fixture's dispatch uses its saved original; install the test provider
    # on that function's state by adding the minimal replies before capture.
    prior_dispatch = bound.first.server.dispatch
    def dispatch(action, body):
        if action in ('pan_status', 'pan_prepare_history_play', 'catalog_prepare_play'):
            hook(action, body)
            return provider(action, body)
        return prior_dispatch(action, body)
    bound.first.server.dispatch = dispatch
    def invoke():
        try:
            if operation == 'pan_open_stream':
                entry.module.play(dict(ticket=entry.ticket))
            elif operation == 'pan_prepare_history_play':
                entry.module.resume(dict(history_id=ref['id']))
            else:
                entry.module.indexed(dict(object_id=ref['id'], provider='quark'))
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()
    worker = Thread(target=invoke)
    worker.start()
    try:
        assert entered.wait(2)
        bound.profile = 'B'
        assert bound.observed_b.wait(2), 'Wait loop failed to observe profile revocation'
        assert finished.wait(2), 'Revoked UI wait did not terminate while IO was pending'
        bound.profile = 'A'
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert not entry.played and len(bound.captures) == 1 and not bound.replacement_calls
        assert bound.bindings[0].is_current() is False
    finally:
        release.set()
        worker.join(4)


def test_invalid_ticket_does_not_locate_any_host(entry, monkeypatch):
    monkeypatch.setattr(playback_client, 'capture_transport', lambda: pytest.fail('invalid route captured'))
    entry.module.play({'ticket': 'not-a-ticket'})
    assert not entry.errors and not entry.played and not entry.calls


def test_personal_history_opens_only_the_explicit_root_and_rechecks_after_read(entry, monkeypatch, tmp_path):
    roots, reads = [], []
    profile = ['A']
    binding = paths.ProfileBinding(resolver=lambda addon: tmp_path/profile[0]/addon)
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', SimpleNamespace(
        PickleDatabase=lambda root: roots.append(Path(root)) or root))
    def get(identifier):
        reads.append(identifier)
        profile[0] = 'B'
        return {'position': 42}
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(
        FileHistory=lambda database: SimpleNamespace(get=get)))
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        entry.module._history_record('a'*64, binding)
    assert roots == [tmp_path/'A/plugin.video.bobbi'] and reads == ['a'*64]
    profile[0] = 'A'
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        entry.module._history_record('a'*64, binding)
    assert len(roots) == 1


def test_personal_history_reads_real_original_profile_database(entry, monkeypatch, tmp_path):
    from bobbi_core.file_ref import from_selected
    plugin = Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi'
    modules = {}
    for name in ('pickle_db', 'file_history'):
        spec = importlib.util.spec_from_file_location('lib.db.'+name, plugin/'lib/db'/f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules, 'lib.db.'+name, module)
        modules[name] = module
    ref = from_selected(entry.expected, entry.file, '0')
    for profile, position in (('A', 11), ('B', 42)):
        history = modules['file_history'].FileHistory(
            modules['pickle_db'].PickleDatabase(tmp_path/profile/'plugin.video.bobbi'))
        context = history.begin(ref)
        assert history.save(dict(_file_history=context, current_time=position, total_time=100,
                                 terminal_reason='STOP', _file_history_sequence=1))
    active = ['A']
    binding = paths.ProfileBinding(resolver=lambda addon: tmp_path/active[0]/addon)
    assert entry.module._history_record(ref['id'], binding)['position'] == 11
    active[0] = 'B'
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        entry.module._history_record(ref['id'], binding)
    active[0] = 'A'
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        entry.module._history_record(ref['id'], binding)
    other = modules['file_history'].FileHistory(
        modules['pickle_db'].PickleDatabase(tmp_path/'B/plugin.video.bobbi'))
    assert other.get(ref['id'])['position'] == 42

"""Bounded start reads through real history; simulated RPC is not device proof."""
from frozen_history import source_bytes
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from urllib.error import URLError
from uuid import uuid4

import pytest

from bobbi_core import playback_presentation
from test_ce2097_file_history import database, history, submission
from test_playback_start_facts import scene


ROOT = Path(__file__).resolve().parents[1]
FROZEN = '35b9d61ebb9429f5b15e3b882efbfc9c022bd6ad'
SUBMISSION = 'addons/plugin.video.bobbi/lib/services/playback_history.py'
PLAYER = 'addons/plugin.video.bobbi/lib/native_player.py'
UNAVAILABLE = dict(available=False, reason='SCOPED_CONTROL_UNAVAILABLE')


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert 0 <= seconds <= .05
        self.sleeps.append(seconds)
        self.now += seconds


def view(scene):
    return playback_presentation.project(scene.raw, scene.owner['boot_id'], scene.owner['epoch'], scene.row)


def install_call(scene, response):
    calls = []

    def call(message, **kwargs):
        calls.append((deepcopy(message), dict(kwargs)))
        return response(len(calls), kwargs['timeout'])

    scene.client.call = call
    return calls


def capture(scene, timer, **options):
    return submission.capture_start(scene.data, scene.client, scene.owner, scene.row['native_instance'],
        scene.binding, clock=lambda: 1700000000, monotonic=timer.monotonic, sleep=timer.sleep, **options)


def assert_reads_only(scene, calls):
    for message, options in calls:
        assert message == dict(operation='playback_presentation', account_scope=scene.data['_account'],
                               include_start_facts=True)
        assert 0 < options['timeout'] <= .3


def test_timeout_start_read_recovers_with_original_identity_and_real_persistence(scene):
    timer = Clock()
    original = deepcopy(scene.data)
    expected = view(scene)

    def response(attempt, timeout):
        if attempt == 1:
            timer.now += timeout
            raise TimeoutError('transient read')
        return deepcopy(expected)

    calls = install_call(scene, response)
    assert capture(scene, timer) is True
    assert len(calls) == 2 and timer.sleeps == [.05]
    assert_reads_only(scene, calls)
    observed = scene.data['_file_start_observation']
    assert {key: value for key, value in scene.data.items() if key != '_file_start_observation'} == original
    assert observed['expected'] == expected['expected']
    assert observed['generation'] == original['_file_history']['generation']
    assert observed['session_id'] == original['_file_history']['session_id']
    assert observed['recorded_at'] == 1700000000
    assert scene.files.save(scene.data)
    stored = scene.db.get_key_checked(history.FACTS_KEY)[scene.file['id']]
    assert stored['observation'] == observed
    assert stored['binding']['sequence'] == original['_file_history_sequence']


def test_timeout_reads_stop_at_three_attempts_and_never_make_facts(scene):
    timer = Clock()
    scene.data['_file_start_observation'] = {'stale': True}

    def response(attempt, timeout):
        timer.now += timeout
        raise TimeoutError('transient read')

    calls = install_call(scene, response)
    assert capture(scene, timer) is False
    assert len(calls) == 3 and len(timer.sleeps) == 2
    assert timer.now <= 100.9 + 1e-9
    assert_reads_only(scene, calls)
    assert '_file_start_observation' not in scene.data
    assert scene.files.save(scene.data)
    assert scene.file['id'] not in (scene.db.get_key_checked(history.FACTS_KEY) or {})


@pytest.mark.parametrize('budget,timeouts', [(.65, [.3, .3]), (.8, [.3, .3, .1])])
def test_timeout_of_last_attempt_uses_remaining_shared_budget(scene, budget, timeouts):
    timer = Clock()

    def response(attempt, timeout):
        timer.now += timeout
        raise TimeoutError('transient read')

    calls = install_call(scene, response)
    assert capture(scene, timer, budget=budget) is False
    assert [options['timeout'] for message, options in calls] == pytest.approx(timeouts)
    assert timer.now == pytest.approx(100 + budget)
    assert '_file_start_observation' not in scene.data


@pytest.mark.parametrize('max_attempts', [1, 2])
def test_smaller_attempt_limit_cannot_be_extended_by_available_time(scene, max_attempts):
    timer = Clock()

    def response(attempt, timeout):
        raise TimeoutError('transient read')

    calls = install_call(scene, response)
    assert capture(scene, timer, max_attempts=max_attempts) is False
    assert len(calls) == max_attempts
    assert len(timer.sleeps) == max_attempts - 1
    assert '_file_start_observation' not in scene.data


@pytest.mark.parametrize('late_by', [0, .01])
def test_success_returning_at_or_after_deadline_cannot_be_published(scene, late_by):
    timer = Clock()
    expected = view(scene)

    def response(attempt, timeout):
        timer.now = 100.9 + late_by
        return expected

    calls = install_call(scene, response)
    assert capture(scene, timer) is False
    assert len(calls) == 1 and not timer.sleeps
    assert '_file_start_observation' not in scene.data


def test_deadline_expiring_between_attempts_prevents_another_rpc(scene):
    timer = Clock()

    def response(attempt, timeout):
        raise TimeoutError('transient read')

    calls = install_call(scene, response)
    sleep = timer.sleep

    def delayed_sleep(seconds):
        sleep(seconds)
        timer.now = 101

    timer.sleep = delayed_sleep
    assert capture(scene, timer) is False
    assert len(calls) == 1 and '_file_start_observation' not in scene.data
    assert timer.sleeps == [.05]


@pytest.mark.parametrize('error', [OSError('ordinary IO'), RuntimeError('owner unavailable'),
                                  ValueError('invalid reply')])
def test_non_timeout_exceptions_are_not_retried(scene, error):
    timer = Clock()

    def response(attempt, timeout):
        raise error

    calls = install_call(scene, response)
    assert capture(scene, timer) is False
    assert len(calls) == 1 and not timer.sleeps
    assert '_file_start_observation' not in scene.data


@pytest.mark.parametrize('failure', ['response_timeout', 'service_unavailable', 'wrapped_connect_timeout'])
def test_real_bound_http_transport_preserves_timeout_type_without_network(scene, monkeypatch, failure):
    from bobbi_platform import runtime
    from bobbi_platform.playback_client import capture_transport

    timer = Clock()
    expected = view(scene)
    registrations, opened, reads = [], [], []
    registration = dict(port=39175, token='f' * 64)

    def registered(path):
        registrations.append(Path(path))
        return dict(registration)

    class Response:
        def __init__(self, attempt):
            self.attempt = attempt

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            assert limit == runtime.MAX_MESSAGE_BYTES + 1
            reads.append(self.attempt)
            if self.attempt == 1 and failure == 'response_timeout':
                raise TimeoutError('synthetic response read timeout')
            if failure == 'service_unavailable':
                return b'{"ok":false,"error":"unavailable"}'
            return json.dumps(dict(ok=True, result=expected)).encode('utf-8')

    class Opener:
        def open(self, request, timeout):
            opened.append((json.loads(request.data), timeout))
            assert request.full_url == 'http://127.0.0.1:39175/control'
            assert request.get_header('Authorization') == 'Bearer ' + registration['token']
            if failure == 'wrapped_connect_timeout':
                raise URLError(TimeoutError('synthetic wrapped connection timeout'))
            return Response(len(opened))

    monkeypatch.setattr(runtime, '_registration', registered)
    monkeypatch.setattr(runtime, 'build_opener', lambda *handlers: Opener())
    binding, client, host_call = capture_transport(binding=scene.binding)
    assert binding is scene.binding
    assert callable(host_call)
    scene.client = client
    assert capture(scene, timer) is (failure == 'response_timeout')
    assert len(opened) == (2 if failure == 'response_timeout' else 1)
    assert timer.sleeps == ([.05] if failure == 'response_timeout' else [])
    assert registrations and set(registrations) == {scene.binding.root() / 'runtime.json'}
    for message, timeout in opened:
        assert message == dict(action='playback', body=dict(operation='playback_presentation',
            account_scope=scene.data['_account'], include_start_facts=True))
        assert 0 < timeout <= .3
    if failure == 'response_timeout':
        assert reads == [1, 2]
        assert scene.data['_file_start_observation']['expected'] == expected['expected']
    else:
        assert reads == ([1] if failure == 'service_unavailable' else [])
        assert '_file_start_observation' not in scene.data


@pytest.mark.parametrize('kind', ['scope_changed', 'generic_unavailable', 'other_unavailable', 'unexpected_expected',
                                 'unexpected_metadata', 'missing_facts', 'metadata'])
def test_scope_or_metadata_failure_is_final_and_does_not_fabricate_facts(scene, kind):
    timer = Clock()
    result = view(scene)
    if kind == 'scope_changed':
        result = dict(available=False, status='rejected', reason='PLAYBACK_SCOPE_CHANGED')
    elif kind == 'generic_unavailable':
        # This wire reason also covers revoked ownership, native mismatches,
        # and invalid protocol/catalog data. It cannot authorize another read.
        result = deepcopy(UNAVAILABLE)
    elif kind == 'other_unavailable':
        result = dict(available=False, reason='UNKNOWN_REASON')
    elif kind == 'unexpected_expected':
        result = dict(UNAVAILABLE, expected=result['expected'])
    elif kind == 'unexpected_metadata':
        result = dict(UNAVAILABLE, start_facts=result['start_facts'])
    elif kind == 'missing_facts':
        result.pop('start_facts')
    else:
        result['start_facts']['audio']['channels'] = True
    calls = install_call(scene, lambda attempt, timeout: deepcopy(result))
    assert capture(scene, timer) is False
    assert len(calls) == 1 and not timer.sleeps
    assert '_file_start_observation' not in scene.data


def mutate_context(scene, change):
    if change == 'history_generation':
        scene.data['_file_history']['generation'] += 1
    elif change == 'history_session':
        scene.data['_file_history']['session_id'] = 'f' * 32
    elif change == 'file_metadata':
        scene.data['_file_history']['file_ref']['name'] = 'Replacement.mkv'
    elif change == 'account':
        scene.data['_account']['epoch'] += 1
    elif change == 'owner_epoch':
        scene.owner['epoch'] += 1
    elif change == 'owner_identity':
        scene.owner['file_identity'] += ':changed'
    elif change == 'request':
        scene.data['request_id'] = 'f' * 32
    elif change == 'url':
        scene.data['url'] += '?changed=1'
    elif change == 'selection_policy':
        scene.data['selection_policy'] = 'standard'
    elif change == 'personal_file':
        scene.data['_pan_file'] = False
    elif change == 'profile':
        scene.current[0] = 'B'
    else:
        raise AssertionError(change)


@pytest.mark.parametrize('change', ['history_generation', 'history_session', 'file_metadata', 'account',
    'owner_epoch', 'owner_identity', 'request', 'url', 'selection_policy', 'personal_file', 'profile'])
@pytest.mark.parametrize('when', ['reply', 'timeout', 'between_attempts'])
def test_original_context_cannot_be_refreshed_after_an_inflight_change(scene, change, when):
    timer = Clock()
    expected = view(scene)

    def response(attempt, timeout):
        if when == 'between_attempts':
            raise TimeoutError('transient read before context changed')
        mutate_context(scene, change)
        if when == 'timeout':
            raise TimeoutError('read ended after context changed')
        return deepcopy(expected)

    calls = install_call(scene, response)
    if when == 'between_attempts':
        sleep = timer.sleep

        def change_between_attempts(seconds):
            sleep(seconds)
            mutate_context(scene, change)

        timer.sleep = change_between_attempts
    assert capture(scene, timer) is False
    assert len(calls) == 1
    assert '_file_start_observation' not in scene.data
    assert len(timer.sleeps) == (1 if when == 'between_attempts' else 0)


@pytest.mark.parametrize('field,replacement', [('boot_id', 'f' * 32), ('epoch', 3),
    ('request_id', 'f' * 32), ('native_instance', str(uuid4())), ('file_sha256', 'f' * 64),
    ('selection_epoch', True), ('expected_sequence', -1), ('user_intent', -1), ('audio_intent', -1)])
def test_returned_owner_instance_and_invalid_counters_are_rejected_without_retry(scene, field, replacement):
    timer = Clock()
    expected = view(scene)
    expected['expected'][field] = replacement
    calls = install_call(scene, lambda attempt, timeout: deepcopy(expected))
    assert capture(scene, timer) is False
    assert len(calls) == 1 and not timer.sleeps
    assert '_file_start_observation' not in scene.data


def hook_from(source):
    cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == '_record_started_history')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<actual-start-history-hook>', 'exec'), namespace)
    return namespace['_record_started_history']


def hook_actor(scene, writes):
    return SimpleNamespace(_cinema_history_pending=True, data=scene.data, playback_client=scene.client,
        _owner_context=scene.owner, _native_instance=scene.row['native_instance'], _file_history_binding=scene.binding,
        _owns_playback_session=lambda: True, _matches_requested_playback=lambda: True,
        _cinema_phase=lambda value: None,
        mark_watched=lambda data: writes.append(submission.snapshot(data, 'STARTED')))


def test_real_native_hook_retries_read_but_submits_started_once(scene, monkeypatch):
    timer = Clock()
    expected = view(scene)

    def response(attempt, timeout):
        if attempt == 1:
            raise TimeoutError('transient read')
        return deepcopy(expected)

    calls = install_call(scene, response)
    actual = submission.capture_start
    boundary = ModuleType('lib.services.playback_history')
    boundary.capture_start = lambda *args, **kwargs: actual(*args, **kwargs,
        monotonic=timer.monotonic, sleep=timer.sleep)
    monkeypatch.setitem(sys.modules, 'lib.services.playback_history', boundary)
    hook = hook_from((ROOT / PLAYER).read_text(encoding='utf-8'))
    writes = []
    actor = hook_actor(scene, writes)
    sequence = scene.data['_file_history_sequence']
    hook(actor)
    hook(actor)
    assert len(calls) == 2 and len(writes) == 1
    assert writes[0]['terminal_reason'] == 'STARTED'
    assert writes[0]['_file_history_sequence'] == sequence + 1
    assert '_file_start_observation' in writes[0]
    assert scene.files.save(writes[0])
    assert scene.db.get_key_checked(history.FACTS_KEY)[scene.file['id']]['observation'] == writes[0]['_file_start_observation']


@pytest.fixture(scope='module')
def frozen_start_boundary():
    source = source_bytes(FROZEN, SUBMISSION)
    legacy = ModuleType('frozen_start_facts_before_retry')
    exec(compile(source, '<frozen-start-facts-before-retry>', 'exec'), legacy.__dict__)
    player_source = source_bytes(FROZEN, PLAYER)
    return legacy, hook_from(player_source)


@pytest.mark.parametrize('first', ['timeout', 'unavailable'])
def test_frozen_old_capture_and_hook_consume_first_failed_read_even_when_next_would_succeed(
        scene, monkeypatch, frozen_start_boundary, first):
    legacy, hook = frozen_start_boundary
    expected = view(scene)

    def response(attempt, timeout):
        if attempt == 1:
            if first == 'timeout':
                raise TimeoutError('transient read')
            return deepcopy(UNAVAILABLE)
        return deepcopy(expected)

    calls = install_call(scene, response)
    monkeypatch.setitem(sys.modules, 'lib.services.playback_history', legacy)
    writes = []
    actor = hook_actor(scene, writes)
    hook(actor)
    hook(actor)
    assert len(calls) == len(writes) == 1
    assert '_file_start_observation' not in writes[0]
    assert actor._cinema_history_pending is False
    assert scene.files.save(writes[0])
    assert scene.file['id'] not in (scene.db.get_key_checked(history.FACTS_KEY) or {})
    # The same frozen reader could succeed later, but its production hook has
    # already consumed the only opportunity. Only timeout is repaired by the
    # new reader; generic unavailable deliberately remains a final boundary.
    assert legacy.capture_start(scene.data, scene.client, scene.owner, scene.row['native_instance'], scene.binding)
    assert len(calls) == 2 and '_file_start_observation' in scene.data

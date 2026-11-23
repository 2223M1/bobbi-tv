"""Tool-only query acceptance; never execute the remote device entrypoint."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest


ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / 'tools/ce_trial_remote.py'
SPEC = importlib.util.spec_from_file_location('query_trial_cli', ROOT / 'tools/ce_playback_trial.py')
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
TEST = dict(title='Fixture', tmdb_id=123, kind='movie', year=2026)
PICKER = dict(window=13001, generation=2, intent=0, tmdb_id=123, kind='movie')


def view(loading='false', count='0', error=''):
    return dict(stable=True, window=13001, visible=[13001], generation=2, intent=0,
        labels={'Window.Property(info.ids)': "{'tmdb_id': 123}",
                'Window.Property(info.media_type)': 'movie',
                'Window.Property(source_loading)': loading,
                'Window.Property(source_count)': count,
                'Window.Property(playback_error)': error})


def functions():
    tree = ast.parse(REMOTE.read_text(encoding='utf-8'))
    names = {'property_dict', 'picker_identity', 'bind_picker', 'require_picker', 'picker_query_receipt'}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = dict(ast=ast, PICKER_WINDOWS=(13001, 13002), time=SimpleNamespace(monotonic=lambda: 1))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(REMOTE), 'exec'), scope)
    return scope


def result(loading='false', count='0', error='', operation='start'):
    record = dict(launch_accepted=True, picker=deepcopy(PICKER))
    query = functions()['picker_query_receipt'](record, view(loading, count, error))
    return dict(operation=operation, launch_accepted=True, record=record, query=query)


@pytest.mark.parametrize('operation', ['start', 'requery'])
@pytest.mark.parametrize('count', ['0', '1', '100'])
def test_completed_error_free_query_is_accepted_including_empty(operation, count):
    value = result(count=count, operation=operation)
    assert value['query']['completed'] is True and value['query']['accepted'] is True
    assert value['query']['source_count'] == int(count)
    assert CLI.result_exit_code(value) == 0


@pytest.mark.parametrize('count', ['0', '7'])
@pytest.mark.parametrize('loading', ['true', 'false', None])
def test_explicit_query_error_is_failure_even_with_cards_or_launch_ack(count, loading):
    value = result(loading, count, '1 个来源查询失败或超时')
    assert value['launch_accepted'] is True and value['record']['launch_accepted'] is True
    assert value['query']['accepted'] is False
    assert CLI.result_exit_code(value) == 1


@pytest.mark.parametrize('loading,count,error', [
    ('true', '0', ''), ('true', '7', ''), ('', '0', ''), (None, '7', ''),
    ('false', '', ''), ('false', '-1', ''), ('false', 'unknown', ''),
    ('false', '１', ''), ('false', '0', None),
])
def test_incomplete_observation_is_not_a_query_failure_or_success(loading, count, error):
    value = result(loading, count, error)
    assert value['query']['accepted'] is None
    assert CLI.result_exit_code(value) == 2


@pytest.mark.parametrize('key,value', [
    ('schema', True), ('schema', 2), ('completed', None), ('completed', 'true'),
    ('accepted', 'true'), ('loading', 'true'), ('error', None),
    ('source_count', True), ('source_count', -1), ('source_count', '0'),
    ('picker', None), ('picker', dict(PICKER, generation=3)),
])
def test_summary_or_malformed_fields_cannot_replace_positive_query_evidence(key, value):
    observed = result()
    observed['query'][key] = value
    assert CLI.result_exit_code(observed) == 2


@pytest.mark.parametrize('location', ['top', 'record'])
def test_positive_query_does_not_invent_launch_acceptance(location):
    observed = result()
    (observed if location == 'top' else observed['record']).pop('launch_accepted')
    assert CLI.result_exit_code(observed) == 2


@pytest.mark.parametrize('record', [None, [], 'record', {'launch_accepted': True, 'picker': 'picker'}])
def test_malformed_record_cannot_supply_query_binding(record):
    observed = result()
    observed['record'] = record
    observed['query']['picker'] = 'picker'
    assert CLI.result_exit_code(observed) == 2


def legacy(count='0', error='', window=13001):
    return dict(operation='start', record=dict(launched_at=123, picker=deepcopy(PICKER)),
        samples=[dict(labels={'Window.Property(source_count)': count,
                              'Window.Property(playback_error)': error},
                      window={'currentwindow': {'id': window}})])


@pytest.mark.parametrize('count', ['0', '7', ''])
def test_legacy_launch_receipt_cannot_prove_completion_from_count_or_no_error(count):
    value = legacy(count)
    before = deepcopy(value)
    assert CLI.result_exit_code(value) == 2
    assert value == before  # Retained launch evidence is not rewritten.


def test_ff0422_attempt1_shape_keeps_error_and_zero_distinct():
    value = legacy('0', '1 个来源查询失败或超时')
    assert CLI.result_exit_code(value) == 1
    value['samples'][-1]['labels']['Window.Property(playback_error)'] = ''
    assert CLI.result_exit_code(value) == 2  # Zero alone is not failure.
    assert CLI.result_exit_code(result(count='0')) == 0  # Proven healthy empty is accepted.


def test_legacy_foreign_window_error_does_not_claim_current_query_failure():
    assert CLI.result_exit_code(legacy('0', 'old error', window=10000)) == 2


def test_transport_or_playback_failure_still_overrides_query_acceptance():
    assert CLI.result_exit_code(result(), remote_code=1) == 1
    assert CLI.result_exit_code(result(), diagnostic=True) == 1
    assert CLI.result_exit_code(dict(result(), samples=[{'failure': 'failed'}])) == 1
    assert CLI.result_exit_code(dict(result(), error='AssertionError')) == 1


def test_old_cards_read_and_other_operation_exit_semantics_are_unchanged():
    assert CLI.result_exit_code(dict(operation='cards', selected=False)) == 0
    assert CLI.result_exit_code(dict(operation='select', selected=False)) == 2
    assert CLI.result_exit_code(dict(operation='observe', passed=True)) == 0
    assert CLI.result_exit_code({}, operation='requery') == 2


def run_start_branch(tmp_path, operation='start', first=None, final=None):
    """Execute the actual start/requery body with no device or product imports."""
    scope = functions()
    state = dict(now=0, reads=0, launches=[], saved=[], printed=[])
    first = first or view()
    final = final or first
    path = tmp_path/'trial.json'
    if operation == 'requery':
        path.write_text('{}')
    def observe():
        state['reads'] += 1
        return deepcopy(first if state['reads'] == 1 else final)
    def sleep(seconds):
        state['now'] += seconds
    scope.update(NAME='fixture', OP=operation, TESTS={'fixture': TEST}, record_path=path,
        PICKER=True, ORDINARY_UI=True, START_OVER=False, RESUME_PERCENT=None,
        json=json, urlencode=urlencode, snapshot=lambda: {}, can_start_trial=lambda _: True,
        trial_metadata=lambda _: {'verified': True}, prepare_home=lambda _: dict(generation=1, intent=0),
        assert_picker_idle=lambda _: None, gui_observation=observe,
        rpc=lambda method: [] if method == 'Player.GetActivePlayers' else pytest.fail(method),
        sample=lambda _: dict(labels={'Window.Property(source_count)': '0',
                                      'Window.Property(playback_error)': ''}),
        save=lambda record: state['saved'].append(deepcopy(record)),
        print=state['printed'].append,
        time=SimpleNamespace(monotonic=lambda: state['now'], sleep=sleep),
        shutil=SimpleNamespace(which=lambda _: 'kodi-send'),
        subprocess=SimpleNamespace(DEVNULL=None, run=lambda args, **kw: state['launches'].append(args)))
    tree = ast.parse(REMOTE.read_text(encoding='utf-8'))
    branch = next(node for node in tree.body if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "OP in ('start', 'requery')")
    code = compile(ast.Module(body=branch.body, type_ignores=[]), str(REMOTE), 'exec')
    return scope, state, code


@pytest.mark.parametrize('operation', ['start', 'requery'])
@pytest.mark.parametrize('error,expected', [('', 0), ('1 个来源查询失败或超时', 1)])
def test_actual_operation_reports_guarded_query_separately_from_launch(tmp_path, operation, error, expected):
    scope, state, code = run_start_branch(tmp_path, operation, final=view(error=error))
    exec(code, scope)
    observed = json.loads(state['printed'][-1])
    assert CLI.result_exit_code(observed) == expected
    assert observed['launch_accepted'] is True and observed['record']['launch_accepted'] is True
    assert observed['query']['picker'] == observed['record']['picker']
    assert observed['query']['error'] == error and observed['query']['source_count'] == 0
    assert len(state['launches']) == 1 and state['reads'] == 2
    assert state['saved'][-1]['launch_accepted'] is True


def test_actual_pending_query_preserves_bounded_wait_and_launch_not_success(tmp_path):
    scope, state, code = run_start_branch(tmp_path, first=view(loading='true'))
    exec(code, scope)
    observed = json.loads(state['printed'][-1])
    assert state['now'] == 28 and len(state['launches']) == 1
    assert observed['launch_accepted'] is True
    assert observed['query']['completed'] is False and observed['query']['accepted'] is None
    assert CLI.result_exit_code(observed) == 2


def test_final_guarded_view_not_loop_break_or_old_sample_decides_completion(tmp_path):
    scope, state, code = run_start_branch(tmp_path, final=view(loading='true'))
    exec(code, scope)
    observed = json.loads(state['printed'][-1])
    assert state['reads'] == 2 and state['now'] == 0
    assert observed['query']['completed'] is False and CLI.result_exit_code(observed) == 2


def test_replaced_picker_guard_remains_fail_closed_after_successful_launch(tmp_path):
    scope, state, code = run_start_branch(tmp_path, final=dict(view(), generation=3))
    with pytest.raises(AssertionError, match='PICKER_REPLACED'):
        exec(code, scope)
    assert len(state['launches']) == 1 and not state['printed']
    assert state['saved'][-1]['launch_accepted'] is True


@pytest.mark.parametrize('operation', ['start', 'requery'])
@pytest.mark.parametrize('loading,error,expected', [
    ('false', '', 0), ('false', 'query failed', 1), ('true', '', 2),
])
def test_cli_retains_query_launch_and_correct_exit_in_full_and_brief_evidence(
        tmp_path, monkeypatch, capsys, operation, loading, error, expected):
    observed = result(loading=loading, error=error, operation=operation)
    closed = []
    client = SimpleNamespace(close=lambda: closed.append(True))
    wire = SimpleNamespace(readonly=lambda *args, **kwargs: (0, observed, False))
    transport = SimpleNamespace(connect=lambda: (client, wire))
    spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _: None))
    monkeypatch.setattr(CLI.importlib.util, 'spec_from_file_location', lambda *args: spec)
    monkeypatch.setattr(CLI.importlib.util, 'module_from_spec', lambda _: transport)
    monkeypatch.setattr(CLI, 'remote_code', lambda _: 'pass')
    work = next(iter(CLI.trial_cases()['works']))
    monkeypatch.setattr(CLI.sys, 'argv', ['trial', work, operation, '--transport-source', str(tmp_path),
                                       '--output-dir', str(tmp_path), '--brief'])
    if expected:
        with pytest.raises(SystemExit) as raised:
            CLI.main()
        assert raised.value.code == expected
    else:
        CLI.main()
    brief = json.loads(capsys.readouterr().out)
    retained = json.loads(Path(brief['evidence']).read_text(encoding='utf-8'))
    assert retained['exit_code'] == retained['trial_exit_code'] == expected
    assert retained['transport_exit_code'] == 0 and retained['result'] == observed
    assert brief['result']['launch_accepted'] is True and brief['result']['query'] == observed['query']
    assert closed == [True]

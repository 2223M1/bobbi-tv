"""Tool-only checks. Never import/execute the remote trial's device entrypoint."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / 'tools/ce_trial_remote.py'


def control_function(name='unsupported_control_evidence'):
    tree = ast.parse(REMOTE.read_text(encoding='utf-8'))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(REMOTE), 'exec'), namespace)
    return namespace


def f9_schema():
    def fields(**params):
        return dict(params=[dict(name=name, **value) for name, value in params.items()])
    return dict(methods={
        'Player.BobiControl': fields(native_instance={'type': 'string'},
            action={'type': 'string', 'enum': ['stop', 'pause', 'resume']}),
        'Player.BobiSubtitle': fields(native_instance={'type': 'string'},
            subtitle_intent={'type': 'integer', 'minimum': 0}, index={'type': 'integer', 'minimum': 0}),
        'Player.Seek': fields(playerid={'type': 'integer'}, value={'type': 'object'}),
        'Player.SetSubtitle': fields(playerid={'type': 'integer'}, subtitle={'type': 'string'}),
        'Settings.SetSettingValue': fields(setting={'type': 'string'}, value={'type': 'any'}),
    })


def test_previous_cancelled_source_is_not_new_picker_failure():
    status = control_function('request_status')['request_status']
    old = dict(request_id='old', cancelled=True, resolver_failure={'category':'buffer_timeout'})
    assert status({}, old) == dict(cancelled=None, failure=None, prior_failure='buffer_timeout')
    assert status({'request_id':'new'}, old)['failure'] is None
    assert status({'request_id':'old'}, old) == dict(cancelled=True, failure='buffer_timeout', prior_failure=None)


@pytest.mark.parametrize('already_cancelled', [False, True])
def test_owned_cancel_accepts_matching_state_without_second_global_back(already_cancelled):
    namespace = control_function('cancel_pending')
    before = dict(boot_id='boot', epoch=2, desired=dict(request_id='request', cancelled=already_cancelled))
    after = copy.deepcopy(before)
    after['desired']['cancelled'] = True
    calls = []
    namespace.update(state=lambda _: (before, {}, {}), snapshot=lambda: after,
                     call=lambda value: calls.append(value) or {'cancelled': False})
    assert namespace['cancel_pending']({'request_id':'request'}) is True
    assert len(calls) == (0 if already_cancelled else 1)
    if calls:
        assert calls[0] == dict(operation='cancel', boot_id='boot', epoch=2, request_id='request')


@pytest.mark.parametrize('changed', ['epoch','request','not_cancelled'])
def test_owned_cancel_readback_cannot_claim_a_different_request(changed):
    namespace = control_function('cancel_pending')
    before = dict(boot_id='boot', epoch=2, desired=dict(request_id='request', cancelled=False))
    after = copy.deepcopy(before)
    after['desired']['cancelled'] = changed != 'not_cancelled'
    if changed == 'epoch': after['epoch'] += 1
    if changed == 'request': after['desired']['request_id'] = 'another'
    namespace.update(state=lambda _: (before, {}, {}), snapshot=lambda: after,
                     call=lambda _: {'cancelled': True})
    with pytest.raises(AssertionError):
        namespace['cancel_pending']({'request_id':'request'})


@pytest.mark.parametrize('operation', ['seek', 'manual_off', 'font_switch'])
def test_unsupported_controls_only_read_schema_and_never_claim_pass(operation):
    namespace = control_function()
    calls = []
    playback = dict(native_instance='n' * 36, request_id='r' * 32)
    record = dict(request_id='r' * 32)
    original = copy.deepcopy(record)
    def state(value, require=False):
        assert value is record and require is True
        calls.append('state')
        return {}, {}, playback
    def rpc(method, params):
        calls.append(method)
        assert method == 'JSONRPC.Introspect'  # No global Player/Settings mutation.
        return f9_schema()
    namespace.update(state=state, rpc=rpc)
    result = namespace['unsupported_control_evidence'](record, operation)
    assert calls == ['state', 'JSONRPC.Introspect', 'state']
    assert record == original
    assert result['state'] == 'not_tested' and result['passed'] is None
    assert result['mutation_performed'] is False and result['operation'] == operation
    assert result['observed_protocol']['Player.BobiControl']['action']['enum'] == ['stop', 'pause', 'resume']
    assert result['observed_protocol']['Player.BobiSubtitle']['index']['minimum'] == 0


def test_future_schema_does_not_silently_authorize_an_unreviewed_action():
    namespace = control_function()
    value = dict(native_instance='n' * 36, request_id='r' * 32)
    schema = f9_schema()
    schema['methods']['Player.BobiControl']['params'][1]['enum'].append('seek')
    namespace.update(state=lambda *a, **kw: ({}, {}, value), rpc=lambda *a: schema)
    result = namespace['unsupported_control_evidence']({}, 'seek')
    assert result['state'] == 'not_tested' and result['mutation_performed'] is False


def test_selection_change_during_read_does_not_produce_same_instance_evidence():
    namespace = control_function()
    replies = iter([dict(native_instance='a' * 36, request_id='r' * 32),
                    dict(native_instance='b' * 36, request_id='r' * 32)])
    namespace.update(state=lambda *a, **kw: ({}, {}, next(replies)), rpc=lambda *a: f9_schema())
    with pytest.raises(AssertionError, match='OTHER_INSTANCE'):
        namespace['unsupported_control_evidence']({}, 'manual_off')


def test_invalid_protocol_evidence_is_not_reported_as_successful_inspection():
    namespace = control_function()
    namespace.update(state=lambda *a, **kw: ({}, {}, {}), rpc=lambda *a: {'methods': []})
    with pytest.raises(AssertionError, match='CONTROL_SCHEMA_UNAVAILABLE'):
        namespace['unsupported_control_evidence']({}, 'font_switch')


def test_no_hidden_unguarded_seek_subtitle_off_or_font_setting_rpc_remains():
    tree = ast.parse(REMOTE.read_text(encoding='utf-8'))
    disallowed = {'Player.Seek', 'Player.SetSubtitle', 'Settings.SetSettingValue'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'rpc' and node.args:
            argument = node.args[0]
            assert not isinstance(argument, ast.Constant) or argument.value not in disallowed


def test_driver_distinguishes_unsupported_from_failure_and_completed_operation():
    spec = importlib.util.spec_from_file_location('ce_trial_cli', ROOT / 'tools/ce_playback_trial.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    assert driver.result_exit_code({'state': 'not_tested', 'passed': None}) == 2
    assert driver.result_exit_code({'state': 'not_tested'}, remote_code=1) == 1
    assert driver.result_exit_code({'error': 'AssertionError'}) == 1
    assert driver.result_exit_code({'selected': True}) == 0
    assert driver.result_exit_code({'operation': 'select', 'selected': False}) == 2
    assert driver.result_exit_code({'operation': 'cards', 'selected': False}) == 0
    assert driver.result_exit_code({'selected': True, 'samples': [{'failure': 'target_unresolved'}]}) == 1
    assert driver.result_exit_code({'selected': True, 'trace_passed': False,
                                   'trace_coverage': {'passed': None}}) == 2
    assert driver.result_exit_code({'trace_passed': False, 'trace_coverage': {'passed': False}}) == 1
    assert driver.result_exit_code({'trace_passed': True, 'trace_coverage': {'passed': True}}) == 0


def picker_harness(monkeypatch, never_rewind=False, replaced_after_focus=False):
    namespace = control_function('rewind_picker')
    rows = [dict(title='top target', key='one'), dict(title='middle', key='two'),
            dict(title='last', key='three')]
    state = dict(index=2, now=0, selected=None, calls=[], focus=False, guards=0)
    def guard(record):
        state['guards'] += 1
        if replaced_after_focus and state['focus']:
            raise AssertionError('PICKER_REPLACED')
    def focus(*args, **kwargs):
        state['focus'] = True
        state['calls'].append('focus')
    def rpc(method, params=None):
        state['calls'].append(method)
        if method == 'Input.ExecuteAction':
            assert params == {'action': 'firstpage'} and state['focus']
            if not never_rewind:
                state['index'] = 0
            return 'OK'
        if method == 'XBMC.GetInfoBooleans':
            return {'Control.HasFocus(1000)': state['focus']}
        if method == 'XBMC.GetInfoLabels':
            card = rows[state['index']]
            values = {'Container(1000).CurrentItem': str(state['index'] + 1),
                      'Container(1000).NumItems': str(len(rows)),
                      'Container(1000).ListItem.Label': card['title'],
                      'Container(1000).ListItem.Property(source_site)': 'fixture',
                      'Container(1000).ListItem.Property(source_key)': card['key']}
            return {key: values.get(key, '') for key in params['labels']}
        if method == 'Input.Down':
            state['index'] = min(state['index'] + 1, len(rows) - 1)  # Does not wrap.
            return 'OK'
        if method == 'Input.Select':
            state['selected'] = rows[state['index']]['key']
            return 'OK'
        pytest.fail('Unexpected method: ' + method)
    def sleep(seconds):
        state['now'] += seconds
    namespace.update(require_picker=guard, rpc=rpc,
        subprocess=types.SimpleNamespace(run=focus, DEVNULL=None),
        shutil=types.SimpleNamespace(which=lambda _: 'kodi-send'),
        time=types.SimpleNamespace(monotonic=lambda: state['now'], sleep=sleep))
    return namespace, state


def test_rewind_observes_first_item_on_nonwrapping_list(monkeypatch):
    namespace, state = picker_harness(monkeypatch)
    assert namespace['rewind_picker']({}) == dict(current_item=1, item_count=3, reset_action='firstpage')
    assert state['index'] == 0 and state['selected'] is None
    assert state['calls'].count('Input.ExecuteAction') == 1 and state['guards'] >= 4


def test_rewind_failure_does_not_start_traversal_or_select(monkeypatch):
    namespace, state = picker_harness(monkeypatch, never_rewind=True)
    with pytest.raises(AssertionError, match='PICKER_FIRST_ITEM_NOT_OBSERVED'):
        namespace['rewind_picker']({}, timeout=.2)
    assert state['index'] == 2 and state['selected'] is None
    assert 'Input.Down' not in state['calls'] and state['calls'].count('Input.ExecuteAction') == 1


def test_picker_replaced_after_focus_rejects_firstpage_action(monkeypatch):
    namespace, state = picker_harness(monkeypatch, replaced_after_focus=True)
    with pytest.raises(AssertionError, match='PICKER_REPLACED'):
        namespace['rewind_picker']({})
    assert 'Input.ExecuteAction' not in state['calls'] and state['selected'] is None


def test_cards_then_select_restarts_at_top_in_real_operation_branch(monkeypatch):
    namespace, state = picker_harness(monkeypatch)
    tree = ast.parse(REMOTE.read_text(encoding='utf-8'))
    branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "OP in ('cards', 'select')")
    results = []
    namespace.update(NAME='fixture', OP='cards', TITLE='top target', SITE='fixture', SOURCE_KEY='one',
                     TRACE=False, record={}, save=lambda _: None, json=json, print=results.append)
    code = compile(ast.Module(body=branch.body, type_ignores=[]), str(REMOTE), 'exec')
    exec(code, namespace)
    assert state['index'] == 2 and [row['Container(1000).ListItem.Label']
        for row in json.loads(results[-1])['cards']] == ['top target', 'middle', 'last']
    namespace['OP'] = 'select'
    exec(code, namespace)
    assert state['selected'] == 'one'
    result = json.loads(results[-1])
    assert result['selected'] is True and result['picker_start']['current_item'] == 1
    assert state['calls'].count('Input.ExecuteAction') == 2

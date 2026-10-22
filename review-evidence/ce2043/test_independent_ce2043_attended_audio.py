"""Execute attended control logic with RPC/imports removed; no network or device IO."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path('D:/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021')
sys.path.insert(0, str(ROOT/'tools'))
import ce_attended_player_action as tool

RID = 'a' * 32
INSTANCE = '11111111-2222-3333-4444-555555555555'


def run(case):
    tree = ast.parse(tool.REMOTE)
    # Keep production read/action/recheck/receipt code, eliminate every IO definition.
    nodes = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
             and not (isinstance(node, ast.FunctionDef) and node.name == 'rpc')]
    calls, output = [], []
    reads = 0
    def rpc(method, params=None):
        nonlocal reads
        calls.append((method, params))
        if method == 'Player.BobiState':
            reads += 1
            changed = (case == 'recheck_changed' and reads == 2) or (case == 'after_changed' and reads == 3)
            return dict(selection_epoch=1, playback=dict(request_id=RID,
                native_instance='other' if changed else INSTANCE, phase='AV_STARTED', sequence=2,
                user_intent=0, audio_intent=2, subtitle_intent=3, paused=False))
        if method == 'Player.GetActivePlayers': return [dict(playerid=1, type='video', playertype='internal')]
        if method == 'Player.GetProperties':
            if params['properties'] == ['audiostreams']:
                return dict(audiostreams=[dict(index=0, language='jpn')] * (2 if case == 'duplicate' else 1))
            if case == 'after_missing' and reads == 3: return {}
            index = 0 if reads == 3 and case not in ('late_switch',) else 1
            return dict(currentaudiostream=dict(index=index, language='jpn' if index == 0 else 'eng'))
        if method == 'XBMC.GetInfoLabels': return {}
        assert method == 'Player.SetAudioStream' and params == dict(playerid=1, stream=0)
        if case == 'lost_ack': raise TimeoutError('fixture')
        return 'OK'
    namespace = dict(REQUEST=RID, INSTANCE=INSTANCE, ACTION='audio-index', PERCENT=None, AUDIO_INDEX=0,
        rpc=rpc, json=json, time=SimpleNamespace(sleep=lambda _: None), print=output.append)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<attended-audio-no-io>', 'exec'), namespace)
    assert len(output) == 1
    return json.loads(output[0]), [call for call in calls if call[0] == 'Player.SetAudioStream']


@pytest.mark.parametrize('case,state,count', [
    ('success', 'observed_after_action', 1), ('late_switch', 'action_acknowledged_pending', 1),
    ('after_missing', 'action_acknowledged_pending', 1), ('after_changed', 'unconfirmed', 1),
    ('lost_ack', 'unconfirmed', 1), ('recheck_changed', 'unconfirmed', 0), ('duplicate', 'unconfirmed', 0),
])
def test_audio_index_requires_observed_after_index_without_replay_or_cas_claim(case, state, count):
    receipt, commands = run(case)
    assert receipt['state'] == state and len(commands) == count
    assert receipt['atomic_instance_bound'] is False
    assert receipt['mode'] == 'attended_human_equivalent_input'
    if case == 'late_switch':
        assert receipt['acknowledged'] is True
        assert receipt['audio_index'] == 0 and receipt['after']['properties']['currentaudiostream']['index'] == 1


def test_pending_after_ack_fails_cli_exit_condition(tmp_path):
    receipt, _ = run('late_switch')
    path = tmp_path/'receipt.json'
    path.write_text(json.dumps(receipt))
    tree = ast.parse((ROOT/'tools/ce_attended_player_action.py').read_text())
    main = next(node for node in tree.body if isinstance(node, ast.If)
                and ast.unparse(node.test) == "__name__ == '__main__'")
    final_condition = main.body[-1]
    assert isinstance(final_condition, ast.If)
    with pytest.raises(SystemExit) as result:
        exec(compile(ast.Module(body=[final_condition], type_ignores=[]), '<audio-cli-exit-no-io>', 'exec'),
             dict(json=json, args=SimpleNamespace(output=path)))
    assert result.value.code == 1

"""Exact IDs, not adjacent logs, prove a native continuation observation."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import queue
import socket
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
tree = ast.parse((ROOT/'tools/ce_trial_remote.py').read_text())
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('next_native_row', 'next_log_rows', 'next_chain_evidence')]
scope = dict(hashlib=hashlib, json=json, re=re)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<real-next-evidence>', 'exec'), scope)
evidence, public, log_rows = (scope[name] for name in ('next_chain_evidence', 'next_native_row', 'next_log_rows'))


def chain():
    parent = dict(request_id='a'*32, native_instance='11111111-1111-1111-1111-111111111111', file_sha256='b'*64)
    child = dict(request_id='c'*32, native_instance='22222222-2222-2222-2222-222222222222', file_sha256='d'*64)
    terminal = dict(parent, phase='TERMINAL', sequence=10, reason='NATURAL_EOF',
                    completion_observation=dict(schema=1, position_ms=99960, duration_ms=100000, age_us=1000, valid=True))
    grant = dict(schema=1, kind='natural', stage='GRANTED', parent_request_id=parent['request_id'],
                 parent_native_instance=parent['native_instance'], selection_sha256='e'*64, child_request_id='')
    reserved = dict(grant, stage='CHILD_RESERVED', child_request_id=child['request_id'])
    return parent, [terminal, dict(child, phase='OPEN', sequence=1), dict(child, phase='AV_STARTED', sequence=2)], [
        dict(request_id=child['request_id'], selection_sha256='e'*64, file_sha256=child['file_sha256'])], [grant, reserved]


def test_full_chain_retains_terminal_observation_and_exact_target():
    args = chain()
    result = evidence(*args)
    assert result['passed'] is True and result['attribution'] == 'exact_causal_chain'
    assert result['terminal']['completion_observation']['valid'] is True
    assert result['target'] == args[2][0]


@pytest.mark.parametrize('damage', ['grant_missing', 'reservation_missing', 'terminal_missing', 'stop', 'error',
    'parent_request', 'parent_native', 'target', 'child_request', 'child_native', 'open_missing',
    'av_missing', 'late_old_sequence', 'grant_order', 'duplicate_grant', 'wrong_selection'])
def test_partial_and_unrelated_events_cannot_be_upgraded(damage):
    parent, rows, selections, logs = chain()
    if damage == 'grant_missing': logs.pop(0)
    elif damage == 'reservation_missing': logs.pop()
    elif damage == 'terminal_missing': rows.pop(0)
    elif damage in ('stop', 'error'): rows[0]['reason'] = damage.upper()
    elif damage == 'parent_request': logs[0]['parent_request_id'] = 'f'*32
    elif damage == 'parent_native': logs[0]['parent_native_instance'] = rows[-1]['native_instance']
    elif damage == 'target': rows[-1]['file_sha256'] = 'f'*64
    elif damage == 'child_request': rows[-1]['request_id'] = parent['request_id']
    elif damage == 'child_native': rows[-1]['native_instance'] = parent['native_instance']
    elif damage == 'open_missing': rows.pop(1)
    elif damage == 'av_missing': rows.pop()
    elif damage == 'late_old_sequence': rows[-1]['sequence'] = 0
    elif damage == 'grant_order': logs.reverse()
    elif damage == 'duplicate_grant': logs.append(deepcopy(logs[0]))
    elif damage == 'wrong_selection': selections[0]['selection_sha256'] = 'f'*64
    result = evidence(parent, rows, selections, logs)
    assert result['passed'] is False and result['missing'] and result['attribution'] == 'incomplete'


def test_absent_completion_data_stays_unavailable_not_a_polling_completion_vote():
    args = chain()
    args[1][0].pop('completion_observation')
    result = evidence(*args)
    assert result['causal_chain_passed'] and result['passed'] is False
    assert result['completion_observation_available'] is False
    assert result['completion_observation_qualified'] is None
    assert 'completion_observation' not in result['terminal']


@pytest.mark.parametrize('changes', [dict(valid=False, position_ms=0, duration_ms=0, age_us=0),
    dict(age_us=5000001), dict(position_ms=22000), dict(position_ms=104000), dict(duration_ms=0)])
def test_complete_identity_chain_cannot_upgrade_rejected_completion(changes):
    args = chain()
    args[1][0]['completion_observation'].update(changes)
    result = evidence(*args)
    assert result['causal_chain_passed'] and result['completion_observation_qualified'] is False
    assert result['passed'] is False


def test_malformed_present_field_does_not_become_legacy_missing_evidence():
    args = chain()
    args[1][0].pop('completion_observation')
    args[1][0]['completion_observation_present'] = True
    result = evidence(*args)
    assert result['causal_chain_passed'] and result['completion_observation_qualified'] is False
    assert result['passed'] is False


def test_native_public_projection_drops_locators_and_unavailable_fields():
    raw = dict(request_id='a'*32, native_instance='11111111-1111-1111-1111-111111111111',
        file_identity='private-file', url='https://private/token', phase='TERMINAL', sequence=1, reason='NATURAL_EOF',
        completion_observation={'valid': True})
    result = public(raw)
    assert result['file_sha256'] == hashlib.sha256(b'private-file').hexdigest()
    assert 'private' not in json.dumps(result) and 'completion_observation' not in result


def test_only_whitelisted_exact_logs_are_consumed():
    _, _, _, logs = chain()
    text = '\n'.join('[BOBBI-CONTINUATION] '+json.dumps(row) for row in logs)
    assert log_rows(text) == logs
    assert log_rows('[CINEMA-NEXT] NATURAL_EOF_SAME_VERSION_HANDOFF') == []
    assert log_rows('[BOBBI-CONTINUATION] '+json.dumps(dict(logs[0], token='secret'))) == []


def acquisition_trial(monkeypatch, tmp_path, damage=None):
    """Actual watcher/thread/parser with local fake wire; no Kodi or network."""
    raw_parent = dict(request_id='a'*32, native_instance='11111111-1111-1111-1111-111111111111',
                      file_identity='parent-private-file', phase='AV_STARTED', sequence=2)
    raw_child = dict(request_id='c'*32, native_instance='22222222-2222-2222-2222-222222222222',
                     file_identity='child-private-file', phase='AV_STARTED', sequence=2)
    terminal = dict(raw_parent, phase='TERMINAL', sequence=3, reason='NATURAL_EOF',
        completion_observation=dict(schema=1, position_ms=99960, duration_ms=100000, age_us=1000, valid=True))
    grant = dict(schema=1, kind='natural', stage='GRANTED', parent_request_id=raw_parent['request_id'],
        parent_native_instance=raw_parent['native_instance'],
        selection_sha256=hashlib.sha256(b'child-private-selection').hexdigest(), child_request_id='')
    logs = [grant, dict(grant, stage='CHILD_RESERVED', child_request_id=raw_child['request_id'])]
    path = tmp_path/'kodi.log'
    path.write_text('baseline\n', encoding='utf-8')

    class Wire:
        def __init__(self): self.incoming, self.sent = queue.Queue(), []
        def settimeout(self, timeout): pass
        def sendall(self, raw):
            self.sent.append(json.loads(raw))
            self.incoming.put(json.dumps(dict(id=1,result={})).encode())
        def recv(self, maximum):
            try: return self.incoming.get(timeout=.05)
            except queue.Empty: raise socket.timeout()
        def close(self): self.incoming.put(b'')
        def event(self, raw):
            self.incoming.put(json.dumps(dict(method='Player.OnBobiState',params=dict(data=raw))).encode())
    wire = Wire()
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: wire)
    counts = dict(snapshot=0, poll=0)
    published = [False]
    def publish():
        published[0] = True
        with path.open('a', encoding='utf-8') as stream:
            for entry in logs:
                stream.write('[BOBBI-CONTINUATION] '+json.dumps(entry)+'\n')
        if damage == 'malformed_event': wire.incoming.put(b'[]')
        if damage != 'missing_open': wire.event(dict(raw_child,phase='OPEN',sequence=1))
        wire.event(raw_child)

    def snapshot():
        counts['snapshot'] += 1
        if counts['snapshot'] == 2:
            wire.event(terminal)
        if (damage in ('owner_once','wrong_target') and counts['snapshot'] == 2 or
                damage == 'owner_forever' and counts['snapshot'] >= 2):
            error = RuntimeError('PLAYBACK_OWNER_UNAVAILABLE')
            error.owner_response = 'unavailable'
            raise error
        child = published[0]
        return dict(desired=dict(request_id=(raw_child if child else raw_parent)['request_id'],file_bound=True,
            selection_identity='unrelated-private' if child and damage == 'wrong_target' else
                'child-private-selection' if child else 'parent-private-selection',
            file_identity=(raw_child if child else raw_parent)['file_identity']))

    def rpc(method):
        assert method == 'Player.BobiState'  # No input, seek, play or stop API.
        counts['poll'] += 1
        if counts['poll'] == 2:
            publish()
            if damage == 'native_poll_once': raise RuntimeError('private://response-must-not-escape')
        return dict(playback=raw_child if published[0] else raw_parent)

    namespace = dict(scope, Path=lambda _: path, time=time, snapshot=snapshot, rpc=rpc,
        state=lambda record, require: ({},{},raw_parent))
    node = next(node for node in ast.parse((ROOT/'tools/ce_trial_remote.py').read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'watch_next')
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<real-next-watch>','exec'),namespace)
    result = namespace['watch_next']({'request_id':raw_parent['request_id']},duration=1)
    assert wire.sent == [dict(jsonrpc='2.0', id=1, method='JSONRPC.SetConfiguration',
                             params={'notifications': {'Player': True}})]
    assert 'private' not in json.dumps(result)
    return result, counts


def test_live_acquisition_positive_control_requires_complete_exact_chain(monkeypatch, tmp_path):
    result, counts = acquisition_trial(monkeypatch, tmp_path)
    assert result['passed'] is True and result['causal_chain_passed'] is True
    assert result['acquisition_errors'] == [] and result['acquisition_error_details'] == []
    assert counts['snapshot'] >= 3 and counts['poll'] >= 3


@pytest.mark.parametrize('damage,channel', [('owner_once','OWNER_SNAPSHOT'),('native_poll_once','NATIVE_POLL')])
def test_one_channel_failure_does_not_close_other_channels_or_erase_error(monkeypatch, tmp_path, damage, channel):
    result, counts = acquisition_trial(monkeypatch, tmp_path, damage)
    assert result['causal_chain_passed'] is True and result['missing'] == []
    assert result['passed'] is False and result['attribution'] == 'incomplete'
    assert result['acquisition_errors'] == [channel+'_RuntimeError']
    detail = result['acquisition_error_details'][0]
    assert detail['channel'] == channel and detail['count'] == 1 and detail['recovered'] is True
    if channel == 'OWNER_SNAPSHOT': assert detail['owner_response'] == 'unavailable'
    assert counts['snapshot'] >= 3 and counts['poll'] >= 3


def test_permanent_owner_gap_keeps_native_and_log_evidence_but_never_invents_target(monkeypatch, tmp_path):
    result, counts = acquisition_trial(monkeypatch, tmp_path, 'owner_forever')
    assert result['passed'] is False and result['causal_chain_passed'] is False
    assert 'child_target' in result['missing'] and result['target'] is None
    assert len(result['continuation_events']) == 2
    assert any(row['phase']=='OPEN' for row in result['native_events'])
    assert result['acquisition_error_details'][0]['recovered'] is False
    assert counts['poll'] >= 3


@pytest.mark.parametrize('damage,missing', [('wrong_target','child_target'),('missing_open','child_open_av')])
def test_recovery_cannot_substitute_wrong_target_or_missing_native_open(monkeypatch, tmp_path, damage, missing):
    result, _ = acquisition_trial(monkeypatch, tmp_path, damage)
    assert result['passed'] is False and result['causal_chain_passed'] is False
    assert missing in result['missing']


def test_malformed_native_message_is_explicit_acquisition_failure(monkeypatch, tmp_path):
    result, _ = acquisition_trial(monkeypatch, tmp_path, 'malformed_event')
    assert result['passed'] is False and 'NATIVE_EVENT_MESSAGE_INVALID' in result['acquisition_errors']

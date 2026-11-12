"""Exact IDs, not adjacent logs, prove a native continuation observation."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

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

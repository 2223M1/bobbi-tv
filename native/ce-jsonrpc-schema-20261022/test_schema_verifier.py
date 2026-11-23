"""Parser counterexamples and real frozen predecessor mismatch; no WSL/device."""
import json
from pathlib import Path

import pytest

from verify_artifact import binary_methods_bytes, verify_methods


HERE = Path(__file__).resolve().parent
OLD = Path('D:/AM6B-Project/ce2038-native-original-audio-20261022/run-1792612141766198431/candidate.bin')


def encoded(name, method):
    return ('"'+name+'": '+json.dumps(method)).encode()+b'\0'


def test_real_predecessor_has_all_methods_but_old_bobicontrol_schema():
    expected = json.loads((HERE/'candidate/xbmc/interfaces/json-rpc/schema/methods.json').read_text())
    actual = binary_methods_bytes(OLD.read_bytes())
    assert len(actual) == len(expected) == 184 and set(actual) == set(expected)
    assert sorted(name for name in actual if actual[name] != expected[name]) == ['Player.BobiControl']
    with pytest.raises(AssertionError, match='BINARY_METHOD_SCHEMA_MISMATCH'):
        verify_methods(OLD.read_bytes(), expected)


def test_complete_method_comparison_not_bare_handoff_strings():
    method = dict(type='method', params=[dict(name='action', enum=['stop', 'handoff_capture'])])
    old = dict(type='method', params=[dict(name='action', enum=['stop'])])
    payload = encoded('Player.BobiControl', old)+b'handoff_capture\0handoff_stop\0'
    with pytest.raises(AssertionError, match='BINARY_METHOD_SCHEMA_MISMATCH'):
        verify_methods(payload, {'Player.BobiControl': method})


@pytest.mark.parametrize('change', ['bound', 'default', 'required', 'missing', 'unexpected'])
def test_field_semantics_and_method_set_are_exact(change):
    method = dict(type='method', params=[dict(name='request_id', maxLength=32, default='', required=False)])
    actual = json.loads(json.dumps(method))
    payload = b''
    if change == 'bound':
        actual['params'][0]['maxLength'] = 33
    elif change == 'default':
        actual['params'][0]['default'] = 'different'
    elif change == 'required':
        actual['params'][0]['required'] = True
    if change != 'missing':
        payload = encoded('Player.BobiControl', actual)
    if change == 'unexpected':
        payload += encoded('Player.Unexpected', method)
    with pytest.raises(AssertionError, match='BINARY_METHOD_'):
        verify_methods(payload, {'Player.BobiControl': method})


def test_duplicate_method_strings_are_rejected():
    method = dict(type='method', params=[])
    payload = encoded('Player.BobiControl', method)*2
    with pytest.raises(AssertionError, match='DUPLICATE_BINARY_METHOD'):
        verify_methods(payload, {'Player.BobiControl': method})


def test_valid_complete_schema_is_accepted_and_types_are_not_methods():
    method = dict(type='method', params=[])
    payload = encoded('Player.BobiControl', method)+encoded('Player.Property', dict(type='string'))
    assert verify_methods(payload, {'Player.BobiControl': method}) == {'Player.BobiControl': method}

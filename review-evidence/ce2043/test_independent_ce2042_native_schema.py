"""Pinned 8bb2 schema build counterexample, no native execution or device IO."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('D:/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021')
OUT = Path('D:/AM6B-Project/ce2029-results-20261021')
RUN = Path('D:/AM6B-Project/ce2038-native-original-audio-20261022/run-1792612141766198431')
PIN = '8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14'
METHOD = 'Player.BobiControl'


def binary_method():
    raw = (RUN/'candidate.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PIN
    matches = [segment for segment in raw.split(b'\0')
               if segment.startswith(b'"Player.BobiControl": {')]
    assert len(matches) == 1
    return json.loads(b'{' + matches[0] + b'}')[METHOD]


def source_method():
    return json.loads((RUN/'source-candidate/xbmc/interfaces/json-rpc/schema/methods.json').read_text())[METHOD]


def test_pinned_shipped_binary_should_export_the_exact_frozen_handoff_control_schema():
    # Deliberately failing requirement witness; do not rewrite historical 8bb2.
    assert binary_method() == source_method()


def test_saved_device_control_contract_matches_the_old_binary_not_actor_capability_flag():
    runtime = json.loads((OUT/'ce2042-runtime-contract2.json').read_text())
    actual = runtime['native_control']['params']
    frozen = binary_method()['params']
    assert [p['name'] for p in actual] == [p['name'] for p in frozen]
    assert actual[-1]['enums'] == frozen[-1]['enum'] == ['stop', 'pause', 'resume']
    assert runtime['current']['handoff_protocol'] == 1
    assert runtime['current']['phase'] == 'AV_STARTED'


def test_generated_header_has_new_schema_and_recompiled_description_tu_really_consumed_it():
    text = (RUN/'candidate/generated/ServiceDescription.h').read_text()
    parts, started = [], False
    for line in text.splitlines():
        value = line.strip()
        if value.startswith(r'"\"Player.BobiControl\": {"'):
            started = True
        if started:
            parts.append(ast.literal_eval(value.rstrip(',')))
            if value.endswith('",'):
                break
    assert json.loads('{' + ''.join(parts) + '}')[METHOD] == source_method()
    deps = (RUN/'candidate/xbmc/interfaces/json-rpc/JSONServiceDescription.cpp.o.d').read_text()
    assert RUN.as_posix().replace('D:', '/mnt/d') + '/candidate/generated/ServiceDescription.h' in deps


def test_frozen_build_omitted_registration_tu_and_verifier_explicitly_retained_its_old_object():
    result = json.loads((RUN/'build-result.json').read_text())
    assert 'xbmc/interfaces/json-rpc/JSONRPC.cpp' not in result['recompiled_units']
    assert 'xbmc/interfaces/json-rpc/JSONServiceDescription.cpp' in result['recompiled_units']
    verify = json.loads((RUN/'artifact-verification.json').read_text())
    assert verify['retained_archive_members']['build/interfaces/json-rpc/jsonrpc_interface.a']['JSONRPC.cpp.o'] == (
        'bda05a83cefe51c195264c81d02a6203cd9f67ec6ca17d9ef85549f85e7f784e')


def test_new_capture_fields_and_action_are_absent_from_old_binary_schema():
    before, after = binary_method(), source_method()
    old_names = {row['name'] for row in before['params']}
    new_names = {row['name'] for row in after['params']}
    assert new_names - old_names == {'request_id', 'expected_subtitle_intent',
        'expected_audio_intent', 'child_request_id', 'handoff_token'}
    assert set(next(p for p in after['params'] if p['name'] == 'action')['enum']) == {
        'stop', 'pause', 'resume', 'handoff_capture', 'handoff_stop'}


def test_all_184_binary_methods_preserved_and_only_control_schema_differs_from_intended_source():
    actual = {}
    for segment in (RUN/'candidate.bin').read_bytes().split(b'\0'):
        if not re.match(rb'^"[A-Za-z0-9_.]+": \{', segment):
            continue
        try:
            value = json.loads(b'{' + segment + b'}')
        except (ValueError, UnicodeError):
            continue
        for name, method in value.items():
            if isinstance(method, dict) and method.get('type') == 'method':
                assert name not in actual
                actual[name] = method
    expected = json.loads((RUN/'source-candidate/xbmc/interfaces/json-rpc/schema/methods.json').read_text())
    assert len(actual) == len(expected) == 184
    assert actual.keys() == expected.keys()
    assert [name for name in expected if actual[name] != expected[name]] == [METHOD]


def test_saved_running_native_image_is_the_same_8bb2_artifact():
    receipt = json.loads((OUT/'ce2042-native-runtime-hash1.json').read_text())
    assert receipt['mode'] == 'readonly' and receipt['kodi_processes'] == 1
    assert receipt['kodi_elf']['sha256'] == PIN

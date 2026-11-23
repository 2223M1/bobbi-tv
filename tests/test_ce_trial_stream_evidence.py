"""Startup trace keeps exact stream identities without exporting free text."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/ce_trial_remote.py'


def functions(names):
    nodes = [node for node in ast.parse(SOURCE.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


def test_exact_stream_whitelist_hashes_free_text_and_rejects_unsafe_types():
    project = functions({'stream_identity'})['stream_identity']
    stream = dict(index=2, language='eng', codec='dts', channels=8, isdefault=True,
        name='https://private.invalid/audio?token=secret', file='/private/track', token='secret',
        samplerate=True, bitrate=float('nan'), isforced=1)
    result = project(stream)
    assert result['index'] == 2 and result['language'] == 'eng' and result['channels'] == 8
    assert result['name_sha256'] == hashlib.sha256(stream['name'].encode()).hexdigest()
    assert result['codec_sha256'] == hashlib.sha256(b'dts').hexdigest()
    assert set(result) == {'index', 'language', 'language_sha256', 'codec_sha256', 'channels', 'isdefault', 'name_sha256'}
    assert not any(secret in json.dumps(result) for secret in ('private', 'secret', '/track'))
    assert project({'language': 'token=' + 'a' * 5000}) == {}


@pytest.mark.parametrize('invalid', [None, [], 'private', {'index': True}, {'index': -1}, {'index': 4097}])
def test_missing_or_invalid_stream_is_not_fabricated(invalid):
    assert functions({'stream_identity'})['stream_identity'](invalid) == {}


def test_capture_keeps_audio_subtitle_and_enabled_state_in_compact_trace():
    namespace = functions({'stream_identity', 'capture_startup_trace'})
    clock = [0.0]
    namespace.update(time=SimpleNamespace(monotonic=lambda: clock[0],
        sleep=lambda duration: clock.__setitem__(0, clock[0] + duration)),
        sample=lambda _: dict(wall=clock[0], phase='AV_STARTED', seconds=1, subtitleenabled=True,
            currentaudiostream=dict(index=1, language='zho', name='private-audio'),
            currentsubtitle=dict(index=3, language='eng', name='private-subtitle', path='/private/subtitle')))
    trace, error = namespace['capture_startup_trace']({}, budget=.5)
    assert error is None and len(trace) == 1
    assert trace[0]['currentaudiostream']['index'] == 1 and trace[0]['currentsubtitle']['index'] == 3
    assert trace[0]['subtitleenabled'] is True and 'private' not in json.dumps(trace)


def test_file_hash_is_bound_to_same_request_and_detects_changed_exact_file():
    namespace = functions({'state'})
    desired = dict(request_id='a' * 32, file_bound=True, file_identity='private-exact-file')
    record = dict(request_id=desired['request_id'])
    namespace.update(hashlib=hashlib, snapshot=lambda: dict(desired=desired),
        rpc=lambda _: {}, save=lambda _: None)
    namespace['state'](record)
    assert record['file_identity_sha256'] == hashlib.sha256(desired['file_identity'].encode()).hexdigest()
    assert 'private' not in json.dumps(record)
    desired['file_identity'] = 'different'
    with pytest.raises(AssertionError, match='TRIAL_FILE_CHANGED'):
        namespace['state'](record)

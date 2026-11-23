"""Exact observed track input is attended, not an automatic atomic command."""
import contextlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import ce_attended_player_action as tool


@pytest.mark.parametrize('case', ['success', 'missing', 'duplicate', 'changed', 'lost_ack', 'late_switch'])
def test_attended_audio_selection_checks_index_instance_and_never_replays(case):
    calls = []
    rid, instance = 'a' * 32, '12345678-1234-1234-1234-123456789012'
    class Response:
        def __init__(self, value):
            self.raw = io.BytesIO(json.dumps({'result': value}).encode())
        def __enter__(self): return self.raw
        def __exit__(self, *args): return False
    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            calls.append(payload)
            method, params = payload['method'], payload['params']
            if method == 'Player.BobiState':
                changed = case == 'changed' and len([c for c in calls if c['method'] == method]) > 1
                return Response(dict(selection_epoch=8, playback=dict(request_id=rid,
                    native_instance='other' if changed else instance, phase='AV_STARTED',
                    sequence=2, user_intent=0)))
            if method == 'Player.GetActivePlayers':
                return Response([dict(type='video', playerid=1, playertype='internal')])
            if method == 'Player.GetProperties':
                if params['properties'] == ['audiostreams']:
                    return Response(dict(audiostreams=[] if case == 'missing' else
                        [dict(index=0)] * (2 if case == 'duplicate' else 1)))
                return Response(dict(currentaudiostream={'index': 1 if case == 'late_switch' else 0}))
            if method == 'XBMC.GetInfoLabels': return Response({})
            assert method == 'Player.SetAudioStream' and params == dict(playerid=1, stream=0)
            if case == 'lost_ack': raise TimeoutError()
            return Response('OK')
    output = io.StringIO()
    with patch('urllib.request.build_opener', return_value=Opener()), patch('time.sleep'), contextlib.redirect_stdout(output):
        exec(tool.REMOTE, dict(REQUEST=rid, INSTANCE=instance, ACTION='audio-index', PERCENT=None, AUDIO_INDEX=0))
    result = json.loads(output.getvalue())
    commands = [c for c in calls if c['method'] == 'Player.SetAudioStream']
    assert len(commands) == (1 if case in ('success', 'lost_ack', 'late_switch') else 0)
    assert result['atomic_instance_bound'] is False
    assert result['state'] == ('observed_after_action' if case == 'success' else
        'action_acknowledged_pending' if case == 'late_switch' else 'unconfirmed')

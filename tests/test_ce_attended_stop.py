"""A maintainer Stop is one native CAS, never a global player-id stop."""
import contextlib
import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import ce_attended_player_action as tool

REQUEST = 'a' * 32
INSTANCE = '12345678-1234-1234-1234-123456789012'


def execute(after='STOP', queued=True, lost_ack=False, changed=False):
    calls = []
    before = dict(request_id=REQUEST, native_instance=INSTANCE, phase='AV_STARTED',
                  sequence=2, user_intent=4)

    class Response:
        def __init__(self, value):
            self.raw = io.BytesIO(json.dumps({'result': value}).encode())
        def __enter__(self): return self.raw
        def __exit__(self, *args): return False

    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            method = payload['method']
            calls.append(payload)
            if method == 'Player.BobiState':
                stopped = any(c['method'] == 'Player.BobiControl' for c in calls)
                row = dict(before)
                if stopped:
                    row.update(phase='TERMINAL', reason=after)
                    if changed: row['native_instance'] = 'other'
                return Response(dict(selection_epoch=8, playback=row))
            if method == 'Player.GetActivePlayers':
                return Response([dict(type='video', playerid=1)])
            if method in ('Player.GetProperties', 'XBMC.GetInfoLabels'): return Response({})
            assert method == 'Player.BobiControl'
            if lost_ack: raise TimeoutError()
            return Response(dict(queued=queued))

    output = io.StringIO()
    with patch('urllib.request.build_opener', return_value=Opener()), contextlib.redirect_stdout(output):
        exec(tool.REMOTE, dict(REQUEST=REQUEST, INSTANCE=INSTANCE, ACTION='stop', PERCENT=None))
    return json.loads(output.getvalue()), calls


def test_stop_confirms_only_exact_terminal_stop():
    result, calls = execute()
    assert result['state'] == 'observed_after_action'
    assert result['stop'] == dict(confirmed=True, reason='STOP')
    control = [c for c in calls if c['method'] == 'Player.BobiControl']
    assert len(control) == 1
    params = control[0]['params']
    assert params['native_instance'] == INSTANCE
    assert (params['expected_sequence'], params['selection_epoch'], params['user_intent']) == (2, 8, 4)
    assert not any(c['method'] in ('Player.Stop', 'Input.ExecuteAction') for c in calls)


def test_stop_lost_ack_never_replays_or_claims_success():
    result, calls = execute(lost_ack=True)
    assert result['state'] == 'unconfirmed'
    assert len([c for c in calls if c['method'] == 'Player.BobiControl']) == 1


def test_stop_rejection_never_claims_success():
    result, calls = execute(queued=False)
    assert result['state'] == 'unconfirmed'
    assert len([c for c in calls if c['method'] == 'Player.BobiControl']) == 1


def test_new_instance_or_natural_eof_is_not_our_stop():
    for options in (dict(changed=True), dict(after='NATURAL_EOF')):
        result, calls = execute(**options)
        assert result['state'] == 'unconfirmed'
        assert len([c for c in calls if c['method'] == 'Player.BobiControl']) == 1

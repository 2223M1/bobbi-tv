"""Accepted continuation boundaries are logged without becoming authority."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from test_playback_authority import playing
from lib.services.playback_control import KodiNative


def eof():
    authority, native, args = playing()
    native.current.update(phase='TERMINAL', reason='NATURAL_EOF', sequence=2)
    return authority, native, args


@pytest.mark.parametrize('diagnostic', ['working', 'missing', 'broken'])
def test_only_accepted_grant_and_reservation_are_noted(diagnostic):
    authority, native, args = eof()
    seen = []
    def note(value):
        if diagnostic == 'broken': raise OSError('diagnostic unavailable')
        seen.append(deepcopy(value))
    if diagnostic != 'missing': native.continuation_diagnostic = note
    instance = native.current['native_instance']
    identity = 'release-next-with-private-locator'
    request = dict(args, operation='authorize_next', native_instance=instance, selection_identity=identity)
    grant = authority.dispatch(request)
    assert grant['authorized']
    assert authority.dispatch(request) == {'authorized': False}
    child = uuid4().hex
    command = dict(args, operation='reserve_child', token=grant['token'], child_request_id=child, selection_identity=identity)
    result = authority.dispatch(command)
    assert result['desired']['request_id'] == child
    with pytest.raises(RuntimeError): authority.dispatch(command)
    if diagnostic == 'working':
        common = dict(schema=1, kind='natural', parent_request_id=args['request_id'],
            parent_native_instance=instance, selection_sha256=sha256(identity.encode()).hexdigest())
        assert seen == [dict(common, stage='GRANTED', child_request_id=''),
                        dict(common, stage='CHILD_RESERVED', child_request_id=child)]
        assert grant['token'] not in json.dumps(seen) and identity not in json.dumps(seen)
    else: assert seen == []


@pytest.mark.parametrize('reason', ['STOP', 'ERROR', 'SUPERSEDED'])
def test_non_eof_never_emits_natural_grant(reason):
    authority, native, args = eof()
    native.current['reason'] = reason
    seen = []
    native.continuation_diagnostic = seen.append
    result = authority.dispatch(dict(args, operation='authorize_next', native_instance=native.current['native_instance'],
                                    selection_identity='next'))
    assert result == {'authorized': False} and seen == []


@pytest.mark.parametrize('failure', ['token', 'selection', 'native_intent', 'old_parent'])
def test_failed_or_stale_child_reservation_never_logs_success(failure):
    authority, native, args = eof()
    seen = []
    native.continuation_diagnostic = seen.append
    grant = authority.dispatch(dict(args, operation='authorize_next', native_instance=native.current['native_instance'],
                                    selection_identity='next'))
    command = dict(args, operation='reserve_child', token=grant['token'], child_request_id=uuid4().hex,
                   selection_identity='next')
    if failure == 'token': command['token'] = 'wrong'
    elif failure == 'selection': command['selection_identity'] = 'other'
    elif failure == 'old_parent': command['request_id'] = uuid4().hex
    else: native.intent = lambda command: {'reserved': False, 'selection_epoch': 999}
    with pytest.raises(RuntimeError): authority.dispatch(command)
    assert [row['stage'] for row in seen] == ['GRANTED']


def diagnostic_row():
    return dict(schema=1, stage='GRANTED', kind='natural', parent_request_id='a'*32,
                parent_native_instance=str(uuid4()), selection_sha256='b'*64, child_request_id='')


def test_sink_emits_only_bounded_identity_json(monkeypatch):
    import xbmc
    seen = []
    monkeypatch.setattr(xbmc, 'log', lambda message, level: seen.append(message))
    value = diagnostic_row()
    assert KodiNative.continuation_diagnostic(value) is True
    assert json.loads(seen[0].split('[BOBBI-CONTINUATION] ', 1)[1]) == value
    assert len(seen[0]) < 400


@pytest.mark.parametrize('key,value', [('schema', True), ('stage', 'unknown'), ('kind', 'untrusted'),
    ('parent_request_id', 'a'*32+'\n'), ('parent_native_instance', 'other'),
    ('selection_sha256', 'http://private'), ('child_request_id', 'a'*32), ('token', 'secret')])
def test_sink_rejects_unbounded_or_secret_fields(monkeypatch, key, value):
    import xbmc
    monkeypatch.setattr(xbmc, 'log', lambda *args: pytest.fail('Rejected diagnostic was logged'))
    row = diagnostic_row()
    row[key] = value
    assert KodiNative.continuation_diagnostic(row) is False

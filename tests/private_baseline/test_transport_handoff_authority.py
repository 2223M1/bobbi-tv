"""One owner/grant for same-file recovery; fake actor is not device evidence."""
from copy import deepcopy
from uuid import uuid4

import pytest

from bobbi_core.playback_authority import PlaybackAuthority
from bobbi_core.playback_request import torrent_file_identity
from bobbi_core.transport_handoff import VerifiedTransportTarget
from bobbi_core.video_context import video_identity
from bobbi_platform.account_manager import AccountManager, AccountError
from test_playback_authority import Native, row, select
from test_native_continuation_account_guard import credentials


HASH = 'b' * 40
SELECTED = dict(source_info_hash=HASH, torrent_file_id=1, torrent_path='Show.S01E01.mkv', torrent_file_bytes=1000)
IDENTITY = torrent_file_identity(HASH, 1, SELECTED['torrent_path'], 1000)


class Actor(Native):
    def __init__(self):
        super().__init__()
        self.handoff = None
    def state(self):
        return dict(super().state(), handoff=deepcopy(self.handoff))
    def captured(self):
        command = self.commands[-1]
        assert command['action'] == 'handoff_capture'
        self.handoff = dict(protocol=1, phase='CAPTURED', restorable=True,
            token=str(uuid4()), position_ms=60000, command_id=command['command_id'],
            capture_command_id=command['command_id'], child_request_id=command['child_request_id'],
            expected_child_epoch=command['selection_epoch'] + 1,
            parent_selection_epoch=command['selection_epoch'], parent_request_id=command['request_id'],
            parent_native_instance=command['native_instance'], user_intent=command['user_intent'],
            subtitle_intent=command['expected_subtitle_intent'], audio_intent=command['expected_audio_intent'])
    def stopped(self, requested=False):
        command = self.commands[-1]
        assert command['action'] == 'handoff_stop'
        self.handoff.update(phase='STOP_REQUESTED' if requested else 'STOPPED', command_id=command['command_id'])
        if not requested:
            self.current.update(phase='TERMINAL', reason='STOP', sequence=2)


def proof(args, account, selected=None):
    selected = selected or SELECTED
    context = video_identity('tmdb:tv:1:s1:e1', 'c' * 64, selected)
    request = dict(request_id=args['request_id'], verification_id=uuid4().hex,
        resource_id='resource', account='provider-scope', generation=2,
        source_info_hash=HASH, media_id=context['media_id'])
    result = {key: request[key] for key in ('request_id','verification_id','resource_id','account','generation')}
    result.update(state='ready', bytes=selected['torrent_file_bytes'], version_key='c' * 64, video_context=context)
    return VerifiedTransportTarget(result, request, account)


def setup(tmp_path):
    native = Actor()
    authority = PlaybackAuthority(native)
    args = select(authority, 'bt:' + HASH)
    assert authority.dispatch(dict(args, operation='bind_file', selection_identity='bt:' + HASH,
        file_identity=IDENTITY, url_sha256='a' * 64))['bound']
    authority.dispatch(dict(args, operation='claim_start', route='resolved_url'))
    native.current = row(args['request_id'], IDENTITY, audio_intent=2, subtitle_intent=3)
    authority.refresh()
    accounts = AccountManager(tmp_path / 'accounts.json')
    account = accounts.install(credentials(), accounts.snapshot())
    authority.configure_accounts(accounts)
    child = uuid4().hex
    message = dict(args, operation='transport_capture', native_instance=native.current['native_instance'],
        selection_identity='bt:' + HASH, child_request_id=child, account_scope=account,
        _verified_transport=proof(args, account))
    return authority, native, args, accounts, account, message


def command(args, account, grant, operation):
    return dict(args, account_scope=account, token=grant['token'], operation=operation)


def test_capture_stop_real_terminal_reserve_same_file_once(tmp_path):
    authority, native, args, _, account, message = setup(tmp_path)
    grant = authority.dispatch(message)
    assert grant['authorized'] and len(native.commands) == 1
    native.captured()
    status = authority.dispatch(command(args, account, grant, 'transport_status'))
    assert status['state'] == 'CAPTURED' and status['position_ms'] == 60000
    stop = command(args, account, grant, 'transport_stop')
    assert authority.dispatch(stop)['queued']
    assert authority.dispatch(stop)['queued'] and len(native.commands) == 2
    reserve = dict(command(args, account, grant, 'reserve_child'),
        selection_identity='bt:' + HASH, child_request_id=message['child_request_id'])
    native.stopped(requested=True)
    assert authority.dispatch(command(args, account, grant, 'transport_status'))['state'] == 'STOP_REQUESTED'
    with pytest.raises(RuntimeError):
        authority.dispatch(reserve)
    native.stopped()
    state = authority.dispatch(reserve)
    assert state['desired']['request_id'] == message['child_request_id']
    assert authority.transport_child['file_identity'] == IDENTITY
    assert authority.selection_account == account
    with pytest.raises(RuntimeError):
        authority.dispatch(reserve)
    child = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=message['child_request_id'])
    assert not authority.dispatch(dict(child, operation='bind_file', selection_identity='bt:' + HASH,
        file_identity='bt:' + HASH + '|transport:new', url_sha256='d' * 64))['bound']
    assert authority.dispatch(dict(child, operation='bind_file', selection_identity='bt:' + HASH,
        file_identity=IDENTITY, url_sha256='d' * 64))['bound']


@pytest.mark.parametrize('change', ['id', 'path', 'bytes', 'json', 'unknown_audio', 'paused', 'external', 'manual_file'])
def test_no_capture_without_exact_trusted_playing_file(tmp_path, change):
    authority, native, args, _, account, message = setup(tmp_path)
    fields = dict(SELECTED)
    if change == 'id': fields['torrent_file_id'] = 2
    if change == 'path': fields['torrent_path'] = 'Show.S01E02.mkv'
    if change == 'bytes': fields['torrent_file_bytes'] += 1
    message['_verified_transport'] = proof(args, account, fields)
    if change == 'json': message['_verified_transport'] = dict(ready=True, selected=SELECTED)
    if change == 'unknown_audio': native.current.pop('audio_intent')
    if change == 'paused': native.current['paused'] = True
    if change == 'external': native.current = row('e' * 32, 'other', audio_intent=0)
    if change == 'manual_file': authority.owner.desired['file_evidence'] = 'USER_CONFIRMED_FILE'
    assert not authority.dispatch(message)['authorized']
    assert native.commands == []


@pytest.mark.parametrize('change', ['audio', 'subtitle', 'seek', 'gui', 'pause', 'account', 'new_select'])
def test_changed_intent_between_capture_and_stop_does_not_stop(tmp_path, change):
    authority, native, args, accounts, account, message = setup(tmp_path)
    grant = authority.dispatch(message)
    native.captured()
    if change == 'audio': native.current['audio_intent'] += 1
    if change == 'subtitle': native.current['subtitle_intent'] += 1
    if change == 'seek': native.current['user_intent'] += 1
    if change == 'gui': native.gui['gui_user_intent'] += 1
    if change == 'pause': native.current['paused'] = True
    if change == 'account': accounts.logout(account)
    if change == 'new_select': select(authority, 'new')
    if change == 'account':
        with pytest.raises(AccountError): authority.dispatch(command(args, account, grant, 'transport_stop'))
    else:
        assert not authority.dispatch(command(args, account, grant, 'transport_stop'))['queued']
    assert len(native.commands) == 1


@pytest.mark.parametrize('reason', ['NATURAL_EOF', 'ERROR', 'SUPERSEDED'])
def test_non_stop_terminal_never_replays_same_episode(tmp_path, reason):
    authority, native, args, _, account, message = setup(tmp_path)
    grant = authority.dispatch(message)
    native.captured()
    authority.dispatch(command(args, account, grant, 'transport_stop'))
    native.current.update(phase='TERMINAL', reason=reason, sequence=2)
    native.handoff['phase'] = 'REJECTED'
    with pytest.raises(RuntimeError):
        authority.dispatch(dict(command(args, account, grant, 'reserve_child'),
            selection_identity='bt:' + HASH, child_request_id=message['child_request_id']))
    assert authority.continuation is None
    if reason == 'NATURAL_EOF':
        result = authority.dispatch(dict(args, operation='authorize_next', native_instance=native.current['native_instance'],
            account_scope=account, selection_identity='next'))
        assert result['authorized']  # Recovery cannot steal the ordinary EOF slot.


def test_lost_stop_reply_never_replays_command(tmp_path, monkeypatch):
    authority, native, args, _, account, message = setup(tmp_path)
    grant = authority.dispatch(message)
    native.captured()
    original = native.control
    def lost(value):
        original(value)
        raise OSError('lost')
    monkeypatch.setattr(native, 'control', lost)
    stop = command(args, account, grant, 'transport_stop')
    assert authority.dispatch(stop)['queued']
    assert authority.dispatch(stop)['queued']
    native.stopped()
    assert authority.dispatch(command(args, account, grant, 'transport_status'))['state'] == 'STOPPED'
    assert len(native.commands) == 2


def test_unavailable_native_protocol_never_uses_global_stop(tmp_path, monkeypatch):
    authority, native, _, _, _, message = setup(tmp_path)
    def unsupported(value):
        raise ValueError('old native schema')
    monkeypatch.setattr(native, 'control', unsupported)
    assert authority.dispatch(message)['state'] == 'UNSUPPORTED'
    assert authority.continuation is None and native.commands == []


def test_expired_or_wrong_child_capsule_cannot_reserve(tmp_path):
    authority, native, args, _, account, message = setup(tmp_path)
    grant = authority.dispatch(message)
    native.captured()
    authority.dispatch(command(args, account, grant, 'transport_stop'))
    native.stopped()
    native.handoff['child_request_id'] = 'f' * 32
    with pytest.raises(RuntimeError):
        authority.dispatch(dict(command(args, account, grant, 'reserve_child'),
            selection_identity='bt:' + HASH, child_request_id=message['child_request_id']))

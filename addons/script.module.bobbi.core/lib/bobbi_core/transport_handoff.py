"""Small proof/receipt boundary for one same-file transport replacement.

No cloud IO, actor ownership or automatic EOF semantics live here. The host
constructs VerifiedTransportTarget only from its own completed resolve result;
JSON clients cannot manufacture an instance of this private in-process type.
"""
from copy import deepcopy
import re
from time import monotonic
from uuid import uuid4

from .native_receipt import UUID
from .playback_request import torrent_file_identity
from .video_context import checked_video


class VerifiedTransportTarget:
    def __init__(self, result, request, account):
        from bobbi_platform.account_manager import validate_snapshot
        if (not isinstance(result, dict) or result.get('state') != 'ready'
                or not isinstance(request, dict)
                or any(result.get(key) != request.get(key) for key in
                       ('request_id', 'verification_id', 'resource_id', 'account', 'generation'))):
            raise ValueError('TRANSPORT_TARGET_NOT_VERIFIED')
        if not re.fullmatch('[0-9a-f]{32}', str(result.get('request_id', ''))):
            raise ValueError('TRANSPORT_REQUEST_REQUIRED')
        if 'qualification' in request and result.get('qualification') != request['qualification']:
            raise ValueError('TRANSPORT_QUALIFICATION_CHANGED')
        self.context = checked_video(result.get('video_context'))
        if (self.context['media_id'] != request['media_id']
                or self.context['selected']['source_info_hash'] != request['source_info_hash']
                or self.context['release_key'] != result.get('version_key')
                or self.context['selected']['torrent_file_bytes'] != result.get('bytes')):
            raise ValueError('TRANSPORT_TARGET_IDENTITY_CHANGED')
        self.request_id = result['request_id']
        self.account = validate_snapshot(account, authenticated=True)
        self.resource_id = result['resource_id']
        self.context = deepcopy(self.context)

    def matches_file(self, identity):
        selected = self.context['selected']
        exact = torrent_file_identity(selected['source_info_hash'], selected['torrent_file_id'],
                                      selected['torrent_path'], selected['torrent_file_bytes'])
        return identity == exact or (isinstance(identity, str) and identity.startswith('transport:')
                                     and identity.endswith('|' + exact))


def checked_receipt(value):
    if (not isinstance(value, dict) or type(value.get('protocol')) is not int or value['protocol'] != 1
            or value.get('phase') not in ('CAPTURED', 'STOP_REQUESTED', 'STOPPED', 'CONSUMED', 'RESTORED', 'REJECTED')
            or type(value.get('restorable')) is not bool):
        return None
    for key in ('command_id', 'capture_command_id', 'child_request_id', 'parent_request_id'):
        if not isinstance(value.get(key), str) or not re.fullmatch('[0-9a-f]{32}', value[key]):
            return None
    if not UUID.fullmatch(str(value.get('parent_native_instance', ''))):
        return None
    if value['phase'] != 'REJECTED' and not UUID.fullmatch(str(value.get('token', ''))):
        return None
    for key in ('position_ms', 'parent_selection_epoch', 'expected_child_epoch',
                'user_intent', 'subtitle_intent', 'audio_intent'):
        if type(value.get(key)) is not int or value[key] < 0:
            return None
    if value['expected_child_epoch'] != value['parent_selection_epoch'] + 1:
        return None
    return {key: deepcopy(value[key]) for key in (
        'command_id', 'capture_command_id', 'child_request_id', 'parent_request_id',
        'parent_native_instance', 'position_ms', 'parent_selection_epoch', 'expected_child_epoch',
        'user_intent', 'subtitle_intent', 'audio_intent', 'phase', 'restorable', 'token') if key in value}


def matches_grant(receipt, grant):
    return bool(receipt and grant and grant.get('kind') == 'transport'
        and receipt['capture_command_id'] == grant['capture_command_id']
        and receipt['child_request_id'] == grant['child_request_id']
        and receipt['parent_request_id'] == grant['request_id']
        and receipt['parent_native_instance'] == grant['native_instance']
        and receipt['parent_selection_epoch'] == grant['native_epoch']
        and receipt['user_intent'] == grant['native_user_intent']
        and receipt['subtitle_intent'] == grant['subtitle_intent']
        and receipt['audio_intent'] == grant['audio_intent'])


def _current(authority, grant, args):
    return bool(grant and grant.get('kind') == 'transport'
                and authority.owner._current(*args) and grant['request_id'] == args[2]
                and authority.native_epoch == grant['native_epoch']
                and authority.gui_state.get('gui_user_intent') == grant['gui_user_intent'])


def _live(authority, grant, row, args):
    return bool(_current(authority, grant, args) and row and row['phase'] == 'AV_STARTED'
        and row['native_instance'] == grant['native_instance'] and not row['paused']
        and row['user_intent'] == grant['native_user_intent']
        and row.get('subtitle_intent') == grant['subtitle_intent']
        and row.get('audio_intent') == grant['audio_intent']
        and not authority.owner.windows and authority.owner.owns_instance(*args, row['native_instance']))


def _command(grant, row, action, command_id, token=''):
    return dict(native_instance=grant['native_instance'], request_id=grant['request_id'],
        user_intent=grant['native_user_intent'], expected_sequence=row['sequence'],
        selection_epoch=grant['native_epoch'], command_id=command_id, action=action,
        expected_subtitle_intent=grant['subtitle_intent'], expected_audio_intent=grant['audio_intent'],
        child_request_id=grant['child_request_id'], handoff_token=token)


def dispatch(authority, message, row, args):
    """Use the existing authority/grant slot; never create a second owner."""
    operation, owner = message['operation'], authority.owner
    if operation == 'transport_capture':
        proof = message.get('_verified_transport')
        child = message.get('child_request_id')
        desired = owner.desired or {}
        if (not isinstance(proof, VerifiedTransportTarget) or proof.request_id != args[2]
                or proof.account != message.get('account_scope')
                or not isinstance(child, str) or not re.fullmatch('[0-9a-f]{32}', child) or child == args[2]
                or authority.continuation or not owner._current(*args)
                or authority.native_epoch != authority.reservation_epoch
                or desired.get('file_evidence') != 'AUTO_VERIFIED_FILE'
                or not proof.matches_file(desired.get('file_identity'))
                or message.get('selection_identity') != desired.get('selection_identity')
                or not row or row['phase'] != 'AV_STARTED' or row['paused'] or owner.windows
                or not owner.owns_instance(*args, message.get('native_instance'))
                or row['native_instance'] != message.get('native_instance')
                or any(type(row.get(key)) is not int or row[key] < 0
                       for key in ('subtitle_intent', 'audio_intent'))):
            return dict(authorized=False, state='REJECTED')
        attempt = (args[2], row['native_instance'], desired['file_identity'])
        if authority.transport_attempt == attempt:
            return dict(authorized=False, state='ALREADY_ATTEMPTED')
        authority.transport_attempt = attempt
        grant = dict(kind='transport', token=uuid4().hex, request_id=args[2],
            child_request_id=child, native_instance=row['native_instance'],
            selection_identity=desired['selection_identity'], file_identity=desired['file_identity'],
            native_user_intent=row['user_intent'], subtitle_intent=row['subtitle_intent'],
            audio_intent=row['audio_intent'], native_epoch=authority.native_epoch,
            gui_user_intent=authority.gui_state.get('gui_user_intent'),
            account_scope=deepcopy(proof.account), capture_command_id=uuid4().hex,
            stop_command_id=None, started=monotonic())
        authority.continuation = grant
        try:
            result = authority.native.control(_command(grant, row, 'handoff_capture', grant['capture_command_id']))
        except ValueError:
            authority.continuation = None  # Older F9: no unscoped fallback.
            return dict(authorized=False, state='UNSUPPORTED')
        except (OSError, RuntimeError):
            result = None  # Unknown receipt; query this command, never re-send.
        if result is not None and (not isinstance(result, dict) or result.get('queued') is not True):
            authority.continuation = None
            return dict(authorized=False, state='REJECTED')
        return dict(authorized=True, state='PENDING', token=grant['token'])

    grant = authority.continuation
    if (not _current(authority, grant, args) or grant['token'] != message.get('token')):
        return dict(state='REJECTED', queued=False)
    observed = checked_receipt(authority.native_handoff)
    matching = matches_grant(observed, grant)
    if matching and observed['phase'] == 'REJECTED':
        authority.continuation = None
        return dict(state='REJECTED', queued=False)
    if monotonic() - grant['started'] > 30:
        authority.continuation = None
        return dict(state='EXPIRED', queued=False)
    if operation == 'transport_status':
        if not matching:
            return dict(state='PENDING')
        if observed['phase'] == 'CAPTURED' and not _live(authority, grant, row, args):
            authority.continuation = None
            return dict(state='REJECTED')
        if observed['phase'] == 'STOPPED' and (not grant['stop_command_id']
                or observed['command_id'] != grant['stop_command_id']):
            return dict(state='REJECTED')
        return dict(state=observed['phase'], capsule=observed.get('token'),
                    position_ms=observed['position_ms'], child_request_id=grant['child_request_id'],
                    file_identity=grant['file_identity'])
    if operation != 'transport_stop':
        raise ValueError('TRANSPORT_OPERATION')
    if grant['stop_command_id']:
        return dict(queued=True, state='PENDING')  # Receipt query, not command replay.
    if (not matching or observed['phase'] != 'CAPTURED' or not observed['restorable']
            or not _live(authority, grant, row, args)):
        return dict(queued=False, state='REJECTED')
    grant['stop_command_id'] = uuid4().hex
    try:
        result = authority.native.control(_command(grant, row, 'handoff_stop',
            grant['stop_command_id'], observed['token']))
    except (OSError, RuntimeError):
        result = None  # A lost response is not permission to retry Stop.
    if result is not None and (not isinstance(result, dict) or result.get('queued') is not True):
        authority.continuation = None
        return dict(queued=False, state='REJECTED')
    return dict(queued=True, state='PENDING')

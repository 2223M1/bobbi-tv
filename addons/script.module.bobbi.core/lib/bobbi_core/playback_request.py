"""Thin request adapter. Local IPC never grants rights through window properties."""
import hashlib
import json
import re
import time
from types import SimpleNamespace
from uuid import uuid4

from .playback_ipc import call


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def source_identity(source):
    info_hash = getattr(source, 'infoHash', '')
    if isinstance(info_hash, str) and re.fullmatch('[0-9a-fA-F]{40}', info_hash):
        return 'bt:' + info_hash.lower()
    prepared = getattr(source, 'preparedResourceId', '')
    if isinstance(prepared, str) and prepared:
        return 'prepared:' + digest(prepared)
    url = getattr(source, 'url', '') or getattr(source, 'guid', '')
    if not isinstance(url, str) or not url:
        raise ValueError('片源缺少稳定身份，未启动未知资源')
    return 'transport:' + digest(url)


def context(snapshot, request_id):
    desired = snapshot.get('desired') if isinstance(snapshot, dict) else None
    if (not isinstance(desired, dict) or desired.get('request_id') != request_id
            or desired.get('cancelled')):
        raise RuntimeError('片源选择已经取消或被新的选择替代')
    return dict(boot_id=snapshot['boot_id'], epoch=snapshot['epoch'], request_id=request_id)


def select(snapshot, request_id, identity):
    return call(dict(operation='select', boot_id=snapshot['boot_id'], epoch=snapshot['epoch'],
                     request_id=request_id, selection_identity=identity))


def data_identity(data):
    return source_identity(SimpleNamespace(infoHash=data.get('info_hash', ''),
        preparedResourceId=data.get('prepared_resource_id', ''), url=data.get('url', '')))


def reserve_ui_entry(data):
    """Called by an explicit entry before slow resolution, never by cached data itself."""
    result = dict(data)
    if result.get('selection_policy') != 'exact':
        return result
    request_id = uuid4().hex
    snapshot = call({'operation': 'snapshot'})
    select(snapshot, request_id, data_identity(result))
    result['request_id'] = result['_ui_reserved_request'] = request_id
    result.pop('_parent_request_id', None)
    result.pop('_continuation_token', None)
    return result


def bind_and_claim(request_id, identity, url, cancelled, route, budget=3.0):
    """Worker-side old-player barrier. Never called from a dialog onClick."""
    if type(budget) not in (float, int) or not 0 < budget <= 3:
        raise ValueError('Bounded native stop barrier required')
    deadline = time.monotonic() + budget
    claim_id = uuid4().hex  # One worker invocation; never reused by a second opener.
    def bounded_call(message):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('上一播放实例未确认退出，未覆盖其他影片')
        result = call(message, timeout=min(0.3, remaining))
        if time.monotonic() >= deadline:
            raise TimeoutError('播放控制响应超过本次总时限')
        return result
    if cancelled():
        raise RuntimeError('本次播放已取消')
    def retry_read_or_bind(message):
        # Reads and an unchanged pre-open bind are idempotent. A snapshot is
        # never used in place of the dedicated command receipt below.
        while not cancelled():
            try:
                return bounded_call(message)
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(.05, max(0, deadline - time.monotonic())))
        raise RuntimeError('本次播放已取消')
    snapshot = retry_read_or_bind({'operation': 'snapshot'})
    args = context(snapshot, request_id)
    selected = snapshot['desired']['selection_identity']
    if not identity.startswith(selected + '|'):
        raise ValueError('实际文件不属于所选片源')
    if not retry_read_or_bind(dict(args, operation='bind_file', selection_identity=selected,
                     file_identity=identity, url_sha256=digest(url)))['bound']:
        raise RuntimeError('本次文件绑定已失效')
    operation = 'claim_start'
    expected = dict(args, claim_id=claim_id, route=route,
                    file_identity=identity, url_sha256=digest(url))
    while not cancelled():
        try:
            result = bounded_call(dict(args, operation=operation, route=route, claim_id=claim_id))
        except OSError:
            if time.monotonic() >= deadline:
                raise
            operation = 'claim_status'  # Confirm this exact command after a lost reply.
            time.sleep(min(.05, max(0, deadline - time.monotonic())))
            continue
        if cancelled():
            break
        if result.get('status') == 'CLAIMED':
            if result.get('receipt') != expected:
                raise RuntimeError('开播回执与当前命令不一致')
            return dict(args, file_identity=identity)
        if result.get('status') not in ('WAIT_TERMINAL', 'NOT_RECEIVED'):
            raise RuntimeError('本次开播请求已失效：' + str(result.get('status')))
        operation = 'claim_start'  # Same command ID; the server deduplicates admission.
        if time.monotonic() >= deadline:
            raise TimeoutError('上一播放实例未确认退出，未覆盖其他影片')
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    bounded_call(dict(args, operation='cancel'))
    raise RuntimeError('本次播放已取消')


def torrent_file_identity(info_hash, file_id, path, size):
    if (not isinstance(info_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', info_hash)
            or type(file_id) is not int or file_id < 1 or not isinstance(path, str) or not path
            or type(size) is not int or size <= 0):
        raise ValueError('Verified torrent metadata identity required')
    exact = json.dumps(dict(id=file_id, path=path, bytes=size), sort_keys=True, separators=(',', ':'))
    return 'bt:' + info_hash.lower() + '|' + digest(exact)


def resolve_torrent(request_id, locator, info_hash, verified_hash):
    """Tie this invocation's verified torrent bytes/magnet to its immutable choice."""
    if (not isinstance(info_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', info_hash)
            or not isinstance(verified_hash, str) or info_hash.lower() != verified_hash.lower()):
        raise ValueError('Torrent content hash mismatch')
    snapshot = owned_state(request_id)
    selected = snapshot['desired']['selection_identity']
    torrent = 'bt:' + info_hash.lower()
    if selected != torrent:
        if (not isinstance(locator, str) or not locator
                or selected != 'transport:' + digest(locator)):
            raise ValueError('Torrent does not resolve the selected transport')
    return dict(context(snapshot, request_id), selection_identity=selected, info_hash=info_hash.lower())


def resolved_torrent_file_identity(request_id, resolution, info_hash, file_id, path, size):
    identity = torrent_file_identity(info_hash, file_id, path, size)
    selected = validate_torrent_resolution(request_id, resolution, info_hash)
    return selected + '|' + identity if selected.startswith('transport:') else identity


def validate_torrent_resolution(request_id, resolution, info_hash):
    if not isinstance(info_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', info_hash):
        raise ValueError('Invalid resolved torrent hash')
    snapshot = owned_state(request_id)
    selected = snapshot['desired']['selection_identity']
    if resolution is None:
        # Direct hash entry remains valid only for an already selected BT hash.
        if selected != 'bt:' + info_hash.lower():
            raise ValueError('Missing selected transport resolution')
        return selected
    expected = dict(context(snapshot, request_id), selection_identity=selected, info_hash=info_hash.lower())
    if resolution != expected:
        raise ValueError('Stale or mismatched torrent resolution')
    return selected


def startup_failure(owner_context):
    """Observe one failed native open without granting cancelled control rights."""
    if not isinstance(owner_context, dict) or not all(owner_context.get(key) is not None
            for key in ('boot_id', 'epoch', 'request_id', 'file_identity')):
        return None
    result = call(dict(operation='startup_failure', **{key: owner_context[key]
        for key in ('boot_id', 'epoch', 'request_id', 'file_identity')}))
    if not isinstance(result, dict):
        return None
    receipt = result.get('receipt')
    if (result.get('failed') is True and isinstance(receipt, dict)
            and all(receipt.get(key) == owner_context[key]
                    for key in ('boot_id', 'epoch', 'request_id', 'file_identity'))
            and isinstance(receipt.get('native_instance'), str) and receipt['native_instance']):
        return receipt
    return None


def owned_state(request_id):
    # A local IPC read can time out briefly during native player teardown/open.
    # That is not proof of a different selection. Retry reads only, with fresh
    # authority each time; never retry/mint a playback command or trust a cache.
    deadline = time.monotonic() + 1.0
    for attempt in range(3):
        try:
            snapshot = call({'operation': 'snapshot'})  # Each read retains the protocol's 0.3 s cap.
        except OSError:
            if attempt == 2 or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            continue
        context(snapshot, request_id)  # Explicit cancel/replacement is immediate.
        return snapshot

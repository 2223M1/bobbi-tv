"""Bounded maintainer fault-injection observations; importing performs no IO.

inspect is read-only: registered backend, native media, qualified projection,
account-scoped preparation status, and procfs. It never refreshes playback
authority, resolves 115 media, touches a mount, or starts a process.
"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import sys
import time
from urllib.parse import quote, urlencode, urlsplit
import urllib.request

KODI = Path('/storage/.kodi')
PROC = Path('/proc')
HEX64 = re.compile('[0-9a-f]{64}')
RID = re.compile('[0-9a-f]{32}')
UUID = re.compile('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
EXE = re.compile(r'(?:TorrServer|torrserver)(?:-(?:linux-)?(?:arm64|arm7|arm|aarch64|amd64|x86_64))?')


class Refused(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def safe_error(error):
    allowed = {'SCOPE_INVALID','BACKEND_INVALID','NATIVE_CHANGED','NOT_BT_VIDEO','PLAYER_PAUSED',
        'QUALIFIED_MISSING','QUALIFIED_AMBIGUOUS','QUALIFIED_CHANGED','ACCOUNT_CHANGED','HOST_UNAVAILABLE',
        'RPC_UNAVAILABLE','LISTENER_AMBIGUOUS','PROCESS_SCAN_INCOMPLETE','PROCESS_CHANGED','PROCESS_INVALID',
        'PIDFD_UNAVAILABLE','WATCHDOG_NOT_READY','WATCHDOG_EXPIRED','ARM_INVALID','ALREADY_ATTEMPTED',
        'RECOVERY_FAILED','SIGNAL_UNCONFIRMED','RECEIPT_INVALID','READ_LIMIT','PRIVATE_DIRECTORY_INVALID',
        'WATCHDOG_STILL_RUNNING','PROCESS_NOT_STOPPED'}
    return {'error': str(error) if isinstance(error, Refused) and str(error) in allowed else 'FAULT_TOOL_ERROR'}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def capabilities():
    """Open/close a pidfd to this diagnostic interpreter only; no signal sent."""
    api = callable(getattr(os, 'pidfd_open', None)) and callable(getattr(signal, 'pidfd_send_signal', None))
    result = dict(schema=1, operation='capabilities', mode='read_only', state='inspected',
        pidfd_api_present=api, pidfd_supported=False, mutation_performed=False,
        signal_sent=False, capability_scope='self_pidfd_open_only')
    if api:
        try:
            descriptor = os.pidfd_open(os.getpid(), 0)
            os.close(descriptor)
            result['pidfd_supported'] = True
        except OSError as error:
            result['pidfd_errno'] = error.errno if type(error.errno) is int else None
    return result


def read_json(path, limit):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'READ_LIMIT')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'READ_LIMIT')
    return json.loads(raw)


def read_text(path, limit):
    with Path(path).open('r', encoding='utf-8') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'READ_LIMIT')
    return raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise Refused('HOST_UNAVAILABLE')


def local_http(url, message, headers=None, timeout=.3):
    request = urllib.request.Request(url, data=encode(message).encode(),
        headers=dict({'Content-Type': 'application/json'}, **(headers or {})))
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(256 * 1024 + 1)
    require(len(raw) <= 256 * 1024, 'READ_LIMIT')
    return json.loads(raw)


def host(action, body):
    config = read_json(KODI / 'userdata/addon_data/script.module.bobbi.platform/runtime.json', 4096)
    require(set(config) == {'port','token'} and type(config['port']) is int and 1024 <= config['port'] <= 65535
            and isinstance(config['token'], str) and len(config['token']) == 64, 'HOST_UNAVAILABLE')
    result = local_http('http://127.0.0.1:%d/control' % config['port'], dict(action=action, body=body),
                        {'Authorization': 'Bearer ' + config['token']})
    require(result.get('ok') is True, 'HOST_UNAVAILABLE')
    return result['result']


def rpc(method, params=None):
    result = local_http('http://127.0.0.1:8080/jsonrpc',
        dict(jsonrpc='2.0', id=903, method=method, params=params or {}))
    require('error' not in result, 'RPC_UNAVAILABLE')
    return result['result']


def bootstrap():
    sys.dont_write_bytecode = True
    for addon in ('plugin.video.bobbi.torrent','script.module.bobbi.core','script.module.bobbi.platform'):
        sys.path.insert(0, str(KODI / 'addons' / addon / 'lib'))


def account_scope(value):
    require(isinstance(value, dict) and set(value) == {'account_id','epoch','authenticated'}
            and value['authenticated'] is True and type(value['epoch']) is int and value['epoch'] >= 0
            and re.fullmatch('115:[0-9a-f]{64}', str(value['account_id'])), 'ACCOUNT_CHANGED')
    return value


def backend_config():
    from bobbi_torrent.backend import validate_backend_config
    path = KODI / 'userdata/addon_data/plugin.video.bobbi.torrent/backend.json'
    value = validate_backend_config(read_json(path, 8192))
    parsed = urlsplit(value['endpoint'])
    # No auth is returned to callers or placed in the watchdog request.
    return dict(endpoint=value['endpoint'], host=parsed.hostname, port=parsed.port,
                fingerprint=digest(encode({key: value[key] for key in
                    ('schema','endpoint','metadata_seconds','buffering_seconds')})))


def native_binding(native, request, instance):
    require(RID.fullmatch(str(request)) and UUID.fullmatch(str(instance)), 'SCOPE_INVALID')
    row = native.get('playback') or {}
    require(row.get('request_id') == request and row.get('native_instance') == instance
        and row.get('phase') == 'AV_STARTED' and type(native.get('selection_epoch')) is int
        and row.get('open_epoch') == native['selection_epoch']
        and HEX64.fullmatch(str(row.get('url_sha256')))
        and isinstance(row.get('file_identity'), str) and 1 <= len(row['file_identity']) <= 1024
        and type(row.get('user_intent')) is int and type(row.get('paused')) is bool, 'NATIVE_CHANGED')
    return dict(request_id=request, native_instance=instance, selection_epoch=native['selection_epoch'],
        open_epoch=row['open_epoch'], user_intent=row['user_intent'],
        file_identity_sha256=digest(row['file_identity']), url_sha256=row['url_sha256'])


def qualified_candidate(index, status, account, native, media_file, backend):
    from bobbi_core.video_context import checked_video
    from bobbi_core.playback_request import torrent_file_identity
    require(index.get('schema_version') == 1 and index.get('prepared_schema') == 2
        and index.get('account_scope') == account and isinstance(index.get('account'), str)
        and isinstance(index.get('titles'), list) and len(index['titles']) <= 1000, 'QUALIFIED_MISSING')
    require(status.get('request_id') == native['request_id'] and status.get('state') == 'accepted', 'QUALIFIED_MISSING')
    matches, count = [], 0
    for title in index['titles']:
        require(isinstance(title, dict) and isinstance(title.get('sources'), list), 'QUALIFIED_MISSING')
        for row in title['sources']:
            count += 1
            require(count <= 8192 and isinstance(row, dict), 'QUALIFIED_MISSING')
            video = checked_video(row.get('video_context'))
            selected = video['selected']
            canonical = torrent_file_identity(selected['source_info_hash'], selected['torrent_file_id'],
                                              selected['torrent_path'], selected['torrent_file_bytes'])
            identity = native['file_identity']
            exact = identity == canonical or (re.fullmatch(r'transport:[0-9a-f]{64}\|.+', identity)
                                               and identity.split('|', 1)[1] == canonical)
            if not exact:
                continue
            require(title.get('kind') == 'tv' and re.fullmatch(r'tmdb:tv:[1-9]\d*:s[1-9]\d*:e[1-9]\d*', video['media_id']),
                    'NOT_BT_VIDEO')
            require(row.get('state') == 'qualified' and row.get('prepared_account') == index['account']
                and row.get('prepared_version_key') == video['release_key']
                and row.get('prepared_source_info_hash') == selected['source_info_hash']
                and row.get('bytes') == selected['torrent_file_bytes']
                and HEX64.fullmatch(str(row.get('prepared_qualification')))
                and HEX64.fullmatch(str(row.get('key'))) and row.get('prepared_file_id'), 'QUALIFIED_MISSING')
            expected_url = backend['endpoint'] + '/stream/' + quote(selected['torrent_path']) + '?' + urlencode(
                {'link': selected['source_info_hash'], 'index': selected['torrent_file_id']}) + '&play'
            require(media_file == expected_url and digest(media_file) == native['url_sha256'], 'NOT_BT_VIDEO')
            details = status.get('result') or {}
            versions = {item.get('version_key') for item in details.get('tasks', [])
                        if isinstance(item, dict) and item.get('media_id') == video['media_id']}
            proof = details.get('source_proof') or {}
            require(versions == {video['release_key']} and proof.get('request_id') == native['request_id']
                and proof.get('account') == index['account'] and checked_video(proof.get('anchor')) == video,
                'QUALIFIED_CHANGED')
            fields = {key: row.get(key) for key in ('key','path','bytes','prepared_file_id','prepared_account',
                'prepared_qualification','prepared_version_key','prepared_source_info_hash','video_context')}
            matches.append(dict(media_id=video['media_id'], bytes=row['bytes'],
                video_key=video['key'], qualification_sha256=digest(row['prepared_qualification']),
                prepared_entry_sha256=digest(encode(fields)), selected_sha256=digest(encode(selected))))
    require(len(matches) == 1, 'QUALIFIED_AMBIGUOUS' if matches else 'QUALIFIED_MISSING')
    return matches[0]


def proc_stat(raw):
    end = raw.rfind(')')
    require(end > 0, 'PROCESS_INVALID')
    pid, comm = raw[:end + 1].split(' (', 1)
    fields = raw[end + 2:].split()
    require(pid.isdigit() and len(fields) >= 20 and fields[19].isdigit(), 'PROCESS_INVALID')
    return dict(pid=int(pid), name=comm[:-1], state=fields[0], start_ticks=int(fields[19]))


def process_identity(pid, proc=PROC, hash_exe=True):
    require(type(pid) is int and pid > 1 and pid != os.getpid(), 'PROCESS_INVALID')
    directory = Path(proc) / str(pid)
    before = proc_stat(read_text(directory / 'stat', 4096))
    path = os.readlink(str(directory / 'exe'))
    require(path.startswith('/') and not path.endswith(' (deleted)') and EXE.fullmatch(Path(path).name)
        and 'kodi' not in path.lower(), 'PROCESS_INVALID')
    info = (directory / 'exe').stat()
    value = dict(pid=pid, start_ticks=before['start_ticks'], exe_path=path, exe_device=info.st_dev,
                 exe_inode=info.st_ino, exe_bytes=info.st_size)
    require(0 < info.st_size <= 128 * 1024 * 1024 and before['state'] not in ('Z','X','x'), 'PROCESS_INVALID')
    if hash_exe:
        sha = hashlib.sha256()
        with (directory / 'exe').open('rb') as stream:
            require(stream.read(4) == b'\x7fELF', 'PROCESS_INVALID')
            stream.seek(0)
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                sha.update(block)
        value['exe_sha256'] = sha.hexdigest()
    after = proc_stat(read_text(directory / 'stat', 4096))
    require(after['pid'] == pid and after['start_ticks'] == before['start_ticks']
        and os.readlink(str(directory / 'exe')) == path, 'PROCESS_CHANGED')
    return value, after['state']


def tcp_listeners(raw, family, port, host_name):
    addresses = {ipaddress.ip_address('127.0.0.1'), ipaddress.ip_address('::1')} if host_name == 'localhost' else {ipaddress.ip_address(host_name)}
    result = set()
    lines = raw.splitlines()
    require(len(lines) <= 32768, 'READ_LIMIT')
    for line in lines[1:]:
        fields = line.split()
        require(len(fields) >= 10, 'PROCESS_SCAN_INCOMPLETE')
        address, hexadecimal_port = fields[1].split(':')
        if fields[3] != '0A' or int(hexadecimal_port, 16) != port:
            continue
        value = bytes.fromhex(address)
        if family == 4:
            value = value[::-1]
        else:
            value = b''.join(value[i:i + 4][::-1] for i in range(0, 16, 4))
        ip = ipaddress.ip_address(value)
        if ip in addresses or ip.is_unspecified:
            require(fields[9].isdigit() and int(fields[9]) > 0, 'PROCESS_SCAN_INCOMPLETE')
            result.add(fields[9])
    return result


def listener_process(backend, proc=PROC):
    proc = Path(proc)
    inodes = set()
    for name, family in (('tcp',4), ('tcp6',6)):
        path = proc / 'net' / name
        if path.is_file():
            require(path.stat().st_size <= 4 * 1024 * 1024, 'READ_LIMIT')
            inodes.update(tcp_listeners(read_text(path, 4 * 1024 * 1024), family, backend['port'], backend['host']))
    require(inodes, 'LISTENER_AMBIGUOUS')
    found, directories, total = {}, list(proc.iterdir()), 0
    require(len(directories) <= 8192, 'PROCESS_SCAN_INCOMPLETE')
    for directory in directories:
        if not directory.name.isdigit():
            continue
        try:
            files = list((directory / 'fd').iterdir())
            total += len(files)
            require(total <= 131072, 'PROCESS_SCAN_INCOMPLETE')
            for path in files:
                try:
                    link = os.readlink(str(path))
                except FileNotFoundError:
                    continue
                match = re.fullmatch(r'socket:\[(\d+)\]', link)
                if match and match[1] in inodes:
                    found.setdefault(int(directory.name), set()).add(match[1])
        except FileNotFoundError:
            continue  # A process that already exited cannot be paused.
        except PermissionError:
            raise Refused('PROCESS_SCAN_INCOMPLETE') from None
    require(len(found) == 1 and next(iter(found.values())) == inodes, 'LISTENER_AMBIGUOUS')
    pid = next(iter(found))
    value, state = process_identity(pid, proc)
    value['listen_inodes'] = sorted(inodes)
    return value, state


def current_inspection(request, instance):
    bootstrap()
    from bobbi_core.capabilities import IPC_PROTOCOL, compatible
    before = rpc('Player.BobiState')
    binding = native_binding(before, request, instance)
    players = rpc('Player.GetActivePlayers')
    # Kodi 21 includes playertype='internal'; exact dictionary equality would
    # reject a real internal video before checking its bound native URL. Keep
    # one video only, not an audio/external/remote player or bool-as-int ID.
    require(isinstance(players, list) and len(players) == 1 and isinstance(players[0], dict)
        and type(players[0].get('playerid')) is int and players[0]['playerid'] == 1
        and players[0].get('type') == 'video'
        and players[0].get('playertype', 'internal') == 'internal', 'NOT_BT_VIDEO')
    media_file = rpc('Player.GetItem', {'playerid':1, 'properties':['file']})['item']['file']
    account = account_scope(host('account_status', {}))
    backend = backend_config()
    index = read_json(KODI / 'userdata/addon_data/plugin.video.bobbi/bobi-prepared.json', 4 * 1024 * 1024)
    status = host('preparation', dict(method='status', body={'request_id':request}, protocol=IPC_PROTOCOL, account=account))
    require(compatible(status.get('component')), 'QUALIFIED_MISSING')
    qualified = qualified_candidate(index, status, account, before['playback'], media_file, backend)
    process, state = listener_process(backend)
    after = rpc('Player.BobiState')
    require(native_binding(after, request, instance) == binding
        and account_scope(host('account_status', {})) == account, 'NATIVE_CHANGED')
    properties = rpc('Player.GetProperties', {'playerid':1, 'properties':['speed','time','totaltime']})
    pidfd = capabilities()['pidfd_supported']
    eligible = pidfd and state not in ('T','t') and before['playback']['paused'] is False and properties.get('speed') == 1
    reasons = (['PIDFD_UNAVAILABLE'] if not pidfd else []) + (['PROCESS_ALREADY_STOPPED'] if state in ('T','t') else [])
    if before['playback']['paused'] or properties.get('speed') != 1:
        reasons.append('PLAYER_PAUSED')
    return dict(schema=1, operation='inspect', mode='read_only', state='inspected', can_inject=eligible,
        refusal_reasons=reasons, pidfd_supported=pidfd, native=binding, qualified=qualified,
        account_fingerprint=account['account_id'][4:], account_epoch=account['epoch'],
        backend_sha256=backend['fingerprint'], backend_port=backend['port'], process=process,
        boot_id_sha256=digest(read_text(PROC / 'sys/kernel/random/boot_id', 128).strip()),
        observation=time.time(), qualification_scope='published_qualified_and_accepted_same_file_not_fresh_cloud_read')


def inspect_entry(parameters):
    try:
        if parameters == {'operation': 'capabilities'}:
            return capabilities()
        require(parameters.get('operation') == 'inspect', 'SCOPE_INVALID')
        return current_inspection(parameters['request_id'], parameters['native_instance'])
    except Exception as error:
        return dict(state='refused', mode='read_only', mutation_performed=False,
            pidfd_supported=None, pidfd_kernel_checked=False,
            pidfd_api_present=callable(getattr(os, 'pidfd_open', None)) and callable(getattr(signal, 'pidfd_send_signal', None)),
            **safe_error(error))

"""Maintainer diagnostic primitives. Importing this module performs no I/O.

Inspect is read-only: no catalog Cache constructor, credentials, CDN request,
player command, settings change, or directory creation. The baseline must be a
retained ordinary-selection receipt, not a title supplied as a substitute.
"""
import hashlib
import io
import json
from pathlib import Path
import pickle
import pickletools
import re
import sqlite3
import time
import urllib.request

BASELINE = dict(request_id='0ed3043bc7424b159264ad87fe64504d',
    selection_identity='transport:939b30906b7f9f8490cf3509ded1d4fe28c4659e9ff707ebd8dfa6decef8042e',
    source_key='b85f6de99c83a549d4238d9313809bc33ad232ad4175948db82c05a9595393b6')


class DiagnosticError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise DiagnosticError(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def safe_error(error):
    # Never serialize exception messages, URLs, response bodies or traceback locals.
    codes = {'TARGET_INVALID', 'CATALOG_NOT_UNIQUE', 'TUPLE_MISMATCH', 'SHARE_REVOKED',
             'HISTORY_INVALID', 'HISTORY_MISMATCH', 'ACCOUNT_INVALID', 'ACCOUNT_CHANGED',
             'OWNER_UNAVAILABLE', 'RPC_REJECTED', 'STATE_CHANGED', 'ACTIVE_PLAYER',
             'ACTIVE_SELECTION', 'NATIVE_NOT_TERMINAL', 'INSPECT_CHANGED', 'UA_INVALID',
             'DIAGNOSTIC_SCOPE', 'OTHER_INSTANCE', 'OTHER_REQUEST', 'NO_NATIVE_INSTANCE'}
    code = str(error) if isinstance(error, DiagnosticError) and str(error) in codes else 'DIAGNOSTIC_ERROR'
    api = getattr(error, 'code', '')
    if api in {'login_required', 'share_unavailable', 'network', 'invalid_response', 'cancelled',
               'deadline', 'identity_changed', 'invalid_locator', 'refresh_required', 'share_revoked',
               'http_rejected', 'network_timeout'}:
        code = api
    return {'error': code}


def checked_target(target):
    require(isinstance(target, dict) and set(target) == {
        'request_id', 'selection_identity', 'source_key', 'title', 'size', 'media', 'year'}, 'TARGET_INVALID')
    # A later explicitly supplied ordinary UI receipt has a new request ID.
    # Keep its release pins fixed; history_proof still requires that exact
    # request's retained file pointer and current account generation.
    require(all(target.get(key) == BASELINE[key] for key in ('selection_identity', 'source_key')),
            'TARGET_INVALID')
    require(isinstance(target['request_id'], str)
            and re.fullmatch('[0-9a-f]{32}', target['request_id']) is not None
            and re.fullmatch('transport:[0-9a-f]{64}', str(target['selection_identity'])) is not None
            and re.fullmatch('[0-9a-f]{64}', str(target['source_key'])) is not None
            and target['media'] == 'movies:782:0:0' and target['year'] == 1997
            and target['title'] == 'Gattaca.1997.2160p.BluRay.REMUX.HEVC.DTS-HD.MA.TrueHD.7.1.Atmos-FGT.mkv'
            and type(target['size']) is int and target['size'] == 55082330412, 'TARGET_INVALID')
    return target


def database_stamp(path):
    require(path.is_file() and not path.is_symlink(), 'TUPLE_MISMATCH')
    # SQLite mode=ro may create shared-memory sidecars for a WAL database.
    # Refuse that format instead of using immutable=1 and silently missing WAL.
    with path.open('rb') as stream:
        header = stream.read(100)
    require(len(header) == 100 and header[:16] == b'SQLite format 3\x00'
            and header[18:20] == b'\x01\x01'
            and not any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')),
            'TUPLE_MISMATCH')
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, header)


class ReadConnection(sqlite3.Connection):
    def close(self):
        try:
            require(database_stamp(self.checked_path) == self.checked_stamp, 'TUPLE_MISMATCH')
        finally:
            super().close()
        require(database_stamp(self.checked_path) == self.checked_stamp, 'TUPLE_MISMATCH')


def readonly(path):
    path = Path(path)
    stamp = database_stamp(path)
    # immutable prevents SQLite itself creating sidecars even if a writer races
    # the precheck. It is NOT permission to ignore WAL: validate again after
    # connect and on both sides of close, and reject every changed file.
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True,
                         timeout=0, factory=ReadConnection)
    db.checked_path, db.checked_stamp = path, stamp
    try:
        require(database_stamp(path) == stamp, 'TUPLE_MISMATCH')
    except BaseException:
        sqlite3.Connection.close(db)
        raise
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    deadline = time.monotonic() + 3
    db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 500)
    return db


def validate_tuple(row, target):
    """Every file/share/media field participates in the fingerprint."""
    checked_target(target)
    share = row.get('share') or {}
    require(row.get('provider') in ('juku', 'qqdocs') and row.get('media') == target['media']
            and row.get('name') == target['title'] and type(row.get('size')) is int
            and row['size'] == target['size'] and re.fullmatch('[0-9]{1,32}', str(row.get('fid', '')))
            and isinstance(share.get('code'), str) and re.fullmatch('s[a-zA-Z0-9]{5,40}', share['code'])
            and isinstance(share.get('password'), str)
            and re.fullmatch('[a-zA-Z0-9]{0,16}', share['password']), 'TUPLE_MISMATCH')
    locator, guid = row.get('locator'), row.get('guid')
    require(isinstance(locator, str) and target['selection_identity'] == 'transport:' + digest(locator),
            'TUPLE_MISMATCH')
    if row['provider'] == 'juku':
        key = digest(encoded([share['code'], row['fid'], row['size'], row['name']]))
        require(locator == 'am6bjuku://' + key and guid == 'juku:' + key, 'TUPLE_MISMATCH')
    else:
        cell = row.get('cell', '')
        require(re.fullmatch(r'(?:[A-Z]{1,2}[1-9]\d*|supp-[0-9a-f]{24})', cell) is not None
                and locator == 'am6bqqdocs://' + cell + '/' + row['fid']
                and guid == 'qqdocs:' + cell + ':' + row['fid'], 'TUPLE_MISMATCH')
    return dict(provider=row['provider'], locator=locator, guid=guid, media=row['media'],
                name=row['name'], size=row['size'], fid=row['fid'],
                share=dict(code=share['code'], password=share['password']))


def retained_tuple(root, target):
    """Exact media query + observed selection hash, never LIKE or guessed URL."""
    checked_target(target)
    root = Path(root)
    matches = []
    path = root / 'userdata/addon_data/plugin.video.bobbi/juku/catalog.sqlite3'
    if path.is_file():
        db = readonly(path)
        try:
            for stored in db.execute('SELECT key,media,payload FROM selections WHERE media=? LIMIT 4097', (target['media'],)):
                locator = 'am6bjuku://' + stored['key']
                if 'transport:' + digest(locator) != target['selection_identity']:
                    continue
                row = json.loads(stored['payload'])
                require(row.get('key') == stored['key'] and row.get('tmdb') == 782
                        and row.get('kind') == 'movie' and row.get('season') == 0
                        and row.get('episode') == 0 and row.get('work_year') == 1997, 'TUPLE_MISMATCH')
                origins = row.get('origins') or []
                if origins:
                    require(not all(db.execute('SELECT revoked FROM library_visibility WHERE code=? AND revoked=1',
                        (origin[7:] if origin.startswith('shared:') else origin,)).fetchone()
                        for origin in origins), 'SHARE_REVOKED')
                matches.append(validate_tuple(dict(row, provider='juku', media=stored['media'],
                    locator=locator, guid='juku:' + stored['key']), target))
        finally:
            db.close()
    path = root / 'userdata/addon_data/script.module.bobbi.catalog/cache.sqlite3'
    if path.is_file():
        db = readonly(path)
        try:
            for stored in db.execute('SELECT key,media,payload FROM selections WHERE media=? LIMIT 4097', (target['media'],)):
                row = json.loads(stored['payload'])
                if not isinstance(row, dict) or not isinstance(row.get('cell'), str) or not isinstance(row.get('fid'), str):
                    continue
                locator = 'am6bqqdocs://' + row['cell'] + '/' + row['fid']
                if 'transport:' + digest(locator) != target['selection_identity']:
                    continue
                guid = 'qqdocs:' + row['cell'] + ':' + row['fid']
                require(stored['key'] == guid + ':' + target['media'], 'TUPLE_MISMATCH')
                catalog = readonly(root / 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3')
                try:
                    shares = catalog.execute('SELECT code,password FROM shares WHERE cell=?', (row['cell'],)).fetchall()
                    require(len(shares) == 1, 'CATALOG_NOT_UNIQUE')
                    if catalog.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='share_status'").fetchone():
                        status = catalog.execute('SELECT enabled FROM share_status WHERE cell=?', (row['cell'],)).fetchone()
                        require(status is None or status['enabled'], 'SHARE_REVOKED')
                    share = dict(shares[0])
                finally:
                    catalog.close()
                matches.append(validate_tuple(dict(row, provider='qqdocs', media=stored['media'],
                    locator=locator, guid=guid, share=share), target))
        finally:
            db.close()
    require(len(matches) == 1, 'CATALOG_NOT_UNIQUE')
    return matches[0]


def primitive_history(raw):
    require(len(raw) <= 64 * 1024 * 1024, 'HISTORY_INVALID')
    forbidden = {'GLOBAL', 'STACK_GLOBAL', 'REDUCE', 'BUILD', 'INST', 'OBJ', 'NEWOBJ',
                 'NEWOBJ_EX', 'EXT1', 'EXT2', 'EXT4', 'PERSID', 'BINPERSID', 'NEXT_BUFFER', 'READONLY_BUFFER'}
    try:
        require(all(op.name not in forbidden for op, _, _ in pickletools.genops(raw)), 'HISTORY_INVALID')
        class Primitives(pickle.Unpickler):
            def find_class(self, module, name):
                raise DiagnosticError('HISTORY_INVALID')
            def persistent_load(self, pid):
                raise DiagnosticError('HISTORY_INVALID')
        stream = io.BytesIO(raw)
        value = Primitives(stream).load()
        require(not stream.read(1), 'HISTORY_INVALID')
        pending, count = [(value, frozenset())], 0
        while pending:
            item, ancestors = pending.pop()
            count += 1
            require(count <= 1000000 and len(ancestors) <= 64, 'HISTORY_INVALID')
            if type(item) in (str, int, float, bool, bytes, type(None)):
                continue
            require(type(item) in (dict, list, tuple, set, frozenset) and id(item) not in ancestors, 'HISTORY_INVALID')
            branch = ancestors | {id(item)}
            items = list(item.keys()) + list(item.values()) if type(item) is dict else list(item)
            pending.extend((child, branch) for child in items)
        require(isinstance(value, dict) and isinstance(value.get('jt:lfh', {}), dict), 'HISTORY_INVALID')
        return value
    except DiagnosticError:
        raise
    except Exception:
        raise DiagnosticError('HISTORY_INVALID') from None


def history_proof(root, target, row, account):
    path = Path(root) / 'userdata/addon_data/plugin.video.bobbi/database.pickle'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64 * 1024 * 1024, 'HISTORY_INVALID')
    history = primitive_history(path.read_bytes())
    found = [item for item in history.get('jt:lfh', {}).values()
             if isinstance(item, dict) and item.get('request_id') == target['request_id']]
    require(len(found) == 1, 'HISTORY_MISMATCH')
    item = found[0]
    pointer = item.get('_share') or {}
    require(pointer.get('locator') == row['locator'] and pointer.get('guid') == row['guid']
            and pointer.get('title') == row['name'] and pointer.get('size') == row['size']
            and pointer.get('media') == row['media'] and item.get('source_title') == row['name']
            and str((item.get('ids') or {}).get('tmdb_id')) == '782'
            and item.get('mode') == 'movies', 'HISTORY_MISMATCH')
    previous = pointer.get('account') or item.get('_account')
    require(isinstance(previous, dict) and previous == account, 'ACCOUNT_CHANGED')
    return dict(exact_request=True, exact_pointer=True, same_account_epoch=True)


def control(action, body):
    config_path = Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/runtime.json')
    require(config_path.is_file() and config_path.stat().st_size <= 16384, 'OWNER_UNAVAILABLE')
    config = json.loads(config_path.read_text())
    request = urllib.request.Request('http://127.0.0.1:%d/control' % config['port'],
        data=json.dumps(dict(action=action, body=body)).encode(),
        headers={'Authorization': 'Bearer ' + config['token'], 'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=.3) as response:
        result = json.load(response)
    require(result.get('ok') is True, 'OWNER_UNAVAILABLE')
    return result['result']


def checked_account(account):
    require(isinstance(account, dict) and set(account) == {'account_id', 'epoch', 'authenticated'}
            and account['authenticated'] is True and type(account['epoch']) is int and 0 <= account['epoch'] < 2**63
            and re.fullmatch('115:[0-9a-f]{64}', str(account['account_id'])) is not None, 'ACCOUNT_INVALID')
    return account


def inspect(root, target, account_status=None):
    account_status = account_status or (lambda: control('account_status', {}))
    before = checked_account(account_status())
    row = retained_tuple(root, target)
    proof = history_proof(root, target, row, before)
    require(account_status() == before, 'ACCOUNT_CHANGED')
    return dict(schema=1, operation='inspect', mode='read_only', state='validated',
        diagnostic_only=True, product_proof=False, playback_performed=False, network_media_read=False,
        baseline_request=target['request_id'], source_key=target['source_key'],
        selection_identity=target['selection_identity'], title=row['name'], size=row['size'],
        media=row['media'], provider=row['provider'], tuple_sha256=digest(encoded(row)),
        fid_sha256=digest(row['fid']), share_sha256=digest(encoded(row['share'])),
        account_fingerprint=before['account_id'][4:], account_epoch=before['epoch'], history=proof)


def remote_entry(parameters):
    try:
        require(parameters.get('operation') == 'inspect', 'DIAGNOSTIC_SCOPE')
        return inspect('/storage/.kodi', parameters['target'])
    except Exception as error:
        return dict(state='not_validated', diagnostic_only=True, product_proof=False, **safe_error(error))

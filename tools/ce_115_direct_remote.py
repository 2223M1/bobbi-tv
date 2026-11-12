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
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

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
    if isinstance(target, dict) and target.get('schema') == 2:
        require(type(target['schema']) is int and set(target) == {
            'schema', 'baseline_sha256', 'request_id', 'selection_identity', 'source_key',
            'title', 'size', 'media', 'year'}, 'TARGET_INVALID')
        require(all(isinstance(target[key], str) and re.fullmatch(pattern, target[key]) is not None
            for key, pattern in (('baseline_sha256', '[0-9a-f]{64}'), ('request_id', '[0-9a-f]{32}'),
                ('selection_identity', 'transport:[0-9a-f]{64}'), ('source_key', '[0-9a-f]{64}'))), 'TARGET_INVALID')
        require(type(target['title']) is str and 0 < len(target['title']) <= 1024
            and not any(ord(c) < 32 or ord(c) == 127 for c in target['title'])
            and type(target['year']) is int and 1880 <= target['year'] <= 2200
            and (target['size'] is None or type(target['size']) is int and 0 < target['size'] <= 512 * 1024**3),
            'TARGET_INVALID')
        media_fields(target)
        return target
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


def media_fields(target):
    """The product's existing movies/tv key, never derive episodes from title."""
    match = re.fullmatch(r'(movies|tv):([1-9][0-9]{0,9}):(0|[1-9][0-9]{0,3}):(0|[1-9][0-9]{0,5})',
                         str(target.get('media', '')))
    require(match is not None, 'TARGET_INVALID')
    mode, tmdb, season, episode = match.groups()
    tmdb, season, episode = int(tmdb), int(season), int(episode)
    require((mode == 'movies' and season == episode == 0) or (mode == 'tv' and episode > 0), 'TARGET_INVALID')
    return mode, tmdb, season, episode


def target_evidence(target):
    """Safe v2 provenance retained even if start/collect never gets an ACK."""
    if target.get('schema') != 2:
        return {}
    checked_target(target)
    return dict(target_schema=2, baseline_sha256=target['baseline_sha256'], baseline_request=target['request_id'],
                selection_identity=target['selection_identity'], source_key=target['source_key'],
                media=target['media'], size=target['size'])


def retained_context(row, target):
    mode, tmdb, season, episode = media_fields(target)
    require(type(row.get('tmdb')) is int and row['tmdb'] == tmdb
        and row.get('kind') == ('movie' if mode == 'movies' else 'tv')
        and type(row.get('season')) is int and row['season'] == season
        and type(row.get('episode')) is int and row['episode'] == episode, 'TUPLE_MISMATCH')
    if target.get('schema') != 2:
        require(type(row.get('work_year')) is int and row['work_year'] == target['year'], 'TUPLE_MISMATCH')
        return
    # Product remember() retains the already-bound spec. Its movie years may
    # include evidenced regional releases; TV year is not an episode identity.
    spec = row.get('spec')
    require(type(spec) is dict and all(spec.get(key) == value for key, value in
        dict(mode=mode, tmdb_id=tmdb, season=season, episode=episode,
             media_key=target['media'], year=target['year']).items())
        and all(type(spec.get(key)) is int for key in ('tmdb_id', 'season', 'episode', 'year')), 'TUPLE_MISMATCH')
    if mode == 'movies':
        years = spec.get('years') or [spec['year']]
        require(type(years) is list and 1 <= len(years) <= 32
            and all(type(year) is int and 1880 <= year <= 2200 for year in years)
            and type(row.get('work_year')) is int and (row['work_year'] == 0 or row['work_year'] in years),
            'TUPLE_MISMATCH')


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


def bounded_document(path, limit):
    require(path.is_file() and not path.is_symlink(), 'STATE_CHANGED')
    def stamp():
        value = path.stat()
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
    before = stamp()
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit and stamp() == before, 'STATE_CHANGED')
    return raw


def profile_status():
    request = urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        json.dumps(dict(jsonrpc='2.0', id=1, method='Profiles.GetCurrentProfile')).encode(),
        {'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as response:
        raw = response.read(65537)
    require(len(raw) <= 65536, 'RPC_REJECTED')
    value = json.loads(raw)
    require('error' not in value and type(value.get('result')) is dict, 'RPC_REJECTED')
    return value['result']


def profile_scope(root, status=None):
    """Prove this fixed CE diagnostic is reading the active default profile."""
    raw = bounded_document(root / 'userdata/profiles.xml', 256 * 1024)
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(), 'STATE_CHANGED')
    label = (status or profile_status)().get('label')
    require(type(label) is str and 0 < len(label) <= 1024, 'STATE_CHANGED')
    matches = [item for item in ET.fromstring(raw).findall('profile') if item.findtext('name') == label]
    require(len(matches) == 1, 'STATE_CHANGED')
    directory = matches[0].findtext('directory')
    require(type(directory) is str and len(directory) <= 4096 and '\\' not in directory, 'STATE_CHANGED')
    if directory.startswith('special://masterprofile/'):
        selected = root / 'userdata' / directory[len('special://masterprofile/'):]
    elif directory.startswith('special://home/'):
        selected = root / directory[len('special://home/'):]
    else:
        require('://' not in directory, 'STATE_CHANGED')
        selected = Path(directory) if Path(directory).is_absolute() else root / 'userdata' / directory
    require('..' not in selected.parts and selected.resolve() == (root / 'userdata').resolve()
            and raw == bounded_document(root / 'userdata/profiles.xml', 256 * 1024), 'STATE_CHANGED')
    return digest(encoded([hashlib.sha256(raw).hexdigest(), digest(label)]))


def checked_catalog_scope(value):
    require(type(value) is dict and set(value) == {'profile_sha256', 'source_config_sha256',
            'endpoint_sha256', 'source_generation_sha256'} and all(type(item) is str
            and re.fullmatch('[0-9a-f]{64}', item) is not None for item in value.values()), 'INSPECT_CHANGED')
    return value


def catalog_scope(root, status=None):
    """Only the current configured endpoint; no legacy or old-source fallback."""
    root = Path(root)
    profile = profile_scope(root, status)
    path = root / 'userdata/addon_data/plugin.video.bobbi/source-library.json'
    raw = bounded_document(path, 4096)
    value = json.loads(raw)
    require(type(value) is dict and type(value.get('schema')) is int and value['schema'] == 1
            and type(value.get('generation')) is str
            and re.fullmatch('[0-9a-f]{32}', value['generation']) is not None, 'STATE_CHANGED')
    library_path = str(root / 'addons/script.module.bobbi.core/lib')
    if library_path not in sys.path:
        sys.path.insert(0, library_path)
    # This pure function does not resolve/create the live Kodi profile.
    from bobbi_core.source_library import normalize
    endpoint = normalize(value.get('endpoint'))
    require(raw == bounded_document(path, 4096) and profile_scope(root, status) == profile, 'STATE_CHANGED')
    return checked_catalog_scope(dict(profile_sha256=profile,
        source_config_sha256=hashlib.sha256(raw).hexdigest(), endpoint_sha256=digest(endpoint),
        source_generation_sha256=digest(value['generation'])))


def validate_tuple(row, target):
    """Every file/share/media field participates in the fingerprint."""
    checked_target(target)
    share = row.get('share') or {}
    require(row.get('provider') in ('juku', 'qqdocs') and row.get('media') == target['media']
            and row.get('name') == target['title'] and type(row.get('size')) is int
            and 0 < row['size'] <= 512 * 1024**3
            and (target['size'] is None or row['size'] == target['size'])
            and re.fullmatch('[0-9]{1,32}', str(row.get('fid', '')))
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


def retained_tuple(root, target, scope=None, status=None):
    """Exact media query + observed selection hash, never LIKE or guessed URL."""
    checked_target(target)
    root = Path(root)
    current = catalog_scope(root, status)
    require(scope is None or checked_catalog_scope(scope) == current, 'STATE_CHANGED')
    matches = []
    path = (root / 'userdata/addon_data/plugin.video.bobbi/source-libraries'
            / current['endpoint_sha256'] / 'catalog.sqlite3')
    if path.is_file():
        db = readonly(path)
        try:
            for stored in db.execute('SELECT key,media,payload FROM selections WHERE media=? LIMIT 4097', (target['media'],)):
                locator = 'am6bjuku://' + stored['key']
                if 'transport:' + digest(locator) != target['selection_identity']:
                    continue
                row = json.loads(stored['payload'])
                require(row.get('key') == stored['key'], 'TUPLE_MISMATCH')
                retained_context(row, target)
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
                        share_status = catalog.execute('SELECT enabled FROM share_status WHERE cell=?', (row['cell'],)).fetchone()
                        require(share_status is None or share_status['enabled'], 'SHARE_REVOKED')
                    share = dict(shares[0])
                finally:
                    catalog.close()
                matches.append(validate_tuple(dict(row, provider='qqdocs', media=stored['media'],
                    locator=locator, guid=guid, share=share), target))
        finally:
            db.close()
    require(catalog_scope(root, status) == current, 'STATE_CHANGED')
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
    mode, tmdb, season, episode = media_fields(target)
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
            and type(pointer.get('size')) is int
            and str((item.get('ids') or {}).get('tmdb_id')) == str(tmdb)
            and item.get('mode') == mode, 'HISTORY_MISMATCH')
    if mode == 'tv':
        tv = item.get('tv_data') or {}
        require(isinstance(tv, dict) and str(tv.get('season')) == str(season)
                and str(tv.get('episode')) == str(episode), 'HISTORY_MISMATCH')
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


def inspect(root, target, account_status=None, status=None):
    account_status = account_status or (lambda: control('account_status', {}))
    scope = catalog_scope(root, status)
    before = checked_account(account_status())
    row = retained_tuple(root, target, scope, status)
    proof = history_proof(root, target, row, before)
    require(account_status() == before, 'ACCOUNT_CHANGED')
    require(catalog_scope(root, status) == scope, 'STATE_CHANGED')
    result = dict(schema=target.get('schema', 1), operation='inspect', mode='read_only', state='validated',
        diagnostic_only=True, product_proof=False, playback_performed=False, network_media_read=False,
        baseline_request=target['request_id'], source_key=target['source_key'],
        selection_identity=target['selection_identity'], title=row['name'], size=row['size'],
        media=row['media'], provider=row['provider'], tuple_sha256=digest(encoded(row)),
        fid_sha256=digest(row['fid']), share_sha256=digest(encoded(row['share'])),
        account_fingerprint=before['account_id'][4:], account_epoch=before['epoch'], history=proof,
        catalog_scope=scope)
    if target.get('schema') == 2:
        result.update(target_evidence(target), size_evidence='retained_tuple_and_exact_history')
        result['size'] = row['size']
    return result


def remote_entry(parameters):
    evidence = {}
    try:
        require(parameters.get('operation') == 'inspect', 'DIAGNOSTIC_SCOPE')
        evidence = target_evidence(checked_target(parameters['target']))
        return inspect('/storage/.kodi', parameters['target'])
    except Exception as error:
        return dict(state='not_validated', diagnostic_only=True, product_proof=False, **evidence, **safe_error(error))

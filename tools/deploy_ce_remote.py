"""Reviewed one-box controller. Programs/enable flags only roll back, not media."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

KODI = Path('/storage/.kodi')
PROFILES = KODI / 'userdata/addon_data'
WORK = Path('/storage/.local/share/bobbi-private-updates')
CONFIG = Path('/storage/.local/share/bobitv/preparation-runtime/r3-20260922/config.json')
LOGIN = Path('/storage/.local/share/am6b-qqdocs-private/115-os_linux.json')
OLD_IDS = ('plugin.video.jacktook', 'script.am6b.opensubtitles', 'skin.am6b.cinema')
UNITS = ('kodi.service', 'bobitv-preparation.service')
TORRENT_ID = 'plugin.video.bobbi.torrent'


def transition_boundary(run, manifest):
    """Validate the driver-pinned migration boundary before touching the host."""
    ids = {row['id'] for row in manifest['components']}
    if TORRENT_ID not in ids:
        return  # Historical 21-component controller fixtures/generations.
    from ce_state_migration import plain, digest
    from bobbi_platform.offline_updates import load_trust
    path = plain(run / 'transition-baseline.json', file=True)
    if path.stat().st_size > 16384:
        raise ValueError('CE_TRANSITION_INVALID')
    value = json.loads(path.read_text(encoding='utf-8'))
    keys = {'schema', 'baseline_sequence', 'from_components', 'to_components',
            'key', 'candidate_sha256', 'candidate_sequence'}
    trust = load_trust()
    if (not isinstance(value, dict) or set(value) != keys
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['baseline_sequence']) is not int or value['baseline_sequence'] != 2026101905
            or type(value['candidate_sequence']) is not int
            or value['candidate_sequence'] <= value['baseline_sequence']
            or value['candidate_sequence'] != manifest['sequence']
            or not isinstance(value['from_components'], list)
            or not isinstance(value['to_components'], list)
            or any(not isinstance(i, str) for i in value['from_components'] + value['to_components'])
            or len(value['from_components']) != 21 or len(set(value['from_components'])) != 21
            or len(value['to_components']) != 22 or len(set(value['to_components'])) != 22
            or TORRENT_ID in value['from_components']
            or set(value['to_components']) != set(value['from_components']) | {TORRENT_ID}
            or set(value['to_components']) != ids or ids != set(trust['components'])
            or value['key'] != trust['key']
            or value['candidate_sha256'] != digest(run / 'candidate.zip')):
        raise ValueError('CE_TRANSITION_INVALID')


def require_clean_transaction():
    # Never reinterpret an unfinished old-generation journal with a new
    # inventory. Its frozen controller must finish recovery first.
    path = WORK / 'journal.json'
    if path.exists() or path.is_symlink():
        raise ValueError('CE_PENDING_TRANSACTION_USE_FROZEN_CONTROLLER')


def migrate_torrent_backend(manifest):
    """One-time connection-only import. The old engine/service stays untouched."""
    if TORRENT_ID not in {row['id'] for row in manifest['components']}:
        return dict(state='not-applicable')
    from ce_state_migration import plain
    from bobbi_torrent.backend import from_legacy_settings, load_config, LEGACY_KEYS
    stopped()
    target = plain(PROFILES / TORRENT_ID / 'backend.json')
    if target.exists():
        load_config(target)
        return dict(state='existing-preserved')
    source = plain(PROFILES / 'plugin.video.jacktorr/settings.xml')
    if not source.exists():
        return dict(state='unconfigured', reason='legacy-settings-absent')
    source = plain(source, file=True)
    if source.stat().st_size > 256 * 1024:
        raise ValueError('CE_TORRENT_SETTINGS_SIZE')
    raw = source.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('CE_TORRENT_SETTINGS_XML')
    root = ET.fromstring(raw)
    if root.tag != 'settings':
        raise ValueError('CE_TORRENT_SETTINGS_XML')
    settings = {}
    for node in root:
        name = node.get('id')
        if name not in LEGACY_KEYS:
            continue
        if name in settings or node.tag != 'setting' or len(node):
            raise ValueError('CE_TORRENT_SETTINGS_XML')
        settings[name] = node.get('value', node.text or '')
    value = from_legacy_settings(settings)
    stopped()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = plain(target.with_suffix('.tmp'))
    if temporary.exists():
        raise ValueError('CE_TORRENT_SETTINGS_TEMP_EXISTS')
    write_json(target, value)
    load_config(target)
    return dict(state='migrated-connection-only', fields=sorted(settings),
                old_service_unchanged=True, preserved_on_rollback=True)


def command(*args):
    result = subprocess.run(list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if result.returncode:
        raise RuntimeError('CE_COMMAND_' + args[0])
    return result.stdout.decode().strip()


def rpc(method, params=None):
    request = urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params or {})).encode(),
        {'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=4) as response:
        result = json.load(response)
    if 'error' in result:
        raise RuntimeError('KODI_RPC_' + str(result['error']['code']))
    return result['result']


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    if os.name == 'posix':
        directory = os.open(str(path.parent), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def bootstrap(run):
    target = run / 'bootstrap/addons'
    expected = {}
    with zipfile.ZipFile(run / 'candidate.zip') as outer:
        for row in json.loads(outer.read('release.json'))['components']:
            with zipfile.ZipFile(io.BytesIO(outer.read(row['file']))) as package:
                for item in package.infolist():
                    expected[item.filename] = hashlib.sha256(package.read(item)).hexdigest()
    if not target.exists():
        with zipfile.ZipFile(run / 'candidate.zip') as archive:
            manifest = json.loads(archive.read('release.json'))
            for row in manifest['components']:
                blob = archive.read(row['file'])
                if hashlib.sha256(blob).hexdigest() != row['sha256']:
                    raise ValueError('BOOTSTRAP_HASH')
                with zipfile.ZipFile(io.BytesIO(blob)) as package:
                    for item in package.infolist():
                        parts = item.filename.split('/')
                        if (item.is_dir() or parts[0] != row['id'] or any(p in ('','.','..') for p in parts)
                                or '\\' in item.filename or ':' in item.filename):
                            raise ValueError('BOOTSTRAP_MEMBER')
                        path = target.joinpath(*parts)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('xb') as stream:
                            stream.write(package.read(item))
    files = {path.relative_to(target).as_posix(): path for path in target.rglob('*') if path.is_file()}
    if set(files) != set(expected) or any(path.is_symlink() for path in target.rglob('*')):
        raise ValueError('BOOTSTRAP_TREE_CHANGED')
    for name, path in files.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
            raise ValueError('BOOTSTRAP_FILE_CHANGED')
    for path in target.glob('*/lib'):
        sys.path.insert(0, str(path))
    from bobbi_platform.offline_updates import SignedBundle, load_trust
    with SignedBundle(run / 'candidate.zip', load_trust(), 'coreelec') as bundle:
        bundle.check_all()
        return bundle.manifest


def stopped():
    for unit in UNITS:
        mask = Path('/run/systemd/system') / unit
        if not mask.is_symlink() or os.readlink(mask) != '/dev/null':
            raise RuntimeError('CE_OWNER_NOT_MASKED')
        if command('systemctl', 'show', unit, '--property=MainPID', '--value') != '0':
            raise RuntimeError('CE_OWNER_RUNNING')


def running_native_sha256():
    from bobbi_core.runtime_paths import native_executable_sha256
    pids = command('pidof', 'kodi.bin').split()
    if len(pids) != 1 or not re.fullmatch(r'[1-9][0-9]{0,9}', pids[0]):
        raise RuntimeError('CE_NATIVE_PROCESS_NOT_UNIQUE')
    # Keep the proc magic-link object: .resolve() would reopen a potentially
    # different inode from the controller's namespace, not the running Kodi.
    return native_executable_sha256(Path('/proc') / pids[0] / 'exe')


def identity(config):
    from bobbi_core.cd2 import CD2
    from bobbi_platform.account_manager import account_id
    session = json.loads(LOGIN.read_text())
    client = CD2(Path(config['cd2_token_file']).read_text().strip(),
                 config['cd2_endpoint'].rstrip('/') + '/clouddrive.CloudDriveFileSrv/')
    try:
        result = client.provider_identity()
        if result['account_id'] != account_id(session) or result['legacy_scope'] != config['account']:
            raise ValueError('LIVE_ACCOUNT_MISMATCH')
        return session, result
    finally:
        client.session.close()


def copy_file(source, target, limit=16 * 1024 * 1024):
    from ce_state_migration import plain, digest
    source, target = plain(source, file=True), plain(target)
    if target.exists() or source.stat().st_size > limit:
        raise ValueError('PROFILE_COPY_DESTINATION_OR_SIZE')
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as reader, target.open('xb') as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    os.chmod(target, 0o600)
    if digest(source) != digest(target):
        raise ValueError('PROFILE_COPY_CHANGED')


def migrate_profiles(run, config):
    from ce_state_migration import migrate_preparation, sqlite_backup
    from bobbi_platform.account_manager import AccountManager
    plugin = PROFILES / 'plugin.video.bobbi'
    platform = PROFILES / 'script.module.bobbi.platform'
    if plugin.exists() or platform.exists():
        raise ValueError('CE_FIRST_MIGRATION_REQUIRES_NEW_PROFILES')
    session, provider = identity(config)
    login_sha = hashlib.sha256(LOGIN.read_bytes()).hexdigest()
    platform.mkdir(mode=0o700)
    accounts = AccountManager(platform / '115-os_linux.json')
    scope = accounts.install(session, accounts.snapshot())
    plugin.mkdir(mode=0o700)
    target = plugin / 'preparation' / (scope['account_id'][4:] + '-' + str(scope['epoch']))
    result = migrate_preparation(Path(config['state_directory']), target, provider, scope,
                                 config['account'], config['destination'], stopped)
    # Copy only persistent user choices/history; never sockets, playback grants,
    # cached URLs, or a previous service's runtime control files.
    for name in ('database.pickle', 'bobi-library.json'):
        old = PROFILES / 'plugin.video.jacktook' / name
        if old.is_file():
            copy_file(old, plugin / name)
    settings = ET.parse(PROFILES / 'plugin.video.jacktook/settings.xml')
    allowed = {n.get('id') for n in ET.parse(run / 'bootstrap/addons/plugin.video.bobbi/resources/settings.xml').findall('.//setting')}
    for node in list(settings.getroot()):
        if node.get('id') not in allowed:
            settings.getroot().remove(node)
        elif node.get('id') == 'auto_play':
            node.text = 'false'
            if 'value' in node.attrib:
                node.set('value', 'false')
    settings.write(plugin / 'settings.xml', encoding='utf-8', xml_declaration=True)
    os.chmod(plugin / 'settings.xml', 0o600)
    old_token = Path('/storage/.config/am6b-subtitles283/assrt-token')
    if old_token.is_file():
        copy_file(old_token, plugin / 'assrt-token', 16384)
        result['assrt_token_preserved'] = True
    # Same device identity, not a shared upstream application key.
    old_juku = PROFILES / 'plugin.video.jacktook/juku'
    if old_juku.is_dir():
        new_juku = plugin / 'juku'
        new_juku.mkdir(mode=0o700)
        for name in ('device.pem', 'session.json'):
            if (old_juku / name).is_file():
                copy_file(old_juku / name, new_juku / name, 65536)
        for name in ('catalog.sqlite3',):
            if (old_juku / name).is_file():
                sqlite_backup(old_juku / name, new_juku / name, stopped)
    skin = PROFILES / 'skin.bobbi.cinema'
    skin.mkdir(mode=0o700)
    for name in ('settings.xml', 'skin_record.xml'):
        old = PROFILES / 'skin.am6b.cinema' / name
        if old.is_file():
            copy_file(old, skin / name)
    keys = {'cd2_endpoint','cd2_token_file','cd2_login_file','account','destination','ffprobe',
            'font_tool','font_native_directory','download_capability','torrserver_endpoint',
            'tmdb_api_key_file','tmdb_proxy','jackett_endpoint','jackett_api_key_file'}
    preparation = {key: config[key] for key in keys if key in config}
    preparation.update(schema=1, enabled=True)
    # Preserve this installation's explicit preparation proxy configuration.
    # It never becomes an installer default; direct metadata is tested separately.
    write_json(platform / 'preparation.json', preparation)
    from bobbi_core.preparation_host import configuration
    configuration(platform / 'preparation.json')
    stopped()
    _, latest = identity(config)
    if latest != provider or hashlib.sha256(LOGIN.read_bytes()).hexdigest() != login_sha or accounts.snapshot() != scope:
        raise ValueError('MIGRATION_ACCOUNT_CHANGED')
    return result


def upgrade_profile_snapshot(check_stopped=True):
    """Stopped-owner sentinels, never re-migrate an already-owned account epoch."""
    from ce_state_migration import plain, digest
    from bobbi_platform.account_manager import validate_snapshot, account_id
    from bobbi_core.runtime_paths import known_ce_native
    if check_stopped:
        stopped()
    for name in ('plugin.video.bobbi', 'script.module.bobbi.platform', 'skin.bobbi.cinema'):
        if not plain(PROFILES / name).is_dir():
            raise ValueError('CE_UPGRADE_PROFILE_MISSING')
    login = plain(PROFILES / 'script.module.bobbi.platform/115-os_linux.json', file=True)
    if login.stat().st_size > 16384:
        raise ValueError('CE_UPGRADE_ACCOUNT_SIZE')
    value = json.loads(login.read_text())
    scope = validate_snapshot(value.get('_account'))
    if scope['authenticated'] and account_id(value) != scope['account_id']:
        raise ValueError('CE_UPGRADE_ACCOUNT_MISMATCH')
    if not scope['authenticated'] and value != {'_account': scope}:
        raise ValueError('CE_UPGRADE_ACCOUNT_MISMATCH')
    marker = plain(PROFILES / 'plugin.video.bobbi/runtime-paths.json', file=True)
    abi = json.loads(marker.read_text())
    if (not isinstance(abi, dict) or set(abi) != {'schema', 'subtitle_abi', 'native_sha256'}
            or type(abi['schema']) is not int or abi['schema'] != 1
            or abi['subtitle_abi'] != 'ce-f9' or not known_ce_native(abi['native_sha256'])):
        raise ValueError('CE_UPGRADE_NATIVE_ABI')
    names = ('script.module.bobbi.platform/115-os_linux.json',
             'script.module.bobbi.platform/preparation.json',
             'plugin.video.bobbi/runtime-paths.json', 'plugin.video.bobbi/settings.xml',
             'plugin.video.bobbi/database.pickle', 'plugin.video.bobbi/bobi-library.json',
             'plugin.video.bobbi/assrt-token', 'skin.bobbi.cinema/settings.xml',
             'skin.bobbi.cinema/skin_record.xml', 'plugin.video.bobbi.torrent/backend.json')
    return {name: digest(PROFILES / name) if (PROFILES / name).exists() else None for name in names}


def flags(database, ids, values=None):
    from bobbi_platform.upstream_addons import UPSTREAM_COMPONENTS
    # Even an older full-generation rollback receipt must not take ownership
    # of Kodi/author-managed dependencies or reset their repository origin.
    ids = [name for name in ids if name not in UPSTREAM_COMPONENTS]
    if values is not None:
        values = {name: value for name, value in values.items() if name not in UPSTREAM_COMPONENTS}
    db = sqlite3.connect(str(database))
    try:
        expected = ('id','addonID','enabled','installDate','lastUpdated','lastUsed','origin','disabledReason')
        if tuple(row[1] for row in db.execute('PRAGMA table_info(installed)')) != expected:
            raise ValueError('KODI_ADDON_SCHEMA_CHANGED')
        old = {name: db.execute('SELECT enabled,disabledReason FROM installed WHERE addonID=?', (name,)).fetchone() for name in ids}
        if values is not None:
            for name, value in values.items():
                if value is None:
                    db.execute('DELETE FROM installed WHERE addonID=?', (name,))
                elif old[name] is None:
                    db.execute("INSERT INTO installed(addonID,enabled,installDate,origin,disabledReason) VALUES(?,?,datetime('now'),'',?)", (name, value[0], value[1]))
                else:
                    db.execute('UPDATE installed SET enabled=?,disabledReason=? WHERE addonID=?', (value[0], value[1], name))
            db.commit()
        return old
    finally:
        db.close()


def gui(value=None):
    path = KODI / 'userdata/guisettings.xml'
    tree = ET.parse(path)
    nodes = {n.get('id'): n for n in tree.findall('setting')}
    keys = ('lookandfeel.skin', 'lookandfeel.soundskin')
    previous = {key: nodes[key].text for key in keys}
    if value:
        for key, content in value.items():
            nodes[key].text = content
            nodes[key].attrib.pop('default', None)
        temporary = path.with_suffix('.bobbi-tmp')
        tree.write(temporary, encoding='utf-8', xml_declaration=True)
        os.replace(temporary, path)
    return previous


class GenerationConflict(RuntimeError):
    """An old deployment receipt must never mutate a newer installation."""


def _generation(value):
    if (not isinstance(value, dict) or set(value) != {'sequence', 'versions'}
            or type(value['sequence']) is not int or value['sequence'] < 0
            or not isinstance(value['versions'], dict)
            or any(not isinstance(k, str) or not isinstance(v, str)
                   for k, v in value['versions'].items())):
        raise RuntimeError('CE_PROGRAM_RECEIPT_INVALID')
    return dict(sequence=value['sequence'], versions=dict(value['versions']))


def owned_generation(engine, value):
    value = _generation(value)
    managed = getattr(engine, 'managed', None)
    if managed is None:
        return value
    expected = getattr(engine, 'expected', managed)
    if not set(value['versions']) <= set(expected):
        raise RuntimeError('CE_PROGRAM_RECEIPT_INVALID')
    return dict(sequence=value['sequence'],
                versions={name: version for name, version in value['versions'].items() if name in managed})


def upstream_preflight(run, engine):
    """Read-only dependency/origin boundary; never enable or install a vendor."""
    from bobbi_platform.upstream_addons import check_dependencies, UPSTREAM_COMPONENTS
    managed = getattr(engine, 'managed', None)
    expected = getattr(engine, 'expected', ())
    if managed is None or set(managed) == set(expected):
        return {}
    required = check_dependencies(KODI / 'addons', run / 'bootstrap/addons', managed)
    return upstream_enabled_versions(engine, required)


def upstream_enabled_versions(engine, required=None):
    from bobbi_platform.upstream_addons import UPSTREAM_COMPONENTS
    managed, expected = getattr(engine, 'managed', None), getattr(engine, 'expected', ())
    if managed is None or set(managed) == set(expected):
        return {}
    names = sorted(set(expected if required is None else required) & UPSTREAM_COMPONENTS)
    database = KODI / 'userdata/Database/Addons33.db'
    result = {}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        for name in names:
            row = db.execute('SELECT enabled,origin FROM installed WHERE addonID=?', (name,)).fetchone()
            if row is None or row[0] != 1:
                raise ValueError('CE_UPSTREAM_DISABLED_USE_KODI:' + name)
            result[name] = dict(version=engine._addon(KODI / 'addons' / name / 'addon.xml')[1], origin=row[1])
    return result


def program_phase(engine, receipt):
    """Recovery precedes inspection; a returned Python flag is not a commit."""
    before = owned_generation(engine, receipt.get('program_before'))
    expected = owned_generation(engine, receipt.get('program_expected'))
    if (expected['sequence'] <= before['sequence'] or not expected['versions']
            or expected['versions'] == before['versions']):
        raise RuntimeError('CE_PROGRAM_RECEIPT_INVALID')
    observed = owned_generation(engine, engine.available())
    restored = dict(sequence=expected['sequence'], versions=before['versions'])
    if observed == before:
        return 'not_applied', observed, restored
    if receipt.get('program_attempted') is True:
        if observed == expected:
            return 'applied', observed, restored
        if observed == restored:
            return 'restored', observed, restored
    raise GenerationConflict('CE_ROLLBACK_STALE_GENERATION')


def restore_program(engine, receipt):
    phase, observed, restored = program_phase(engine, receipt)
    receipt['program_observed'] = observed
    if phase == 'applied':
        receipt['applied_generation'] = observed
        try:
            engine.rollback()
        except Exception:
            # The rollback commit may also precede a retention/receipt error.
            # Only successful recovery + exact durable inspection can settle it.
            recovered = owned_generation(engine, engine.available())
            if recovered == owned_generation(engine, receipt['program_expected']):
                raise
            if recovered != restored:
                raise GenerationConflict('CE_ROLLBACK_GENERATION_CHANGED')
        observed = owned_generation(engine, engine.available())
        if observed != restored:
            raise GenerationConflict('CE_ROLLBACK_GENERATION_CHANGED')
        receipt['program_observed'] = observed
    if phase in ('applied', 'restored'):
        receipt['rolled_back_generation'] = observed
    receipt['installed'] = False  # Display compatibility; never a decision input.


def restore(run, receipt, lease):
    from bobbi_platform.offline_updates import load_trust, rollback_engine
    errors = []
    stale = False
    if 'program_before' in receipt or receipt.get('installed'):
        try:
            engine = rollback_engine(load_trust(), 'coreelec', KODI / 'addons', WORK, lease.idle, lease.commit)
            restore_program(engine, receipt)
        except GenerationConflict as error:
            # Do not restore OLD flags/skin over a verified different generation.
            stale = True
            errors.append('program:' + str(error))
        except Exception as error:
            errors.append('program:' + type(error).__name__)
    if 'flags' in receipt and not stale:
        try:
            flags(KODI / 'userdata/Database/Addons33.db', receipt['flags'], receipt['flags'])
        except Exception as error:
            errors.append('flags:' + type(error).__name__)
    if 'gui' in receipt and not stale:
        try:
            gui(receipt['gui'])
        except Exception as error:
            errors.append('gui:' + type(error).__name__)
    receipt['rolled_back'] = not errors
    if errors:
        receipt['recovery_errors'] = errors
    write_json(run / 'deployment.json', receipt)
    if errors:
        raise RuntimeError('CE_ROLLBACK_INCOMPLETE')


def main(run, mode):
    if mode not in ('stage', 'status', 'deploy', 'upgrade', 'rollback'):
        raise ValueError('CE_DEPLOY_MODE')
    if 'CoreELEC' not in Path('/etc/os-release').read_text():
        raise ValueError('CORELEC_ONLY')
    manifest = bootstrap(run)
    transition_boundary(run, manifest)
    if mode == 'stage':
        return dict(state='staged', components=len(manifest['components']), system_unchanged=True)
    if mode == 'status':
        return dict(state='status', players=rpc('Player.GetActivePlayers'), application=rpc('Application.GetProperties', {'properties':['version']}),
                    host_file=(PROFILES / 'script.module.bobbi.platform/runtime.json').is_file())
    receipt_path = run / 'deployment.json'
    if mode in ('deploy', 'upgrade') and receipt_path.exists():
        raise ValueError('DEPLOY_RUN_ALREADY_USED')
    config = None
    if mode == 'deploy':
        config = json.loads(CONFIG.read_text())
        sys.path.insert(0, config['python_library_directory'])
    from bobbi_platform.maintenance_lease import CoreELECLease
    from bobbi_platform.offline_updates import SignedBundle, load_trust
    from ce_state_migration import sqlite_backup
    WORK.mkdir(mode=0o700, parents=True, exist_ok=True)
    lease = CoreELECLease(WORK)
    receipt = json.loads(receipt_path.read_text()) if mode == 'rollback' else dict(schema=1, installed=False, services={})
    try:
        if mode != 'rollback':
            require_clean_transaction()
        if mode == 'rollback':
            from bobbi_platform.offline_updates import rollback_engine
            # New receipts bind rollback to the native host that preceded this
            # program generation. Restore its overlay first, not legacy plugins
            # under a newer native ABI selector they do not recognize.
            if receipt.get('native_before') and running_native_sha256() != receipt['native_before']:
                raise ValueError('CE_RESTORE_PREVIOUS_NATIVE_BEFORE_PROGRAM_ROLLBACK')
            # Reject an old run before masking/stopping services or changing UI flags.
            check = rollback_engine(load_trust(), 'coreelec', KODI / 'addons', WORK, lease.idle, lease.commit)
            program_phase(check, receipt)
            upstream_enabled_versions(check)
        else:
            from bobbi_core.runtime_paths import known_ce_native
            receipt['native_before'] = running_native_sha256()
            if not known_ce_native(receipt['native_before']):
                raise ValueError('CE_NATIVE_BUILD_CHANGED')
            if mode == 'deploy':
                identity(config)
            else:
                # An update owns programs, not the retired migration account.
                # Local logout/account changes need neither CD2 nor old files.
                upgrade_profile_snapshot(check_stopped=False)
            with SignedBundle(run / 'candidate.zip', load_trust(), 'coreelec') as source:
                check = source.engine(KODI / 'addons', WORK, lease.idle, lease.commit)
                receipt['program_before'] = owned_generation(check, check.available())
                receipt['upstream_preserved'] = upstream_preflight(run, check)
            receipt['program_expected'] = owned_generation(check, dict(sequence=manifest['sequence'],
                versions={row['id']: row['version'] for row in manifest['components']}))
            receipt['program_attempted'] = False
            if (receipt['program_expected']['sequence'] <= receipt['program_before']['sequence']
                    or not receipt['program_expected']['versions']
                    or receipt['program_expected']['versions'] == receipt['program_before']['versions']):
                raise GenerationConflict('CE_DEPLOY_GENERATION_NOT_NEW')
            if mode == 'upgrade' and (receipt['program_before']['sequence'] <= 0
                                      or not receipt['program_before']['versions']):
                raise ValueError('CE_UPGRADE_REQUIRES_INSTALLED_GENERATION')
            for unit in UNITS:
                mask = Path('/run/systemd/system') / unit
                if mask.exists() or mask.is_symlink():
                    raise ValueError('CE_ALREADY_RUNTIME_OVERRIDDEN')
                receipt['services'][unit] = {key: command('systemctl','show',unit,'--property='+key,'--value') for key in ('ActiveState','UnitFileState')}
        # The first service mutation must already be recoverable after a crash.
        # Do not carry a prior successful rollback flag into a new attempt.
        receipt.pop('rolled_back', None)
        receipt['services_attempted'] = []
        write_json(receipt_path, receipt)
    except BaseException:
        lease.close()
        raise
    success, stopped_units = False, []
    try:
        for unit in UNITS:
            receipt['services_attempted'].append(unit)
            write_json(receipt_path, receipt)
            stopped_units.append(unit)
            command('systemctl', 'mask', '--runtime', unit)
            command('systemctl', 'stop', unit)
        stopped()
        if mode == 'rollback':
            restore(run, receipt, lease)
        else:
            database = KODI / 'userdata/Database/Addons33.db'
            sqlite_backup(database, run / 'Addons33.before.db', stopped)
            copy_file(KODI / 'userdata/guisettings.xml', run / 'guisettings.before.xml')
            ids = [row['id'] for row in manifest['components']]
            receipt['flags'] = flags(database, ids + list(OLD_IDS))
            receipt['gui'] = gui()
            receipt['new_profiles_preserved_on_failure'] = [str(PROFILES / name) for name in
                ('plugin.video.bobbi', 'script.module.bobbi.platform', 'skin.bobbi.cinema')]
            if TORRENT_ID in ids:
                receipt['new_profiles_preserved_on_failure'].append(str(PROFILES / TORRENT_ID))
            with SignedBundle(run / 'candidate.zip', load_trust(), 'coreelec') as source:
                engine = source.engine(KODI / 'addons', WORK, lease.idle, lease.commit)
                if owned_generation(engine, engine.available()) != receipt['program_before']:
                    raise GenerationConflict('CE_DEPLOY_GENERATION_CHANGED')
                receipt['upstream_preserved'] = upstream_preflight(run, engine)
                write_json(receipt_path, receipt)
                receipt['torrent_connection'] = migrate_torrent_backend(manifest)
                write_json(receipt_path, receipt)
                if mode == 'upgrade':
                    preserved = upgrade_profile_snapshot()
                    receipt['migration'] = dict(performed=False, policy='existing-current-profile-preserved')
                else:
                    preserved = None
                    receipt['migration'] = migrate_profiles(run, config)
                receipt['program_attempted'] = True
                write_json(receipt_path, receipt)  # Durable BEFORE engine's commit.
                engine.apply(source.raw, source.signature)
                phase, current, _ = program_phase(engine, receipt)
                if phase != 'applied':
                    raise RuntimeError('CE_APPLY_GENERATION_UNCONFIRMED')
                receipt['applied_generation'] = current
                if preserved is not None:
                    if upgrade_profile_snapshot() != preserved:
                        raise RuntimeError('CE_UPGRADE_PROFILE_CHANGED')
                    receipt['profile_sentinels_unchanged'] = sorted(preserved)
            receipt['installed'] = True
            write_json(receipt_path, receipt)
            flags(database, ids + list(OLD_IDS), dict({name:(1,0) for name in ids}, **{name:(0,1) for name in OLD_IDS}))
            gui({'lookandfeel.skin':'skin.bobbi.cinema', 'lookandfeel.soundskin':'resource.uisounds.bobbi-modern'})
            command('systemctl', 'disable', 'bobitv-preparation.service')
            write_json(receipt_path, receipt)
        success = True
    except Exception as error:
        receipt['failure'] = type(error).__name__ + ':' + str(error)[:120] if str(error).startswith(('CE_','MIGRATION_','PROFILE_','LIVE_','KODI_')) else type(error).__name__
        try:
            # If stop itself failed, no program transaction was attempted.
            # Durable unchanged-generation inspection can restore our services
            # without pretending every owner successfully stopped. Unknown or
            # changed generations still fail restore and keep the masks.
            if receipt.get('program_attempted') is True:
                stopped()
            restore(run, receipt, lease)
        except Exception as rollback_error:
            receipt['rollback_failure'] = type(rollback_error).__name__
            write_json(receipt_path, receipt)
        raise
    finally:
        try:
            if success or receipt.get('rolled_back') is True:
                recovery_errors = []
                for unit in reversed(stopped_units):
                    try:
                        command('systemctl', 'unmask', '--runtime', unit)
                    except Exception as error:
                        recovery_errors.append('unmask:' + unit + ':' + type(error).__name__)
                for unit, old in receipt.get('services', {}).items():
                    if unit not in stopped_units:
                        continue  # This attempt never controlled that service.
                    if unit == 'bobitv-preparation.service' and success and mode in ('deploy', 'upgrade'):
                        continue
                    try:
                        if old['UnitFileState'] == 'enabled':
                            command('systemctl','enable',unit)
                        if old['ActiveState'] == 'active':
                            command('systemctl','start',unit)
                    except Exception as error:
                        recovery_errors.append('restore:' + unit + ':' + type(error).__name__)
                if recovery_errors:
                    receipt['service_recovery_errors'] = recovery_errors
                    write_json(receipt_path, receipt)
                    raise RuntimeError('CE_SERVICE_RESTORE_FAILED')
                receipt.pop('recovery_required_owners_held_stopped', None)
                receipt.pop('service_recovery_errors', None)
                write_json(receipt_path, receipt)
            else:
                # Never start an unknown mix of the old/new playback owners.
                receipt['recovery_required_owners_held_stopped'] = True
                write_json(receipt_path, receipt)
        finally:
            lease.close()
    return dict(state='upgraded' if mode=='upgrade' else 'deployed' if mode=='deploy' else 'rolled_back', program_sequence=manifest['sequence'],
                migration=receipt.get('migration'), cd2_and_mount_untouched=True,
                playback_verified=False)

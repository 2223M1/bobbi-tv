"""Read-only catalog/code compatibility boundary shared by every installer.

Inspect retained code as syntax, never import it. Shared add-ons must support
every registered Kodi profile, including a committed schema still in a WAL.
"""
import ast
from contextlib import closing
import hashlib
import json
from io import BytesIO
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET
import zipfile

from .updates import UpdateError, _safe_path

CORE = 'script.module.bobbi.core'
PROGRAM = 'lib/bobbi_core/media_library_index.py'
CATALOG = 'script.module.bobbi.platform/media-index.sqlite3'
REGISTRY = 'script.module.bobbi.platform/libraries.sqlite3'
REGISTRY_PROGRAM = 'lib/bobbi_core/library_contract.py'


class CatalogCompatibilityError(UpdateError, ValueError):
    """No code replacement is allowed while retained data is unproven."""


def _plain(path, file=False):
    path = _safe_path(path)
    if file and not path.is_file():
        raise CatalogCompatibilityError('CE_CATALOG_SCHEMA_UNREADABLE')
    return path


def profile_roots(userdata):
    """Resolve only the bounded, explicit local Kodi profile inventory."""
    userdata = _plain(userdata)
    inventory = _plain(userdata / 'profiles.xml')
    roots = {userdata}
    if not inventory.exists():
        return (userdata,)
    try:
        _plain(inventory, file=True)
        if inventory.stat().st_size > 65536:
            raise ValueError('profile inventory budget')
        raw = inventory.read_bytes()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('profile inventory markup')
        tree = ET.fromstring(raw)
        entries = tree.findall('profile')
        if tree.tag != 'profiles' or not 1 <= len(entries) <= 64:
            raise ValueError('profile inventory unknown')
        for entry in entries:
            if len(entry.findall('directory')) != 1:
                raise ValueError('profile directory unknown')
            value = (entry.findtext('directory') or '').strip().replace('\\', '/')
            if value in ('', 'special://masterprofile', 'special://masterprofile/',
                         'special://home/userdata', 'special://home/userdata/'):
                path = userdata
            elif value.startswith('special://masterprofile/'):
                path = userdata / value[len('special://masterprofile/'):]
            elif value.startswith('special://home/userdata/'):
                path = userdata / value[len('special://home/userdata/'):]
            else:
                if '://' in value or value.startswith('//'):
                    raise ValueError('non-local profile')
                path = Path(value)
                path = path if path.is_absolute() else userdata / path
            if '..' in path.parts:
                raise ValueError('profile traversal')
            roots.add(_plain(path))
        return tuple(sorted(roots, key=str))
    except (OSError, ValueError, UpdateError, ET.ParseError):
        raise CatalogCompatibilityError('CE_CATALOG_OTHER_PROFILES_REQUIRE_EXPLICIT_REVIEW') from None


def read_schema(path):
    path = _plain(path)
    for suffix in ('-wal', '-shm', '-journal'):
        _plain(Path(str(path) + suffix))
    if not path.exists():
        return None
    _plain(path, file=True)
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.15)) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if type(version) is not int or version <= 0:
                raise CatalogCompatibilityError('CE_CATALOG_SCHEMA_UNINITIALIZED_OR_UNKNOWN')
            return version
    except sqlite3.Error:
        raise CatalogCompatibilityError('CE_CATALOG_SCHEMA_UNREADABLE') from None


def schemas(userdata, master_addon_data=None):
    roots = profile_roots(userdata)
    master = _plain(userdata)
    result = {}
    for root in roots:
        data = Path(master_addon_data) if root == master and master_addon_data is not None else root / 'addon_data'
        path = _plain(data / CATALOG)
        version = read_schema(path)
        if version is not None:
            result[path] = version
    return result


def registry_requirements(userdata, master_addon_data=None):
    """Content can require a newer reader even while PRAGMA user_version remains 1."""
    required = set()
    for root in profile_roots(userdata):
        data = Path(master_addon_data) if root == _plain(userdata) and master_addon_data is not None else root / 'addon_data'
        path = _plain(data / REGISTRY)
        if read_schema(path) is None:
            continue
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.15)) as db:
                if db.execute('PRAGMA user_version').fetchone() != (1,):
                    raise ValueError()
                db.execute('BEGIN')
                defs = db.execute("SELECT type FROM sqlite_master WHERE name='sources'").fetchone()
                if defs != ('table',):
                    raise ValueError()
                # Avoid loading an unbounded malformed BLOB or evaluating a view.
                sizes = db.execute('SELECT length(CAST(record AS BLOB)) FROM sources LIMIT 33').fetchall()
                if len(sizes) > 32 or any(type(n) is not int or not 0 < n <= 4 * 1024**2 for n, in sizes):
                    raise ValueError()
                emby = 0
                for raw, in db.execute('SELECT record FROM sources LIMIT 32'):
                    record = json.loads(raw)
                    kind = record['kind']
                    if kind == 't4':
                        required.add('t4')
                        sites = record.get('metadata', {}).get('sites', ())
                        if isinstance(sites, list) and any(isinstance(s, dict) and 'headers' in s for s in sites):
                            required.add('t4_headers')
                    elif kind == 'media_server':
                        provider = record['metadata']['provider']
                        if provider == 'emby':
                            emby += 1
                    elif kind not in ('catalog', 'vfs'):
                        raise ValueError()
                if emby > 1:
                    required.add('multi_emby')
        except (OSError, TypeError, ValueError, KeyError, RecursionError, sqlite3.Error):
            raise CatalogCompatibilityError('CE_REGISTRY_FORMAT_REQUIRES_EXPLICIT_OFFLINE_RESTORE') from None
    return required


def registry_support(raw, required, digest=None):
    """Capability is part of the retained, digested component; never infer it from its version."""
    try:
        if len(raw) > 256 * 1024 or (digest is not None and hashlib.sha256(raw).hexdigest() != digest):
            raise ValueError()
        tree = ast.parse(raw.decode('utf-8-sig'))
        values = [n.value for n in tree.body if isinstance(n, ast.Assign) and
                  any(isinstance(target, ast.Name) and target.id == 'REGISTRY_READ_FEATURES' for target in n.targets)]
        if len(values) != 1 or not isinstance(values[0], ast.Tuple):
            raise ValueError()
        features = ast.literal_eval(values[0])
        if any(type(s) is not str for s in features) or not required.issubset(features):
            raise ValueError()
    except (TypeError, SyntaxError, UnicodeError, ValueError):
        raise CatalogCompatibilityError('CE_REGISTRY_FORMAT_REQUIRES_EXPLICIT_OFFLINE_RESTORE') from None


def check_registry_program(required, root, digest=None):
    if required:
        try:
            path = _plain(Path(root) / REGISTRY_PROGRAM, file=True)
            if path.stat().st_size > 256 * 1024:
                raise ValueError()
            registry_support(path.read_bytes(), required, digest)
        except (OSError, ValueError, UpdateError):
            raise CatalogCompatibilityError('CE_REGISTRY_FORMAT_REQUIRES_EXPLICIT_OFFLINE_RESTORE') from None


def supported_schemas(raw, expected_digest=None):
    """The one parser for on-disk and signed-archive constructor contracts."""
    try:
        if len(raw) > 256 * 1024 or (expected_digest is not None
                and hashlib.sha256(raw).hexdigest() != expected_digest):
            raise ValueError('program input changed')
        tree = ast.parse(raw.decode('utf-8-sig'))
        constructors = [method for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MediaIndex'
                        for method in node.body if isinstance(method, ast.FunctionDef) and method.name == '__init__']
        if len(constructors) != 1:
            raise ValueError('constructor unknown')
        accepted = [node.comparators[0] for node in ast.walk(constructors[0])
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == 'version'
            and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotIn)
            and len(node.comparators) == 1 and isinstance(node.comparators[0], (ast.Tuple, ast.List, ast.Set))]
        if len(accepted) != 1 or not accepted[0].elts or any(not isinstance(node, ast.Constant)
                or type(node.value) is not int or not 0 <= node.value <= 100 for node in accepted[0].elts):
            raise ValueError('schema contract unknown')
        return {node.value for node in accepted[0].elts}
    except (ValueError, SyntaxError, UnicodeError):
        raise CatalogCompatibilityError('CE_CATALOG_PROGRAM_SCHEMA_UNPROVEN') from None


def program_schemas(root, expected_digest=None):
    try:
        path = _plain(Path(root) / PROGRAM, file=True)
        if path.stat().st_size > 256 * 1024:
            raise ValueError('oversized program')
        return supported_schemas(path.read_bytes(), expected_digest)
    except (OSError, ValueError, UpdateError):
        raise CatalogCompatibilityError('CE_CATALOG_PROGRAM_SCHEMA_UNPROVEN') from None


def require_supported(observed, supported):
    if any(version not in supported for version in observed.values()):
        raise CatalogCompatibilityError('CE_CATALOG_SCHEMA_INCOMPATIBLE_REQUIRES_EXPLICIT_OFFLINE_RESTORE')


def check_program(userdata, root, expected_digest=None, master_addon_data=None):
    observed = schemas(userdata, master_addon_data)
    check_registry_program(registry_requirements(userdata, master_addon_data), root)
    if observed:
        require_supported(observed, program_schemas(root, expected_digest))


def check_bundle(userdata, signed):
    observed = schemas(userdata)
    required = registry_requirements(userdata)
    if not observed and not required:
        return
    try:
        rows = [row for row in signed.manifest['components'] if row['id'] == CORE]
        if len(rows) != 1:
            raise ValueError('catalog owner missing')
        row = rows[0]
        with zipfile.ZipFile(BytesIO(signed.read(row['file'], row['size']))) as archive:
            def source(relative):
                name = CORE + '/' + relative
                matches = [item for item in archive.infolist() if item.filename == name]
                if len(matches) != 1 or matches[0].file_size > 256 * 1024:
                    raise ValueError('program input unknown')
                return archive.read(name)
            if required:
                registry_support(source(REGISTRY_PROGRAM), required)
            supported = supported_schemas(source(PROGRAM)) if observed else set()
    except CatalogCompatibilityError:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, UpdateError):
        raise CatalogCompatibilityError('CE_CATALOG_PROGRAM_SCHEMA_UNPROVEN') from None
    require_supported(observed, supported)

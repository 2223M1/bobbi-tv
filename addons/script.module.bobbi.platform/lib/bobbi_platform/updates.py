"""Coordinated addon-only updates; no network, Kodi or signature primitive here.

The caller supplies a complete component inventory, signature verifier, bounded
downloader and an EXCLUSIVE runtime lease context manager. The lease MUST keep
Kodi/addon activity and other installers stopped for the entire commit/recovery,
not merely report an idle instant. No stock Kodi ownership claim is implied.
Callbacks: verify(raw_bytes, signature) -> exactly True; download(url, max_bytes)
-> bytes; is_idle() -> exactly True; commit_lease() -> context manager. Downloads
must enforce max_bytes while reading, begin at allowed_release_url, and follow
at most MAX_REDIRECTS redirects accepted by allowed_release_redirect. GitHub's
release-asset CDN uses signed query URLs; those are transport-only and must not
be logged/persisted. The engine cannot inspect an injected HTTP transport.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from urllib.parse import urlsplit
import uuid
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

MAX_MANIFEST = 256 * 1024
MAX_BACKUP_RECEIPT = 16 * 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILES = 10000
MAX_RATIO = 200
MAX_REDIRECTS = 3


class UpdateError(RuntimeError):
    pass


class Busy(UpdateError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpdateError('Duplicate JSON key')
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(UpdateError('Invalid JSON number')))
    except (ValueError, UnicodeError) as error:
        raise UpdateError('Invalid JSON') from error


def allowed_release_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.netloc == 'github.com'
                and not url.query and not url.fragment
                and re.fullmatch(r'/2223M1/bobbi-tv/releases/download/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.zip', url.path)
                is not None and all(part not in ('.', '..') for part in url.path.split('/')))
    except ValueError:
        return False


def allowed_release_redirect(value):
    """Transport-only redirect policy, never a manifest URL admission rule.

    Caller tracks the chain length, prohibits HTTPS downgrades, applies the same
    byte budget to the final response and revalidates every hop before fetching.
    Final content must still match the signed manifest's size and SHA256.
    """
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 33 for c in value):
        return False
    if allowed_release_url(value):
        return True
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.netloc in
                ('release-assets.githubusercontent.com', 'objects.githubusercontent.com')
                and not url.fragment and url.path.startswith('/') and bool(url.path.strip('/')))
    except ValueError:
        return False


def _component(value):
    return (isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,100}', value)
            and 'bobbi' in value.split('.'))


def _version(value):
    # Public releases use numeric triples; no ambiguous lexical version order.
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})', value):
        raise UpdateError('Version must be a canonical numeric triple')
    return tuple(int(part) for part in value.split('.'))


def _safe_path(path):
    path = Path(path).absolute()
    # Check before normalization (a/../b may traverse a link) and then compare
    # normalized roots. Reject Windows junctions/reparse points as well.
    for candidate in (path, Path(os.path.abspath(str(path)))):
        for item in (candidate, *candidate.parents):
            if item.is_symlink():
                raise UpdateError('Symlink update path')
            try:
                attributes = getattr(item.lstat(), 'st_file_attributes', 0)
            except FileNotFoundError:
                continue
            if attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                raise UpdateError('Reparse update path')
    return Path(os.path.abspath(str(path)))


def _sync_dir(path):
    # Windows does not support opening a directory for fsync through os.open.
    if os.name != 'nt':
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _atomic(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
        _sync_dir(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def archive_rows(archive, item):
    """Shared, read-only layout contract for extraction and space planning."""
    rows = archive.infolist()
    if len(rows) > MAX_FILES:
        raise UpdateError('Archive file budget exceeded')
    total, names = 0, set()
    for row in rows:
        name = row.filename
        parts = PurePosixPath(name).parts
        mode = row.external_attr >> 16
        key = name.rstrip('/').casefold()
        if (row.orig_filename != name or not name or '\\' in name or '\x00' in name or ':' in name
                or name.startswith('/') or any(part in ('', '.', '..') for part in name.rstrip('/').split('/'))
                or not parts or parts[0] != item['id'] or key in names
                or any(ord(c) < 32 for c in name) or row.flag_bits & 1
                or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
            raise UpdateError('Unsafe or duplicate archive path')
        if any(part.endswith(('.', ' ')) or part.split('.')[0].upper() in
               {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'} for part in parts):
            raise UpdateError('Nonportable archive path')
        names.add(key)
        total += row.file_size
        if (total > MAX_EXPANDED or row.file_size > MAX_EXPANDED
                or row.file_size > max(1, row.compress_size) * MAX_RATIO):
            raise UpdateError('Archive expansion budget exceeded')
    return rows


class _Lock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        _safe_path(self.path)
        self.stream = open(str(self.path), 'a+b')
        self.stream.seek(0, os.SEEK_END)
        if not self.stream.tell():
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise Busy('Another update is active') from error
        return self

    def __exit__(self, *_):
        if os.name == 'nt':
            import msvcrt
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()


class UpdateEngine:
    def __init__(self, addons_root, work_root, expected_components, channel, profile,
                 verify_signature, download, is_idle, commit_lease, offline=False,
                 retain_previous=False, managed_components=None, dependency_check=None):
        self.addons = _safe_path(addons_root)
        self.work = _safe_path(work_root)
        if (self.addons == self.work or self.addons in self.work.parents
                or self.work in self.addons.parents):
            raise UpdateError('Update work must be separate from addons')
        self.expected = frozenset(expected_components)
        self.managed = self.expected if managed_components is None else frozenset(managed_components)
        self.offline, self.retain_previous = bool(offline), bool(retain_previous)
        if self.managed != self.expected:
            from .upstream_addons import FULL_COMPONENTS, OWNED_COMPONENTS
            if (not self.offline or self.expected != FULL_COMPONENTS
                    or self.managed != OWNED_COMPONENTS or not callable(dependency_check)):
                raise UpdateError('Unreviewed partial component ownership')
        self.dependency_check = dependency_check
        component_check = (lambda item: isinstance(item, str) and
            re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,100}', item)) if offline else _component
        if not self.expected or any(not component_check(item) for item in self.expected):
            raise UpdateError('Explicit bobbi component inventory required')
        if (channel not in (('private-candidate', 'private-stable') if offline else ('preview', 'stable'))
                or profile not in ('kodi', 'android', 'coreelec', 'windows')):
            raise UpdateError('Unknown release channel or profile')
        self.channel, self.profile = channel, profile
        self.verify, self.download, self.idle, self.lease = verify_signature, download, is_idle, commit_lease
        self.addons.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        if self.addons.stat().st_dev != self.work.stat().st_dev:
            raise UpdateError('Staging and addons must share a filesystem')
        self.state_path, self.journal_path = self.work / 'state.json', self.work / 'journal.json'
        self.previous_path = self.work / 'previous.json'

    def _version(self, value):
        if not self.offline:
            return _version(value)
        # Kodi dependencies may carry +matrix.1. The signed generation is the
        # ordering authority; never reinterpret that suffix as a new channel.
        match = re.fullmatch(r'(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})(?:\.(0|[1-9][0-9]{0,8}))?(?:[+~-][A-Za-z0-9._-]{1,64})?',
                             value) if isinstance(value, str) else None
        if not match:
            raise UpdateError('Invalid Kodi component version')
        return tuple(int(part or 0) for part in match.groups())

    def _location(self, item):
        return item['file' if self.offline else 'url']

    def _location_allowed(self, item):
        if not self.offline:
            return allowed_release_url(item['url'])
        return item['file'] == item['id'] + '/' + item['id'] + '-' + item['version'] + '.zip'

    def _read(self, path, maximum=MAX_MANIFEST):
        _safe_path(path)
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > maximum:
            raise UpdateError('Invalid update metadata')
        return _json(path.read_bytes())

    def _state(self):
        value = self._read(self.state_path)
        if value is None:
            return {'sequence': 0, 'versions': {}}
        return self._checked_state(value)

    def _checked_state(self, value):
        if (not isinstance(value, dict) or set(value) != {'sequence', 'versions'}
                or type(value['sequence']) is not int or value['sequence'] < 0
                or not isinstance(value['versions'], dict)
                or (not set(value['versions']) <= self.expected if self.offline else
                    set(value['versions']) not in (set(), set(self.expected)))):
            raise UpdateError('Invalid installed release state')
        for name, version in value['versions'].items():
            if self.managed != self.expected and name not in self.managed:
                from .upstream_addons import kodi_version
                kodi_version(version)
            else:
                self._version(version)
        return value

    def _managed_state(self, state):
        return dict(sequence=state['sequence'],
                    versions={name: value for name, value in state['versions'].items() if name in self.managed})

    def _dependencies(self, stage):
        if self.dependency_check is not None:
            return self.dependency_check(self.addons, stage, self.managed)
        return {}

    def _idle(self):
        if self.idle() is not True:
            raise Busy('Playback or preparation is active')

    def _manifest(self, raw, signature, state):
        if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST:
            raise UpdateError('Bounded signed manifest bytes required')
        if self.verify(raw, signature) is not True:
            raise UpdateError('Signature rejected')
        value = _json(raw)
        if (not isinstance(value, dict) or set(value) != {'schema', 'channel', 'profile', 'sequence', 'components'}
                or type(value['schema']) is not int or value['schema'] != (2 if self.offline else 1)
                or value['channel'] != self.channel or value['profile'] != self.profile
                or type(value['sequence']) is not int or value['sequence'] <= state['sequence']
                or not isinstance(value['components'], list)
                or len(value['components']) != len(self.expected)):
            raise UpdateError('Release profile, schema or sequence rejected')
        found = set()
        for item in value['components']:
            if (not isinstance(item, dict) or set(item) != {'id', 'version', 'file' if self.offline else 'url', 'size', 'sha256'}
                    or not isinstance(item['id'], str) or item['id'] not in self.expected or item['id'] in found
                    or not isinstance(item['version'], str) or not self._location_allowed(item) or type(item['size']) is not int
                    or not 0 < item['size'] <= MAX_ARCHIVE or not isinstance(item['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', item['sha256'])):
                raise UpdateError('Invalid complete component manifest')
            version = self._version(item['version'])
            found.add(item['id'])
            if item['id'] not in self.managed:
                # Package bytes still undergo complete hash/archive validation;
                # their version does not own the independently installed addon.
                continue
            previous = state['versions'].get(item['id'])
            installed = self.addons / item['id']
            if installed.exists():
                actual_id, actual_version = self._addon(installed / 'addon.xml')
                if actual_id != item['id']:
                    raise UpdateError('Installed addon identity mismatch')
                if version < self._version(actual_version):
                    raise UpdateError('Installed version downgrade rejected')
            if previous is not None and version < self._version(previous):
                raise UpdateError('Release version downgrade rejected')
        if found != self.expected:
            raise UpdateError('Incomplete coordinated release')
        return value

    @staticmethod
    def _addon(path):
        _safe_path(path)
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise UpdateError('Missing or oversized addon.xml')
        raw = path.read_bytes()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise UpdateError('XML declarations rejected')
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as error:
            raise UpdateError('Malformed addon.xml') from error
        if root.tag != 'addon':
            raise UpdateError('Invalid addon.xml root')
        return root.get('id'), root.get('version')

    def _extract(self, data, item, stage):
        if (not isinstance(data, bytes) or len(data) != item['size']
                or hashlib.sha256(data).hexdigest() != item['sha256']):
            raise UpdateError('Archive size or SHA256 mismatch')
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                rows = archive_rows(archive, item)
                for row in rows:
                    target = stage.joinpath(*PurePosixPath(row.filename).parts)
                    if row.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(row) as source, open(str(target), 'xb') as output:
                            remaining = row.file_size
                            while remaining:
                                chunk = source.read(min(65536, remaining))
                                if not chunk:
                                    raise UpdateError('Truncated archive entry')
                                output.write(chunk)
                                remaining -= len(chunk)
                            if source.read(1):
                                raise UpdateError('Archive entry size changed')
                            output.flush()
                            os.fsync(output.fileno())
        except (zipfile.BadZipFile, RuntimeError, EOFError) as error:
            raise UpdateError('Invalid addon archive') from error
        if self._addon(stage / item['id'] / 'addon.xml') != (item['id'], item['version']):
            raise UpdateError('Archive addon ID or version mismatch')
        # File contents and directory entries must both survive a process crash
        # before a journal is allowed to name this staged release.
        for directory, _, _ in os.walk(str(stage / item['id']), topdown=False):
            _sync_dir(Path(directory))
        _sync_dir(stage)

    def _move(self, source, target):
        """Small fault-injection seam; all paths are engine-derived."""
        os.replace(str(source), str(target))
        _sync_dir(source.parent)
        if target.parent != source.parent:
            _sync_dir(target.parent)

    def _remove(self, path):
        _safe_path(path)
        if path.exists():
            # No followed links, including malicious installed addon children.
            if path.is_dir():
                shutil.rmtree(str(path))
            else:
                path.unlink()

    def _tree(self, root):
        """Exact, bounded program-only backup inventory; never traverses links."""
        result, size = {}, 0
        if not root.is_dir():
            raise UpdateError('Missing program backup')
        for folder, dirs, files in os.walk(str(root), followlinks=False):
            for name in dirs + files:
                item = _safe_path(Path(folder) / name)
                if item.is_file():
                    size += item.stat().st_size
                    if size > MAX_EXPANDED or len(result) >= MAX_FILES:
                        raise UpdateError('Program backup exceeds budget')
                    digest = hashlib.sha256()
                    with item.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(block)
                    result[item.relative_to(root).as_posix()] = digest.hexdigest()
        return result

    def _retain(self, journal, tx):
        old = self._read(self.previous_path, MAX_BACKUP_RECEIPT)
        digests = {name: self._tree(tx / 'backup' / name)
                   for name, existed in journal['entries'].items() if existed}
        receipt = dict(transaction=tx.name, entries=journal['entries'],
            state=journal['old_state'], current_sequence=self._state()['sequence'], digests=digests)
        self._receipt_budget(receipt)
        _atomic(self.previous_path, receipt)
        self._remove(tx / 'stage')
        if isinstance(old, dict) and old.get('transaction') != tx.name:
            previous_tx = old.get('transaction')
            if isinstance(previous_tx, str) and re.fullmatch('[0-9a-f]{32}', previous_tx):
                self._remove(self.work / previous_tx)

    def _preserved(self, tx):
        previous = self._read(self.previous_path, MAX_BACKUP_RECEIPT) if self.retain_previous else None
        return isinstance(previous, dict) and previous.get('transaction') == tx.name

    @staticmethod
    def _receipt_budget(receipt):
        # Backup hashes describe thousands of files, unlike a small signed
        # component manifest. Never write a receipt that our reader rejects.
        if len(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode('utf-8')) > MAX_BACKUP_RECEIPT:
            raise UpdateError('Program backup receipt exceeds budget')

    def _preflight_retention(self, journal, sequence):
        if self.retain_previous:
            digests = {name: self._tree(self.addons / name)
                for name, existed in journal['entries'].items() if existed}
            self._receipt_budget(dict(transaction=journal['transaction'], entries=journal['entries'],
                state=journal['old_state'], current_sequence=sequence, digests=digests))

    def _recover(self):
        journal = self._read(self.journal_path)
        if journal is None:
            return False
        if (self.managed != self.expected and isinstance(journal, dict)
                and isinstance(journal.get('entries'), dict)
                and set(journal['entries']) == self.expected):
            raise UpdateError('Legacy full-inventory journal requires its frozen controller recovery')
        if (not isinstance(journal, dict) or set(journal) != {'transaction', 'phase', 'entries', 'old_state'}
                or not isinstance(journal['transaction'], str)
                or not re.fullmatch('[0-9a-f]{32}', journal['transaction'])
                or journal['phase'] not in ('committing', 'committed')
                or not isinstance(journal['entries'], dict) or set(journal['entries']) != self.managed
                or any(type(value) is not bool for value in journal['entries'].values())
                or not isinstance(journal['old_state'], dict)):
            raise UpdateError('Invalid transaction journal; manual repair required')
        self._checked_state(journal['old_state'])
        if set(journal['old_state']['versions']) - self.managed:
            raise UpdateError('Transaction state exceeds managed inventory')
        tx = _safe_path(self.work / journal['transaction'])
        if journal['phase'] == 'committed':
            # The durable state is the commit point. Cleanup does not change
            # live addons and need not reacquire a runtime lease after success.
            self._state()
            if self.retain_previous:
                self._retain(journal, tx)
            else:
                self._remove(tx)
            self.journal_path.unlink()
            _sync_dir(self.work)
            return True
        if (not tx.is_dir() or not _safe_path(tx / 'stage').is_dir()
                or not _safe_path(tx / 'backup').is_dir()):
            raise UpdateError('Transaction staging or backups missing; manual repair required')
        self._idle()
        with self.lease():
            self._idle()
            if journal['phase'] == 'committing':
                for addon_id, existed in journal['entries'].items():
                    target = _safe_path(self.addons / addon_id)
                    backup = _safe_path(tx / 'backup' / addon_id)
                    staged = _safe_path(tx / 'stage' / addon_id)
                    if backup.exists():
                        self._remove(target)
                        self._move(backup, target)
                    elif not existed and not staged.exists():
                        self._remove(target)
                _atomic(self.state_path, journal['old_state'])
            self.journal_path.unlink()
            _sync_dir(self.work)
            self._remove(tx)
        return True

    def recover(self):
        """Must succeed before exposing update availability or loading addons."""
        with _Lock(self.work / 'update.lock'):
            return self._recover()

    def available(self):
        """Read local installed state only, after interrupted update recovery."""
        with _Lock(self.work / 'update.lock'):
            self._recover()
            return self._state()

    def apply(self, raw_manifest, signature):
        with _Lock(self.work / 'update.lock'):
            self._recover()
            state = self._state()
            manifest = self._manifest(raw_manifest, signature, state)
            self._idle()  # Before ANY download callback.
            tx = self.work / uuid.uuid4().hex
            stage, backup = tx / 'stage', tx / 'backup'
            stage.mkdir(parents=True)
            backup.mkdir()
            _sync_dir(tx)
            _sync_dir(self.work)
            try:
                for item in manifest['components']:
                    self._extract(self.download(self._location(item), item['size']), item, stage)
                self._dependencies(stage)
                with self.lease():
                    self._idle()  # Immediately before transaction publication/moves.
                    # Another installer may have run during downloads. Capture
                    # existence and recheck downgrade/identity under the lease.
                    for item in manifest['components']:
                        if item['id'] not in self.managed:
                            continue
                        installed = _safe_path(self.addons / item['id'])
                        if installed.exists():
                            actual_id, actual_version = self._addon(installed / 'addon.xml')
                            if actual_id != item['id'] or self._version(actual_version) > self._version(item['version']):
                                raise UpdateError('Installed addon changed during staging')
                    self._dependencies(stage)
                    if self.offline:
                        state = dict(state, versions={name: self._addon(self.addons / name / 'addon.xml')[1]
                            for name in sorted(self.managed) if (self.addons / name).exists()})
                    journal = {'transaction': tx.name, 'phase': 'committing',
                               'entries': {name: (self.addons / name).exists() for name in sorted(self.managed)},
                               'old_state': state}
                    self._preflight_retention(journal, manifest['sequence'])
                    _atomic(self.journal_path, journal)
                    for name, existed in journal['entries'].items():
                        if existed:
                            self._move(self.addons / name, backup / name)
                        self._move(stage / name, self.addons / name)
                    result = {'sequence': manifest['sequence'],
                              'versions': {item['id']: item['version'] for item in manifest['components']
                                           if item['id'] in self.managed}}
                    _atomic(self.state_path, result)
                    journal['phase'] = 'committed'
                    _atomic(self.journal_path, journal)
                self._recover()  # Finalize committed journal; never rollback success.
                return result
            except Exception:
                if self.journal_path.exists():
                    self._recover()
                raise
            finally:
                if not self.journal_path.exists() and not self._preserved(tx):
                    self._remove(tx)

    def rollback(self):
        """Explicit previous program generation only; sequence high-water stays."""
        if not self.retain_previous:
            raise UpdateError('Previous program retention is not enabled')
        with _Lock(self.work / 'update.lock'):
            self._recover()
            current = self._state()
            previous = self._read(self.previous_path, MAX_BACKUP_RECEIPT)
            if (not isinstance(previous, dict) or
                    set(previous) != {'transaction', 'entries', 'state', 'current_sequence', 'digests'} or
                    not isinstance(previous['transaction'], str) or
                    not re.fullmatch('[0-9a-f]{32}', previous['transaction']) or
                    previous['current_sequence'] != current['sequence'] or
                    not isinstance(previous['entries'], dict)
                    or set(previous['entries']) not in (set(self.managed), set(self.expected)) or
                    any(type(flag) is not bool for flag in previous['entries'].values()) or
                    not isinstance(previous['digests'], dict) or
                    set(previous['digests']) != {name for name, flag in previous['entries'].items() if flag}):
                raise UpdateError('Previous program generation unavailable')
            restored = self._checked_state(previous['state'])
            if set(restored['versions']) != set(previous['digests']):
                raise UpdateError('Previous component state mismatch')
            self._idle()
            tx = self.work / uuid.uuid4().hex
            stage, backup = tx / 'stage', tx / 'backup'
            stage.mkdir(parents=True)
            backup.mkdir()
            try:
                for name, expected in previous['digests'].items():
                    source = _safe_path(self.work / previous['transaction'] / 'backup' / name)
                    if self._tree(source) != expected:
                        raise UpdateError('Previous program integrity failed')
                    # Historical full receipts are verified in full, including
                    # upstream backups, but those files no longer grant writes.
                    if name not in self.managed:
                        continue
                    shutil.copytree(str(source), str(stage / name))
                    if self._tree(stage / name) != expected:
                        raise UpdateError('Previous staging integrity failed')
                    for relative in expected:
                        copied = stage / name / relative
                        mode = stat.S_IMODE(copied.stat().st_mode)
                        try:
                            if os.name == 'nt':
                                copied.chmod(mode | stat.S_IWUSR)
                            with copied.open('r+b' if os.name == 'nt' else 'rb') as stream:
                                os.fsync(stream.fileno())
                        finally:
                            if os.name == 'nt':
                                copied.chmod(mode)
                    for folder, _, _ in os.walk(str(stage / name), topdown=False):
                        _sync_dir(Path(folder))
                _sync_dir(stage)
                _sync_dir(tx)
                _sync_dir(self.work)
                self._dependencies(stage)
                with self.lease():
                    self._idle()
                    self._dependencies(stage)
                    journal = dict(transaction=tx.name, phase='committing',
                        entries={name: (self.addons / name).exists() for name in sorted(self.managed)},
                        old_state=self._managed_state(current))
                    self._preflight_retention(journal, current['sequence'])
                    _atomic(self.journal_path, journal)
                    for name, existed in journal['entries'].items():
                        if existed:
                            self._move(self.addons / name, backup / name)
                        if (stage / name).exists():
                            self._move(stage / name, self.addons / name)
                    # A deliberate rollback doesn't permit replaying old signed
                    # packages. A future update needs a higher release sequence.
                    result = dict(sequence=current['sequence'], versions=self._managed_state(restored)['versions'])
                    _atomic(self.state_path, result)
                    journal['phase'] = 'committed'
                    _atomic(self.journal_path, journal)
                self._recover()
                return result
            except Exception:
                if self.journal_path.exists():
                    self._recover()
                raise
            finally:
                if not self.journal_path.exists() and not self._preserved(tx):
                    self._remove(tx)

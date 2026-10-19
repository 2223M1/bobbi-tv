"""Local-only signed complete generations. No URL downloader or GitHub token."""
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

from .signatures import verify
from .updates import UpdateEngine, UpdateError, MAX_ARCHIVE, MAX_MANIFEST, _json, _safe_path

MAX_BUNDLE = 768 * 1024 * 1024
TRUST = Path(__file__).with_name('release_trust.json')


def load_trust(path=TRUST):
    path = _safe_path(path)
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST:
        raise UpdateError('Offline release trust unavailable')
    value = _json(path.read_bytes())
    if (not isinstance(value, dict) or set(value) != {'schema', 'key', 'components'} or
            value['schema'] != 1 or not isinstance(value['key'], dict) or
            not isinstance(value['components'], list) or not value['components'] or
            any(not isinstance(item, str) or not re.fullmatch('[a-z0-9][a-z0-9._-]{1,100}', item)
                for item in value['components']) or
            len(set(value['components'])) != len(value['components'])):
        raise UpdateError('Invalid offline trust configuration')
    return value


class SignedBundle:
    """Holds a single open archive throughout check/stage; no path substitution."""
    def __init__(self, path, trust, profile):
        self.path, self.trust, self.profile = _safe_path(path), trust, profile
        self.archive = None

    def __enter__(self):
        if not self.path.is_file() or self.path.stat().st_size > MAX_BUNDLE:
            raise UpdateError('Bounded local update file required')
        self.archive = zipfile.ZipFile(str(self.path))
        try:
            rows = self.archive.infolist()
            if len(rows) != len(self.trust['components']) + 2:
                raise UpdateError('Incomplete or extra offline package members')
            names, size = set(), 0
            for row in rows:
                mode = row.external_attr >> 16
                if (row.is_dir() or row.orig_filename != row.filename or row.filename in names or
                        row.filename.casefold() in {n.casefold() for n in names} or
                        '\\' in row.filename or ':' in row.filename or
                        row.filename.startswith('/') or
                        any(part in ('', '.', '..') for part in row.filename.split('/')) or
                        row.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or
                        row.file_size > MAX_ARCHIVE or
                        row.file_size > max(1, row.compress_size) * 200):
                    raise UpdateError('Unsafe offline package member')
                names.add(row.filename)
                size += row.file_size
            if size > MAX_BUNDLE or not {'release.json', 'release.sig'} <= names:
                raise UpdateError('Offline package budget or signature missing')
            if (self.archive.getinfo('release.json').file_size > MAX_MANIFEST or
                    self.archive.getinfo('release.sig').file_size > 1024):
                raise UpdateError('Oversized signed release metadata')
            self.raw = self.archive.read('release.json')
            self.signature = self.archive.read('release.sig').decode('ascii')
            if not verify(self.raw, self.signature, self.trust['key']):
                raise UpdateError('Offline release signature rejected')
            self.manifest = _json(self.raw)
            value = self.manifest
            if (not isinstance(value, dict) or
                    set(value) != {'schema', 'channel', 'profile', 'sequence', 'components'} or
                    value['schema'] != 2 or type(value['schema']) is not int or
                    value['channel'] not in ('private-candidate', 'private-stable') or
                    value['profile'] != self.profile or type(value['sequence']) is not int or
                    value['sequence'] < 1 or not isinstance(value['components'], list) or
                    len(value['components']) != len(self.trust['components'])):
                raise UpdateError('Offline release contract rejected')
            by_file, by_id = {}, set()
            for item in value['components']:
                if (not isinstance(item, dict) or set(item) != {'id', 'version', 'file', 'size', 'sha256'} or
                        not isinstance(item['id'], str) or item['id'] not in self.trust['components'] or
                        item['id'] in by_id or not isinstance(item['version'], str) or
                        not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[+~-][A-Za-z0-9._-]{1,64})?', item['version']) or
                        item['file'] != item['id'] + '/' + item['id'] + '-' + item['version'] + '.zip' or
                        type(item['size']) is not int or not 0 < item['size'] <= MAX_ARCHIVE or
                        not isinstance(item['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', item['sha256'])):
                    raise UpdateError('Invalid offline component')
                by_id.add(item['id'])
                by_file[item['file']] = item
            if names != set(by_file) | {'release.json', 'release.sig'}:
                raise UpdateError('Offline package membership differs from signature')
            self.by_file = by_file
            return self
        except BaseException:
            self.archive.close()
            self.archive = None
            raise

    def read(self, name, maximum):
        item = self.by_file.get(name)
        if item is None or item['size'] != maximum:
            raise UpdateError('Unlisted component read rejected')
        if self.archive.getinfo(name).file_size != maximum:
            raise UpdateError('Offline component length mismatch')
        raw = self.archive.read(name)
        if len(raw) != maximum or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise UpdateError('Offline component integrity failed')
        return raw

    def check_all(self):
        for name, item in self.by_file.items():
            self.read(name, item['size'])
        return self.manifest

    def engine(self, addons_root, work_root, is_idle, commit_lease):
        from .upstream_addons import managed_components, check_dependencies
        managed = managed_components(self.trust['components'])
        return UpdateEngine(addons_root, work_root, self.trust['components'],
            self.manifest['channel'], self.profile,
            lambda raw, sig: verify(raw, sig, self.trust['key']), self.read,
            is_idle, commit_lease, offline=True, retain_previous=True,
            managed_components=managed,
            dependency_check=check_dependencies if managed != frozenset(self.trust['components']) else None)

    def __exit__(self, *_):
        if self.archive is not None:
            self.archive.close()


def rollback_engine(trust, profile, addons_root, work_root, is_idle, commit_lease):
    from .upstream_addons import managed_components, check_dependencies
    managed = managed_components(trust['components'])
    return UpdateEngine(addons_root, work_root, trust['components'], 'private-candidate', profile,
        lambda *_: False, lambda *_: (_ for _ in ()).throw(UpdateError('Offline only')),
        is_idle, commit_lease, offline=True, retain_previous=True,
        managed_components=managed,
        dependency_check=check_dependencies if managed != frozenset(trust['components']) else None)

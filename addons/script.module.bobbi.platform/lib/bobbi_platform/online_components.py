"""Optional transport reuse; only a complete signed archive leaves this module.

No independently installed addons, discovery changes, accounts or new trust root.
Cold downloads seed a one-generation cache. Missing/unsupported component assets
fall back to the original full transfer, within the same overall deadline.
"""
import errno
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
import zipfile
import zlib

from . import online_updates as online
from .instance_lock import InstanceLock
from .offline_updates import MAX_BUNDLE, SignedBundle, signed_manifest, archive_info
from .updates import MAX_MANIFEST, UpdateError, _safe_path

METADATA_LIMIT = MAX_MANIFEST + 4096
CACHE_NAME = re.compile(r'[a-f0-9]{64}\.zip')
ERRORS = (UpdateError, OSError, ValueError, zipfile.BadZipFile, EOFError, zlib.error)


def component_name(row):
    return 'bobbi-component-' + row['sha256'] + '.zip'


def metadata_name(tag):
    online.release_url(tag)  # Same fixed release-tag grammar.
    return 'BobbiTV-' + tag.upper() + '.components-v1.zip'


def metadata(raw, trust):
    if len(raw) > METADATA_LIMIT:
        raise UpdateError('ONLINE_LENGTH_INVALID')
    with zipfile.ZipFile(BytesIO(raw)) as source:
        rows = source.infolist()
        if (len(rows) != 2 or {row.filename for row in rows} != {'release.json', 'release.sig'}
                or any(row.compress_type != zipfile.ZIP_STORED or row.flag_bits & 1
                       or row.file_size > (MAX_MANIFEST if row.filename == 'release.json' else 1024)
                       for row in rows)):
            raise UpdateError('ONLINE_COMPONENT_METADATA_INVALID')
        manifest_raw = source.read('release.json')
        signature_raw = source.read('release.sig')
    manifest, _ = signed_manifest(manifest_raw, signature_raw.decode('ascii'), trust, 'coreelec')
    return manifest_raw, signature_raw, manifest


def _regular(path):
    path = _safe_path(path)
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise UpdateError('ONLINE_CACHE_PATH_INVALID')
    return path


def digest(path, active):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            active()
            block = stream.read(128*1024)
            if not block:
                return result.hexdigest()
            result.update(block)


class ComponentCache:
    def __init__(self, work, active):
        self.work, self.active = _safe_path(work), active
        self.root = self.work/'components-v1'
        self.lease = InstanceLock(_safe_path(self.work.parent/'.bobbi-component-download.lock'))
        self.created = set()

    def __enter__(self):
        self.active()
        try:
            self.lease.acquire()
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise UpdateError('ONLINE_DOWNLOAD_BUSY') from None
            raise
        return self

    def __exit__(self, *_):
        self.lease.close()

    def prepare(self):
        _safe_path(self.root).mkdir(parents=True, exist_ok=True)
        _regular(self.root/'transfer.part').unlink(missing_ok=True)
        entries = self.entries()  # Check all path types before changing any blob.
        if sum(path.stat().st_size for path in entries) > MAX_BUNDLE:
            self.prune([])

    def entries(self):
        result = []
        # Only our fixed content-addressed namespace is owned by this cache.
        # Never traverse directories or collect installer recovery points.
        for path in self.root.iterdir():
            self.active()
            if CACHE_NAME.fullmatch(path.name):
                result.append(_regular(path))
            if len(result) > 256:
                raise UpdateError('ONLINE_COMPONENT_CACHE_LIMIT')
        return result

    def prune(self, rows):
        keep = {row['sha256']+'.zip' for row in rows}
        for path in self.entries():
            if path.name not in keep:
                path.unlink()

    def path(self, row):
        return _regular(self.root/(row['sha256']+'.zip'))

    def valid(self, row):
        path = self.path(row)
        if not path.exists():
            return False
        if path.stat().st_size == row['size'] and digest(path, self.active) == row['sha256']:
            return True
        path.unlink()
        return False

    def space(self, needed):
        if shutil.disk_usage(self.work).free < needed + 16*1024*1024:
            raise UpdateError('INSTALLATION_SPACE_REQUIRED')

    def put(self, row, receive):
        self.space(row['size'])
        temporary = _regular(self.root/'transfer.part')
        result, count = hashlib.sha256(), 0
        try:
            with temporary.open('xb') as stream:
                def consume(block):
                    nonlocal count
                    self.active()
                    count += len(block)
                    if count > row['size']:
                        raise UpdateError('ONLINE_LENGTH_INVALID')
                    stream.write(block)
                    result.update(block)
                receive(consume)
                self.active()
                if count != row['size'] or result.hexdigest() != row['sha256']:
                    raise UpdateError('ONLINE_COMPONENT_CONTENT_INVALID')
                stream.flush()
                os.fsync(stream.fileno())
            path = self.path(row)
            os.replace(temporary, path)
            self.created.add(path)
        finally:
            temporary.unlink(missing_ok=True)

    def seed(self, path, trust):
        with SignedBundle(path, trust, 'coreelec') as source:
            rows = source.manifest['components']
            self.prune(rows)
            for row in rows:
                self.active()
                if not self.valid(row):
                    self.put(row, lambda consume: consume(source.read(row['file'], row['size'])))

    def cancel(self):
        for path in self.created:
            _regular(path).unlink(missing_ok=True)

    def assemble(self, raw, signature, manifest, offer):
        self.space(offer['size'])
        fd, filename = tempfile.mkstemp(prefix='online-', suffix='.zip', dir=str(self.work))
        os.close(fd)
        path = Path(filename)
        try:
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as target:
                for name, content in [('release.json', raw), ('release.sig', signature)]:
                    target.writestr(archive_info(name), content)
                for row in manifest['components']:
                    info = archive_info(row['file'])
                    info.file_size = row['size']
                    with self.path(row).open('rb') as source, target.open(info, 'w') as dest:
                        remaining = row['size']
                        while remaining:
                            self.active()
                            block = source.read(min(128*1024, remaining))
                            if not block:
                                raise UpdateError('ONLINE_SHORT_READ')
                            dest.write(block)
                            remaining -= len(block)
            if path.stat().st_size != offer['size'] or digest(path, self.active) != offer['sha256']:
                raise UpdateError('ONLINE_CONTENT_INVALID')
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise


def _reuse(offer, cache, trust, cancelled, progress, deadline, report):
    # Optional discovery gets at most 15s; reuse gets at most 120s and leaves
    # time for the existing complete transfer. Neither resets the total budget.
    reuse_deadline = min(deadline, time.monotonic()+120)
    root = offer['url'].rsplit('/', 1)[0] + '/'
    chunks = []
    def receive(url, maximum, consume, expected=None, until=reuse_deadline, received=lambda _: None):
        def counted(block):
            report['downloaded_bytes'] += len(block)
            consume(block)
            received(len(block))
        online._transfer(url, maximum, counted, cancelled, lambda _: None,
                         expected=expected, deadline=until)
    receive(root+metadata_name(offer['tag']), METADATA_LIMIT, chunks.append,
            until=min(reuse_deadline, time.monotonic()+15))
    raw, signature, manifest = metadata(b''.join(chunks), trust)
    if manifest['sequence'] != offer['sequence']:
        raise UpdateError('ONLINE_GENERATION_MISMATCH')
    rows = manifest['components']
    cache.prune(rows)
    total = sum(row['size'] for row in rows)
    done = 0
    for row in rows:
        cache.active()
        if cache.valid(row):
            report['reused_bytes'] += row['size']
        else:
            inflight = 0
            def received(count):
                nonlocal inflight
                inflight += count
                progress(min(99, int(100*(done+inflight)/total)))
            cache.put(row, lambda consume: receive(root+component_name(row), row['size'], consume,
                                                  row['size'], received=received))
        done += row['size']
        progress(min(99, int(100*done/total)))
    return cache.assemble(raw, signature, manifest, offer)


def download(offer, work, trust, cancelled=lambda: False, progress=lambda _: None, report=None):
    """Product entry; the original download remains the complete-only fallback."""
    offer = online.parse_offer(json.dumps(offer))
    work = _safe_path(work)
    work.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic()+online.TRANSFER_SECONDS
    report = report if report is not None else {}
    report.update(mode='full', downloaded_bytes=0, reused_bytes=0, cache_bytes=0)
    selected = None
    def active():
        if cancelled():
            raise online.Cancelled('ONLINE_CANCELLED')
        if time.monotonic() >= deadline:
            raise UpdateError('ONLINE_TIMEOUT')
    with ComponentCache(work, active) as cache:
        usable = False
        try:
            try:
                cache.prepare()
                usable = True
                if cache.entries():
                    report['mode'] = 'components'
                    selected = _reuse(offer, cache, trust, cancelled, progress, deadline, report)
                    with SignedBundle(selected, trust, 'coreelec') as signed:
                        if signed.check_all()['sequence'] != offer['sequence']:
                            raise UpdateError('ONLINE_GENERATION_MISMATCH')
                    active()
            except online.Cancelled:
                raise
            except ERRORS as error:
                active()
                if selected is not None:
                    selected.unlink(missing_ok=True)
                    selected = None
                report['mode'] = 'full-fallback'
                report['fallback'] = type(error).__name__  # No URL or response body.
                report['reused_bytes'] = 0
            if selected is None:
                progress(0)
                # A cache must never consume the space needed by the fallback.
                # Only uninstalled transport blobs belong to this namespace.
                if usable and shutil.disk_usage(work).free < offer['size']+16*1024*1024:
                    try:
                        cache.prune([])
                    except online.Cancelled:
                        raise
                    except ERRORS:
                        active()
                full_report = {}
                selected = online.download(offer, work, trust, cancelled, progress,
                                           deadline=deadline, report=full_report)
                report['downloaded_bytes'] += full_report['downloaded_bytes']
                if usable:
                    try:
                        cache.seed(selected, trust)
                    except online.Cancelled:
                        raise
                    except ERRORS:
                        active()  # Cache is optional, installation is not.
                        report['cache_seed'] = 'unavailable'
            active()
            if usable:
                try:
                    report['cache_bytes'] = sum(path.stat().st_size for path in cache.entries())
                except online.Cancelled:
                    raise
                except ERRORS:
                    active()
                    report['cache_bytes'] = None
            progress(100)
            active()
            return selected
        except BaseException as error:
            if selected is not None:
                selected.unlink(missing_ok=True)
            if isinstance(error, online.Cancelled):
                cache.cancel()
            raise

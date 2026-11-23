"""One leased, bounded download checkpoint; never an installation authority.

Only a strong origin validator permits Range reuse. The full release digest,
signature and generation are still checked by the caller before delivery.
"""
import errno
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

from .instance_lock import InstanceLock
from .updates import UpdateError, _atomic, _json, _safe_path

CHECKPOINT_BYTES = 4 * 1024 * 1024


def strong_etag(value):
    return (isinstance(value, str) and len(value) <= 256
            and re.fullmatch(r'"[\x21\x23-\x7e]+"', value) is not None)


class PartialDownload:
    def __init__(self, work, offer, urls, active):
        self.work, self.offer, self.urls, self.active = work, offer, urls, active
        self.path = _safe_path(work/'online.partial')
        self.journal = _safe_path(work/'online-resume.json')
        # Stable lock inode outside downloads: never unlink a process lease.
        self.lease = InstanceLock(_safe_path(work.parent/'.bobbi-online-download.lock'))
        self.stream = None
        self.count = self.checkpoint_count = 0
        self.digest = hashlib.sha256()
        self.source = self.etag = ''
        self.request_offset = 0
        self.target = {key: offer[key] for key in ('tag','sequence','size','sha256')}

    def __enter__(self):
        self.active()
        try:
            self.lease.acquire()
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise UpdateError('ONLINE_DOWNLOAD_BUSY') from None
            raise
        try:
            for path in (self.path, self.journal):
                _safe_path(path)
                if path.exists():
                    info = path.stat()
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise UpdateError('ONLINE_CACHE_PATH_INVALID')
            self._load()
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *_):
        try:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
        finally:
            self.lease.close()

    def _load(self):
        saved = None
        if self.journal.is_file() and self.path.is_file():
            try:
                with self.journal.open('rb') as source:
                    saved = _json(source.read(4097))
                valid = (isinstance(saved, dict)
                    and set(saved) == {'schema','target','source','etag','count','prefix_sha256'}
                    and type(saved['schema']) is int and saved['schema'] == 1
                    and saved['target'] == self.target and saved['source'] in self.urls
                    and strong_etag(saved['etag']) and type(saved['count']) is int
                    and 0 < saved['count'] <= self.offer['size']
                    and saved['count'] <= self.path.stat().st_size <= self.offer['size']
                    and isinstance(saved['prefix_sha256'], str)
                    and re.fullmatch('[a-f0-9]{64}', saved['prefix_sha256']))
                if not valid:
                    saved = None
            except (ValueError, UpdateError):
                saved = None
        self.stream = self.path.open('r+b' if self.path.exists() else 'w+b')
        if saved:
            remaining = saved['count']
            while remaining:
                self.active()
                block = self.stream.read(min(128*1024, remaining))
                if not block:
                    break
                self.digest.update(block)
                remaining -= len(block)
            self.active()
            if not remaining and self.digest.hexdigest() == saved['prefix_sha256']:
                self.count = self.checkpoint_count = saved['count']
                self.source, self.etag = saved['source'], saved['etag']
                self.stream.truncate(self.count)  # Crash tail was never checkpointed.
                return
        self.reset()

    def reset(self, source='', etag=''):
        self.stream.seek(0)
        self.stream.truncate()
        self.journal.unlink(missing_ok=True)
        self.count = self.checkpoint_count = 0
        self.digest = hashlib.sha256()
        self.source, self.etag = source, etag if strong_etag(etag) else ''

    def request(self, url):
        self.request_url = url
        self.request_offset = self.count if url == self.source and self.etag else 0
        return ({'Range': 'bytes={}-'.format(self.request_offset), 'If-Range': self.etag}
                if self.request_offset else {})

    def response(self, response):
        if response.status == 200:
            self.reset(self.request_url, response.headers.get('ETag', ''))
            return 0
        if (response.status != 206 or not self.request_offset
                or response.headers.get('ETag') != self.etag
                or response.headers.get('Content-Range') != 'bytes {}-{}/{}'.format(
                    self.request_offset, self.offer['size']-1, self.offer['size'])):
            raise UpdateError('ONLINE_RANGE_INVALID')
        return self.request_offset

    def write(self, block):
        if self.count + len(block) > self.offer['size']:
            raise UpdateError('ONLINE_LENGTH_INVALID')
        if self.stream.write(block) != len(block):
            raise OSError('Online checkpoint write incomplete')
        self.digest.update(block)
        self.count += len(block)
        if self.etag and self.count-self.checkpoint_count >= CHECKPOINT_BYTES:
            self.checkpoint()

    def flush(self):
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def checkpoint(self):
        if not self.etag or not self.count:
            return False
        self.flush()
        _atomic(self.journal, dict(schema=1,target=self.target,source=self.source,
            etag=self.etag,count=self.count,prefix_sha256=self.digest.hexdigest()))
        self.checkpoint_count = self.count
        return True

    def discard(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self.path.unlink(missing_ok=True)
        self.journal.unlink(missing_ok=True)

    def deliver(self):
        """Give this caller a unique completed file, not the shared cache path."""
        self.flush()
        self.stream.close()
        self.stream = None
        fd, filename = tempfile.mkstemp(prefix='online-', suffix='.zip', dir=str(self.work))
        os.close(fd)
        destination = Path(filename)
        try:
            os.replace(self.path, destination)
            self.journal.unlink(missing_ok=True)
            return destination
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

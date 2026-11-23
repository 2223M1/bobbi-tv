"""Opt-in bounded discovery diagnostics, never a search decision.

No URLs, credentials, raw queries or response bodies. The marker expires in at
most 15 minutes; normal searches have only an inactive function call. Each
Kodi search interpreter owns one sink, shared by its existing worker threads.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from threading import Lock
import time

_sink = None
MAX_REPORTS = 8
MAX_BYTES = 256 * 1024
MAX_EVENTS = 128
STAGES = frozenset(('rss_parsed', 'catalog_input', 'catalog_kept', 'provider_return',
                    'processed', 'session_pool', 'ranked', 'visible'))
STATES = frozenset(('', 'cache', 'network', 'RUNNING', 'COMPLETE', 'PARTIAL',
                    'TIMEOUT', 'FAILED', 'CANCELLED'))


def _read(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Diagnostic file unavailable')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Diagnostic size limit')
    return raw


def _marker(directory):
    try:
        value = json.loads(_read(Path(directory)/'search-trace.json', 1024))
        now = time.time()
        if (type(value) is dict and set(value) == {'expires', 'hashes'}
                and type(value['expires']) in (int, float)
                and now < value['expires'] <= now + 900 and math.isfinite(value['expires'])
                and type(value['hashes']) is list and len(value['hashes']) <= 4
                and all(type(h) is str and re.fullmatch('[0-9a-f]{40}', h) for h in value['hashes'])):
            return value
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    return None


def reports(directory):
    """Only our bounded diagnostic files; never read Kodi logs or account files."""
    result = []
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        return result
    for index, path in enumerate(directory.iterdir()):
        if index >= 4096:
            raise ValueError('Diagnostic directory limit')
        if re.fullmatch(r'search-trace-[0-9a-f]{32}\.jsonl', path.name):
            if not path.is_symlink() and path.is_file():
                result.append(path)
    return sorted(result, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)[:MAX_REPORTS]


def enabled(directory):
    return _marker(directory) is not None


def set_enabled(directory, enabled):
    """User-requested recording, independent of global Kodi debug logging."""
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Diagnostic directory unavailable')
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory/'search-trace.json'
    if marker.is_symlink():
        raise ValueError('Diagnostic marker unavailable')
    if not enabled:
        marker.unlink(missing_ok=True)
        return
    if len(reports(directory)) >= MAX_REPORTS:
        raise ValueError('Diagnostic report limit')
    fd, temporary = tempfile.mkstemp(prefix='.search-trace-', dir=str(directory))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dict(expires=time.time()+900, hashes=[]), stream)
        os.replace(temporary, marker)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clear(directory):
    """Explicit user cleanup: disable first, remove only this recorder's files."""
    set_enabled(directory, False)
    for path in reports(directory):
        path.unlink()


def configure(directory, invocation):
    global _sink
    _sink = None
    try:
        directory = Path(directory)
        value = _marker(directory)
        if not value or type(invocation) is not str or not re.fullmatch('[0-9a-f]{32}', invocation):
            return
        # Reuse the existing nonblocking OS lock only to allocate a report.
        # This is a separate directory, never the provider admission lock.
        from .search_admission import try_acquire
        lease = try_acquire(directory/'search-trace-lock')
        if lease is None:
            return
        try:
            if len(reports(directory)) >= MAX_REPORTS or _marker(directory) != value:
                return
            target = directory/('search-trace-'+invocation+'.jsonl')
            with target.open('x', encoding='utf-8'):
                pass
            _sink = Trace(target, set(value['hashes']), value['expires'], invocation)
        finally:
            lease.release()
    except (OSError, ValueError, TypeError, KeyError):
        pass  # Optional diagnostics cannot change discovery.


class Trace:
    def __init__(self, path, hashes, expires, invocation):
        self.path, self.hashes, self.expires, self.invocation = path, hashes, expires, invocation
        self.lock, self.seen = Lock(), set()
        self.limited = False

    def _active(self):
        marker = _marker(self.path.parent)
        return (time.time() <= self.expires and marker is not None
                and marker['expires'] == self.expires and set(marker['hashes']) == self.hashes)

    def _write(self, record):
        signature = json.dumps(record, sort_keys=True, separators=(',', ':'))
        with self.lock:
            if not self._active() or signature in self.seen or self.limited:
                return
            line = json.dumps(dict(record, monotonic=time.monotonic()), separators=(',', ':'))+'\n'
            if self.path.is_symlink() or not self.path.is_file():
                return
            size = self.path.stat().st_size
            if (len(self.seen) >= MAX_EVENTS-1
                    or size + len(line.encode('utf-8')) + 100 > MAX_BYTES):
                self.limited = True
                line = '{"stage":"limit"}\n'
                if size + len(line.encode('utf-8')) > MAX_BYTES:
                    return
            self.seen.add(signature)
            # Never recreate a report removed by explicit user cleanup.
            with self.path.open('r+', encoding='utf-8') as stream:
                stream.seek(0, os.SEEK_END)
                stream.write(line)

    def record(self, stage, rows, state=''):
        if not self._active():
            return
        if stage not in STAGES or state not in STATES:
            return
        selected = []
        for row in rows[:4096]:
            info_hash = str(getattr(row, 'infoHash', '')).lower()
            if info_hash in self.hashes:
                selected.append(dict(info_hash=info_hash,
                    title_sha256=hashlib.sha256(str(getattr(row, 'title', '')).encode('utf-8')).hexdigest(),
                    type=str(getattr(row, 'type', '')) if str(getattr(row, 'type', '')) in ('Torrent', 'Direct') else 'other'))
        record = dict(invocation=self.invocation, stage=stage, state=state, count=len(rows),
                      omitted=max(0, len(rows)-4096), selected=selected[:16], selected_omitted=max(0,len(selected)-16))
        self._write(record)

    def providers(self, providers):
        from .search_completion import provider_diagnostics
        self._write(dict(invocation=self.invocation, stage='providers',
                         providers=provider_diagnostics(providers)))


def observe(stage, rows, state='', invocation=None):
    try:
        if _sink is not None and (invocation is None or invocation == _sink.invocation):
            _sink.record(stage, rows, state)
    except Exception:
        pass  # Diagnostic failures are not search failures.


def observe_providers(invocation, providers):
    try:
        if _sink is not None and invocation == _sink.invocation:
            _sink.providers(providers)
    except Exception:
        pass


def read_report(path):
    """Re-project even local files before preview/export; never export raw logs."""
    from .search_completion import provider_diagnostics
    path = Path(path)
    if not re.fullmatch(r'search-trace-[0-9a-f]{32}\.jsonl', path.name):
        raise ValueError('Diagnostic file unavailable')
    lines = _read(path, MAX_BYTES).splitlines()
    result = []
    incomplete = len(lines) >= MAX_EVENTS
    for line in lines[:MAX_EVENTS]:
        try:
            value = json.loads(line)
            if type(value) is not dict:
                raise ValueError('Invalid diagnostic row')
            stage = value.get('stage')
            if stage == 'providers' and type(value.get('providers')) is list:
                providers = {}
                for item in value['providers'][:40]:
                    if type(item) is not dict or type(item.get('provider')) is not str:
                        continue
                    ordinal = item.get('ordinal')
                    if type(ordinal) is not int or not 0 <= ordinal < 1000:
                        continue
                    providers[item['provider']+':'+str(ordinal)] = item
                result.append(dict(stage='providers', providers=provider_diagnostics(providers)))
            elif type(stage) is str and stage in STAGES and value.get('state', '') in STATES:
                count, omitted = value.get('count'), value.get('omitted', 0)
                if any(type(n) is not int or not 0 <= n <= 10000000 for n in (count, omitted)):
                    raise ValueError('Invalid diagnostic count')
                result.append(dict(stage=stage, state=value.get('state', ''), count=count, omitted=omitted))
            else:
                incomplete = True
        except (ValueError, TypeError, RecursionError):
            incomplete = True
    return dict(schema=1, incomplete=incomplete, events=result)

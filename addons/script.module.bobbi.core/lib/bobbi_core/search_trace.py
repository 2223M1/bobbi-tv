"""Opt-in bounded selected-hash discovery diagnostics, never a search decision.

No URLs, credentials, raw queries or response bodies. The marker expires in at
most 15 minutes; normal searches have only an inactive function call. Each
Kodi search interpreter owns one sink, shared by its existing worker threads.
"""
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
import time

_sink = None


def configure(directory, invocation):
    global _sink
    _sink = None
    try:
        directory = Path(directory)
        marker = directory/'search-trace.json'
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 1024:
            return
        value = json.loads(marker.read_text(encoding='utf-8'))
        if (set(value) != {'expires', 'hashes'} or type(value['expires']) not in (int, float)
                or not time.time() < value['expires'] <= time.time()+900
                or type(value['hashes']) is not list or not 1 <= len(value['hashes']) <= 4
                or any(type(h) is not str or not re.fullmatch('[0-9a-f]{40}', h) for h in value['hashes'])
                or not re.fullmatch('[0-9a-f]{32}', invocation)):
            return
        target = directory/('search-trace-'+invocation+'.jsonl')
        with target.open('x', encoding='utf-8'):
            pass
        _sink = Trace(target, set(value['hashes']), value['expires'], invocation)
    except (OSError, ValueError, TypeError, KeyError):
        pass  # Optional diagnostics cannot change discovery.


class Trace:
    def __init__(self, path, hashes, expires, invocation):
        self.path, self.hashes, self.expires, self.invocation = path, hashes, expires, invocation
        self.lock, self.seen = Lock(), set()

    def record(self, stage, rows, state=''):
        if time.time() > self.expires:
            return
        if not re.fullmatch('[a-z_]{1,40}', stage) or state not in (
                '', 'cache', 'network', 'RUNNING', 'COMPLETE', 'PARTIAL', 'TIMEOUT', 'FAILED', 'CANCELLED'):
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
        signature = json.dumps(record, sort_keys=True, separators=(',', ':'))
        with self.lock:
            if signature in self.seen or len(self.seen) >= 128:
                return
            self.seen.add(signature)
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(record, monotonic=time.monotonic()), separators=(',', ':'))+'\n')


def observe(stage, rows, state=''):
    try:
        if _sink is not None:
            _sink.record(stage, rows, state)
    except Exception:
        pass  # Diagnostic failures are not search failures.

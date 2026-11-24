"""Small profile-bound outbox. Only typed events leave Bobbi; never read kodi.log."""
from contextlib import closing, contextmanager
import gzip
import http.client
import json
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4

FILE = 'optimization-v1.sqlite3'
HOST = 'bobbi-diagnostics.feixingwawa.cn'
STAGES = {'emby_browse', 'emby_play', 'install', 'update', 'rollback'}
OUTCOMES = {'ok', 'handoff', 'failed', 'auth', 'unavailable', 'space', 'changed', 'unsupported'}
BUCKETS = (0, 1, 2, 5, 15, 60, 120)
LIMIT, AGE = 100, 7 * 86400


@contextmanager
def transaction(root):
    path = Path(root) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=.15)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS preference (slot INTEGER PRIMARY KEY, enabled INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS pending (id TEXT UNIQUE, created INTEGER, due INTEGER, attempts INTEGER, '
                   'build TEXT, stage TEXT, outcome TEXT, elapsed INTEGER)')
        yield db


def status(root):
    with transaction(root) as db:
        db.execute('DELETE FROM pending WHERE created < ?', (int(time.time()) - AGE,))
        on = db.execute('SELECT enabled FROM preference WHERE slot=1').fetchone()
        return (on is None or on == (1,)), db.execute('SELECT COUNT(*) FROM pending').fetchone()[0]


def set_enabled(root, enabled):
    if type(enabled) is not bool:
        raise ValueError('DIAGNOSTICS_SETTING')
    with transaction(root) as db:
        db.execute('INSERT OR REPLACE INTO preference VALUES(1,?)', (int(enabled),))
        if not enabled:
            db.execute('DELETE FROM pending')


def valid(e):
    return (re.fullmatch(r'[0-9a-f]{32}', e['id']) and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4}', e['build'])
            and e['stage'] in STAGES and e['outcome'] in OUTCOMES and type(e['elapsed']) is int and e['elapsed'] in BUCKETS)


def record(root, build, stage, outcome, seconds):
    now = int(time.time())
    elapsed = next((n for n in BUCKETS if n >= seconds), BUCKETS[-1])
    e = dict(id=uuid4().hex, build=build, stage=stage, outcome=outcome, elapsed=elapsed)
    if not valid(e):
        raise ValueError('DIAGNOSTICS_EVENT')
    with transaction(root) as db:
        if db.execute('SELECT enabled FROM preference WHERE slot=1').fetchone() not in (None, (1,)):
            return
        db.execute('DELETE FROM pending WHERE created < ?', (now-AGE,))
        db.execute('INSERT INTO pending VALUES(?,?,?,0,?,?,?,?)',
                   (e['id'], now, now, build, stage, outcome, elapsed))
        db.execute('DELETE FROM pending WHERE rowid NOT IN (SELECT rowid FROM pending ORDER BY rowid DESC LIMIT ?)', (LIMIT,))


def _component_version(component: str) -> str:
    try:
        from xbmcaddon import Addon
        return Addon(component).getAddonInfo('version')
    except Exception:
        import xml.etree.ElementTree as ET
        here = Path(__file__).resolve()
        # Fallback for headless Host/CI where xbmcaddon C++ bridge is absent
        for parent in here.parents:
            candidate = parent / 'addon.xml'
            if candidate.is_file() and parent.name == component:
                return ET.parse(candidate).getroot().get('version') or '0.0.0'
            sibling = parent / component / 'addon.xml'
            if sibling.is_file():
                return ET.parse(sibling).getroot().get('version') or '0.0.0'
        raise


def observe(root, stage, outcome, started):
    try:
        component = 'script.bobbi.start' if stage in ('install','update','rollback') else 'script.module.bobbi.platform'
        record(root, _component_version(component),
               stage, outcome, max(0.0, time.monotonic()-started))
    except Exception:
        pass  # Diagnostics never affect installation, directory results or native handoff.


def send(event):
    body = gzip.compress(json.dumps(event, separators=(',', ':')).encode(), mtime=0)
    with closing(http.client.HTTPSConnection(HOST, timeout=3)) as connection:
        connection.request('POST', '/v1/diagnostics', body=body, headers={
            'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
        with connection.getresponse() as response:
            return response.status == 200 and json.loads(response.read(129)) == {'ack':event['id']}


def flush_one(root, current, transport=send):
    """Reserve one attempt, release DB before HTTP. Opt-out cancels queued retries."""
    if not current() or not (Path(root) / FILE).is_file():
        return
    try:
        now = int(time.time())
        with transaction(root) as db:
            db.execute('DELETE FROM pending WHERE created < ?', (now-AGE,))
            if db.execute('SELECT enabled FROM preference WHERE slot=1').fetchone() not in (None, (1,)):
                return
            row = db.execute('SELECT id,build,stage,outcome,elapsed,attempts FROM pending WHERE due<=? '
                             'ORDER BY rowid LIMIT 1', (now,)).fetchone()
            if not row:
                return
            e = dict(zip(('id','build','stage','outcome','elapsed'), row[:5]), v=1)
            if not valid(e):
                db.execute('DELETE FROM pending WHERE id=?', (row[0],))
                return
            delay = min(21600, 60 * 2**min(row[5], 9))
            db.execute('UPDATE pending SET due=?,attempts=attempts+1 WHERE id=?', (now+delay, row[0]))
        # A disable during an in-flight HTTP call cannot recall that call. Queued
        # rows are erased atomically; toggling back on cannot revive old retries.
        with transaction(root) as db:
            present = db.execute('SELECT 1 FROM pending WHERE id=?', (row[0],)).fetchone()
        if present and current() and transport(e):
            with transaction(root) as db:
                db.execute('DELETE FROM pending WHERE id=?', (row[0],))
    except (OSError, http.client.HTTPException, sqlite3.Error, TypeError, ValueError, RuntimeError):
        return

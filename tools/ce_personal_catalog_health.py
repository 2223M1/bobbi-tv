"""Bounded, read-only personal-catalog inventory; no constructors or source I/O.

This is deliberately separate from ce_catalog_health's public TMDb search.
SQLite mode=ro includes committed WAL data; immutable=1 would hide that data.
No checkpoint, migration, account refresh, listing or playback is performed.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import time

MAX_ROWS = 2000
CATALOG_TABLES = ('objects', 'typed_objects', 'typed_observations', 'memberships',
                  'reviews', 'scans', 'file_supplements', 'file_segments', 'segment_changes')
KINDS = ('mounted_path', 'local_path', 'network_path')
STATES = ('queued', 'running', 'completed', 'canceled', 'interrupted', 'failed')


def _count(db, table):
    # Table names come only from the module's fixed allowlist, never a row.
    count = db.execute('SELECT count(*) FROM (SELECT 1 FROM ' + table + ' LIMIT ?)',
                       (MAX_ROWS + 1,)).fetchone()[0]
    return dict(count=min(count, MAX_ROWS), exact=count <= MAX_ROWS)


def _database(path, kind, deadline):
    from bobbi_platform import catalog_compatibility as guard
    path = guard._plain(path)
    for suffix in ('-wal', '-shm', '-journal'):
        guard._plain(Path(str(path) + suffix))
    if not path.exists():
        return dict(state='absent')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.15)) as db:
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        db.execute('BEGIN')  # One read snapshot, never BEGIN IMMEDIATE.
        version = db.execute('PRAGMA user_version').fetchone()[0]
        result = dict(state='observed', schema=version,
            wal_present=Path(str(path) + '-wal').exists(), counts={})
        wanted = CATALOG_TABLES if kind == 'catalog' else ('sources', 'metadata', 'pan_directories')
        tables = dict(db.execute('SELECT name,type FROM sqlite_master WHERE name IN (' +
            ','.join('?' for _ in wanted) + ')', wanted).fetchall())
        result['missing_tables'] = [name for name in wanted if tables.get(name) != 'table']
        for name in wanted:
            if tables.get(name) == 'table':
                result['counts'][name] = _count(db, name)
        if kind == 'catalog':
            if version not in (1, 2, 3, 4):
                result['state'] = 'unknown_schema'
            elif version == 4 and result['missing_tables']:
                result['state'] = 'incomplete_schema'
            if tables.get('typed_objects') == 'table':
                lanes = dict.fromkeys(KINDS + ('unknown_or_invalid',), 0)
                for raw, size in db.execute('SELECT substr(ref,1,8192),length(ref) FROM typed_objects LIMIT ?', (MAX_ROWS,)):
                    try:
                        value = json.loads(raw) if type(size) is int and size <= 8192 else None
                        lane = value.get('reference_kind') if type(value) is dict else None
                    except (ValueError, TypeError):
                        lane = None
                    lanes[lane if lane in KINDS else 'unknown_or_invalid'] += 1
                result['typed_lanes_sample'] = lanes
                if lanes['unknown_or_invalid']:
                    result['state'] = 'invalid_rows_observed'
            if tables.get('scans') == 'table':
                states = dict.fromkeys(STATES + ('unknown',), 0)
                for state, in db.execute('SELECT state FROM scans LIMIT ?', (MAX_ROWS,)):
                    states[state if state in STATES else 'unknown'] += 1
                result['scan_states_sample'] = states
        elif version != 1:
            result['state'] = 'unknown_schema'
        elif tables.get('sources') == tables.get('metadata') == 'table':
            revisions = dict(valid=0, missing_legacy=0, invalid=0)
            # Do not read source JSON: it contains locations and credentials.
            rows = db.execute("SELECT typeof(m.value),length(m.value),m.value GLOB '*[^0-9a-f]*' "
                "FROM sources s LEFT JOIN metadata m ON m.key='source_revision:'||s.id LIMIT ?", (MAX_ROWS,))
            for value_type, length, invalid in rows:
                key = 'missing_legacy' if value_type == 'null' else (
                    'valid' if value_type == 'text' and length == 64 and invalid == 0 else 'invalid')
                revisions[key] += 1
            result['source_revisions_sample'] = revisions
            if revisions['invalid']:
                result['state'] = 'invalid_rows_observed'
        elif any(tables.get(name) != 'table' for name in ('sources', 'metadata')):
            result['state'] = 'incomplete_schema'
        return result


def inspect_catalog(userdata, program_root=None, seconds=5):
    from bobbi_platform import catalog_compatibility as guard
    if type(seconds) not in (int, float) or not 0 < seconds <= 10:
        raise ValueError('CATALOG_PROBE_BUDGET')
    deadline = time.monotonic() + seconds
    result = dict(schema=1, operation='personal_catalog_health', mode='readonly', profiles=[],
        state='observed', row_budget_per_table=MAX_ROWS, mutation_performed=False,
        qualification='Read snapshots and bounded counts, not a full integrity check or protocol certification. '
            'Committed WAL is included; no checkpoint or migration. Missing legacy revisions are not initialized. '
            'No source names, refs, paths, locations, account IDs or credentials are exported.')
    try:
        roots = guard.profile_roots(Path(userdata).absolute())
        supported = guard.program_schemas(Path(program_root).absolute()) if program_root else None
        result['program_supported_schemas'] = sorted(supported) if supported is not None else None
    except (OSError, ValueError):
        result.update(state='unavailable', reason='PROFILE_OR_PROGRAM_UNPROVEN')
        return result
    for number, root in enumerate(roots, 1):
        row = dict(profile=number, master=root == Path(userdata).absolute())
        for key, name in (('catalog', 'media-index.sqlite3'), ('registry', 'libraries.sqlite3')):
            if time.monotonic() >= deadline:
                row[key] = dict(state='unavailable', reason='PROBE_BUDGET')
                continue
            try:
                path = root / 'addon_data/script.module.bobbi.platform' / name
                row[key] = _database(path, key, deadline)
                if key == 'catalog' and row[key]['state'] != 'absent':
                    row[key]['program_compatible'] = (row[key]['schema'] in supported
                        if supported is not None else None)
            except (OSError, ValueError, sqlite3.Error):
                row[key] = dict(state='unavailable', reason='DATABASE_UNREADABLE_OR_BUDGET')
        result['profiles'].append(row)
    if any(row[key]['state'] not in ('observed', 'absent')
           or row[key].get('program_compatible') is False
           for row in result['profiles'] for key in ('catalog', 'registry')):
        result['state'] = 'attention_required'
    return result


def remote_code():
    source = Path(__file__).read_text(encoding='utf-8')
    return ('import sys,json\nsys.dont_write_bytecode=True\n'
        "sys.path.insert(0,'/storage/.kodi/addons/script.module.bobbi.platform/lib')\n"
        "namespace={'__name__':'ce_personal_catalog_health'}\nexec(compile(" + repr(source) +
        ",'ce-personal-catalog-health','exec'),namespace)\n"
        "print(json.dumps(namespace['inspect_catalog']('/storage/.kodi/userdata',"
        "'/storage/.kodi/addons/script.module.bobbi.core')))\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument('--userdata', type=Path, help='Offline fixture or explicitly supplied local profile root')
    origin.add_argument('--transport-source', type=Path, help='Existing CE transport; reads only')
    parser.add_argument('--program-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Keep earlier evidence')
    if args.transport_source:
        import probe_ce_candidate as transport
        transport.REMOTE = remote_code()
        transport.run(args.transport_source, args.output)
        if json.loads(args.output.read_text(encoding='utf-8')).get('state') != 'observed':
            raise SystemExit(2)
        return
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.platform/lib'))
    value = inspect_catalog(args.userdata, args.program_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps(value))
    if value['state'] != 'observed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()

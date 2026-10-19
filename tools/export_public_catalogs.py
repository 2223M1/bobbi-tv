"""One-time clean catalogue reconstruction. Never copies source DB pages."""
import argparse
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = {
    'entries': 'id INTEGER PRIMARY KEY, group_key TEXT, origin TEXT, text TEXT, norm TEXT',
    'shares': 'cell TEXT PRIMARY KEY, group_key TEXT, code TEXT, password TEXT',
    'terms': 'term TEXT, entry_id INTEGER, PRIMARY KEY(term,entry_id)',
    'term_counts': 'term TEXT PRIMARY KEY,n INTEGER',
    'share_status': 'cell TEXT PRIMARY KEY, enabled INTEGER NOT NULL CHECK(enabled IN (0,1))',
}
COLUMNS = {
    'entries': 'id,group_key,origin,text,norm', 'shares': 'cell,group_key,code,password',
    'terms': 'term,entry_id', 'term_counts': 'term,n', 'share_status': 'cell,enabled',
}


def rebuild(source, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Refusing to overwrite an existing catalogue')
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True) as old, \
            sqlite3.connect(str(destination)) as new:
        for table, schema in SCHEMA.items():
            new.execute('CREATE TABLE ' + table + '(' + schema + ')')
            columns = COLUMNS[table]
            rows = old.execute('SELECT ' + columns + ' FROM ' + table)
            count = 0
            for row in rows:
                if table == 'shares' and (not re.fullmatch('[a-z0-9]{6,32}', row[2])
                        or not re.fullmatch('[a-zA-Z0-9]{0,16}', row[3])):
                    raise ValueError('Non-public share data')
                if any(isinstance(value, str) and re.search(r'(?i)(?:SEID|CID|UID)=|Bearer\s|-----BEGIN.*PRIVATE KEY', value)
                       for value in row):
                    raise ValueError('Account material in catalogue')
                new.execute('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in row) + ')', row)
                count += 1
            counts[table] = count
        new.execute('CREATE INDEX shares_group ON shares(group_key)')
        new.commit()
        assert new.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    return counts


def mdsub(source, destination):
    data = json.loads(Path(source).read_text(encoding='utf-8'))
    fields = ('path', 'kind', 'tmdb_id', 'size', 'work', 'evidence', 'season', 'episodes')
    result = dict(schema=1, catalog_date=data['catalog_date'], files=[
        {key: row[key] for key in fields if key in row} for row in data['files']])
    import sys
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.mdsub/lib'))
    from bobbi_mdsub.catalog import validate
    validate(result)
    target = Path(destination)
    if target.exists():
        raise ValueError('Refusing to overwrite existing catalogue')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return len(result['files'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    args = parser.parse_args()
    print(rebuild(args.baseline / 'script.module.am6b.qqdocs/resources/catalog.sqlite3',
        ROOT / 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3'))
    print('MDsub files:', mdsub(args.baseline / 'script.module.am6b.mdsub/resources/catalog.json',
        ROOT / 'addons/script.module.bobbi.mdsub/resources/catalog.json'))

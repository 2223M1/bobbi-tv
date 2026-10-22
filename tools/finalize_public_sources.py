"""Mechanical public metadata normalization, never runtime profiles."""
import ast
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Remove inherited application credentials. They are not claimed to be the
    # user's secrets, but a public fork should not impersonate another app.
    rules = {
        'lib/clients/anilist.py': [(r'(get_setting\("anilist_client_secret",\s*)"[^"\n]+"', r'\1""')],
        'lib/api/tvdbapi/tvdbapi.py': [(r'("apikey"\s*:\s*)"[^"\n]+"', r'\1""')],
        'lib/api/fanart/fanart.py': [(r'(CLIENT_KEY\s*=\s*)"[^"\n]+"', r'\1""')],
        'lib/services/migrations.py': [(r'(DEFAULT_SECRET\s*=\s*)"[^"\n]+"', r'\1""')],
        'lib/api/nuvio.py': [(r'(PUBLISHABLE_KEY\s*=\s*)"[^"\n]+"', r'\1""')],
    }
    for name, replacements in rules.items():
        path = ROOT / 'addons/plugin.video.bobbi' / name
        value = path.read_text(encoding='utf-8')
        for pattern, replacement in replacements:
            value = re.sub(pattern, replacement, value)
        ast.parse(value)
        path.write_text(value, encoding='utf-8')
    # Our generated terms table is huge with a duplicate rowid index. Compact
    # it without changing any rows, then vacuum the already-clean public DB.
    database = ROOT / 'addons/script.module.bobbi.catalog/resources/catalog.sqlite3'
    with sqlite3.connect(str(database)) as db:
        schema = db.execute("SELECT sql FROM sqlite_master WHERE name='terms'").fetchone()[0]
        if 'WITHOUT ROWID' not in schema:
            db.execute('CREATE TABLE terms_compact(term TEXT,entry_id INTEGER,PRIMARY KEY(term,entry_id)) WITHOUT ROWID')
            db.execute('INSERT INTO terms_compact SELECT term,entry_id FROM terms')
            assert db.execute('SELECT count(*) FROM terms_compact').fetchone() == db.execute('SELECT count(*) FROM terms').fetchone()
            db.execute('DROP TABLE terms')
            db.execute('ALTER TABLE terms_compact RENAME TO terms')
            db.commit()
            db.execute('VACUUM')
    print('Public defaults normalized; clean catalogue compacted')


if __name__ == '__main__':
    main()

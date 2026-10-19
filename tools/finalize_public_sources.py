"""Mechanical public metadata/notice normalization, never runtime profiles."""
import ast
import json
from pathlib import Path
import re
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
MIT = '''MIT License

Copyright (c) {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''


def main():
    for addon in ('script.module.bobbi.catalog', 'script.module.bobbi.mdsub'):
        (ROOT / 'addons' / addon / 'LICENSE').write_text(MIT.format(author='AM6B / bobbi TV contributors'), encoding='utf-8')
    for addon in ('script.bobbi.start', 'repository.bobbi'):
        shutil.copyfile(ROOT / 'LICENSE', ROOT / 'addons' / addon / 'LICENSE')
    target = ROOT / 'addons/plugin.video.bobbi/lib/api/tmdbv3api'
    (target / 'LICENSE-MIT-supplement.txt').write_text(
        'Notice supplement by bobbi TV: upstream setup.py explicitly declares MIT and names Anthony Bloomer.\n'
        'The upstream 1.9.0 tag/wheel omit a standalone license file. The standard text below is supplied\n'
        'for clarity, not represented as a recovered upstream file or new grant on upstream behalf.\n'
        'Metadata evidence is retained alongside this supplement. Local adaptations preserve that declaration.\n\n'
        + MIT.format(author='Anthony Bloomer and tmdbv3api contributors'), encoding='utf-8')
    shutil.copyfile(ROOT / 'licenses/vendor/tmdbv3api-1.9.0-setup-evidence.txt', target / 'UPSTREAM-SETUP-LICENSE-EVIDENCE.txt')
    for path in (ROOT / 'licenses/vendor').glob('*.txt'):
        destination = ROOT / 'addons/plugin.video.bobbi/licenses' / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
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
    print('Public notices/defaults normalized; clean catalogue compacted')


if __name__ == '__main__':
    main()

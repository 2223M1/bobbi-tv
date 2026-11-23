"""Backed, additive extension install for the existing single-owner ledger."""
import hashlib
import shutil
import sqlite3
from uuid import uuid4


def install_extension(ledger, key, version, definitions):
    db = ledger.db
    current = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    present = {name: db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
               for name in definitions}
    if current:
        if current[0] != str(version) or any(not present[name]
                or ' '.join(present[name][0].split()) != ' '.join(sql.split()) for name, sql in definitions.items()):
            raise ValueError('Unknown or incomplete ledger extension; no automatic repair')
        return None
    if any(present.values()):
        raise ValueError('Unversioned extension tables; preserve existing data')
    size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    if size > 128 * 1024 * 1024 or shutil.disk_usage(ledger.path.parent).free < size * 2 + 128 * 1024 * 1024:
        raise ValueError('Ledger extension backup capacity gate')
    backup = ledger.path.with_name(ledger.path.name + '.pre-extension-' + uuid4().hex)
    saved = sqlite3.connect(str(backup))
    try:
        db.backup(saved)
        if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Extension backup integrity failed')
    finally:
        saved.close()
    sha = hashlib.sha256()
    with backup.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            sha.update(chunk)
    with ledger.transaction():
        for sql in definitions.values():
            db.execute(sql)
        db.execute('INSERT INTO settings VALUES(?,?)', (key, str(version)))
        ledger._audit('extension_installed', None, dict(key=key, version=version,
                      backup_name=backup.name, sha256=sha.hexdigest()))
    return backup

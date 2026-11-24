"""Existing CE installs share program code, but not every profile's configured sources."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import zipfile

import pytest
from bobbi_platform import catalog_compatibility as guard


def fixture(userdata, records, *, other=False):
    userdata.mkdir(parents=True, exist_ok=True)
    root = userdata
    if other:
        (userdata / 'profiles.xml').write_text('<profiles><profile><directory>profiles/Two</directory></profile></profiles>')
        root = userdata / 'profiles/Two'
    path = root / 'addon_data' / guard.REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = sqlite3.connect(path)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute('PRAGMA wal_autocheckpoint=0')
    writer.execute('PRAGMA user_version=1')
    writer.execute('CREATE TABLE sources(id TEXT PRIMARY KEY, record TEXT NOT NULL)')
    for idx, row in enumerate(records):
        writer.execute('INSERT INTO sources VALUES(?,?)', (str(idx), json.dumps(row)))
    writer.commit()
    return writer, path


def program(root, raw):
    path = root / guard.REGISTRY_PROGRAM
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def package(raw):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr(guard.CORE + '/' + guard.REGISTRY_PROGRAM, raw)
    return SimpleNamespace(manifest={'components': [{'id':guard.CORE, 'file':'component.zip','size':len(data.getvalue())}]},
                           read=lambda *_:data.getvalue())


@pytest.mark.parametrize('records,required',[
    ([{'kind':'t4'}], {'t4'}),
    ([{'kind':'media_server','metadata':{'provider':'emby'}}]*2, {'multi_emby'}),
    ([{'kind':'t4'}] + [{'kind':'media_server','metadata':{'provider':'emby'}}]*2, {'t4','multi_emby'}),
])
def test_shared_code_cannot_drop_profile_specific_reader(tmp_path, records, required):
    userdata, target = tmp_path/'userdata', tmp_path/'retained'
    writer, path = fixture(userdata, records, other=True)
    try:
        old = b'raise RuntimeError("never execute retained program")'
        program(target, old)
        before = path.read_bytes(), Path(str(path)+'-wal').read_bytes()
        assert guard.registry_requirements(userdata) == required
        for op in (lambda:guard.check_program(userdata, target), lambda:guard.check_bundle(userdata, package(old))):
            with pytest.raises(guard.CatalogCompatibilityError, match='EXPLICIT_OFFLINE_RESTORE'):
                op()
        assert before == (path.read_bytes(), Path(str(path)+'-wal').read_bytes())
        new = b"REGISTRY_READ_FEATURES = ('multi_emby', 't4')\n"+old
        program(target, new)
        guard.check_program(userdata, target)
        guard.check_bundle(userdata, package(new))
        with pytest.raises(guard.CatalogCompatibilityError):
            guard.check_registry_program(required, target, hashlib.sha256(old).hexdigest())
    finally:
        writer.close()


def test_legacy_profile_does_not_require_new_code(tmp_path):
    userdata = tmp_path/'userdata'
    writer, _ = fixture(userdata, [{'kind':'vfs'}, {'kind':'catalog'},
                            {'kind':'media_server','metadata':{'provider':'emby'}}])
    try:
        guard.check_program(userdata, tmp_path/'no-new-reader')
        assert not guard.registry_requirements(userdata)
    finally:
        writer.close()

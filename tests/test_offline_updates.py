"""Signed local delivery, whole-generation recovery, program-only rollback."""
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from bobbi_platform.offline_updates import SignedBundle
from bobbi_platform.updates import UpdateError
from test_updates import archive

IDS = ('plugin.video.bobbi', 'script.module.requests')


@pytest.fixture(scope='module')
def signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    numbers = key.public_key().public_numbers()
    return key, dict(schema=1, key=dict(algorithm='RSA3072-SHA256', e=65537, n=format(numbers.n, 'x')),
                     components=list(IDS))


def bundle(path, signer, sequence=1, version='1.0.0', transform=None, extra=None):
    key, _ = signer
    items, blobs = [], {}
    for name in IDS:
        raw = archive(name, version)
        filename = name + '/' + name + '-' + version + '.zip'
        blobs[filename] = raw
        items.append(dict(id=name, version=version, file=filename, size=len(raw),
                          sha256=hashlib.sha256(raw).hexdigest()))
    value = dict(schema=2, channel='private-candidate', profile='windows', sequence=sequence, components=items)
    if transform:
        transform(value)
    raw = json.dumps(value, sort_keys=True).encode()
    signature = base64.b64encode(key.sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(path, 'w') as target:
        target.writestr('release.json', raw)
        target.writestr('release.sig', signature)
        for name, content in blobs.items():
            target.writestr(name, content)
        if extra:
            target.writestr(*extra)
    return path


@contextmanager
def lease():
    yield


def apply(path, signer, root, crash=None):
    with SignedBundle(path, signer[1], 'windows') as source:
        engine = source.engine(root / 'addons', root / 'work', lambda: True, lease)
        if crash:
            crash(engine)
        return engine, engine.apply(source.raw, source.signature)


def test_local_signed_generation_and_rollback_never_touch_userdata(tmp_path, signer):
    user = tmp_path / 'userdata'
    user.mkdir()
    (user / 'account').write_text('fixture only')
    first = bundle(tmp_path / 'one.zip', signer)
    second = bundle(tmp_path / 'two.zip', signer, 2, '2.0.0')
    apply(first, signer, tmp_path)
    engine, state = apply(second, signer, tmp_path)
    assert state['sequence'] == 2
    assert engine.rollback() == dict(sequence=2, versions=dict.fromkeys(IDS, '1.0.0'))
    for name in IDS:
        assert '1.0.0' in (engine.addons / name / 'addon.xml').read_text()
    assert (user / 'account').read_text() == 'fixture only'
    with pytest.raises(UpdateError, match='sequence'):
        apply(second, signer, tmp_path)
    # Retain the previous program after deliberate rollback as well.
    assert engine.rollback()['versions'] == dict.fromkeys(IDS, '2.0.0')


def test_first_install_rollback_removes_only_managed_programs(tmp_path, signer):
    other = tmp_path / 'addons/plugin.user.other'
    other.mkdir(parents=True)
    (other / 'keep').write_text('keep')
    engine, _ = apply(bundle(tmp_path / 'one.zip', signer), signer, tmp_path)
    assert engine.rollback() == dict(sequence=1, versions={})
    assert (other / 'keep').read_text() == 'keep'
    assert all(not (engine.addons / name).exists() for name in IDS)


def test_unknown_or_cross_platform_packages_are_rejected(tmp_path, signer):
    path = bundle(tmp_path / 'wrong.zip', signer, extra=('userdata/account', 'never install'))
    with pytest.raises(UpdateError):
        apply(path, signer, tmp_path)
    path = bundle(tmp_path / 'cross.zip', signer, transform=lambda value: value.update(profile='android'))
    with pytest.raises(UpdateError):
        apply(path, signer, tmp_path)
    assert not (tmp_path / 'addons').exists()


def test_wrong_key_or_changed_package_cannot_be_installed(tmp_path, signer):
    path = bundle(tmp_path / 'signed.zip', signer)
    bad_trust = dict(signer[1], key=dict(signer[1]['key'], n='f' * 768))
    with pytest.raises(UpdateError, match='signature'):
        with SignedBundle(path, bad_trust, 'windows'):
            pass
    with zipfile.ZipFile(path) as source:
        rows = {row.filename: source.read(row) for row in source.infolist()}
    name = next(n for n in rows if n.endswith('.zip'))
    rows[name] += b'changed'
    changed = tmp_path / 'changed.zip'
    with zipfile.ZipFile(changed, 'w') as target:
        for name, raw in rows.items():
            target.writestr(name, raw)
    with pytest.raises(UpdateError, match='length'):
        apply(changed, signer, tmp_path)
    assert list((tmp_path / 'addons').iterdir()) == []


def test_tampered_program_backup_refuses_rollback(tmp_path, signer):
    apply(bundle(tmp_path / 'one.zip', signer), signer, tmp_path)
    engine, _ = apply(bundle(tmp_path / 'two.zip', signer, 2, '2.0.0'), signer, tmp_path)
    previous = json.loads(engine.previous_path.read_text())
    (engine.work / previous['transaction'] / 'backup' / IDS[0] / 'code.py').write_text('changed')
    with pytest.raises(UpdateError, match='integrity'):
        engine.rollback()
    assert engine.available()['sequence'] == 2


@pytest.mark.parametrize('cut', [1, 2, 3, 4])
def test_every_retained_rollback_move_crash_recovers_current_generation(tmp_path, signer, cut):
    apply(bundle(tmp_path / 'one.zip', signer), signer, tmp_path)
    engine, _ = apply(bundle(tmp_path / 'two.zip', signer, 2, '2.0.0'), signer, tmp_path)
    original, count = engine._move, []
    def crash(source, target):
        original(source, target)
        count.append(1)
        if len(count) == cut:
            raise KeyboardInterrupt('simulated crash')
    engine._move = crash
    with pytest.raises(KeyboardInterrupt):
        engine.rollback()
    engine._move = original
    assert engine.available() == dict(sequence=2, versions=dict.fromkeys(IDS, '2.0.0'))
    for name in IDS:
        assert '2.0.0' in (engine.addons / name / 'addon.xml').read_text()
    assert engine.rollback()['versions'] == dict.fromkeys(IDS, '1.0.0')


@pytest.mark.parametrize('version', ['0.2.3+matrix.1', '2026.9.6.0'])
def test_kodi_vendor_suffix_uses_signed_generation_not_lexical_version(tmp_path, signer, version):
    engine, _ = apply(bundle(tmp_path / 'one.zip', signer, version=version), signer, tmp_path)
    assert engine.available()['versions'] == dict.fromkeys(IDS, version)


def test_large_real_program_inventory_has_readable_retained_receipt_and_rolls_back(tmp_path, signer):
    from bobbi_platform.updates import MAX_MANIFEST
    engine,_=apply(bundle(tmp_path/'one.zip',signer),signer,tmp_path)
    program=engine.addons/IDS[0]
    # Legitimate program assets are within the 10,000-file addon budget but
    # their per-file hashes exceed the unrelated 256 KiB release manifest cap.
    for index in range(1600):
        (program/('asset-%04d-'%index+'x'*90+'.txt')).write_bytes(b'fixture asset')
    engine,_=apply(bundle(tmp_path/'two.zip',signer,2,'2.0.0'),signer,tmp_path)
    assert engine.previous_path.stat().st_size > MAX_MANIFEST
    assert engine.available()['sequence']==2
    assert engine.rollback()['versions']==dict.fromkeys(IDS,'1.0.0')
    assert len(list(program.glob('asset-*.txt')))==1600


def test_backup_receipt_budget_is_checked_before_any_live_move(tmp_path,signer,monkeypatch):
    from bobbi_platform import updates
    engine,_=apply(bundle(tmp_path/'one.zip',signer),signer,tmp_path)
    monkeypatch.setattr(updates,'MAX_BACKUP_RECEIPT',engine.previous_path.stat().st_size+1)
    with pytest.raises(UpdateError,match='receipt exceeds budget'):
        apply(bundle(tmp_path/'two.zip',signer,2,'2.0.0'),signer,tmp_path)
    assert not engine.journal_path.exists()
    assert engine.available()['sequence']==1
    for name in IDS:
        assert '1.0.0' in (engine.addons/name/'addon.xml').read_text()

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication_gate', ROOT / 'tools/ce_release_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def publication(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    assets = {}
    for name in ('complete.zip', 'entry.zip', 'component.zip'):
        path = source / name
        path.write_bytes(name.encode() * 10)
        assets[name] = gate.identity(path)
    feeds = {}
    for name in ('addons.xml', 'current.json', 'start/new.zip'):
        path = source / 'feed' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        feeds[name] = gate.identity(path)
    receipt = dict(schema=2, track='preview', commit='a' * 40, tree='b' * 40, tag='ce2067',
                   assets=assets, feeds={'github': feeds, 'gitee': feeds})
    target = tmp_path / 'repository/preview'
    target.mkdir(parents=True)
    (target / 'current.json').write_bytes(b'previous pointer')
    (target / 'old.zip').write_bytes(b'old retained entry')
    calls = []
    def transfer(url, maximum, consume, cancelled, progress, **kw):
        if url.startswith('https://api.github.com/'):
            consume(json.dumps(dict(tag_name=receipt['tag'], draft=False, prerelease=True,
                                    target_commitish=receipt['commit'])).encode())
            return
        name = url.split('/preview/', 1)[1] if '/preview/' in url else url.rsplit('/', 1)[1]
        calls.append(name)
        expected = feeds[name] if '/preview/' in url else assets[name]
        assert maximum == kw['expected'] == expected['bytes']
        consume(Path(expected['path']).read_bytes())
    return receipt, target, tmp_path / 'remote.json', transfer, calls


def test_promote_reads_every_remote_asset_before_pointers_and_preserves_old_zips(publication):
    receipt, target, report, transfer, calls = publication
    def checked_transfer(*a, **kw):
        assert (target / 'current.json').read_bytes() == b'previous pointer'
        transfer(*a, **kw)
    gate.promote(receipt, 'github', target, report, checked_transfer)
    assert calls == (list(receipt['assets']) + list(receipt['feeds']['github'])) * 2
    assert (target / 'current.json').read_bytes() == b'current.json'
    assert (target / 'old.zip').read_bytes() == b'old retained entry'
    assert json.loads(report.read_text())['passed'] is True


@pytest.mark.parametrize('failure', ['wrong_bytes', 'short_read', 'network'])
def test_any_remote_asset_failure_preserves_entire_previous_feed(publication, failure):
    receipt, target, report, transfer, _ = publication
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    def broken(url, maximum, consume, *a, **kw):
        if url.endswith('component.zip'):
            if failure == 'network': raise OSError('network offline')
            consume(b'x' * (maximum if failure == 'wrong_bytes' else maximum - 1))
        else: transfer(url, maximum, consume, *a, **kw)
    with pytest.raises((OSError, ValueError)):
        gate.promote(receipt, 'github', target, report, broken)
    assert {p.name: p.read_bytes() for p in target.iterdir()} == before
    assert json.loads(report.read_text())['passed'] is False


@pytest.mark.parametrize('kind', ['asset', 'feed'])
def test_frozen_local_input_mutation_prevents_network_or_feed_write(publication, kind):
    receipt, target, report, transfer, calls = publication
    row = next(iter(receipt['assets'].values() if kind == 'asset' else receipt['feeds']['github'].values()))
    Path(row['path']).write_bytes(b'changed since freeze')
    with pytest.raises(ValueError, match='input changed'):
        gate.promote(receipt, 'github', target, report, transfer)
    assert not calls
    assert (target / 'current.json').read_bytes() == b'previous pointer'


def test_mutation_during_remote_readback_blocks_promotion(publication):
    receipt, target, report, transfer, _ = publication
    def changing(*a, **kw):
        transfer(*a, **kw)
        Path(receipt['feeds']['github']['current.json']['path']).write_bytes(b'late mutation')
    with pytest.raises(ValueError): gate.promote(receipt, 'github', target, report, changing)
    assert (target / 'current.json').read_bytes() == b'previous pointer'


def test_invalid_feed_member_never_escapes_output_root(publication):
    receipt, target, report, transfer, _ = publication
    receipt['feeds']['github']['../escape.json'] = receipt['feeds']['github']['current.json']
    with pytest.raises(ValueError, match='feed path'):
        gate.promote(receipt, 'github', target, report, transfer)
    assert not (target.parent / 'escape.json').exists()
    assert (target / 'current.json').read_bytes() == b'previous pointer'


@pytest.mark.parametrize('mirror', ['github', 'gitee'])
@pytest.mark.parametrize('fault', ['stale', 'corrupt', 'timeout'])
def test_each_actual_track_feed_must_read_back_before_any_promotion(publication, mirror, fault):
    receipt, target, report, transfer, _ = publication
    def changed(url, maximum, consume, *a, **kw):
        if url == gate.feed_url('preview', mirror):
            if fault == 'timeout': raise TimeoutError()
            consume(b'old stable pointer' if fault == 'stale' else b'x' * maximum)
        else: transfer(url, maximum, consume, *a, **kw)
    with pytest.raises((ValueError, TimeoutError)):
        gate.promote(receipt, 'github', target, report, changed)
    result = json.loads(report.read_text())
    assert not result['promotable'] and not result['passed']
    assert (target / 'current.json').read_bytes() == b'previous pointer'


def test_remote_prerelease_cannot_be_presented_as_stable(publication):
    receipt, target, report, transfer, _ = publication
    receipt['track'] = 'stable'
    with pytest.raises(ValueError, match='release identity'):
        gate.readback(receipt, 'github', report, transfer)
    assert not json.loads(report.read_text())['promotable']


def test_old_single_mirror_receipts_cannot_promote(publication):
    receipt, target, report, transfer, _ = publication
    receipt.pop('schema')
    with pytest.raises(ValueError, match='Versioned dual-mirror'):
        gate.promote(receipt, 'github', target, report, transfer)


def test_source_check_gate_binds_both_builds_to_actual_source(tmp_path, monkeypatch):
    import hashlib
    import sys
    import zipfile
    sys.path.insert(0, str(ROOT / 'tools'))
    import build_release
    source = tmp_path / 'component'
    source.mkdir()
    (source / 'addon.xml').write_bytes(b'<addon id="fixture" version="1.0.0"/>')
    monkeypatch.setattr(build_release, 'sources', lambda: {'fixture': source})
    first, second = tmp_path / 'first', tmp_path / 'second'
    for root in (first, second):
        target = root / 'fixture/fixture-1.0.0.zip'
        target.parent.mkdir(parents=True)
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr('fixture/addon.xml', (source / 'addon.xml').read_bytes())
        row = dict(id='fixture', version='1.0.0', file='fixture/fixture-1.0.0.zip',
                   bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        (root / 'manifest.json').write_text(json.dumps(dict(channel='source-check', installable=False, components=[row])))
    receipt = gate.source_check_evidence(first, second)
    assert receipt['reproducible_files'] == 2 and len(receipt['files']) == 4
    (source / 'addon.xml').write_bytes(b'changed source')
    with pytest.raises(ValueError, match='frozen source'):
        gate.source_check_evidence(first, second)


def test_preview_promotion_cannot_overwrite_legacy_or_stable_pointer(publication):
    receipt, target, report, transfer, _ = publication
    for other in (target.parent, target.parent / 'stable'):
        with pytest.raises(ValueError, match='selected track directory'):
            gate.promote(receipt, 'github', other, report, transfer)
    assert not (target.parent / 'current.json').exists()
    assert not (target.parent / 'stable').exists()

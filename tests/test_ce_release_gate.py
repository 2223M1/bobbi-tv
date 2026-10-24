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
    receipt = dict(commit='a' * 40, tree='b' * 40, tag='ce2067', assets=assets, feeds={'github': feeds})
    target = tmp_path / 'repository'
    target.mkdir()
    (target / 'current.json').write_bytes(b'previous pointer')
    (target / 'old.zip').write_bytes(b'old retained entry')
    calls = []
    def transfer(url, maximum, consume, cancelled, progress, **kw):
        name = url.rsplit('/', 1)[1]
        calls.append(name)
        assert maximum == kw['expected'] == assets[name]['bytes']
        consume(Path(assets[name]['path']).read_bytes())
    return receipt, target, tmp_path / 'remote.json', transfer, calls


def test_promote_reads_every_remote_asset_before_pointers_and_preserves_old_zips(publication):
    receipt, target, report, transfer, calls = publication
    def checked_transfer(*a, **kw):
        assert (target / 'current.json').read_bytes() == b'previous pointer'
        transfer(*a, **kw)
    gate.promote(receipt, 'github', target, report, checked_transfer)
    assert calls == list(receipt['assets'])
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

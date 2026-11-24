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
                   assets=assets, feeds={'github': feeds, 'gitcode': feeds})
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


@pytest.mark.parametrize('mirror', ['github', 'gitcode'])
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


def scoped(publication, policy):
    receipt, target, report, _, _ = publication
    mirrors = gate.MIRRORS[policy]
    receipt.update(schema=3, mirror_policy=policy, offers={}, sequence=2067)
    base = dict(schema=2, track='preview', prerelease=True, manifest_channel='private-candidate',
                versions={'script.bobbi.start': '1.0'}, size=123, sha256='1' * 64)
    remote = {}
    old = {}
    for mirror in mirrors:
        new = dict(base, tag=receipt['tag'], sequence=2067, url=gate.release_url(receipt['tag'], mirror))
        old[mirror] = dict(new, tag='ce2066', sequence=2066, url=gate.release_url('ce2066', mirror))
        path = target.parent / (mirror + '.json')
        path.write_text(json.dumps(new))
        receipt['offers'][mirror] = new
        receipt['feeds'][mirror] = dict(receipt['feeds'][mirror], **{'current.json': gate.identity(path)})
        url = gate.feed_url('preview', mirror)
        remote[url] = json.dumps(old[mirror]).encode()
        for name, row in receipt['assets'].items():
            remote[gate.release_url(new['tag'], mirror).rsplit('/', 1)[0]+'/'+name] = Path(row['path']).read_bytes()
    receipt['feeds'] = {k: receipt['feeds'][k] for k in mirrors}
    (target/'current.json').write_text(json.dumps(old['github']))
    calls = []
    def transfer(url, limit, consume, *args, **kwargs):
        calls.append(url)
        if url.startswith('https://api.github.com/'):
            raw = json.dumps(dict(tag_name=receipt['tag'], draft=False, prerelease=True, target_commitish=receipt['commit'])).encode()
        else: raw = remote[url]
        consume(raw)
    return receipt, target, report, remote, calls, transfer


@pytest.mark.parametrize('policy', ['github-only', 'dual'])
def test_stage_with_old_live_pointer_then_verify_actual_published_feed(publication, policy):
    r, target, report, remote, calls, transfer = scoped(publication, policy)
    gate.promote(r, 'github', target, report, transfer)
    before = json.loads(report.read_text())
    assert before['phase'] == 'before-feed-commit' and set(before['previous_sequences']) == set(gate.MIRRORS[policy])
    assert before['passed'] and all(row['kind'] == 'asset' for row in before['files'])
    assert json.loads((target/'current.json').read_text()) == r['offers']['github']
    for mirror in gate.MIRRORS[policy]:
        base = gate.feed_url('preview', mirror).rsplit('/', 1)[0] + '/'
        for name, row in r['feeds'][mirror].items():
            if name != 'current.json': remote[base+name] = Path(row['path']).read_bytes()
    def catalog(track, files):
        assert track == 'preview' and 'current.json' not in files
        return 'a'*40, {name: Path(row['path']).read_bytes() for name, row in files.items()}
    with pytest.raises(ValueError, match='differs'):
        gate.readback(r, 'github', report, transfer, read_catalog=catalog)
    assert not json.loads(report.read_text())['passed']
    for mirror in gate.MIRRORS[policy]:
        remote[gate.feed_url('preview', mirror)] = Path(r['feeds'][mirror]['current.json']['path']).read_bytes()
    after = gate.readback(r, 'github', report, transfer, read_catalog=catalog)
    assert all(row['transport']=='https' for row in after['files'] if row['kind']=='asset' or row['file']=='current.json')
    if policy == 'dual':
        def bad(track, files):
            ident, blobs = catalog(track, files)
            blobs['addons.xml'] += b'!'
            return ident, blobs
        with pytest.raises(ValueError, match='differs'):
            gate.readback(r, 'github', report, transfer, read_catalog=bad)
    assert after['phase'] == 'live-feed-readback' and after['passed']
    assert len(after['files']) == sum(len(r['assets'])+len(items) for items in r['feeds'].values())
    if policy == 'github-only': assert not any('gitcode' in url for url in calls)


@pytest.mark.parametrize('fault', ['remote-ahead','remote-conflict','local-ahead','new-broken','gitcode-broken',
                                   'different-versioned-zip','wrong-mirror','altered-offer','missing-mirror'])
def test_scoped_promotion_failures_leave_previous_pointer(publication, fault):
    r, target, report, remote, _, transfer = scoped(publication, 'dual')
    url = gate.feed_url('preview', 'github')
    if fault in ('remote-ahead', 'remote-conflict', 'local-ahead'):
        raw = json.dumps(dict(r['offers']['github'], sequence=2067 if fault=='remote-conflict' else 2068, size=999)).encode()
        if fault == 'local-ahead': (target/'current.json').write_bytes(raw)
        else: remote[url] = raw
    if fault == 'new-broken': remote[gate.release_url(r['tag'], 'github').rsplit('/',1)[0]+'/complete.zip'] = b'bad'
    if fault == 'gitcode-broken': remote[gate.release_url(r['tag'], 'gitcode').rsplit('/',1)[0]+'/entry.zip'] = b'bad'
    if fault == 'different-versioned-zip':
        (target/'start').mkdir(); (target/'start/new.zip').write_bytes(b'existing package')
    if fault == 'wrong-mirror': r['mirror_policy'] = 'github-only'
    if fault == 'altered-offer': r['offers']['github']['sequence'] += 1
    if fault == 'missing-mirror': r['feeds'].pop('gitcode')
    before = {p: p.read_bytes() for p in target.rglob('*') if p.is_file()}
    with pytest.raises(ValueError): gate.promote(r, 'github', target, report, transfer)
    assert before == {p: p.read_bytes() for p in target.rglob('*') if p.is_file()}


def test_remote_release_rejects_unexpected_extra_component_assets(publication):
    r, target, report, remote, _, _ = scoped(publication, 'github-only')
    r['assets'].pop('component.zip')
    def transfer_with_extra(url, limit, consume, *args, **kwargs):
        if url.startswith('https://api.github.com/'):
            raw = json.dumps(dict(
                tag_name=r['tag'], draft=False, prerelease=True, target_commitish=r['commit'],
                assets=[{'name': 'complete.zip'}, {'name': 'entry.zip'}, {'name': 'bobbi-component-extra.zip'}]
            )).encode()
        else:
            raw = remote[url]
        consume(raw)
    with pytest.raises(ValueError, match='release identity'):
        gate.promote(r, 'github', target, report, transfer_with_extra)

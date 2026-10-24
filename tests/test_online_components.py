"""Component reuse still delivers one signed generation to the real installer."""
from io import BytesIO
import hashlib
import json
import zipfile
from urllib.error import HTTPError
import base64
import time
from pathlib import Path

import pytest

from bobbi_platform import online_components as components, online_updates as online
from bobbi_platform.offline_updates import SignedBundle, archive_info
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import package, signing, environment
from test_online_updates import Response, offer_for, entry
from test_online_transport import endpoint
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


def canonical(path, signing, sequence=1, version='1.0.0'):
    package(path, signing, sequence, version)
    with zipfile.ZipFile(path) as source:
        rows = [(name, source.read(name)) for name in source.namelist()]
    with zipfile.ZipFile(path, 'w') as dest:
        for name, raw in rows:
            dest.writestr(archive_info(name), raw)
    return path


def assets(path):
    with zipfile.ZipFile(path) as source:
        raw = source.read('release.json')
        manifest = json.loads(raw)
        output = BytesIO()
        with zipfile.ZipFile(output, 'w') as target:
            for name in ('release.json', 'release.sig'):
                target.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), source.read(name))
        blobs = {components.component_name(row): source.read(row['file']) for row in manifest['components']}
        blobs['BobbiTV-CE2054.components-v1.zip'] = output.getvalue()
        blobs['BobbiTV-CE2054.bobbi-update.zip'] = path.read_bytes()
        return manifest, blobs


def network(monkeypatch, blobs):
    calls = []
    def opened(url):
        name = url.rsplit('/', 1)[-1]
        calls.append(name)
        if name not in blobs:
            raise HTTPError(url, 404, 'fixture', {}, None)
        value = blobs[name]
        if isinstance(value, BaseException):
            raise value
        return Response(value)
    monkeypatch.setattr(online, '_open', opened)
    return calls


def test_cold_download_then_warm_reuse_is_byte_identical(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    calls = network(monkeypatch, blobs)
    work = tmp_path/'work'
    result = components.download(offer_for(path.read_bytes()), work, signing[1])
    assert result.read_bytes() == path.read_bytes()
    assert calls == ['BobbiTV-CE2054.bobbi-update.zip']
    result.unlink()
    calls.clear()
    report = {}
    result = components.download(offer_for(path.read_bytes()), work, signing[1], report=report)
    assert result.read_bytes() == path.read_bytes()
    assert calls == ['BobbiTV-CE2054.components-v1.zip']
    assert report['reused_bytes'] == sum(row['size'] for row in manifest['components'])
    assert report['downloaded_bytes'] == len(blobs[calls[0]])
    assert report['mode'] == 'components'
    with SignedBundle(result, signing[1], 'coreelec') as checked:
        assert checked.check_all() == manifest


@pytest.mark.parametrize('damage', ['missing', 'size', 'digest'])
def test_bad_cache_only_fetches_missing_component(tmp_path, signing, monkeypatch, damage):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    calls = network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    row = manifest['components'][0]
    cached = work/'components-v1'/(row['sha256']+'.zip')
    if damage == 'missing': cached.unlink()
    elif damage == 'size': cached.write_bytes(b'bad')
    else: cached.write_bytes(b'x'*row['size'])
    calls.clear()
    result = components.download(offer_for(path.read_bytes()), work, signing[1])
    assert result.read_bytes() == path.read_bytes()
    assert calls == ['BobbiTV-CE2054.components-v1.zip', components.component_name(row)]


@pytest.mark.parametrize('failure', ['absent', 'metadata', 'signature', 'short', 'hash', 'assembly'])
def test_component_failure_uses_original_complete_download(tmp_path, signing, monkeypatch, failure):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    calls = network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    metadata = 'BobbiTV-CE2054.components-v1.zip'
    row = manifest['components'][0]
    if failure == 'absent': blobs.pop(metadata)
    if failure == 'metadata': blobs[metadata] = b'not zip'
    if failure == 'signature':
        output = BytesIO()
        with zipfile.ZipFile(BytesIO(blobs[metadata])) as src, zipfile.ZipFile(output, 'w') as dst:
            dst.writestr('release.json', src.read('release.json'))
            dst.writestr('release.sig', b'A'*512)
        blobs[metadata] = output.getvalue()
    if failure in ('short', 'hash'):
        (work/'components-v1'/(row['sha256']+'.zip')).unlink()
        blobs[components.component_name(row)] = b'x'*(row['size']-1 if failure == 'short' else row['size'])
    if failure == 'assembly':
        # Same signed content in an older noncanonical outer ZIP stays usable
        # through the full path; it must not be returned as another byte vector.
        package(path, signing)
        blobs['BobbiTV-CE2054.bobbi-update.zip'] = path.read_bytes()
    calls.clear()
    report = {}
    result = components.download(offer_for(path.read_bytes()), work, signing[1], report=report)
    assert result.read_bytes() == path.read_bytes()
    assert calls[-1] == 'BobbiTV-CE2054.bobbi-update.zip'
    assert report['mode'] == 'full-fallback'
    assert not (work/'components-v1/transfer.part').exists()


def test_cancel_during_components_never_downloads_full_or_installs(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    calls = network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    row = manifest['components'][0]
    (work/'components-v1'/(row['sha256']+'.zip')).unlink()
    cancelled = [False]
    calls.clear()
    def progress(value): cancelled[0] = True
    with pytest.raises(online.Cancelled):
        components.download(offer_for(path.read_bytes()), work, signing[1],
                            lambda: cancelled[0], progress)
    assert 'BobbiTV-CE2054.bobbi-update.zip' not in calls
    assert not list(work.glob('online-*.zip'))
    assert not (work/'components-v1/transfer.part').exists()


def test_second_caller_cannot_remove_first_callers_cache(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    _, blobs = assets(path)
    network(monkeypatch, blobs)
    work = tmp_path/'work'
    with components.ComponentCache(work, lambda: None):
        with pytest.raises(UpdateError, match='ONLINE_DOWNLOAD_BUSY'):
            components.download(offer_for(path.read_bytes()), work, signing[1])


def test_real_online_entry_installs_warm_reassembled_generation(entry, signing, monkeypatch):
    from bobbi_platform import ce_install_ui
    path = canonical(entry.env.root/'new.zip', signing)
    _, blobs = assets(path)
    calls = network(monkeypatch, blobs)
    offer = offer_for(path.read_bytes())
    monkeypatch.setattr(online, 'latest', lambda cancelled: offer)
    components.download(offer, entry.env.work/'downloads', signing[1]).unlink()
    calls.clear()
    ce_install_ui.main(online=True)
    assert entry.env.installer._read()['phase'] == 'complete'
    assert entry.env.installer._read()['sequence'] == 1
    assert calls == ['BobbiTV-CE2054.components-v1.zip']
    assert (entry.env.user/'watching').read_text() == 'user-history'
    assert not list((entry.env.work/'downloads').glob('online-*.zip'))


def test_changed_generation_fetches_only_changed_component_and_removes_unreferenced_cache(tmp_path, signing, monkeypatch):
    old = canonical(tmp_path/'old.zip', signing)
    rows, old_blobs = assets(old)
    network(monkeypatch, old_blobs)
    work = tmp_path/'work'
    components.download(offer_for(old.read_bytes()), work, signing[1]).unlink()
    new = tmp_path/'new.zip'
    with zipfile.ZipFile(old) as source:
        manifest = json.loads(source.read('release.json'))
        manifest['sequence'] = 2
        row = manifest['components'][0]
        changed = source.read(row['file']) + b'new component fixture'
        row.update(sha256=hashlib.sha256(changed).hexdigest(), size=len(changed))
        raw = json.dumps(manifest).encode()
        sig = base64.b64encode(signing[0].sign(raw, padding.PKCS1v15(), hashes.SHA256()))
        with zipfile.ZipFile(new, 'w') as target:
            for name, blob in [('release.json', raw), ('release.sig', sig)]:
                target.writestr(archive_info(name), blob)
            for item in manifest['components']:
                target.writestr(archive_info(item['file']), changed if item['id'] == row['id'] else source.read(item['file']))
    _, blobs = assets(new)
    calls = network(monkeypatch, blobs)
    unrelated = work/'user-backup.zip'
    unrelated.write_bytes(b'keep')
    report = {}
    result = components.download(offer_for(new.read_bytes(), sequence=2), work, signing[1], report=report)
    assert result.read_bytes() == new.read_bytes()
    assert calls == ['BobbiTV-CE2054.components-v1.zip', components.component_name(row)]
    assert {p.name for p in (work/'components-v1').iterdir()} == {r['sha256']+'.zip' for r in manifest['components']}
    assert report['reused_bytes'] == sum(r['size'] for r in manifest['components'][1:])
    assert unrelated.read_bytes() == b'keep'


@pytest.mark.parametrize('phase', ['metadata', 'component'])
@pytest.mark.parametrize('end', ['cancel', 'deadline'])
def test_real_tls_stall_cancels_without_fallback_and_next_request_succeeds(
        tmp_path, signing, endpoint, monkeypatch, phase, end):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    work = tmp_path/'work'
    original_open = online._open
    slow = [False]
    def opened(url):
        name = url.rsplit('/', 1)[-1]
        endpoint.blob = blobs[name]
        stalled = slow[0] and (name.endswith('.components-v1.zip') if phase == 'metadata' else name.startswith('bobbi-component-'))
        return original_open(endpoint.url+('/headers' if stalled else '/blob'))
    monkeypatch.setattr(online, '_open', opened)
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    row = manifest['components'][0]
    (work/'components-v1'/(row['sha256']+'.zip')).unlink()
    before = len(endpoint.requests)
    slow[0] = True
    if end == 'deadline': monkeypatch.setattr(online, 'TRANSFER_SECONDS', .4)
    started = time.monotonic()
    with pytest.raises(UpdateError, match='ONLINE_'+('CANCELLED' if end == 'cancel' else 'TIMEOUT')):
        components.download(offer_for(path.read_bytes()), work, signing[1],
            lambda: end == 'cancel' and time.monotonic()-started > .4)
    assert time.monotonic()-started < 1.5
    assert endpoint.requests[-1][0] == '/headers'
    assert len(endpoint.requests)-before == (1 if phase == 'metadata' else 2)
    assert not list(work.glob('online-*.zip'))
    assert not (work/'components-v1/transfer.part').exists()
    slow[0] = False
    monkeypatch.setattr(online, 'TRANSFER_SECONDS', 600)
    assert components.download(offer_for(path.read_bytes()), work, signing[1]).read_bytes() == path.read_bytes()


def test_missing_endpoint_does_not_reset_total_budget(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    _, blobs = assets(path)
    network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    clock = [0.]
    monkeypatch.setattr(components.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(online, 'TRANSFER_SECONDS', 20)
    calls = []
    def opened(url):
        calls.append(url)
        if url.endswith('.components-v1.zip'):
            clock[0] = 16.
            raise TimeoutError()
        class Slow(Response):
            def read(self, size):
                clock[0] = 21.
                return super().read(size)
        return Slow(path.read_bytes())
    monkeypatch.setattr(online, '_open', opened)
    with pytest.raises(UpdateError, match='ONLINE_TIMEOUT'):
        components.download(offer_for(path.read_bytes()), work, signing[1])
    assert len(calls) == 2


def test_cache_seed_is_optional_when_space_is_only_enough_for_complete_archive(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    _, blobs = assets(path)
    network(monkeypatch, blobs)
    def no_cache(self, needed): raise UpdateError('INSTALLATION_SPACE_REQUIRED')
    monkeypatch.setattr(components.ComponentCache, 'space', no_cache)
    report = {}
    result = components.download(offer_for(path.read_bytes()), tmp_path/'work', signing[1], report=report)
    assert result.read_bytes() == path.read_bytes()
    assert report['cache_seed'] == 'unavailable'


def test_cache_directory_fault_does_not_block_full_download(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    _, blobs = assets(path)
    calls = network(monkeypatch, blobs)
    work = tmp_path/'work'
    work.mkdir()
    (work/'components-v1').write_bytes(b'not a directory; do not delete')
    result = components.download(offer_for(path.read_bytes()), work, signing[1])
    assert result.read_bytes() == path.read_bytes()
    assert calls == ['BobbiTV-CE2054.bobbi-update.zip']
    assert (work/'components-v1').read_bytes() == b'not a directory; do not delete'


def test_linked_cache_blob_cannot_modify_external_file(tmp_path, signing, monkeypatch):
    import os
    path = canonical(tmp_path/'one.zip', signing)
    _, blobs = assets(path)
    network(monkeypatch, blobs)
    work = tmp_path/'work'
    root = work/'components-v1'
    root.mkdir(parents=True)
    external = tmp_path/'external'
    external.write_bytes(b'preserve')
    os.link(external, root/('f'*64+'.zip'))
    result = components.download(offer_for(path.read_bytes()), work, signing[1])
    assert result.read_bytes() == path.read_bytes()
    assert external.read_bytes() == b'preserve'


def test_new_assets_keep_old_feed_schema_and_are_reproducible(tmp_path, signing, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'tools'))
    from build_component_assets import build
    path = canonical(tmp_path/'one.zip', signing)
    one = build(path, tmp_path/'assets-one', 'ce2054', signing[1])
    two = build(path, tmp_path/'assets-two', 'ce2054', signing[1])
    assert one == two and one['published'] is False
    assert all((tmp_path/'assets-one'/row['file']).read_bytes() == (tmp_path/'assets-two'/row['file']).read_bytes() for row in one['assets'])
    offer = offer_for(path.read_bytes())
    assert set(online.parse_offer(json.dumps(offer))) == {'schema', 'tag', 'sequence', 'size', 'sha256', 'url'}
    with pytest.raises(ValueError, match='must be new'):
        build(path, tmp_path/'assets-one', 'ce2054', signing[1])


@pytest.mark.parametrize('host,path', [
    ('gitee.com', '/M12223/bobbi-tv-updates/attach_files/123/download/'),
    ('foruda.gitee.com', '/attach_file/123/'),
])
def test_component_redirects_remain_in_existing_delivery_namespaces(host, path):
    for filename in ['BobbiTV-CE2064.components-v1.zip', 'bobbi-component-'+'a'*64+'.zip']:
        assert online._allowed_redirect('https://'+host+path+filename)
        assert not online._allowed_redirect('http://'+host+path+filename)
        assert not online._allowed_redirect('https://'+host+'.invalid'+path+filename)
    assert not online._allowed_redirect('https://'+host+path+'arbitrary.zip')


def test_network_failure_retains_verified_blobs_for_retry_not_partial_components(tmp_path, signing, monkeypatch):
    from urllib.error import URLError
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    rows = manifest['components'][:2]
    for row in rows:
        (work/'components-v1'/(row['sha256']+'.zip')).unlink()
    failing = dict(blobs)
    failing[components.component_name(rows[1])] = URLError('fixture unavailable')
    failing['BobbiTV-CE2054.bobbi-update.zip'] = URLError('fixture unavailable')
    network(monkeypatch, failing)
    with pytest.raises(URLError):
        components.download(offer_for(path.read_bytes()), work, signing[1])
    assert (work/'components-v1'/(rows[0]['sha256']+'.zip')).is_file()
    assert not (work/'components-v1'/(rows[1]['sha256']+'.zip')).exists()
    assert not (work/'components-v1/transfer.part').exists()
    calls = network(monkeypatch, blobs)
    result = components.download(offer_for(path.read_bytes()), work, signing[1])
    assert result.read_bytes() == path.read_bytes()
    assert calls == ['BobbiTV-CE2054.components-v1.zip', components.component_name(rows[1])]


def test_cancel_after_new_blob_commit_discards_only_this_calls_new_blobs(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    row = manifest['components'][0]
    new_path = work/'components-v1'/(row['sha256']+'.zip')
    new_path.unlink()
    prior = {p.name for p in (work/'components-v1').iterdir()}
    cancelled = [False]
    with pytest.raises(online.Cancelled):
        components.download(offer_for(path.read_bytes()), work, signing[1], lambda: cancelled[0],
                            lambda _: cancelled.__setitem__(0, new_path.exists()))
    assert {p.name for p in (work/'components-v1').iterdir()} == prior
    assert not new_path.exists()


@pytest.mark.parametrize('field,value', [('sequence', 99), ('profile', 'android'), ('schema', True)])
def test_signed_but_wrong_metadata_falls_back_without_requesting_components(tmp_path, signing, monkeypatch, field, value):
    path = canonical(tmp_path/'one.zip', signing)
    manifest, blobs = assets(path)
    network(monkeypatch, blobs)
    work = tmp_path/'work'
    components.download(offer_for(path.read_bytes()), work, signing[1]).unlink()
    manifest[field] = value
    raw = json.dumps(manifest).encode()
    signature = base64.b64encode(signing[0].sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as target:
        target.writestr(archive_info('release.json'), raw)
        target.writestr(archive_info('release.sig'), signature)
    blobs['BobbiTV-CE2054.components-v1.zip'] = output.getvalue()
    calls = network(monkeypatch, blobs)
    result = components.download(offer_for(path.read_bytes()), work, signing[1])
    assert result.read_bytes() == path.read_bytes()
    assert calls == ['BobbiTV-CE2054.components-v1.zip', 'BobbiTV-CE2054.bobbi-update.zip']


def test_fixed_zip_headers_do_not_depend_on_build_host_platform(monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'platform', 'win32')
    windows = archive_info('fixture')
    monkeypatch.setattr(sys, 'platform', 'linux')
    linux = archive_info('fixture')
    assert windows.create_system == linux.create_system == 3
    assert windows.external_attr == linux.external_attr == 0o600 << 16
    outputs = []
    for info in (windows, linux):
        output = BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr(info, b'fixture')
        outputs.append(output.getvalue())
    assert outputs[0] == outputs[1]


def test_cancel_in_optional_cache_metrics_is_not_swallowed(tmp_path, signing, monkeypatch):
    path = canonical(tmp_path/'one.zip', signing)
    _, blobs = assets(path)
    network(monkeypatch, blobs)
    calls = []
    def entries(self):
        calls.append(1)
        if len(calls) == 3:
            raise online.Cancelled('ONLINE_CANCELLED')
        return []
    monkeypatch.setattr(components.ComponentCache, 'entries', entries)
    monkeypatch.setattr(components.ComponentCache, 'seed', lambda *args: None)
    work = tmp_path/'work'
    with pytest.raises(online.Cancelled):
        components.download(offer_for(path.read_bytes()), work, signing[1])
    assert not list(work.glob('online-*.zip'))

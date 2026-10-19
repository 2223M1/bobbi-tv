"""Offline transaction/security checks, not Kodi or device certification."""
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
from pathlib import Path
import stat
import zipfile

import pytest

from bobbi_platform.updates import (Busy, UpdateEngine, UpdateError,
                                    allowed_release_redirect, allowed_release_url)

IDS = ('plugin.video.bobbi', 'script.module.bobbi.platform')


def archive(addon_id, version='1.0.0', extra=(), xml_id=None, xml_version=None):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as output:
        output.writestr(addon_id + '/addon.xml', '<addon id="{}" version="{}"/>'.format(
            xml_id or addon_id, xml_version or version))
        output.writestr(addon_id + '/code.py', 'VALUE = "' + version + '"\n')
        for name, content in extra:
            output.writestr(name, content)
    return buffer.getvalue()


class Harness:
    def __init__(self, root):
        self.root = root
        self.blobs = {}
        self.downloads = []
        self.idle_values = []
        self.lease_active = False
        self.verifications = []
        self.signature_valid = True
        self.engine = UpdateEngine(root / 'addons', root / 'update-work', IDS,
                                   'preview', 'android', self.verify, self.download,
                                   self.idle, self.lease)

    def verify(self, raw, signature):
        self.verifications.append((raw, signature))
        return self.signature_valid and signature == b'signed'

    def download(self, url, maximum):
        self.downloads.append((url, maximum))
        return self.blobs[url]

    def idle(self):
        return self.idle_values.pop(0) if self.idle_values else True

    @contextmanager
    def lease(self):
        assert not self.lease_active
        self.lease_active = True
        try:
            yield
        finally:
            self.lease_active = False

    def manifest(self, sequence=1, version='1.0.0'):
        items = []
        for name in IDS:
            url = 'https://github.com/2223M1/bobbi-tv/releases/download/v{}/{}.zip'.format(version, name)
            blob = archive(name, version)
            self.blobs[url] = blob
            items.append({'id': name, 'version': version, 'url': url,
                          'size': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()})
        return {'schema': 1, 'channel': 'preview', 'profile': 'android',
                'sequence': sequence, 'components': items}

    def apply(self, value):
        return self.engine.apply(json.dumps(value).encode(), b'signed')

    def replace_blob(self, manifest, blob):
        item = manifest['components'][0]
        self.blobs[item['url']] = blob
        item.update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest())


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def test_complete_install_and_monotonic_state(harness):
    manifest = harness.manifest()
    result = harness.apply(manifest)
    assert result == {'sequence': 1, 'versions': dict.fromkeys(IDS, '1.0.0')}
    assert harness.engine.available() == result
    assert len(harness.downloads) == 2
    assert harness.verifications[0][1] == b'signed'
    for name in IDS:
        assert '1.0.0' in (harness.engine.addons / name / 'addon.xml').read_text()
    with pytest.raises(UpdateError):
        harness.apply(manifest)
    assert len(harness.downloads) == 2


def test_busy_before_download_and_before_commit(harness):
    manifest = harness.manifest()
    harness.idle_values = [False]
    with pytest.raises(Busy):
        harness.apply(manifest)
    assert harness.downloads == []
    harness.idle_values = [True, False]
    with pytest.raises(Busy):
        harness.apply(manifest)
    assert len(harness.downloads) == 2
    assert list(harness.engine.addons.iterdir()) == []
    assert not harness.engine.journal_path.exists()


def test_signature_rejected_before_json_or_download(harness):
    harness.signature_valid = False
    with pytest.raises(UpdateError, match='Signature'):
        harness.engine.apply(b'not JSON', b'signed')
    assert harness.downloads == []


@pytest.mark.parametrize('key,value', [('schema', True), ('schema', 2), ('channel', 'stable'),
    ('profile', 'coreelec'), ('sequence', True), ('sequence', 0)])
def test_wrong_release_contract(harness, key, value):
    manifest = harness.manifest()
    manifest[key] = value
    with pytest.raises(UpdateError):
        harness.apply(manifest)
    assert harness.downloads == []


def test_duplicate_json_keys_rejected(harness):
    raw = json.dumps(harness.manifest()).replace('"schema": 1', '"schema": 1, "schema": 1').encode()
    with pytest.raises(UpdateError, match='Duplicate'):
        harness.engine.apply(raw, b'signed')
    assert harness.downloads == []


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'foreign', 'version', 'size', 'hash', 'url'])
def test_component_contract(harness, change):
    manifest = harness.manifest()
    if change == 'missing':
        manifest['components'].pop()
    elif change == 'duplicate':
        manifest['components'][1] = dict(manifest['components'][0])
    elif change == 'foreign':
        manifest['components'][0]['id'] = 'plugin.video.other'
    else:
        manifest['components'][0][change if change != 'hash' else 'sha256'] = {
            'version': '01.0.0', 'size': True, 'hash': '0' * 63,
            'url': 'https://github.com/another/project/releases/download/v1/addon.zip'}[change]
    with pytest.raises(UpdateError):
        harness.apply(manifest)
    assert harness.downloads == []


@pytest.mark.parametrize('url', ['http://github.com/2223M1/bobbi-tv/releases/download/v1/a.zip',
    'https://github.com.evil.test/2223M1/bobbi-tv/releases/download/v1/a.zip',
    'https://user@github.com/2223M1/bobbi-tv/releases/download/v1/a.zip',
    'https://github.com/2223M1/bobbi-tv/releases/download/../a.zip',
    'https://github.com/2223M1/bobbi-tv/releases/download/v1/a.zip?token=secret',
    'https://github.com/2223M1/bobbi-tv/releases/download/v1/%2e%2e.zip'])
def test_url_allowlist(url):
    assert not allowed_release_url(url)


def test_github_cdn_is_redirect_only_not_manifest_origin():
    cdn = 'https://release-assets.githubusercontent.com/github-production-release-asset/123/file?sig=fixture'
    assert allowed_release_redirect(cdn)
    assert not allowed_release_url(cdn)
    for value in ('http://release-assets.githubusercontent.com/a',
                  'https://release-assets.githubusercontent.com:443/a',
                  'https://user@release-assets.githubusercontent.com/a',
                  'https://release-assets.githubusercontent.com.evil.test/a',
                  'https://release-assets.githubusercontent.com/a#fragment'):
        assert not allowed_release_redirect(value)


@pytest.mark.parametrize('fault', ['hash', 'size', 'download_error', 'verify_error'])
def test_callback_and_integrity_failures_leave_no_partial_install(harness, fault):
    manifest = harness.manifest()
    item = manifest['components'][0]
    if fault == 'hash':
        harness.blobs[item['url']] = bytes([harness.blobs[item['url']][0] ^ 1]) + harness.blobs[item['url']][1:]
    elif fault == 'size':
        harness.blobs[item['url']] += b'x'
    else:
        def failed(*_):
            raise OSError('offline')
        if fault == 'download_error':
            harness.engine.download = failed
        else:
            harness.engine.verify = failed
    with pytest.raises((UpdateError, OSError)):
        harness.apply(manifest)
    assert list(harness.engine.addons.iterdir()) == []
    assert not harness.engine.journal_path.exists()


@pytest.mark.parametrize('path', ['../escape', '/absolute', IDS[0] + '/../../escape',
    IDS[0] + '/a\\b', IDS[0] + '/a/./b', IDS[0] + '/foo:bar', IDS[0] + '/NUL.txt',
    IDS[0] + '/trail.', 'other.addon/extra'])
def test_archive_traversal_and_nonportable_names(harness, path):
    manifest = harness.manifest()
    # ZipInfo normalizes native Windows separators when creating a fixture;
    # mutate both equal-length local/central names to retain hostile ZIP bytes.
    blob = archive(IDS[0], extra=[(path.replace('\\', '/'), 'bad')])
    if '\\' in path:
        blob = blob.replace(path.replace('\\', '/').encode(), path.encode())
    harness.replace_blob(manifest, blob)
    with pytest.raises(UpdateError):
        harness.apply(manifest)
    assert list(harness.engine.addons.iterdir()) == []


@pytest.mark.parametrize('fault', ['duplicate', 'case_alias', 'symlink', 'bomb', 'wrong_id', 'wrong_version', 'invalid_zip'])
def test_archive_attacks(harness, fault):
    manifest = harness.manifest()
    if fault == 'invalid_zip':
        blob = b'not a ZIP'
    elif fault == 'wrong_id':
        blob = archive(IDS[0], xml_id='plugin.video.other')
    elif fault == 'wrong_version':
        blob = archive(IDS[0], xml_version='9.9.9')
    elif fault == 'symlink':
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as output:
            item = zipfile.ZipInfo(IDS[0] + '/link')
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(item, '../../outside')
        blob = buffer.getvalue()
    else:
        extra = {'duplicate': [(IDS[0] + '/code.py', 'other')],
                 'case_alias': [(IDS[0] + '/CODE.PY', 'other')],
                 'bomb': [(IDS[0] + '/bomb', '0' * 1000000)]}[fault]
        with pytest.warns(UserWarning) if fault == 'duplicate' else _no_warning_context():
            blob = archive(IDS[0], extra=extra)
    harness.replace_blob(manifest, blob)
    with pytest.raises((UpdateError, OSError)):
        harness.apply(manifest)
    assert list(harness.engine.addons.iterdir()) == []


@contextmanager
def _no_warning_context():
    yield


def test_downgrade_even_with_higher_manifest_sequence(harness):
    harness.apply(harness.manifest(sequence=1, version='2.0.0'))
    with pytest.raises(UpdateError, match='downgrade'):
        harness.apply(harness.manifest(sequence=2, version='1.0.0'))
    assert harness.engine.available()['sequence'] == 1


def test_stage_entire_bundle_before_any_swap(harness):
    manifest = harness.manifest()
    second = manifest['components'][1]
    harness.blobs[second['url']] = b'bad second download'
    moves = []
    harness.engine._move = lambda *args: moves.append(args)
    with pytest.raises(UpdateError):
        harness.apply(manifest)
    assert moves == []


def test_swap_failure_rolls_back_all_and_preserves_userdata(harness):
    harness.apply(harness.manifest())
    unrelated = harness.engine.addons / 'unrelated'
    unrelated.mkdir()
    (unrelated / 'keep').write_text('keep')
    userdata = harness.root / 'userdata/addon_data/plugin.video.bobbi'
    userdata.mkdir(parents=True)
    (userdata / 'account').write_text('fixture-only')
    original_move = harness.engine._move
    failed = []
    def move(source, target):
        assert harness.lease_active
        if source.parent.name == 'stage' and target.name == IDS[1] and not failed:
            failed.append(True)
            raise OSError('injected swap error')
        original_move(source, target)
    harness.engine._move = move
    with pytest.raises(OSError):
        harness.apply(harness.manifest(sequence=2, version='2.0.0'))
    assert harness.engine.available()['sequence'] == 1
    for name in IDS:
        assert '1.0.0' in (harness.engine.addons / name / 'addon.xml').read_text()
    assert (unrelated / 'keep').read_text() == 'keep'
    assert (userdata / 'account').read_text() == 'fixture-only'
    assert not harness.engine.journal_path.exists()


@pytest.mark.parametrize('existing', [False, True])
def test_interrupted_move_recovers_before_available(harness, existing):
    if existing:
        harness.apply(harness.manifest())
    original_move = harness.engine._move
    def crash(source, target):
        original_move(source, target)
        if source.parent.name == 'stage':
            raise KeyboardInterrupt('simulated abrupt process interruption')
    harness.engine._move = crash
    with pytest.raises(KeyboardInterrupt):
        harness.apply(harness.manifest(sequence=2, version='2.0.0'))
    assert harness.engine.journal_path.exists()
    harness.engine._move = original_move
    state = harness.engine.available()
    assert state['sequence'] == (1 if existing else 0)
    for name in IDS:
        target = harness.engine.addons / name / 'addon.xml'
        if existing:
            assert '1.0.0' in target.read_text()
        else:
            assert not target.exists()
    assert not harness.engine.journal_path.exists()
    assert harness.engine.recover() is False


def test_lock_prevents_parallel_writer(harness):
    from bobbi_platform.updates import _Lock
    with _Lock(harness.engine.work / 'update.lock'):
        with pytest.raises(Busy):
            harness.engine.available()


def test_symlink_target_rejected(harness, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (harness.engine.addons / IDS[0]).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Host does not permit symlink fixture')
    with pytest.raises(UpdateError):
        harness.apply(harness.manifest())
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('existing,cut', [(False, 1), (False, 2),
    (True, 1), (True, 2), (True, 3), (True, 4)])
def test_every_move_crash_cut_recovers(harness, existing, cut):
    if existing:
        harness.apply(harness.manifest())
    original_move = harness.engine._move
    calls = []
    def crash(source, target):
        original_move(source, target)
        calls.append((source, target))
        if len(calls) == cut:
            raise KeyboardInterrupt('crash cut')
    harness.engine._move = crash
    with pytest.raises(KeyboardInterrupt):
        harness.apply(harness.manifest(sequence=2, version='2.0.0'))
    harness.engine._move = original_move
    assert harness.engine.available()['sequence'] == (1 if existing else 0)
    for name in IDS:
        addon = harness.engine.addons / name / 'addon.xml'
        assert addon.exists() is existing
        if existing:
            assert '1.0.0' in addon.read_text()


@pytest.mark.parametrize('commit_marker', [False, True])
def test_crash_after_state_publication_and_commit_marker(harness, monkeypatch, commit_marker):
    from bobbi_platform import updates
    harness.apply(harness.manifest())
    original_atomic = updates._atomic
    def crash(path, value):
        original_atomic(path, value)
        if ((not commit_marker and path == harness.engine.state_path and value['sequence'] == 2)
                or (commit_marker and path == harness.engine.journal_path and value['phase'] == 'committed')):
            raise KeyboardInterrupt('durable metadata crash cut')
    monkeypatch.setattr(updates, '_atomic', crash)
    with pytest.raises(KeyboardInterrupt):
        harness.apply(harness.manifest(sequence=2, version='2.0.0'))
    monkeypatch.setattr(updates, '_atomic', original_atomic)
    state = harness.engine.available()
    expected = '2.0.0' if commit_marker else '1.0.0'
    assert state['sequence'] == (2 if commit_marker else 1)
    for name in IDS:
        assert expected in (harness.engine.addons / name / 'addon.xml').read_text()


def test_failed_rollback_keeps_journal_for_later_recovery(harness):
    harness.apply(harness.manifest())
    original_move = harness.engine._move
    def failed(source, target):
        if (source.parent.name == 'stage' and target.name == IDS[1]) or source.parent.name == 'backup':
            raise OSError('simulated temporarily unavailable filesystem')
        original_move(source, target)
    harness.engine._move = failed
    with pytest.raises(OSError):
        harness.apply(harness.manifest(sequence=2, version='2.0.0'))
    assert harness.engine.journal_path.exists()
    with pytest.raises(OSError):
        harness.engine.available()
    harness.engine._move = original_move
    assert harness.engine.available()['sequence'] == 1
    for name in IDS:
        assert '1.0.0' in (harness.engine.addons / name / 'addon.xml').read_text()


def test_normalized_roots_cannot_overlap(tmp_path):
    with pytest.raises(UpdateError, match='separate'):
        UpdateEngine(tmp_path / 'addons', tmp_path / 'other/../addons/work', IDS,
                     'preview', 'android', None, None, None, None)


def test_corrupt_or_missing_recovery_data_never_exposes_available_state(harness):
    harness.engine.journal_path.write_text(json.dumps({'transaction': 'a' * 32,
        'phase': 'committing', 'entries': dict.fromkeys(IDS, True),
        'old_state': {'sequence': 0, 'versions': {}}}))
    with pytest.raises(UpdateError, match='missing'):
        harness.engine.available()
    assert harness.engine.journal_path.exists()


def test_recovery_waits_for_idle_lease(harness):
    original_move = harness.engine._move
    def crash(source, target):
        original_move(source, target)
        raise KeyboardInterrupt('cut')
    harness.engine._move = crash
    with pytest.raises(KeyboardInterrupt):
        harness.apply(harness.manifest())
    harness.engine._move = original_move
    harness.idle_values = [False]
    with pytest.raises(Busy):
        harness.engine.available()
    assert harness.engine.journal_path.exists()
    assert harness.engine.available()['sequence'] == 0


def test_other_installer_change_during_download_cannot_be_downgraded(harness):
    original_download = harness.engine.download
    def download(url, maximum):
        target = harness.engine.addons / IDS[0]
        target.mkdir(exist_ok=True)
        (target / 'addon.xml').write_text('<addon id="{}" version="9.0.0"/>'.format(IDS[0]))
        return original_download(url, maximum)
    harness.engine.download = download
    with pytest.raises(UpdateError, match='changed during staging'):
        harness.apply(harness.manifest())
    assert '9.0.0' in (harness.engine.addons / IDS[0] / 'addon.xml').read_text()
    assert not harness.engine.journal_path.exists()

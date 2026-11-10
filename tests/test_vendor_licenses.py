import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from test_ce_general_installer import signing, package

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
SPEC = importlib.util.spec_from_file_location('vendor_licenses', ROOT / 'tools/vendor_licenses.py')
notices = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notices)


def minimal_manifest(raw=b'Official full notice\n'):
    commit = 'a' * 40
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    return {'schema': 1, 'baseline': 'b' * 40, 'documents': [{
        'id': 'example', 'kind': 'full-license', 'file': 'licenses/vendor/example.txt',
        'repository': 'official/example', 'commit': commit, 'source_path': 'LICENSE',
        'source_url': 'https://raw.githubusercontent.com/official/example/' + commit + '/LICENSE',
        'git_blob_sha': blob, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
    }], 'components': [{'id': 'example', 'documents': ['example'], 'status': 'full-upstream-license-retained'}],
        'release_gates': ['not release clearance']}


def write_manifest(root, data):
    path = root / notices.MANIFEST
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def test_checkout_retains_locked_notices_without_claiming_release_clearance():
    result = notices.verify(ROOT)
    assert result['documents'] == 9
    assert 'skin.bobbi.cinema' in result['unresolved_components']
    with pytest.raises(ValueError, match='Unresolved distribution licenses'):
        notices.require_distribution(ROOT)
    assert notices.require_distribution(ROOT, ['script.module.requests'])['documents'] == 9


@pytest.mark.parametrize('field,value', [
    ('commit', 'main'), ('source_url', 'https://example.invalid/LICENSE'),
    ('file', '../escape'), ('file', 'licenses/vendor/../../escape'),
    ('file', 'licenses\\vendor\\escape.txt'), ('source_path', '../LICENSE'),
    ('repository', 'official/example?token=synthetic'), ('bytes', 999999999),
])
def test_manifest_rejects_unpinned_unsafe_sources(field, value):
    data = minimal_manifest()
    data['documents'][0][field] = value
    with pytest.raises(ValueError):
        notices.validate_manifest(data)


def test_manifest_rejects_duplicates_and_unknown_component_refs():
    data = minimal_manifest()
    data['documents'].append(copy.deepcopy(data['documents'][0]))
    with pytest.raises(ValueError, match='Duplicate'):
        notices.validate_manifest(data)
    data = minimal_manifest()
    data['components'][0]['documents'] = ['missing']
    with pytest.raises(ValueError, match='references'):
        notices.validate_manifest(data)


def test_fetch_is_verified_idempotent_and_does_not_overwrite(tmp_path):
    raw = b'Official full notice\n'
    write_manifest(tmp_path, minimal_manifest(raw))
    result = notices.fetch(tmp_path, lambda doc: raw)
    assert result['fetched'] == 1
    assert notices.verify(tmp_path)['documents'] == 1
    assert notices.fetch(tmp_path, lambda doc: pytest.fail('unexpected network'))['fetched'] == 0
    dest = tmp_path / 'licenses/vendor/example.txt'
    dest.write_bytes(b'locally changed')
    with pytest.raises(ValueError, match='digest'):
        notices.fetch(tmp_path, lambda doc: raw)
    assert dest.read_bytes() == b'locally changed'


def test_bad_download_never_creates_notice_output(tmp_path):
    write_manifest(tmp_path, minimal_manifest())
    with pytest.raises(ValueError, match='digest'):
        notices.fetch(tmp_path, lambda doc: b'incorrect')
    assert not (tmp_path / 'licenses/vendor').exists()


def test_download_checks_pinned_git_blob_and_does_not_execute_source(monkeypatch):
    raw = b'Official full notice\n'
    doc = minimal_manifest(raw)['documents'][0]
    called = []
    def run(argv, **kwargs):
        called.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps({
            'encoding': 'base64', 'sha': doc['git_blob_sha'],
            'content': base64.b64encode(raw).decode(),
        }).encode())
    monkeypatch.setattr(notices.subprocess, 'run', run)
    assert notices.download(doc) == raw
    assert called == [['gh', 'api', '--hostname', 'github.com',
                       'repos/official/example/contents/LICENSE?ref=' + 'a' * 40]]


def test_download_errors_do_not_echo_external_output(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ['gh'], stderr=b'synthetic-sensitive-diagnostic')
    monkeypatch.setattr(notices.subprocess, 'run', fail)
    with pytest.raises(ValueError) as result:
        notices.download(minimal_manifest()['documents'][0])
    assert 'synthetic-sensitive' not in str(result.value)


def archive_document(raw=b'Exact locked license\n'):
    from io import BytesIO
    import zipfile
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('script.module.example/LICENSE.txt', raw)
    blob = stream.getvalue()
    doc = dict(id='example', kind='full-license', file='licenses/vendor/example.txt',
        source_kind='locked-archive', source_path='script.module.example/LICENSE.txt',
        archive_url='https://mirrors.kodi.tv/addons/omega/script.module.example/script.module.example-1.0.0.zip',
        archive_sha256=hashlib.sha256(blob).hexdigest(), archive_bytes=len(blob),
        sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    return doc, blob, raw


def test_archive_notice_requires_exact_archive_member_and_document():
    doc, blob, raw = archive_document()
    data = minimal_manifest()
    data['documents'] = [doc]
    notices.validate_manifest(data)
    assert notices.archive_document(doc, blob) == raw
    for changed in (blob[:-1], b'x' + blob[1:]):
        with pytest.raises(ValueError, match='archive differs'):
            notices.archive_document(doc, changed)
    with pytest.raises(ValueError):
        notices.archive_document(dict(doc, source_path='../LICENSE.txt'), blob)
    with pytest.raises(ValueError):
        notices.archive_document(dict(doc, sha256='0'*64), blob)


@pytest.mark.parametrize('change', [dict(source_path='../LICENSE.txt'), dict(archive_url='http://mirrors.kodi.tv/file.zip'),
                                   dict(archive_sha256='not-a-digest'), dict(archive_bytes=True)])
def test_archive_sources_cannot_escape_lock(change):
    doc, _, _ = archive_document()
    data = minimal_manifest()
    data['documents'] = [dict(doc, **change)]
    with pytest.raises(ValueError): notices.validate_manifest(data)


def test_unresolved_cannot_be_relabelled_without_full_license_evidence():
    data = minimal_manifest()
    data['documents'][0]['kind'] = 'metadata-evidence-not-license'
    with pytest.raises(ValueError, match='full license'):
        notices.validate_manifest(data)


def test_only_exact_listed_delivery_paths_are_allowed():
    from delivery_policy import require_clean
    require_clean(['licenses/upstream-LICENSE.txt'], 'script.module.requests')
    require_clean(['script.module.requests/licenses/upstream-LICENSE.txt'])
    for path in ('licenses/private-NOTICE.txt', 'LICENSE.txt', 'licenses/../upstream-LICENSE.txt'):
        with pytest.raises(ValueError): require_clean([path], 'script.module.requests')


@pytest.mark.parametrize('fault', ['missing', 'changed', 'duplicate'])
def test_final_component_archive_license_bytes_are_required(fault):
    from io import BytesIO
    import zipfile
    doc = next(doc for doc in notices.load_manifest()['documents'] if doc['id'] == 'script.module.requests')
    raw = (ROOT / doc['file']).read_bytes()
    name = 'script.module.requests/licenses/upstream-LICENSE.txt'
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        if fault != 'missing': archive.writestr(name, raw if fault != 'changed' else b'x' + raw[1:])
        if fault == 'duplicate':
            with pytest.warns(UserWarning): archive.writestr(name, raw)
    with zipfile.ZipFile(BytesIO(stream.getvalue())) as archive, pytest.raises(ValueError):
        notices.verify_component_archive('script.module.requests', archive)


def test_signed_complete_and_nested_entry_keep_every_pinned_notice(tmp_path, signing):
    from io import BytesIO
    import zipfile
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from bobbi_platform.offline_updates import SignedBundle
    source = package(tmp_path / 'source.zip', signing)
    with SignedBundle(source, signing[1], 'coreelec') as signed:
        signed.check_all()
        with pytest.raises(ValueError, match='Missing'):
            notices.verify_bundle_notices(signed)
    data = notices.load_manifest()
    docs = {doc['id']: doc for doc in data['documents']}
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read('release.json'))
        members = {row['file']: archive.read(row['file']) for row in manifest['components']}
    for row in manifest['components']:
        stream = BytesIO()
        with zipfile.ZipFile(BytesIO(members[row['file']])) as old, zipfile.ZipFile(stream, 'w') as target:
            for name in old.namelist(): target.writestr(name, old.read(name))
            for delivery in data['deliveries']:
                if delivery['component'] == row['id']:
                    target.writestr(row['id'] + '/' + delivery['path'],
                                    (ROOT / docs[delivery['document']]['file']).read_bytes())
        blob = stream.getvalue()
        row.update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
        members[row['file']] = blob
    raw = json.dumps(manifest).encode()
    bundle = tmp_path / 'complete.zip'
    with zipfile.ZipFile(bundle, 'w') as target:
        target.writestr('release.json', raw)
        target.writestr('release.sig', base64.b64encode(signing[0].sign(raw, padding.PKCS1v15(), hashes.SHA256())))
        for name, blob in members.items(): target.writestr(name, blob)
    outer = tmp_path / 'entry.zip'
    with zipfile.ZipFile(outer, 'w') as target:
        target.writestr('script.bobbi.start/resources/complete.bobbi-update.zip', bundle.read_bytes())
    with zipfile.ZipFile(outer) as archive:
        extracted = tmp_path / 'nested.zip'
        extracted.write_bytes(archive.read('script.bobbi.start/resources/complete.bobbi-update.zip'))
    with SignedBundle(extracted, signing[1], 'coreelec') as signed:
        signed.check_all()
        notices.verify_bundle_notices(signed)

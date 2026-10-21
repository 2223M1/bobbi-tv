import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

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


def test_checked_in_notices_and_truthful_unresolved_status():
    result = notices.verify(ROOT)
    assert result['documents'] == 6
    assert result['unresolved_components'] == ['tmdbv3api', 'bencodepy-legacy']
    data = notices.load_manifest(ROOT)
    metadata = next(d for d in data['documents'] if d['id'] == 'tmdbv3api-metadata')
    assert metadata['kind'] == 'metadata-evidence-not-license'
    assert 'setup-evidence' in metadata['file']


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

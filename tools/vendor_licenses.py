"""Fetch exact pinned public dependency notices, or verify them offline.

Only manifest-listed metadata/license documents are downloaded. Source package
code is never executed, and no whole-project license grant is inferred.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from provenance_document import read_source, records

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'licenses/THIRD-PARTY.json'
MAX_DOCUMENT = 128 * 1024


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def load_manifest(root=ROOT):
    data = json.loads(read_source(root, MANIFEST))
    validate_manifest(data)
    return data


def validate_manifest(data):
    if data.get('schema') != 1 or not _hex(data.get('baseline'), 40):
        raise ValueError('Unsupported notice manifest')
    ids, outputs = set(), set()
    for doc in data['documents']:
        name = doc['file']
        path = PurePosixPath(name)
        if (not name.startswith('licenses/vendor/') or name != path.as_posix()
                or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name):
            raise ValueError('Invalid notice destination')
        if doc['id'] in ids or name.casefold() in outputs:
            raise ValueError('Duplicate notice destination or identifier')
        ids.add(doc['id'])
        outputs.add(name.casefold())
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', doc['repository']):
            raise ValueError('Invalid public repository identifier')
        if not all((_hex(doc['commit'], 40), _hex(doc['git_blob_sha'], 40), _hex(doc['sha256'], 64))):
            raise ValueError('Notice must pin an immutable commit and digests')
        source = PurePosixPath(doc['source_path'])
        if (source.is_absolute() or '..' in source.parts or source.as_posix() != doc['source_path']
                or not re.fullmatch(r'[A-Za-z0-9_./-]+', doc['source_path'])):
            raise ValueError('Invalid public source path')
        expected = 'https://raw.githubusercontent.com/{}/{}/{}'.format(
            doc['repository'], doc['commit'], doc['source_path'])
        if doc['source_url'] != expected or not 0 < doc['bytes'] <= MAX_DOCUMENT:
            raise ValueError('Unpinned source URL or invalid document size')
        if doc['kind'] not in ('full-license', 'metadata-evidence-not-license'):
            raise ValueError('Unknown notice evidence kind')
    component_ids = set()
    for component in data['components']:
        if component['id'] in component_ids or not set(component['documents']) <= ids:
            raise ValueError('Invalid component notice references')
        component_ids.add(component['id'])


def verify_bytes(doc, raw):
    if len(raw) != doc['bytes'] or hashlib.sha256(raw).hexdigest() != doc['sha256']:
        raise ValueError('Notice content digest mismatch: ' + doc['id'])
    blob = b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw
    if hashlib.sha1(blob).hexdigest() != doc['git_blob_sha']:
        raise ValueError('Notice Git blob mismatch: ' + doc['id'])
    raw.decode('utf-8')


def download(doc):
    """Use gh's configured HTTPS transport; never pass auth values ourselves."""
    endpoint = 'repos/{}/contents/{}?ref={}'.format(
        doc['repository'], doc['source_path'], doc['commit'])
    try:
        result = subprocess.run(['gh', 'api', '--hostname', 'github.com', endpoint],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        raise ValueError('Pinned public notice download failed: ' + doc['id']) from None
    if len(result.stdout) > 2 * MAX_DOCUMENT:
        raise ValueError('Unexpected notice API response size')
    try:
        response = json.loads(result.stdout)
        if response['encoding'] != 'base64' or response['sha'] != doc['git_blob_sha']:
            raise ValueError
        raw = base64.b64decode(''.join(response['content'].split()), validate=True)
        verify_bytes(doc, raw)
        return raw
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ValueError('Pinned public notice response rejected: ' + doc['id']) from None


def _destination(root, name):
    root = Path(root).resolve()
    dest = root / name
    for path in (dest, *dest.parents):
        if path == root:
            break
        if path.is_symlink():
            raise ValueError('Symlink notice destination rejected')
    if root not in dest.resolve().parents:
        raise ValueError('Notice destination escaped project')
    return dest


def fetch(root=ROOT, fetcher=download):
    """Verify every payload before writing any missing notice; no overwrite."""
    data = load_manifest(root)
    pending = []
    embedded = records(root)
    for doc in data['documents']:
        dest = _destination(root, doc['file'])
        if doc['file'] in embedded:
            verify_bytes(doc, read_source(root, doc['file']))
        elif dest.exists():
            verify_bytes(doc, dest.read_bytes())
        else:
            raw = fetcher(doc)
            verify_bytes(doc, raw)
            pending.append((dest, raw))
    for dest, raw in pending:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(raw)
    return summary(data, len(pending))


def summary(data, fetched=0):
    unresolved = [c['id'] for c in data['components'] if c['status'].startswith('unresolved-')]
    return {'status': 'PINNED_NOTICES_VERIFIED_NOT_RELEASE_CLEARANCE',
            'documents': len(data['documents']), 'fetched': fetched,
            'unresolved_components': unresolved, 'release_gates': data['release_gates']}


def verify(root=ROOT):
    data = load_manifest(root)
    for doc in data['documents']:
        dest = _destination(root, doc['file'])
        if not dest.is_file() and doc['file'] not in records(root):
            raise ValueError('Missing pinned notice: ' + doc['id'])
        verify_bytes(doc, read_source(root, doc['file']))
    return summary(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='Fetch missing pinned notice documents; default is offline verification')
    args = parser.parse_args()
    try:
        print(json.dumps(fetch() if args.fetch else verify(), indent=2))
    except ValueError as error:
        parser.exit(1, str(error) + '\n')

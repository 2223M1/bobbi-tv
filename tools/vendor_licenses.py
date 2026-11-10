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
from io import BytesIO
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'licenses/THIRD-PARTY.json'
MAX_DOCUMENT = 128 * 1024


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def load_manifest(root=ROOT):
    data = json.loads((Path(root) / MANIFEST).read_text(encoding='utf-8'))
    validate_manifest(data)
    return data


def validate_manifest(data):
    if type(data.get('schema')) is not int or data['schema'] != 1 or not _hex(data.get('baseline'), 40):
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
        if not _hex(doc['sha256'], 64) or type(doc['bytes']) is not int or not 0 < doc['bytes'] <= MAX_DOCUMENT:
            raise ValueError('Invalid document digest/size')
        if doc.get('source_kind') == 'locked-archive':
            url = urlsplit(doc['archive_url'])
            member = PurePosixPath(doc['source_path'])
            if (url.scheme != 'https' or url.netloc != 'mirrors.kodi.tv' or url.query or url.fragment
                    or not re.fullmatch(r'/addons/omega/[a-z0-9_.-]+/[a-zA-Z0-9_.+-]+\.zip', url.path)
                    or not _hex(doc['archive_sha256'], 64) or type(doc['archive_bytes']) is not int
                    or not 0 < doc['archive_bytes'] <= 16 * 1024**2 or member.is_absolute()
                    or '..' in member.parts or member.as_posix() != doc['source_path'] or '\\' in doc['source_path']):
                raise ValueError('Invalid pinned archive source')
        elif not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', doc['repository']):
            raise ValueError('Invalid public repository identifier')
        elif not all((_hex(doc['commit'], 40), _hex(doc['git_blob_sha'], 40), _hex(doc['sha256'], 64))):
            raise ValueError('Notice must pin an immutable commit and digests')
        source = PurePosixPath(doc['source_path'])
        if (source.is_absolute() or '..' in source.parts or source.as_posix() != doc['source_path']
                or not re.fullmatch(r'[A-Za-z0-9_./-]+', doc['source_path'])):
            raise ValueError('Invalid public source path')
        if doc.get('source_kind') != 'locked-archive':
            expected = 'https://raw.githubusercontent.com/{}/{}/{}'.format(
                doc['repository'], doc['commit'], doc['source_path'])
            if doc['source_url'] != expected:
                raise ValueError('Unpinned source URL or invalid document size')
        if doc['kind'] not in ('full-license', 'attribution-notice', 'metadata-evidence-not-license'):
            raise ValueError('Unknown notice evidence kind')
        if doc['kind'] == 'full-license' and PurePosixPath(doc['source_path']).suffix == '.xml':
            raise ValueError('Metadata is not a full license')
    component_ids = set()
    for component in data['components']:
        if component['id'] in component_ids or not set(component['documents']) <= ids:
            raise ValueError('Invalid component notice references')
        component_ids.add(component['id'])
        if component['status'] not in ('full-upstream-license-retained', 'unresolved-source', 'unresolved-full-license'):
            raise ValueError('Invalid component license status')
        if component['status'] == 'full-upstream-license-retained' and not any(
                doc['id'] in component['documents'] and doc['kind'] == 'full-license' for doc in data['documents']):
            raise ValueError('Resolved component requires full license evidence')
    destinations = set()
    for delivery in data.get('deliveries', []):
        path = PurePosixPath(delivery['path'])
        if (delivery['document'] not in ids or not re.fullmatch(r'[a-z0-9_.-]+', delivery['component'])
                or not delivery['path'].startswith('licenses/') or '..' in path.parts
                or path.is_absolute() or path.as_posix() != delivery['path'] or '\\' in delivery['path']
                or (delivery['component'], delivery['path']) in destinations):
            raise ValueError('Invalid notice delivery')
        destinations.add((delivery['component'], delivery['path']))


def verify_bytes(doc, raw):
    if len(raw) != doc['bytes'] or hashlib.sha256(raw).hexdigest() != doc['sha256']:
        raise ValueError('Notice content digest mismatch: ' + doc['id'])
    blob = b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw
    if doc.get('git_blob_sha') and hashlib.sha1(blob).hexdigest() != doc['git_blob_sha']:
        raise ValueError('Notice Git blob mismatch: ' + doc['id'])
    raw.decode('utf-8')


def download(doc):
    """Use gh's configured HTTPS transport; never pass auth values ourselves."""
    if doc.get('source_kind') == 'locked-archive':
        with urlopen(doc['archive_url'], timeout=30) as response:
            raw = response.read(doc['archive_bytes'] + 1)
        return archive_document(doc, raw)
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


def archive_document(doc, raw):
    if len(raw) != doc['archive_bytes'] or hashlib.sha256(raw).hexdigest() != doc['archive_sha256']:
        raise ValueError('Pinned notice archive differs')
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        members = [row for row in archive.infolist() if row.filename == doc['source_path']]
        if len(members) != 1 or members[0].file_size != doc['bytes'] or members[0].flag_bits & 1:
            raise ValueError('Invalid notice archive member')
        result = archive.read(members[0])
    verify_bytes(doc, result)
    return result


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
    for doc in data['documents']:
        dest = _destination(root, doc['file'])
        if dest.exists():
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
    actual = {path.parent.name for path in (Path(root) / 'third_party/addons').glob('*/addon.xml')}
    if not actual <= {row['id'] for row in data['components']}:
        raise ValueError('Unlisted third-party component')
    lock_path = Path(root) / 'release/kodi-vendors.json'
    if lock_path.exists():
        locks = json.loads(lock_path.read_text(encoding='utf-8'))
        for doc in data['documents']:
            if doc['id'] in locks:
                lock = locks[doc['id']]
                relative = doc['source_path'].removeprefix(doc['id'] + '/')
                if (lock['files'].get(relative) != doc['sha256'] or
                        doc.get('source_kind') == 'locked-archive' and any(
                            doc.get(key) != lock.get(key) for key in ('archive_url', 'archive_sha256', 'archive_bytes')) or
                        doc.get('source_kind') != 'locked-archive' and doc.get('commit') != lock.get('commit')):
                    raise ValueError('Notice differs from frozen vendor source')
    for doc in data['documents']:
        dest = _destination(root, doc['file'])
        if not dest.is_file():
            raise ValueError('Missing pinned notice: ' + doc['id'])
        verify_bytes(doc, dest.read_bytes())
    docs = {doc['id']: doc for doc in data['documents']}
    for delivery in data.get('deliveries', []):
        bases = [Path(root) / base / delivery['component'] for base in ('addons', 'third_party/addons')]
        roots = [base for base in bases if (base / 'addon.xml').is_file()]
        if len(roots) != 1:
            raise ValueError('Unknown notice component')
        verify_bytes(docs[delivery['document']], _destination(roots[0], delivery['path']).read_bytes())
    return summary(data)


def require_distribution(root=ROOT, components=None):
    result = verify(root)
    unresolved = set(result['unresolved_components'])
    if components is not None:
        if not set(components) <= {row['id'] for row in load_manifest(root)['components']}:
            raise ValueError('Unlisted distribution component')
        unresolved &= set(components)
    if unresolved:
        raise ValueError('Unresolved distribution licenses: ' + ', '.join(sorted(unresolved)))
    return result


def verify_component_archive(component, archive, root=ROOT):
    """Check final ZIP bytes, not just a source-tree notice claim."""
    data = load_manifest(root)
    from delivery_policy import EXCLUDE
    allowed = {row['component'] + '/' + row['path'] for row in data.get('deliveries', [])}
    if any(EXCLUDE.search(name) and name not in allowed for name in archive.namelist()):
        raise ValueError('Unlisted packaged notice')
    docs = {doc['id']: doc for doc in data['documents']}
    for delivery in data.get('deliveries', []):
        if delivery['component'] == component:
            name = component + '/' + delivery['path']
            if archive.namelist().count(name) != 1:
                raise ValueError('Missing or duplicate packaged notice')
            verify_bytes(docs[delivery['document']], archive.read(name))


def verify_bundle_notices(signed, root=ROOT):
    """Shared notice gate after SignedBundle.check_all; no second package parser."""
    for row in signed.manifest['components']:
        with zipfile.ZipFile(BytesIO(signed.read(row['file'], row['size']))) as archive:
            verify_component_archive(row['id'], archive, root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='Fetch missing pinned notice documents; default is offline verification')
    args = parser.parse_args()
    try:
        print(json.dumps(fetch() if args.fetch else verify(), indent=2))
    except ValueError as error:
        parser.exit(1, str(error) + '\n')

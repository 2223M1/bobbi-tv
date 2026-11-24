"""Read exact historical negative-control sources without old branches or network."""
import hashlib
import json
from pathlib import Path
import zlib


FIXTURES = Path(__file__).parent / 'fixtures' / 'frozen_history'


def source_bytes(commit, path, *, directory=FIXTURES):
    entries = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))['commits']
    try:
        record = entries[commit]['files'][path]
    except KeyError as exc:
        raise ValueError(f'Unregistered historical source {commit}:{path}') from exc
    try:
        raw = zlib.decompress((directory / (record['sha256'] + '.zlib')).read_bytes())
    except (OSError, zlib.error) as exc:
        raise ValueError(f'Missing or damaged historical source {commit}:{path}') from exc
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != record['sha256'] or blob != record['git_blob']:
        raise ValueError(f'Historical source identity mismatch {commit}:{path}')
    return raw

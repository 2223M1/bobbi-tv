"""Classify known upstream-source scan findings without printing key material."""
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'a86d8fa7fd4e07605f240fe69bf299392f7cb023'
FILES = {
    'README.md': 'upstream documented curl authentication examples',
    'server/web/sslcerts/manage_test.go': 'upstream TLS unit-test key fixture; not used as a deployment key',
    'server/web/pages/template/pages/index.html': 'upstream browser Firebase public configuration',
    'web/public/index.html': 'upstream browser Firebase public configuration',
}


def main():
    records = []
    with zipfile.ZipFile(ROOT / 'dist/public-alpha/TorrServer-source-MatriX.147.zip') as archive:
        for name, reason in FILES.items():
            local = archive.read('TorrServer-' + COMMIT + '/' + name)
            with urlopen('https://raw.githubusercontent.com/YouROK/TorrServer/' + COMMIT + '/' + name, timeout=20) as response:
                official = response.read(4 * 1024 * 1024)
            if local != official:
                raise ValueError('Corresponding-source file differs from upstream')
            if 'index.html' in name and not re.search(b'firebase', local, re.I):
                raise ValueError('Public web configuration classification changed')
            if name.endswith('_test.go') and b'func Test' not in local:
                raise ValueError('Test fixture classification changed')
            records.append(dict(path=name, reason=reason, matched_upstream=True,
                sha256=hashlib.sha256(local).hexdigest()))
    result = dict(upstream_commit=COMMIT, findings=5, affected_files=records,
        personal_secrets=False, source_modified=False,
        notes='Original corresponding source is retained intact. These are not the bobbi signer, cloud sessions, SSH credentials or NAS passwords. No broad secret suppression was added.')
    (ROOT / 'release/upstream-scan-review.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Five upstream findings classified across four byte-matched official files; no secret values emitted')


if __name__ == '__main__':
    main()

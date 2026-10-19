"""Promote the pinned, licensed Segno QR renderer with its original notices."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def promote():
    source = ROOT / 'staging/baseline/plugin.video.bobbi/lib/vendor/segno'
    proof = json.loads((ROOT / 'staging/baseline/export-manifest.json').read_text(encoding='utf-8'))
    target = ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/_vendor/segno'
    for path in sorted(source.glob('*.py')):
        key = 'plugin.video.bobbi/lib/vendor/segno/' + path.name
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != proof['files'][key]['sha256']:
            raise ValueError('QR source input differs from pinned baseline')
        target.mkdir(parents=True, exist_ok=True)
        (target / path.name).write_bytes(raw)
    (target / 'LICENSE').write_bytes((ROOT / 'licenses/vendor/segno-1.6.6-LICENSE.txt').read_bytes())
    print('Pinned Segno QR sources and BSD notice promoted.')


if __name__ == '__main__':
    promote()

"""Unauthenticated consumer-side repository verification, with bounded downloads."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://raw.githubusercontent.com/2223M1/bobbi-tv/main/repository/'


def read(name, limit):
    with urlopen(Request(BASE + name, headers={'Cache-Control': 'no-cache',
                        'User-Agent': 'bobbi-release-verification'}), timeout=25) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Public response exceeded expected size: ' + name)
    return raw


def main():
    expected = json.loads((ROOT / 'repository/manifest.json').read_text())
    manifest = json.loads(read('manifest.json', 65536))
    if manifest != expected:
        raise ValueError('Remote manifest differs from local release')
    xml = read('addons.xml', 1024 * 1024)
    if hashlib.sha256(xml).hexdigest() != read('addons.xml.sha256', 128).decode().strip():
        raise ValueError('Remote index checksum mismatch')
    if {node.attrib['id'] for node in ET.fromstring(xml)} != {row['id'] for row in expected['components']}:
        raise ValueError('Remote index component mismatch')
    def verify(row):
        digest = read(row['file'] + '.sha256', 128).decode().strip()
        raw = read(row['file'], row['bytes'])
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != digest or digest != row['sha256']:
            raise ValueError('Remote component checksum mismatch: ' + row['id'])
        return row['id']
    with ThreadPoolExecutor(max_workers=3) as pool:
        components = list(pool.map(verify, expected['components']))
    print(json.dumps(dict(public_unauthenticated_access=True, index_verified=True,
                          package_sha256_verified=len(components)), indent=2))


if __name__ == '__main__':
    main()

"""The Kodi feed distributes a small launcher, not independently mixed cinema modules."""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from bobbi_platform.online_updates import parse_offer

ROOT = Path(__file__).resolve().parents[1]


def test_published_feed_contains_only_repository_and_independent_bootstrap():
    feed = ROOT/'repository'
    index = ET.parse(feed/'addons.xml').getroot()
    assert {node.get('id') for node in index} == {'repository.bobbi', 'script.bobbi.start'}
    for node in index:
        name, version = node.get('id'), node.get('version')
        raw = (feed/name/(name+'-'+version+'.zip')).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == (feed/name/(name+'-'+version+'.zip.sha256')).read_text()
        with zipfile.ZipFile(feed/name/(name+'-'+version+'.zip')) as package:
            assert package.read(name+'/addon.xml') == (ROOT/'addons'/name/'addon.xml').read_bytes()
            if name == 'script.bobbi.start':
                assert len(raw) < 1024*1024
                names = package.namelist()
                assert name+'/bootstrap/bobbi_platform/online_updates.py' in names
                assert not any('complete.bobbi-update.zip' in p or 'userdata/' in p for p in names)
                for path in names:
                    if path.startswith(name+'/bootstrap/bobbi_platform/'):
                        source = ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform'/path.rsplit('/', 1)[1]
                        assert package.read(path) == source.read_bytes()
            else:
                assert name+'/default.py' not in package.namelist()
    repo = ET.parse(ROOT/'addons/repository.bobbi/addon.xml').getroot()
    extension = repo.find('extension[@point="xbmc.addon.repository"]')
    assert extension is not None
    assert extension.find('./dir/info').text.endswith('/main/repository/addons.xml')
    offer = parse_offer((feed/'current.json').read_bytes())
    assert offer['tag'] == 'ce2054' and offer['sequence'] == 2026102054

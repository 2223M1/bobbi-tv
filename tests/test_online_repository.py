"""The Kodi feed distributes a small launcher, not independently mixed cinema modules."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from bobbi_platform.online_updates import parse_offer

ROOT = Path(__file__).resolve().parents[1]


def test_published_feed_contains_only_repository_and_independent_bootstrap():
    # A checked-in feed describes the published release, not unpromoted source.
    # Never rewrite an immutable ZIP merely to match a candidate checkout.
    feed = ROOT/'repository'
    index = ET.parse(feed/'addons.xml').getroot()
    assert {node.get('id') for node in index} == {'repository.bobbi', 'script.bobbi.start'}
    for node in index:
        name, version = node.get('id'), node.get('version')
        raw = (feed/name/(name+'-'+version+'.zip')).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == (feed/name/(name+'-'+version+'.zip.sha256')).read_text()
        with zipfile.ZipFile(feed/name/(name+'-'+version+'.zip')) as package:
            assert package.testzip() is None
            assert len(package.namelist()) == len(set(package.namelist()))
            assert ET.tostring(ET.fromstring(package.read(name+'/addon.xml'))) == ET.tostring(node).strip()
            if name == 'script.bobbi.start':
                assert len(raw) < 1024*1024
                names = package.namelist()
                assert name+'/bootstrap/bobbi_platform/online_updates.py' in names
                assert not any('complete.bobbi-update.zip' in p or 'userdata/' in p for p in names)
            else:
                assert name+'/default.py' not in package.namelist()
    repo = ET.parse(ROOT/'addons/repository.bobbi/addon.xml').getroot()
    extension = repo.find('extension[@point="xbmc.addon.repository"]')
    assert extension is not None
    assert extension.find('./dir/info').text.endswith('/main/repository/addons.xml')
    offer = parse_offer((feed/'current.json').read_bytes())
    assert offer['tag'] == 'ce2054' and offer['sequence'] == 2026102054


def test_candidate_bootstrap_imports_without_installed_core_or_platform(tmp_path):
    sys.path.insert(0, str(ROOT/'tools'))
    from build_ce_entry import BOOTSTRAP
    assert 'online_transport.py' in BOOTSTRAP
    target = tmp_path/'bobbi_platform'
    target.mkdir()
    for name in BOOTSTRAP:
        shutil.copyfile(ROOT/'addons/script.module.bobbi.platform/lib/bobbi_platform'/name, target/name)
    subprocess.run([sys.executable, '-I', '-B', '-c',
        'import sys; sys.path.insert(0, sys.argv[1]); '
        'from bobbi_platform.online_updates import latest, download; '
        'from bobbi_platform.ce_install_ui import main; '
        'assert "bobbi_core" not in sys.modules', str(tmp_path)],
        cwd=tmp_path, check=True, timeout=15)

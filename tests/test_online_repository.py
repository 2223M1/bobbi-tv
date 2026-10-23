"""The Kodi feed distributes a small launcher, not independently mixed cinema modules."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType
import xml.etree.ElementTree as ET
import zipfile

import pytest

from bobbi_platform.online_updates import MIRROR_FEED, parse_offer, release_url
from bobbi_platform.updates import UpdateError

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
    assert extension.find('./dir/info').text == MIRROR_FEED + 'addons.xml'
    offer = parse_offer((feed/'current.json').read_bytes())
    assert offer['tag'] == 'ce2057' and offer['sequence'] == 2026102057


@pytest.mark.parametrize('algorithm', ['sha256', 'md5'])
def test_published_index_matches_its_change_and_download_digests(algorithm):
    feed = ROOT/'repository'
    assert hashlib.new(algorithm, (feed/'addons.xml').read_bytes()).hexdigest() == (
        feed/('addons.xml.' + algorithm)).read_text(encoding='ascii')


def test_github_discovery_still_works_with_actual_ce2054_entry():
    # Do not turn the GitHub fallback index into a mirror-only migration gate.
    # Run the shipped old parser, not a reimplementation of its contract.
    old = ROOT/'repository/script.bobbi.start/script.bobbi.start-0.2.42.zip'
    name = 'script.bobbi.start/bootstrap/bobbi_platform/online_updates.py'
    with zipfile.ZipFile(old) as archive:
        legacy = ModuleType('bobbi_platform._published_ce2054_online')
        exec(compile(archive.read(name), str(old) + '/' + name, 'exec'), legacy.__dict__)
    current = (ROOT/'repository/current.json').read_bytes()
    offer = legacy.parse_offer(current)
    assert offer == parse_offer(current)
    assert offer['url'] == release_url(offer['tag'], 'github')
    with pytest.raises(UpdateError, match='ONLINE_OFFER_INVALID'):
        legacy.parse_offer(json.dumps(dict(offer, url=release_url(offer['tag'], 'gitee'))))


def test_actual_published_launcher_bootstraps_without_installed_modules(tmp_path):
    index = ET.parse(ROOT/'repository/addons.xml').getroot()
    entry = next(node for node in index if node.get('id') == 'script.bobbi.start')
    package = ROOT/'repository/script.bobbi.start'/('script.bobbi.start-' + entry.get('version') + '.zip')
    prefix = 'script.bobbi.start/bootstrap/'
    with zipfile.ZipFile(package) as archive:
        for name in archive.namelist():
            if name.startswith(prefix):
                relative = Path(name[len(prefix):])
                assert '..' not in relative.parts and not relative.is_absolute()
                target = tmp_path/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
    subprocess.run([sys.executable, '-I', '-B', '-c',
        'import sys; sys.path.insert(0, sys.argv[1]); '
        'from bobbi_platform.ce_install_ui import main; '
        'from bobbi_platform.online_updates import OFFER_URL, latest, download; '
        'assert OFFER_URL == sys.argv[2]; '
        'assert "bobbi_core" not in sys.modules', str(tmp_path), MIRROR_FEED + 'current.json'],
        cwd=tmp_path, check=True, timeout=15)


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

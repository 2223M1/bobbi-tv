import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_release
from bobbi_platform import pair_code
from bobbi_platform.native_engine import BINARIES, SETTINGS


def test_entire_dependency_graph_closed():
    roots = build_release.sources()
    for addon, path in roots.items():
        xml = ET.parse(path / 'addon.xml').getroot()
        for item in xml.findall('./requires/import'):
            if item.get('optional') != 'true':
                assert item.get('addon') in set(roots) | build_release.OFFICIAL
    assert {'script.bobbi.start', 'repository.bobbi', 'skin.bobbi.cinema'} <= set(roots)


def test_public_inventory_is_exact():
    import json
    recorded = json.loads(build_release.INVENTORY.read_text())['components']
    roots = build_release.sources()
    assert set(recorded) == set(roots)
    for addon, path in roots.items():
        assert build_release.files(path) == recorded[addon], addon


def test_retired_repository_has_no_anonymous_endpoint_and_packages_keep_hashes():
    import hashlib
    root = ET.parse(ROOT / 'addons/repository.bobbi/addon.xml').getroot()
    assert root.find("./extension[@point='xbmc.addon.repository']") is None
    assert root.findtext('./extension/dir/datadir') is None
    assert (ROOT / 'addons/repository.bobbi/default.py').is_file()
    repository = ROOT / 'repository'
    for path in repository.glob('*/*.zip'):
        assert path.with_suffix('.zip.sha256').read_text() == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (repository / 'addons.xml.sha256').read_text() == hashlib.sha256((repository / 'addons.xml').read_bytes()).hexdigest()


@pytest.mark.parametrize('value', ['', 'abcdef', '12345', '1234567', '123456\n', 123456])
def test_pair_code_rejects_non_codes(value):
    with pytest.raises(ValueError):
        pair_code.exchange(value)


def test_ce_engine_is_pinned_and_not_a_media_transform():
    assert set(BINARIES) == {'arm7', 'arm64'}
    assert all(size > 60_000_000 and len(digest) == 64 for size, digest in BINARIES.values())
    assert SETTINGS['BitTorr']['UseDisk'] is False
    assert SETTINGS['BitTorr']['DisableUPNP'] is True
    assert SETTINGS['BitTorr']['EnableDLNA'] is False


def test_current_sources_use_portable_transport_and_explicit_setup():
    root = ROOT / 'addons/plugin.video.bobbi/lib'
    assert 'from lib.clients.portable_http import iter_events' in (root / 'clients/jackett_http.py').read_text(encoding='utf-8')
    assert '"bobbi_setup"' in (root / 'router.py').read_text(encoding='utf-8')
    assert 'RunScript(script.bobbi.setup,updates)' in (root / 'navigation.py').read_text(encoding='utf-8')

"""Regression tests for EXT-01 (QR dedup), EXT-02 (legacy packaging retirement), and EXT-03 (0-ref clients)."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from bobbi_platform.qr import write_png

ROOT = Path(__file__).resolve().parents[1]


def test_ext_01_public_qr_interface_and_single_segno_copy(tmp_path):
    assert not (ROOT / 'addons/plugin.video.bobbi/lib/vendor/segno').exists()
    assert (ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/_vendor/segno/__init__.py').is_file()

    dest = tmp_path / 'nested' / 'sample.png'
    out = write_png('https://example.invalid/pair#token', dest, scale=8, border=4)
    assert Path(out) == dest
    raw = dest.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR'

    with pytest.raises(ValueError, match='QR_CONTENT_INVALID'):
        write_png('', dest)
    with pytest.raises(ValueError, match='QR_PARAMETERS_INVALID'):
        write_png('https://example.invalid', dest, scale=0)

    platform_xml = ET.parse(ROOT / 'addons/script.module.bobbi.platform/addon.xml').getroot()
    plugin_xml = ET.parse(ROOT / 'addons/plugin.video.bobbi/addon.xml').getroot()
    platform_ver = tuple(int(x) for x in platform_xml.attrib['version'].split('.'))
    req = next(
        node.attrib['version']
        for node in plugin_xml.findall('./requires/import')
        if node.attrib.get('addon') == 'script.module.bobbi.platform'
    )
    assert tuple(int(x) for x in req.split('.')) >= (0, 1, 99)
    assert platform_ver >= tuple(int(x) for x in req.split('.'))


def test_ext_02_legacy_round_scripts_retired_and_delivery_policy_intact():
    for name in (
        'package_ce2021_github.py',
        'package_ce2024_handoff.py',
        'package_ce2028_handoff.py',
    ):
        assert not (ROOT / 'tools' / name).exists()
    assert (ROOT / 'tools/delivery_policy.py').is_file()


def test_ext_03_zero_reference_clients_removed_without_breaking_active_domain_types():
    clients_dir = ROOT / 'addons/plugin.video.bobbi/lib/clients'
    for retired in ('anizip.py', 'fma.py', 'medifusion.py', 'peerflix.py'):
        assert not (clients_dir / retired).exists()

    plugin_root = str(ROOT / 'addons/plugin.video.bobbi')
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    from lib.domain.source_types import Indexer
    assert Indexer.PEERFLIX == 'Peerflix'
    assert Indexer.MEDIAFUSION == 'MediaFusion'
    utils_src = (ROOT / 'addons/plugin.video.bobbi/lib/utils/general/utils.py').read_text(encoding='utf-8')
    assert 'PEERFLIX' in utils_src

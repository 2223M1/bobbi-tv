import ast
import importlib.util
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_build', ROOT / 'tools/build_preview.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_preview_is_reproducible_and_dependency_closed(tmp_path):
    first, second = tmp_path / 'one', tmp_path / 'two'
    one, two = builder.build(first), builder.build(second)
    assert one == two
    assert one['status'] == 'diagnostic-preview-not-cinema'
    ids = {item['id'] for item in one['components']}
    for item in one['components']:
        assert (first / item['file']).read_bytes() == (second / item['file']).read_bytes()
        with zipfile.ZipFile(first / item['file']) as archive:
            names = archive.namelist()
            assert all(name.startswith(item['id'] + '/') for name in names)
            assert item['id'] + '/LICENSE' in names
            root = ET.fromstring(archive.read(item['id'] + '/addon.xml'))
            for dep in root.findall('./requires/import'):
                assert dep.get('addon') in ids | {'xbmc.python'}


def test_kodi_sources_parse_with_python38_grammar():
    for path in (ROOT / 'addons').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 8))


def test_incomplete_cinema_cannot_claim_stable():
    gates = json.loads((ROOT / 'release/gates.json').read_text(encoding='utf-8'))
    assert gates['stable_release_allowed'] is False
    assert all(not value['clean_install'] for value in gates['profiles'].values())

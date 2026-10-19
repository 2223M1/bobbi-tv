import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bobbi_prepare_test', ROOT / 'tools/prepare_candidate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_bencode_implementation_replaced_without_leaving_legacy_import():
    path = 'plugin.video.bobbi/lib/utils/torrent/torrserver_utils.py'
    out = module.transform(path, b'from lib.vendor.bencodepy import bencodepy\n')
    assert out == b'from lib.utils.torrent import flatbencode as bencodepy\n'
    ast.parse(out)


def test_replacement_preserves_canonical_torrent_info_roundtrip():
    path = ROOT / 'addons/plugin.video.bobbi/lib/utils/torrent/flatbencode.py'
    spec = importlib.util.spec_from_file_location('bobbi_flatbencode_test', path)
    flat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flat)
    data = b'd6:lengthi42e4:name9:movie.mkv12:piece lengthi16384e6:pieces20:01234567890123456789e'
    assert flat.encode(flat.decode(data)) == data


def test_new_mine_menu_routes_to_library_and_real_setup():
    path = ROOT / 'addons/plugin.video.bobbi/lib/clients/maintainable_ui.py'
    namespace = {}
    exec(path.read_text(encoding='utf-8'), namespace)
    entries = namespace['entries']('am6b_home')
    assert entries[0][1] == 'plugin://plugin.video.bobbi.library/'
    assert entries[1][1] == 'plugin://plugin.video.bobbi.library/?action=manage'
    assert len(entries) == 4
    assert any('bobbi_setup' in target for _, target, _ in entries)
    assert not any('bobi_library' in target for _, target, _ in entries)
    assert len(namespace['entries']('am6b_discovery')) == 5

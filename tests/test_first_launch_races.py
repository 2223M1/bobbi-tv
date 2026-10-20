import ast
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addons/plugin.video.bobbi'


def test_widget_profile_mkdir_is_atomic_and_idempotent(tmp_path):
    tree = ast.parse((PLUGIN / 'lib/db/cached.py').read_text(encoding='utf-8'))
    statements = [node for node in tree.body if isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                  and node.value.func.attr == 'makedirs']
    assert len(statements) == 1
    call = statements[0].value
    assert any(k.arg == 'exist_ok' and k.value.value is True for k in call.keywords)
    code = compile(ast.Module(body=statements, type_ignores=[]), '<actual-cache-startup>', 'exec')
    barrier = threading.Barrier(16)
    directory = str(tmp_path / 'first/profile')
    def start(_):
        barrier.wait(timeout=5)
        exec(code, {'os':os, 'ADDON_DATA':directory})
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(start, range(16)))
    assert Path(directory).is_dir()


def test_optional_trakt_secrets_have_valid_empty_defaults():
    root = ET.parse(PLUGIN / 'resources/settings.xml')
    for name in ('trakt_client','trakt_secret'):
        node = root.find(".//setting[@id='%s']" % name)
        assert not node.find('default').text
        assert node.findtext('constraints/allowempty') == 'true'


def test_no_unguarded_makedirs_remain_in_plugin():
    for path in (PLUGIN / 'lib').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'makedirs':
                assert any(k.arg == 'exist_ok' and isinstance(k.value, ast.Constant) and k.value.value is True
                           for k in node.keywords), str(path)

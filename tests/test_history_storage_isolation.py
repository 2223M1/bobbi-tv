"""Captured profile storage runs with no Kodi, plugin UI or global cache."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_storage_import_write_read_without_runtime_modules(tmp_path):
    script = '''
import importlib.abc, importlib.util, pathlib, sys
class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] not in {'lib', 'xbmc', 'xbmcgui', 'xbmcvfs', 'xbmcaddon', 'bobbi_platform'}, fullname
sys.meta_path.insert(0, NoRuntime())
spec = importlib.util.spec_from_file_location('isolated_storage', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = pathlib.Path(sys.argv[2])
database = module.PickleDatabase(profile_root=root / 'A')
other = module.PickleDatabase(profile_root=root / 'B')
assert database.set_item('jt:lfh', 'same-file', {'position':42})
assert other.get_item('jt:lfh', 'same-file') is None
assert module.PickleDatabase(profile_root=root / 'A').get_item('jt:lfh', 'same-file') == {'position':42}
assert not (root / 'B' / 'database.pickle').exists()
'''
    result = subprocess.run([sys.executable, '-I', '-c', script,
        str(ROOT / 'addons/plugin.video.bobbi/lib/db/pickle_db.py'), str(tmp_path)],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr

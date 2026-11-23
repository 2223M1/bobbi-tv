"""Fail new reverse imports; an explicit debt list is not a clean-layer claim."""
import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (name.name for name in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.module
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            target = node.func
            if (isinstance(target, ast.Name) and target.id in ('__import__', 'import_module') or
                    isinstance(target, ast.Attribute) and target.attr == 'import_module'):
                if isinstance(node.args[0].value, str):
                    yield node.args[0].value


def test_no_new_core_environment_or_platform_plugin_dependencies():
    debt = json.loads((ROOT / 'docs/architecture/dependency-debt.json').read_text(encoding='utf-8'))
    for layer in ('core', 'platform'):
        folder = ROOT / ('addons/script.module.bobbi.%s/lib/bobbi_%s' % (layer, layer))
        observed = {}
        for file in folder.rglob('*.py'):
            name = file.relative_to(folder).as_posix()
            for module in imports(ast.parse(file.read_text(encoding='utf-8-sig'))):
                forbidden = (module.split('.')[0] == 'lib' or layer == 'core' and
                    (module.split('.')[0] in ('xbmc', 'xbmcgui', 'xbmcaddon', 'xbmcvfs') or
                     module.startswith('bobbi_platform')))
                if forbidden:
                    observed.setdefault(name, set()).add(module)
        allowed = {name: set(entries) for name, entries in debt[layer].items()}
        assert observed == allowed, 'Migrate the responsibility; do not silently widen the exception list.'
        assert all(reason.strip() for entries in debt[layer].values() for reason in entries.values())


def test_account_value_contract_imports_without_kodi_platform_or_plugin():
    script = '''
import importlib.abc, sys
class DenyEnvironment(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] not in {'bobbi_platform', 'lib', 'xbmc', 'xbmcaddon', 'xbmcvfs', 'xbmcgui'}, fullname
sys.meta_path.insert(0, DenyEnvironment())
sys.path.insert(0, sys.argv[1])
from bobbi_core.account_scope import validate_snapshot, AccountError
value = {'account_id':'115:'+'a'*64, 'authenticated':True, 'epoch':7}
assert validate_snapshot(value, authenticated=True) == value
assert validate_snapshot(value) is not value
try:
    validate_snapshot(dict(value, epoch=True))
except AccountError:
    pass
else:
    raise AssertionError('boolean epoch accepted')
'''
    result = subprocess.run([sys.executable, '-I', '-c', script,
        str(ROOT / 'addons/script.module.bobbi.core/lib')], text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_platform_reexports_same_contract_without_a_second_validator():
    from bobbi_core.account_scope import validate_snapshot, AccountError
    from bobbi_platform import account_manager
    assert account_manager.validate_snapshot is validate_snapshot
    assert account_manager.AccountError is AccountError


def test_library_contract_imports_without_platform_kodi_or_storage():
    script = '''
import importlib.abc, json, sys
class DenyEnvironment(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] not in {'bobbi_platform', 'lib', 'xbmc', 'xbmcaddon', 'xbmcvfs', 'xbmcgui', 'sqlite3'}, fullname
sys.meta_path.insert(0, DenyEnvironment())
sys.path.insert(0, sys.argv[1])
from bobbi_core.library_contract import import_catalog, LibraryError, vfs_source, joined_path, directory_items
source = import_catalog(json.dumps({'schema':'bobbi-library-v1', 'name':'Saved',
    'items':[{'id':'movie', 'title':'Movie', 'url':'https://media.example/movie.mkv'}]}))
assert source.items[0].id == 'movie'
source = vfs_source('NAS', 'smb://media.example/Movies/', 'user', 'password')
assert joined_path(source, 'Movie & More.mkv') == 'smb://user:password@media.example/Movies/Movie%20%26%20More.mkv'
assert directory_items(['Season 1'], ['movie.mkv', 'danger.strm']) == ((True, 'Season 1'), (False, 'movie.mkv'))
for path in ('../movie.mkv', 'a/../movie.mkv', '/outside.mkv'):
    try:
        joined_path(source, path)
    except LibraryError:
        pass
    else:
        raise AssertionError('path escaped registered source')
'''
    result = subprocess.run([sys.executable, '-I', '-c', script,
        str(ROOT / 'addons/script.module.bobbi.core/lib')], text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_library_storage_reexports_identical_contracts():
    from bobbi_core import library_contract
    from bobbi_platform import libraries
    for name in ('LibraryError', 'Source', 'Item', 'import_catalog', 'vfs_source',
                 'validate_source', 'split_location', 'joined_path', 'directory_items'):
        assert getattr(libraries, name) is getattr(library_contract, name)


def test_replaced_actor_window_is_not_a_second_shipped_flow():
    plugin = ROOT / 'addons/plugin.video.bobbi'
    assert not (plugin / 'lib/gui/actor_info_window.py').exists()
    assert not (plugin / 'resources/skins/Default/1080i/actor_info.xml').exists()
    # The public saved-URL entry is retained in PeopleClient, not a dynamic
    # loader for the removed private dialog. Check the new bounded route in
    # test_public_detail_convergence's executable URL regression as well.
    source = (plugin / 'lib/clients/tmdb/people_client.py').read_text(encoding='utf-8')
    assert 'def handle_tmdb_person_info(params):' in source
    assert 'actor_info_window' not in source


def test_internal_consumers_use_implementation_not_legacy_aliases():
    plugin = ROOT / 'addons/plugin.video.bobbi'
    cinema = plugin / 'lib/cinema'
    aliases = set()
    for path in cinema.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == '_import_module' and len(node.args) == 1
               and isinstance(node.args[0], ast.Constant)
               and str(node.args[0].value).startswith('bobbi_core.') for node in ast.walk(tree)):
            aliases.add(path.stem)
    assert len(aliases) == 57  # Same-module compatibility names, not duplicate owners.
    # Preparation is now an actual one-operation Kodi adapter, not a core alias.
    aliases.update(('preparation_client', 'playback_request', 'playback_ipc', 'prepared_protection'))
    for path in plugin.rglob('*.py'):
        if path.parent == cinema and path.stem in aliases:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom) and not node.level:
                assert not (node.module == 'lib.cinema' and any(n.name in aliases for n in node.names)), path
                assert node.module not in {'lib.cinema.' + name for name in aliases}, path


def test_legacy_alias_retains_one_module_and_one_state_in_both_import_orders():
    for order in ('legacy-first', 'core-first'):
        script = '''
import importlib, sys
sys.path[:0] = sys.argv[1:3]
names = ['lib.cinema.playback_owner', 'bobbi_core.playback_owner']
if sys.argv[3] == 'core-first': names.reverse()
first, second = (importlib.import_module(name) for name in names)
assert first is second
assert first.PlaybackOwner is second.PlaybackOwner
first.compatibility_state_probe = object()
assert second.compatibility_state_probe is first.compatibility_state_probe
'''
        result = subprocess.run([sys.executable, '-I', '-c', script,
            str(ROOT / 'addons/plugin.video.bobbi'), str(ROOT / 'addons/script.module.bobbi.core/lib'),
            order], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr

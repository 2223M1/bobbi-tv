"""R3-SET-01/02/03 & SC-01..07 acceptance tests: cache preservation, bundled version notes, and update notice migration."""
import ast
from datetime import timedelta
import io
import json
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace
import zipfile

import pytest

from bobbi_platform import ce_update_notice as notice, version_notes
from bobbi_platform.updates import UpdateError

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / 'addons/plugin.video.bobbi'
PLUGIN_LIB = PLUGIN_ROOT / 'lib'


def _extract_func(path: Path, name: str, namespace: dict, *, class_name: str | None = None):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    body = (
        tree.body
        if class_name is None
        else next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    )
    node = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)
    isolated = ast.Module(body=[node], type_ignores=[])
    exec(compile(isolated, str(path), 'exec'), namespace)
    return namespace[name]


class _SQLiteBackedFakeCache:
    """Real SQLite LIKE & clean_all semantics for testing Stremio/Nuvio cache preservation."""

    def __init__(self, initial: dict | None = None):
        self.sql = sqlite3.connect(':memory:')
        self.sql.execute('CREATE TABLE cached (key TEXT PRIMARY KEY, value TEXT)')
        self._lock = threading.RLock()
        self._object_store = {}
        self._clean_all = _extract_func(PLUGIN_LIB / 'db/cached.py', 'clean_all', {}, class_name='SQLiteCache')
        for k, v in (initial or {}).items():
            self.set(k, v, timedelta(days=365))

    def _live(self):
        return True

    def _mutate(self, statement, params=()):
        self.sql.execute(statement, params)

    def get(self, key):
        row = self.sql.execute('SELECT value FROM cached WHERE key = ?', (key,)).fetchone()
        return json.loads(row[0]) if row is not None else None

    def set(self, key, value, ttl=timedelta(hours=1)):
        self.sql.execute('INSERT OR REPLACE INTO cached VALUES (?, ?)', (key, json.dumps(value)))
        self._object_store[key] = value

    def delete(self, key):
        self.sql.execute('DELETE FROM cached WHERE key = ?', (key,))
        self._object_store.pop(key, None)

    def delete_like(self, pattern):
        self.sql.execute('DELETE FROM cached WHERE key LIKE ?', (pattern,))
        for k in list(self._object_store):
            if self.sql.execute('SELECT ? LIKE ?', (k, pattern)).fetchone()[0]:
                self._object_store.pop(k, None)

    def clear_list(self, key):
        self.set(key, [], timedelta(seconds=1))

    def clean_all(self):
        self._clean_all(self)

    def keys(self):
        return {r[0] for r in self.sql.execute('SELECT key FROM cached').fetchall()}

    def close(self):
        self.sql.close()


def test_r3_set01_clear_stremio_and_global_cache_preserve_persistent_configs_while_factory_reset_clears():
    persistent_seed = {
        # Mixed custom + account addons, same manifest ID across multiple URLs, and credential-bearing URL
        'stremio_user_addons': [
            {
                'transportName': 'custom',
                'transportUrl': 'https://addon-a.example/token-secret-1/manifest.json',
                'manifest': {'id': 'org.multi.instance', 'name': 'Multi A'},
            },
            {
                'transportName': 'custom',
                'transportUrl': 'https://addon-b.example/token-secret-2/manifest.json',
                'manifest': {'id': 'org.multi.instance', 'name': 'Multi B'},
            },
            {
                'transportName': 'account',
                'transportUrl': 'https://account.example/manifest.json',
                'manifest': {'id': 'org.account.addon', 'name': 'Account Addon'},
            },
        ],
        'stremio_addons': '["org.multi.instance|1111111111111111","org.multi.instance|2222222222222222"]',
        'stremio_catalog_addons': '["org.account.addon|3333333333333333"]',
        'stremio_tv_addons': '["org.multi.instance|1111111111111111"]',
        'stremio_subtitle_addons': 'org.multi.instance|1111111111111111',
        'stremio_bypass_addons': 'true',
        'stremio_bypass_addon_list': 'org.multi.instance|2222222222222222',
        'stremio_addon_aliases': {'org.multi.instance|1111111111111111': '家庭源 A'},
        'stremio_catalog_aliases': {'org.account.addon|3333333333333333|movie|top': '精选电影'},
        'torrentio.providers': 'yts,nyaasi',
        'nuvio_user_addons': [
            {
                'transportName': 'nuvio',
                'transportUrl': 'https://nuvio.example/manifest.json',
                'manifest': {'id': 'com.nuvio.one', 'name': 'Nuvio One'},
            }
        ],
        'nuvio_addons': '["com.nuvio.one|abcdef0123456789"]',
    }
    ephemeral_seed = {
        'stremio.catalog.tmp': {'items': [1]},
        'stremio_stream:abcdef123456': {'streams': []},
        'deadbeef:stremio_resource:998877': {'metas': []},
        'search_catalog|query=dune': [1, 2],
        'list_catalog|movie': [3],
        'list_stremio_movie|tt123': [4],
        'nuvio.library.movies': [5],
        'movie_popular|1': [6],
    }

    fake_cache = _SQLiteBackedFakeCache({**persistent_seed, **ephemeral_seed})
    try:
        notices = []
        clear_stremio = _extract_func(
            PLUGIN_LIB / 'utils/general/utils.py',
            'clear_stremio_cache',
            {'cache': fake_cache, 'notification': notices.append, 'translation': str},
        )
        clear_stremio()
        assert len(notices) == 1
        # All Stremio ephemeral entries deleted; ALL persistent Stremio & Nuvio configs untouched!
        for k, expected_val in persistent_seed.items():
            assert fake_cache.get(k) == expected_val, f'{k} was altered by clear_stremio_cache'
            assert fake_cache._object_store[k] == expected_val
        for eph in (
            'stremio.catalog.tmp',
            'stremio_stream:abcdef123456',
            'deadbeef:stremio_resource:998877',
            'search_catalog|query=dune',
            'list_catalog|movie',
            'list_stremio_movie|tt123',
        ):
            assert eph not in fake_cache.keys()

        # Global clear_all_cache deletes remaining ephemeral rows (movie_popular, nuvio.library.*)
        # while STILL preserving every persistent Stremio & Nuvio source config key!
        clear_all = _extract_func(
            PLUGIN_LIB / 'utils/general/utils.py',
            'clear_all_cache',
            {'cache': fake_cache, 'timedelta': timedelta},
        )
        clear_all()
        assert 'nuvio.library.movies' not in fake_cache.keys()
        assert 'movie_popular|1' not in fake_cache.keys()
        assert 'bobbi_metadata_epoch' in fake_cache.keys()
        for k, expected_val in persistent_seed.items():
            assert fake_cache.get(k) == expected_val, f'{k} was lost during clear_all_cache'
            assert fake_cache._object_store[k] == expected_val

        # Empty source list case is also clean & idempotent.
        empty_cache = _SQLiteBackedFakeCache({})
        try:
            _extract_func(
                PLUGIN_LIB / 'utils/general/utils.py',
                'clear_stremio_cache',
                {'cache': empty_cache, 'notification': lambda *_: None, 'translation': str},
            )()
            _extract_func(
                PLUGIN_LIB / 'utils/general/utils.py',
                'clear_all_cache',
                {'cache': empty_cache, 'timedelta': timedelta},
            )()
            assert empty_cache.keys() == {'bobbi_metadata_epoch'}
        finally:
            empty_cache.close()

        # Explicit factory_reset deletes ALL persistent Stremio & Nuvio keys after confirmation (#90286),
        # while a cancelled factory_reset_action performs zero deletions.
        sb_path = PLUGIN_LIB / 'utils/kodi/settings_backup.py'
        sb_tree = ast.parse(sb_path.read_text(encoding='utf-8'))
        const_assign = next(
            n for n in sb_tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'PERSISTENT_SOURCE_CONFIG_KEYS' for t in n.targets)
        )
        sb_env = {
            'cache': fake_cache,
            'SETTINGS_XML_PATH': str(PLUGIN_ROOT / 'resources/settings.xml'),
            'reset_all_settings': lambda **kw: None,
            'clear_all_cache': clear_all,
            'clear_trakt_db_cache': lambda: None,
            'clear_tmdb_cache': lambda: None,
            'clear_stremio_cache': clear_stremio,
            'clear_debrid_cache': lambda: None,
            'clear_mdblist_cache': lambda: None,
            '_clear_factory_reset_database_state': lambda: None,
            'notification': notices.append,
            'dialog_ok': lambda *a: None,
            'translation': str,
            'xbmcgui': SimpleNamespace(Dialog=lambda: SimpleNamespace(yesno=lambda *a: False)),
        }
        exec(compile(ast.Module(body=[const_assign], type_ignores=[]), str(sb_path), 'exec'), sb_env)
        _extract_func(sb_path, 'clear_persistent_source_configs', sb_env)
        _extract_func(sb_path, 'factory_reset', sb_env)
        factory_reset_action = _extract_func(sb_path, 'factory_reset_action', sb_env)

        # Cancelled confirmation -> nothing removed!
        factory_reset_action()
        for k in persistent_seed:
            assert fake_cache.get(k) == persistent_seed[k]

        # Confirmed (#90286) -> all persistent Stremio & Nuvio configs explicitly removed!
        sb_env['xbmcgui'] = SimpleNamespace(Dialog=lambda: SimpleNamespace(yesno=lambda *a: True))
        factory_reset_action()
        assert not set(persistent_seed).intersection(fake_cache.keys())
    finally:
        fake_cache.close()


def test_sc07_kodi_logs_merged_selector_local_open_without_upload_and_path_guard(tmp_path):
    (tmp_path / 'kodi.log').write_text('line-1\nline-2\n', encoding='utf-8')
    (tmp_path / 'kodi.old.log').write_text('old-1\n', encoding='utf-8')
    uploads = []
    texts = []
    notices = []
    picks = []

    class Dialog:
        def select(self, heading, options):
            return picks.pop(0)

    env = {
        'os': __import__('os'),
        'deque': __import__('collections').deque,
        'translatePath': lambda _: str(tmp_path),
        'translation': str,
        'notification': notices.append,
        'dialog_text': lambda heading, content: texts.append((heading, content)),
        'export_to_kodi_paste': lambda content: uploads.append(content) or 'https://paste.kodi.tv/abc',
    }
    fake_xbmcgui = SimpleNamespace(Dialog=Dialog)
    old_xbmcgui = sys.modules.get('xbmcgui')
    sys.modules['xbmcgui'] = fake_xbmcgui
    try:
        fn = _extract_func(PLUGIN_LIB / 'utils/general/utils.py', 'show_log_export_dialog', env)

        # 1. Merged entry (no log_file): pick kodi.old.log (1), then cancel action dialog (-1) -> zero viewer, zero upload
        picks[:] = [1, -1]
        fn({})
        assert texts == [] and uploads == []

        # 2. Merged entry: pick kodi.log (0), then view locally (0) -> opens textviewer, zero upload!
        picks[:] = [0, 0]
        fn({})
        assert len(texts) == 1 and 'line-2' in texts[0][1] and uploads == []

        # 3. Legacy kodi.old.log URL: view locally (0) -> opens old log, zero upload!
        texts.clear()
        picks[:] = [0]
        fn({'log_file': 'kodi.old.log'})
        assert len(texts) == 1 and 'old-1' in texts[0][1] and uploads == []

        # 4. Path traversal / unknown log_file rejected without reading or uploading
        texts.clear()
        fn({'log_file': '../secret.txt'})
        assert texts == [] and uploads == [] and len(notices) == 1
    finally:
        if old_xbmcgui is None:
            sys.modules.pop('xbmcgui', None)
        else:
            sys.modules['xbmcgui'] = old_xbmcgui


def test_r3_set02_changelog_packaged_in_component_zip_and_displayed_offline(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'tools'))
    import build_release

    changelog = PLUGIN_ROOT / 'CHANGELOG.md'
    assert changelog.is_file()

    # Verify build_release.files() accepts CHANGELOG.md (passes delivery_policy.require_clean)
    # and build_release.archive() packs plugin.video.bobbi/CHANGELOG.md into the inner component zip!
    tracked_files = build_release.files(PLUGIN_ROOT)
    assert 'CHANGELOG.md' in tracked_files
    inner_zip = tmp_path / 'plugin.video.bobbi-0.1.98.zip'
    build_release.archive(PLUGIN_ROOT, tracked_files, inner_zip)
    with zipfile.ZipFile(inner_zip) as zf:
        assert 'plugin.video.bobbi/CHANGELOG.md' in zf.namelist()
        extracted_notes = zf.read('plugin.video.bobbi/CHANGELOG.md').decode('utf-8')

    # Verify precision requirements on release notes content:
    assert 'Emby' in extracted_notes and '当前浏览账号' in extracted_notes
    assert 'Jellyfin' in extracted_notes and 'Plex' in extracted_notes and '单连接' in extracted_notes
    assert 'CoreELEC' in extracted_notes and '重启 Kodi' in extracted_notes

    # Verify version_notes.read_installed_notes & show_about & navigation.show_changelog
    notes = version_notes.read_installed_notes(changelog, '0.1.98')
    assert notes['available'] is True and notes['matched_version'] is True
    assert '0.1.98' in notes['body']

    viewed = []
    dlg = SimpleNamespace(textviewer=lambda title, body, *a: viewed.append((title, body)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: dlg))
    version_notes.show_about(dlg, changelog_path=changelog, installed_version='0.1.98')
    assert len(viewed) == 1 and '0.1.98' in viewed[0][0] and 'TMDB' in viewed[0][1]

    # Even if changelog file is missing on disk, show_changelog renders clean status without "Error reading file."
    viewed.clear()
    toasts = []
    nav_env = {
        'CHANGELOG_PATH': str(tmp_path / 'missing-CHANGELOG.md'),
        'ADDON_VERSION': '0.1.98',
        'translation': str,
        'dialog_text': _extract_func(
            PLUGIN_LIB / 'utils/kodi/utils.py',
            'dialog_text',
            {
                'xbmcgui': SimpleNamespace(Dialog=lambda: dlg),
                'xbmc': SimpleNamespace(LOGERROR=4),
                'logger': lambda *a: None,
                'notification': toasts.append,
            },
        ),
    }
    _extract_func(PLUGIN_LIB / 'navigation.py', 'show_changelog', nav_env)({})
    assert toasts == []
    assert len(viewed) == 1 and '缺失或暂不可读' in viewed[0][1]


@pytest.mark.parametrize(
    'legacy_xml,existing_notice,expected_enabled,expect_written',
    [
        # 1. No explicit legacy value (default="true") -> no file written, default True
        ('<settings version="2"><setting id="update_action" default="true">0</setting></settings>', None, True, False),
        ('<settings version="2"><setting id="update_action" default="true">2</setting></settings>', None, True, False),
        (None, None, True, False),
        # 2. Explicit legacy 0 (Ask) -> migrates once to True
        ('<settings version="2"><setting id="update_action">0</setting></settings>', None, True, True),
        # 3. Explicit legacy 1 (Notify) -> migrates once to True
        ('<settings version="2"><setting id="update_action">1</setting></settings>', None, True, True),
        # 4. Explicit legacy 2 (None) -> migrates once to False
        ('<settings version="2"><setting id="update_action">2</setting></settings>', None, False, True),
        # 5. Existing new owner True + legacy 2 -> NEVER overwritten!
        ('<settings version="2"><setting id="update_action">2</setting></settings>', True, True, True),
        # 6. Existing new owner False + legacy 0 -> NEVER overwritten!
        ('<settings version="2"><setting id="update_action">0</setting></settings>', False, False, True),
    ],
)
def test_r3_set03_update_action_one_time_idempotent_migration_matrix(
    tmp_path, legacy_xml, existing_notice, expected_enabled, expect_written
):
    addon_data = tmp_path / 'addon_data'
    work = addon_data / 'script.bobbi.start'
    work.mkdir(parents=True)
    plugin_data = addon_data / 'plugin.video.bobbi'
    plugin_data.mkdir(parents=True)
    settings_xml = plugin_data / 'settings.xml'
    if legacy_xml is not None:
        settings_xml.write_text(legacy_xml, encoding='utf-8')
        before_xml = settings_xml.read_bytes()

    if existing_notice is not None:
        notice.enabled(work, existing_notice)

    assert notice.enabled(work) is expected_enabled
    notice_file = work / 'update-notices.json'
    assert notice_file.exists() is expect_written

    # Old XML file is never modified or deleted.
    if legacy_xml is not None:
        assert settings_xml.read_bytes() == before_xml

    # Idempotency: if user later changes preference in new owner, legacy XML never re-overrides it!
    flipped = not expected_enabled
    notice.enabled(work, flipped)
    assert notice.enabled(work) is flipped

    # Also verify check() honors migrated False (returns 'inactive' without network lookup)
    (work / 'installation.json').write_text(
        json.dumps(dict(schema=1, tx='a' * 32, items=[], sequence=7, high_watermark=9, phase='complete')),
        encoding='utf-8',
    )
    if not flipped:
        assert notice.check(work, lambda: False, lambda *_: pytest.fail('muted'), lookup=lambda *a, **k: pytest.fail('muted')) == 'inactive'

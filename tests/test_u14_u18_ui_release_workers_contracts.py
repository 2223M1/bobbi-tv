"""Behavioral regression contracts for U14, U15, U16, and U18."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(os.environ.get('BOBBI_REPO_ROOT', os.environ.get('BOBBI_AUDIT_REPO', Path(__file__).resolve().parents[1]))).resolve()
for rel in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib', 'addons/plugin.video.bobbi'):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_glass_module():
    from bobbi_platform import glass_settings
    return glass_settings


def _drive_home_rails(choices, values=None, current=lambda: True, on_select=None, *, rail_specs=None):
    gs = _load_glass_module()
    seq = iter(choices)
    values = values or {}
    writes = []

    def select(*_args):
        val = next(seq)
        if on_select:
            on_select(val)
        return val

    kwargs = {'rail_specs': rail_specs} if rail_specs is not None else {}
    changed = gs.manage_home_rails(
        SimpleNamespace(select=select),
        lambda k: bool(values.get(k, False)),
        lambda k: str(values.get(k, '')),
        lambda *a: writes.append(('set_bool', *a)),
        lambda *a: writes.append(('set_string', *a)),
        lambda *a: writes.append(('reset', *a)),
        current,
        **kwargs,
    )
    return changed, writes


# --- CT-HOME-CANCEL (UI-03) ---


def test_cancel_after_edit_does_not_persist_without_explicit_save():
    changed, writes = _drive_home_rails([0, 0, -1])
    assert changed is False
    assert writes == []


def test_explicit_save_persists_the_user_change():
    gs = _load_glass_module()
    changed, writes = _drive_home_rails([0, 0, len(gs.HOME_RAIL_KEYS) + 1])
    assert changed is True
    assert ('set_bool', 'BobbiHideRail_continue_watching', True) in writes


@pytest.mark.parametrize('exit_choice', [-1, 'save_index'])
def test_exit_without_edits_has_no_writes(exit_choice):
    gs = _load_glass_module()
    choice = len(gs.HOME_RAIL_KEYS) + 1 if exit_choice == 'save_index' else -1
    assert _drive_home_rails([choice]) == (False, [])


def test_reorder_then_main_cancel_has_zero_writes():
    assert _drive_home_rails([0, 1, -1]) == (False, [])


def test_reset_draft_then_main_cancel_preserves_prior_preferences():
    gs = _load_glass_module()
    customized = {
        'BobbiRailSlot1': gs.HOME_RAIL_KEYS[1],
        'BobbiRailSlot2': gs.HOME_RAIL_KEYS[0],
        'BobbiHideRail_continue_watching': True,
    }
    assert _drive_home_rails([len(gs.HOME_RAIL_KEYS), -1], customized) == (False, [])


def test_explicit_save_keeps_reordered_slots():
    gs = _load_glass_module()
    changed, writes = _drive_home_rails([0, 1, len(gs.HOME_RAIL_KEYS) + 1])
    assert changed is True
    assert ('set_string', 'BobbiRailSlot1', gs.HOME_RAIL_KEYS[1]) in writes
    assert ('set_string', 'BobbiRailSlot2', gs.HOME_RAIL_KEYS[0]) in writes


def test_explicit_reset_save_restores_default_without_new_persistence_keys():
    gs = _load_glass_module()
    customized = {
        'BobbiRailSlot1': gs.HOME_RAIL_KEYS[1],
        'BobbiRailSlot2': gs.HOME_RAIL_KEYS[0],
        'BobbiHideRail_continue_watching': True,
    }
    changed, writes = _drive_home_rails([len(gs.HOME_RAIL_KEYS), len(gs.HOME_RAIL_KEYS) + 1], customized)
    expected = [('reset', f'BobbiRailSlot{i}') for i in range(1, len(gs.HOME_RAIL_KEYS) + 1)]
    expected += [('reset', f'BobbiHideRail_{k}') for k in gs.HOME_RAIL_KEYS]
    assert changed is True
    assert writes == expected


def test_context_loss_while_save_dialog_is_open_prevents_commit():
    gs = _load_glass_module()
    active = [True]

    def change_context(value):
        if value == len(gs.HOME_RAIL_KEYS) + 1:
            active[0] = False

    assert _drive_home_rails(
        [0, 0, len(gs.HOME_RAIL_KEYS) + 1],
        current=lambda: active[0],
        on_select=change_context,
    ) == (False, [])


def test_subdialog_back_preserves_draft_for_later_explicit_save():
    gs = _load_glass_module()
    changed, writes = _drive_home_rails([0, 0, 1, -1, len(gs.HOME_RAIL_KEYS) + 1])
    assert changed is True
    assert ('set_bool', 'BobbiHideRail_continue_watching', True) in writes


# --- CT-HOME-GENERATOR (Single-source JSON -> XML + Python) ---


def test_single_json_declaration_drives_both_xml_and_python_meta_and_check_catches_drift(tmp_path):
    spec_mod = importlib.util.spec_from_file_location('u14_home_gen', ROOT / 'tools/generate_home_rails.py')
    gen = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(gen)

    receipt = gen.check_generated(ROOT)
    assert receipt['python_output'] == 'addons/script.module.bobbi.platform/lib/bobbi_platform/home_rails_meta.py'
    assert receipt['python_sha256'] == hashlib.sha256((ROOT / gen.META_OUTPUT).read_bytes()).hexdigest()

    # Copy minimal tree to tmp_path and verify stale Python metadata fails --check without auto-repair
    shutil.copytree(ROOT / gen.SKIN, tmp_path / gen.SKIN)
    for rel in (gen.SPEC, Path('tools/generate_home_rails.py'), gen.META_OUTPUT):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    assert gen.check_generated(tmp_path)['python_sha256'] == receipt['python_sha256']

    py_target = tmp_path / gen.META_OUTPUT
    tampered = py_target.read_bytes() + b'# manual drift\n'
    py_target.write_bytes(tampered)
    with pytest.raises(ValueError, match='Python metadata is stale'):
        gen.check_generated(tmp_path)
    assert py_target.read_bytes() == tampered

    # Mutate JSON only (rename, delete, add rail) -> both XML and Python constants update together
    doc = gen.load_spec(ROOT / gen.SPEC)
    doc['rails'] = [r for r in doc['rails'] if r['key'] != 'anime_movies']
    doc['rails'][0] = dict(doc['rails'][0], title='继续播放自定义')
    doc['rails'].append({
        'key': 'extra_movies',
        'control_id': 9865,
        'title': '精选影单',
        'layout': 'poster',
        'route': 'catalog',
        'params': {'section': 'movie', 'page': 1},
        'limit': 20,
        'preloaditems': 2,
    })
    (tmp_path / gen.SPEC).write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    raw_xml, hero_xml, py_bytes = gen.all_outputs(tmp_path)
    assert '继续播放自定义' in raw_xml.decode('utf-8')
    assert '精选影单' in raw_xml.decode('utf-8') and '9865' in hero_xml.decode('utf-8')
    assert 'anime_movies' not in raw_xml.decode('utf-8')

    ns = {}
    exec(py_bytes.decode('utf-8'), ns)
    assert ns['HOME_RAIL_KEYS'][-1] == 'extra_movies'
    assert 'anime_movies' not in ns['HOME_RAIL_KEYS']
    assert ns['HOME_RAIL_TITLES']['continue_watching'] == '继续播放自定义'
    changed, writes = _drive_home_rails([0, 0, len(ns['HOME_RAIL_KEYS']) + 1], rail_specs=ns['HOME_RAIL_SPECS'])
    assert changed is True
    assert ('set_bool', 'BobbiHideRail_continue_watching', True) in writes


# --- CT-DIRECTORY-END (UI-01) ---


def test_home_rail_directory_ends_once_across_all_six_scenarios(tmp_path, monkeypatch):
    from bobbi_core.library_contract import Source
    from bobbi_platform import emby_dynamic, paths
    from bobbi_platform.libraries import Registry
    from bobbi_platform.pan_accounts import PanError

    profile_active = [True]
    other_profile = tmp_path / 'other_profile'
    other_profile.mkdir()
    cur_dir = lambda *_a: tmp_path if profile_active[0] else other_profile
    monkeypatch.setattr(paths, 'profile_root', cur_dir)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(cur_dir())))
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(abortRequested=lambda: False),
        getInfoLabel=lambda _: 'Master user' if profile_active[0] else 'Other profile',
    ))

    class FakeItem:
        def __init__(self, label=''):
            self.label = label

        def setLabel2(self, _v):
            pass

        def setProperty(self, _k, _v):
            pass

        def setInfo(self, _t, _i):
            pass

        def setContentLookup(self, _v):
            pass

        def setArt(self, _a):
            pass

    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=FakeItem))
    calls = []
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(
        setContent=lambda *a: None,
        addDirectoryItems=lambda *a: calls.append(('add', a)),
        endOfDirectory=lambda *a, **kw: calls.append(('end', a, kw)),
    ))

    def run_case(section='recent'):
        calls.clear()
        emby_dynamic.execute_home_rail(101, {'section': section})
        return list(calls)

    net_hits = []
    monkeypatch.setattr(emby_dynamic, 'Client', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('zero network expected')))

    # 1. No DB
    res = run_case()
    assert [c[0] for c in res] == ['add', 'end'] and res[-1][2]['succeeded'] is True

    # 2. Empty existing DB
    Registry(tmp_path / 'libraries.sqlite3').close()
    res = run_case()
    assert [c[0] for c in res] == ['add', 'end'] and res[-1][2]['succeeded'] is True

    # 3. NAS-only DB (WebDAV source, no Emby)
    reg = Registry(tmp_path / 'libraries.sqlite3')
    reg.save(Source(
        id='c' * 32,
        name='Home NAS',
        kind='vfs',
        location='davs://nas.example.test/dav/',
        username='u',
        password='p',
        metadata={},
    ))
    reg.close()
    res = run_case()
    assert [c[0] for c in res] == ['add', 'end'] and res[-1][2]['succeeded'] is True
    assert net_hits == []

    # Add valid Emby source for cases 4, 5, 6
    reg = Registry(tmp_path / 'libraries.sqlite3')
    sid = 'a' * 32
    reg.save(Source(
        id=sid,
        name='Living Emby',
        kind='media_server',
        location='https://emby.example.test:8920',
        username='',
        password='tok',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srv1', 'user_id': 'usr1'},
    ), activate_emby=reg.emby_binding()[1])
    reg.close()

    from contextlib import nullcontext
    mode = ['ok']

    class FakeClient:
        def __init__(self, _prov, _saved):
            self.session = SimpleNamespace(budget=lambda _s: nullcontext())

        def _identity(self, **_kw):
            net_hits.append(mode[0])
            if mode[0] == 'fail':
                raise PanError('PAN_NETWORK_ERROR')

        def page_rows(self, *_a, **_kw):
            if mode[0] == 'switch_profile':
                profile_active[0] = False
            return ([{'Id': '10', 'Name': 'Movie A', 'Type': 'Movie'}], 1)

    monkeypatch.setattr(emby_dynamic, 'Client', FakeClient)

    # 4. Valid Emby
    res = run_case()
    assert [c[0] for c in res] == ['add', 'end'] and res[-1][2]['succeeded'] is True
    assert len(res[0][1][1]) == 1

    # 5. Connection failure -> single end, empty rows
    mode[0] = 'fail'
    res = run_case()
    assert [c[0] for c in res] == ['add', 'end'] and res[-1][2]['succeeded'] is True
    assert res[0][1][1] == []

    # 6. Profile switch mid-fetch -> single end with succeeded=False, zero leaked items
    mode[0] = 'switch_profile'
    res = run_case()
    assert [c[0] for c in res] == ['end'] and res[-1][2]['succeeded'] is False

    # 7. Uncaught failure inside registry factory -> single end with succeeded=False (never overwritten as True)
    profile_active[0] = True
    calls.clear()
    with pytest.raises(RuntimeError, match='boom'):
        emby_dynamic.execute_home_rail(
            101,
            {'section': 'recent'},
            registry_factory=lambda: (_ for _ in ()).throw(RuntimeError('boom')),
        )
    assert [c[0] for c in calls] == ['end'] and calls[-1][2]['succeeded'] is False


# --- CT-MODAL-REVISION (UI-02) ---


def test_modal_deferral_dedup_context_switch_and_retry_on_failure(monkeypatch):
    sid = 'a' * 32
    gen = 'b' * 64
    state = {
        'modal': True,
        'profile_ok': True,
        'folder': f'plugin://plugin.video.bobbi.library/?action=emby_page&source={sid}&revision={gen}&parent=root',
        'fail_refresh': False,
    }
    refreshed = []
    props = {}

    def exec_builtin(cmd):
        if state['fail_refresh']:
            raise RuntimeError('transient builtin error')
        refreshed.append(cmd)

    xbmc_mock = SimpleNamespace(
        getInfoLabel=lambda _: state['folder'],
        getCondVisibility=lambda _: state['modal'],
        executebuiltin=exec_builtin,
    )
    monkeypatch.setitem(sys.modules, 'xbmc', xbmc_mock)

    spec = importlib.util.spec_from_file_location(
        'u14_widget_refresh', ROOT / 'addons/plugin.video.bobbi/lib/services/widget_refresh.py'
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    window = SimpleNamespace(
        getProperty=lambda k: props.get(k, ''),
        setProperty=lambda k, v: props.__setitem__(k, v),
    )
    host = SimpleNamespace(check_profile=lambda: state['profile_ok'], root=Path('/tmp/p1'), plugin_root=Path('/tmp/p1'))
    service = mod.WidgetRefreshService(host=host, window=window)

    # 1. Deferred while modal is open; coalesces revisions; refreshes ONCE after dismissal even on unchanged revision
    service._schedule_container_refresh(sid, gen, 2, state['folder'])
    service._offer({'emby_server': 'rev-2'})
    service.tick()
    assert refreshed == [] and service._pending_container_source == sid

    # Transient builtin error after modal closes keeps pending refresh queued for retry
    state['modal'] = False
    state['fail_refresh'] = True
    service.tick()
    assert refreshed == [] and service._pending_container_source == sid

    # Next tick succeeds (even with same 'rev-2' offered) -> refreshes once, then deduplicates same revision
    state['fail_refresh'] = False
    service._offer({'emby_server': 'rev-2'})
    service.tick()
    assert refreshed == ['Container.Refresh'] and service._pending_container_source is None

    service._schedule_container_refresh(sid, gen, 2, state['folder'])
    service.tick()
    assert refreshed == ['Container.Refresh']

    # 2. Navigating to another folder while modal is open discards stale pending refresh
    state['modal'] = True
    service._schedule_container_refresh(sid, gen, 3, state['folder'])
    service.tick()
    state['folder'] = 'plugin://plugin.video.bobbi/?action=search'
    state['modal'] = False
    service.tick()
    assert refreshed == ['Container.Refresh'] and service._pending_container_source is None

    # 3. Account generation change while modal is open discards stale pending refresh
    state['folder'] = f'plugin://plugin.video.bobbi.library/?action=emby_page&source={sid}&revision={gen}&parent=root'
    state['modal'] = True
    service._schedule_container_refresh(sid, gen, 4, state['folder'])
    service.tick()
    new_gen = 'c' * 64
    state['folder'] = f'plugin://plugin.video.bobbi.library/?action=emby_page&source={sid}&revision={new_gen}&parent=root'
    state['modal'] = False
    service.tick()
    assert refreshed == ['Container.Refresh'] and service._pending_container_source is None

    # 4. Profile switch discards pending refresh immediately
    state['modal'] = True
    service._schedule_container_refresh(sid, gen, 5, state['folder'])
    state['profile_ok'] = False
    service.tick()
    state['profile_ok'] = True
    state['modal'] = False
    service.tick()
    assert refreshed == ['Container.Refresh'] and service._pending_container_source is None


# --- CT-HTTP-RUNTIME & CT-STAGING-BYTES (U15: REL-01, REL-02) ---


def test_upgrade_declares_the_http_runtime_used_by_hardening_tests(tmp_path):
    from bobbi_platform import ce_install_ui as ui
    from bobbi_platform.updates import UpdateError
    from bobbi_platform.upstream_addons import (
        DECLARED_HTTP_RUNTIME_FLOORS,
        UPSTREAM_COMPONENTS,
        check_dependencies,
    )

    expected = {'script.module.requests': '2.34.2', 'script.module.urllib3': '2.8.0'}
    assert DECLARED_HTTP_RUNTIME_FLOORS == expected

    for name in UPSTREAM_COMPONENTS:
        folder = tmp_path / name
        folder.mkdir()
        version = expected.get(name, '99.0.0')
        (folder / 'addon.xml').write_text(f'<addon id="{name}" version="{version}"/>', encoding='utf-8')
    minimums = check_dependencies(tmp_path, ROOT / 'addons')
    assert {name: minimums[name] for name in expected} == expected

    # Outdated 2.31.0 / 2.2.3 raises clear diagnostic and never overwrites Kodi-owned folder
    (tmp_path / 'script.module.requests/addon.xml').write_text(
        '<addon id="script.module.requests" version="2.31.0"/>', encoding='utf-8'
    )
    with pytest.raises(UpdateError) as exc_info:
        check_dependencies(tmp_path, ROOT / 'addons')
    diag = ui.diagnosis('apply', exc_info.value)
    msg = ui.failure_message(exc_info.value, 'apply')
    assert 'DEPENDENCY_TOO_OLD' in diag and 'script.module.requests' in diag
    assert '不会私自覆盖' in msg and 'Kodi' in msg


def test_http_runtime_subprocess_records_actual_loaded_files_versions_and_python():
    import subprocess
    probe = (
        'import json, sys; '
        'repo = sys.argv[1]; '
        'sys.path[:0] = ['
        'repo + "/third_party/addons/script.module.requests/lib", '
        'repo + "/third_party/addons/script.module.urllib3/lib", '
        'repo + "/third_party/addons/script.module.certifi/lib", '
        'repo + "/third_party/addons/script.module.chardet/lib", '
        'repo + "/third_party/addons/script.module.idna/lib", '
        'repo + "/addons/script.module.bobbi.core/lib", '
        'repo + "/addons/script.module.bobbi.platform/lib"'
        ']; '
        'from bobbi_platform.upstream_addons import inspect_http_runtime; '
        'print(json.dumps(inspect_http_runtime()))'
    )
    res = subprocess.run([sys.executable, '-I', '-B', '-c', probe, str(ROOT)], capture_output=True, text=True, check=True)
    report = json.loads(res.stdout)
    assert report['requests']['version'] == '2.34.2'
    assert report['urllib3']['version'] == '2.8.0'
    assert 'third_party/addons/script.module.requests' in report['requests']['file']
    assert 'third_party/addons/script.module.urllib3' in report['urllib3']['file']
    assert report['python_version_info'][:2] >= [3, 11]


def test_native_staging_does_not_reopen_unverified_changed_archives(tmp_path, monkeypatch):
    import zipfile as zf_mod

    spec = importlib.util.spec_from_file_location('u15_stage_components', ROOT / 'native/stage-components.py')
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    host = tmp_path / 'host'
    (host / 'system').mkdir(parents=True)
    (host / 'system/addon-manifest.xml').write_text('<addons><addon>xbmc.python</addon></addons>', encoding='utf-8')
    names = ('plugin.video.bobbi', 'skin.bobbi.cinema', 'resource.uisounds.bobbi-modern')
    rows = []
    original_zipfile = zf_mod.ZipFile

    def write_archive(path, name, code):
        with original_zipfile(path, 'w') as archive:
            archive.writestr(name + '/addon.xml', f'<addon id="{name}" version="1.0"/>')
            archive.writestr(name + '/code.py', code)

    for name in names:
        path = tmp_path / (name + '.zip')
        write_archive(path, name, 'verified code')
        rows.append({
            'id': name,
            'version': '1.0',
            'file': path.name,
            'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'version': 'fixture', 'components': rows}), encoding='utf-8')
    first = tmp_path / (names[0] + '.zip')
    first_read_count = [0]

    def open_with_change(path, *args, **kwargs):
        if Path(path) == first and (not args or args[0] == 'r'):
            first_read_count[0] += 1
            if first_read_count[0] == 2:
                write_archive(first, names[0], 'changed after validation')
        return original_zipfile(path, *args, **kwargs)

    monkeypatch.setattr(stage.zipfile, 'ZipFile', open_with_change)
    stage.stage(manifest, host)
    assert first_read_count[0] == 1
    assert (host / 'addons' / names[0] / 'code.py').read_text(encoding='utf-8') == 'verified code'

"""R3 N3-01 dependency closure, failure classification, space budget, and recovery tests."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'addons/script.module.bobbi.platform/lib') not in sys.path:
    sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))

import bobbi_platform.ce_install_ui as ui
from bobbi_platform.ce_install_ui import KodiHost
from bobbi_platform.ce_installer import MANAGED, Installer
from bobbi_platform.ce_recovery import RecoveryStore
from bobbi_platform.ce_storage import install_plan
from bobbi_platform.offline_updates import load_trust
from bobbi_platform.updates import UpdateError
from bobbi_platform.upstream_addons import (
    CANCELLED,
    DIRECTORY_CONFLICT,
    DISABLED,
    FULL_COMPONENTS,
    MISSING_HOST,
    MISSING_SEEDABLE,
    NEEDS_UPGRADE,
    NOT_REQUIRED,
    SATISFIED,
    STATE_UNKNOWN,
    UPSTREAM_COMPONENTS,
    check_dependencies,
    plan_dependencies,
)

RETIRED_AUX_UPSTREAMS = frozenset({
    'script.skinvariables',
    'script.module.jurialmunkey',
    'script.module.infotagger',
})
ACTIVE_SEEDABLE_UPSTREAMS = frozenset(UPSTREAM_COMPONENTS - RETIRED_AUX_UPSTREAMS)


def write_addon(base: Path, addon_id: str, version: str = '1.0.0',
                requires: tuple[dict[str, str], ...] = (),
                origin: str | None = None, extra_files: dict[str, str] | None = None) -> Path:
    folder = base / addon_id
    folder.mkdir(parents=True, exist_ok=True)
    imports = []
    for req in requires:
        opt = ' optional="true"' if req.get('optional') == 'true' else ''
        ver = f' version="{req["version"]}"' if 'version' in req else ''
        imports.append(f'<import addon="{req["addon"]}"{ver}{opt}/>')
    xml = f'<addon id="{addon_id}" version="{version}"><requires>{"".join(imports)}</requires></addon>'
    (folder / 'addon.xml').write_text(xml, encoding='utf-8')
    if origin is not None:
        (folder / 'origin').write_text(origin, encoding='utf-8')
    for rel, body in (extra_files or {}).items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding='utf-8')
    return folder


def addon_zip_bytes(addon_id: str, version: str = '1.0.0',
                    requires: tuple[dict[str, str], ...] = ()) -> bytes:
    imports = []
    for req in requires:
        opt = ' optional="true"' if req.get('optional') == 'true' else ''
        ver = f' version="{req["version"]}"' if 'version' in req else ''
        imports.append(f'<import addon="{req["addon"]}"{ver}{opt}/>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f'{addon_id}/addon.xml',
            f'<addon id="{addon_id}" version="{version}"><requires>{"".join(imports)}</requires></addon>',
        )
        zf.writestr(f'{addon_id}/default.py', f'VERSION = "{version}"\n')
    return buf.getvalue()


def build_signed_bundle(dest: Path, key, trust: dict, *, sequence: int = 1,
                        version: str = '1.0.0', skin_requires_skinvariables: bool = False,
                        requests_min: str = '0.0.1') -> Path:
    items = []
    blobs = {}
    for comp in sorted(FULL_COMPONENTS):
        reqs: tuple[dict[str, str], ...] = ()
        if comp == 'plugin.video.bobbi':
            reqs = tuple(
                {'addon': dep, 'version': requests_min if dep == 'script.module.requests' else '0.0.1'}
                for dep in sorted(ACTIVE_SEEDABLE_UPSTREAMS)
            )
        elif comp == 'skin.bobbi.cinema' and skin_requires_skinvariables:
            reqs = ({'addon': 'script.skinvariables', 'version': '2.2.2'},)
        elif comp == 'script.skinvariables':
            reqs = ({'addon': 'script.module.jurialmunkey', 'version': '0.2.35'},)
        comp_ver = '2.2.9' if comp == 'script.skinvariables' else '0.2.35' if comp == 'script.module.jurialmunkey' else version
        raw = addon_zip_bytes(comp, version=comp_ver, requires=reqs)
        fname = f'{comp}/{comp}-{comp_ver}.zip'
        blobs[fname] = raw
        items.append({
            'id': comp,
            'version': comp_ver,
            'file': fname,
            'size': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(),
        })
    manifest_bytes = json.dumps(
        {'schema': 2, 'channel': 'private-stable', 'profile': 'coreelec', 'sequence': sequence, 'components': items},
        sort_keys=True,
    ).encode('utf-8')
    sig = base64.b64encode(key.sign(manifest_bytes, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(dest, 'w') as zf:
        zf.writestr('release.json', manifest_bytes)
        zf.writestr('release.sig', sig)
        for name, data in blobs.items():
            zf.writestr(name, data)
    return dest


@pytest.fixture(scope='module')
def signing_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    nums = key.public_key().public_numbers()
    trust = {
        'schema': 1,
        'components': sorted(FULL_COMPONENTS),
        'key': {'algorithm': 'RSA3072-SHA256', 'e': 65537, 'n': format(nums.n, 'x')},
    }
    return key, trust


def test_real_skin_removes_skinvariables_while_keeping_22_component_envelope(tmp_path):
    skin_xml = ET.parse(ROOT / 'addons/skin.bobbi.cinema/addon.xml').getroot()
    imported_ids = {node.get('addon') for node in skin_xml.findall('./requires/import')}
    assert 'script.skinvariables' not in imported_ids

    trust = load_trust()
    assert len(trust['components']) == 22
    assert set(trust['components']) == FULL_COMPONENTS
    assert RETIRED_AUX_UPSTREAMS <= set(trust['components'])

    stage = tmp_path / 'stage'
    stage.mkdir()
    for base in (ROOT / 'addons', ROOT / 'third_party/addons'):
        for addon_xml in base.glob('*/addon.xml'):
            comp = addon_xml.parent.name
            if comp in FULL_COMPONENTS:
                target = stage / comp
                target.mkdir(parents=True)
                (target / 'addon.xml').write_bytes(addon_xml.read_bytes())

    live = tmp_path / 'live'
    live.mkdir()
    plan = plan_dependencies(
        live,
        stage,
        managed=MANAGED,
        details=lambda name: {'version': '3.4.3', 'enabled': True} if name == 'script.module.pycryptodome' else None,
    )
    assert set(plan['order']).isdisjoint(RETIRED_AUX_UPSTREAMS)
    for retired in RETIRED_AUX_UPSTREAMS:
        assert plan['items'].get(retired, {'state': NOT_REQUIRED})['state'] == NOT_REQUIRED
    for needed in ACTIVE_SEEDABLE_UPSTREAMS:
        assert needed in plan['order']
        assert plan['items'][needed]['state'] == MISSING_SEEDABLE


def test_retained_old_skinvariables_and_user_skin_succeed_with_zero_touch(tmp_path, monkeypatch):
    """DEP-01/02/03/04/05: Old jurialmunkey/skinvariables & other skins stay untouched."""
    stage, live = tmp_path / 'stage', tmp_path / 'addons'
    stage.mkdir()
    live.mkdir()
    for comp in FULL_COMPONENTS:
        reqs = ()
        ver = '1.0.0'
        if comp == 'plugin.video.bobbi':
            reqs = ({'addon': 'script.module.requests', 'version': '2.31.0'},)
        elif comp == 'script.skinvariables':
            ver = '2.2.9'
            reqs = ({'addon': 'script.module.jurialmunkey', 'version': '0.2.35'},)
        elif comp == 'script.module.jurialmunkey':
            ver = '0.2.35'
        write_addon(stage, comp, ver, requires=reqs, extra_files={'staged_marker.txt': 'new'})

    # Existing user installation: old official jurialmunkey 0.2.2, disabled skinvariables 2.1.14, user skin
    write_addon(live, 'script.module.requests', '2.31.0', origin='repository.xbmc.org')
    write_addon(live, 'script.module.jurialmunkey', '0.2.2', origin='repository.xbmc.org',
                extra_files={'sentinel.txt': 'user-jurial-0.2.2'})
    write_addon(live, 'script.skinvariables', '2.1.14',
                requires=({'addon': 'script.module.jurialmunkey', 'version': '0.2.2'},),
                origin='repository.xbmc.org', extra_files={'sentinel.txt': 'user-sv-2.1.14'})
    write_addon(live, 'skin.arctic.fuse.2', '2.4.1',
                requires=({'addon': 'script.skinvariables', 'version': '2.1.0'},),
                origin='repository.jurialmunkey', extra_files={'skin_sentinel.txt': 'keep-me'})

    registered = {
        'script.module.pycryptodome': {'version': '3.4.3', 'enabled': True},
        'script.module.requests': {'version': '2.31.0', 'enabled': True},
        'script.module.jurialmunkey': {'version': '0.2.2', 'enabled': True},
        'script.skinvariables': {'version': '2.1.14', 'enabled': False},
        'skin.arctic.fuse.2': {'version': '2.4.1', 'enabled': True},
    }
    commands, rpc_calls = [], []

    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(waitForAbort=lambda _: False),
        executebuiltin=lambda cmd, wait=False: commands.append(cmd),
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Window=lambda _: SimpleNamespace(getProperty=lambda _: 'ready', clearProperty=lambda _: None),
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda p: str(live) if str(p).startswith('special://') else str(p)
    ))
    monkeypatch.setattr(ui, 'rpc', lambda method, params=None: rpc_calls.append((method, params)))

    host = KodiHost()
    monkeypatch.setattr(host, 'details', lambda aid: registered.get(aid))
    host.dependencies(stage)

    assert commands == []
    assert rpc_calls == []
    assert (live / 'script.module.jurialmunkey/sentinel.txt').read_text(encoding='utf-8') == 'user-jurial-0.2.2'
    assert (live / 'script.skinvariables/sentinel.txt').read_text(encoding='utf-8') == 'user-sv-2.1.14'
    assert (live / 'skin.arctic.fuse.2/skin_sentinel.txt').read_text(encoding='utf-8') == 'keep-me'
    assert not (live / 'script.module.infotagger').exists()
    assert not (live / 'script.skinvariables/staged_marker.txt').exists()
    assert registered['script.skinvariables']['enabled'] is False


def test_retained_upstream_uses_installed_manifest_without_ghost_floor(tmp_path):
    """DEP-16: Retained older requests must not inherit staged requests' higher urllib3 floor."""
    stage, live = tmp_path / 'stage', tmp_path / 'addons'
    stage.mkdir()
    live.mkdir()
    for comp in MANAGED:
        reqs = ({'addon': 'script.module.requests', 'version': '2.25.0'},) if comp == 'plugin.video.bobbi' else ()
        write_addon(stage, comp, '1.0.0', requires=reqs)
    # Staged seed has requests 2.31.0 requiring urllib3 >= 2.2.3
    write_addon(stage, 'script.module.requests', '2.31.0',
                requires=({'addon': 'script.module.urllib3', 'version': '2.2.3'},))
    write_addon(stage, 'script.module.urllib3', '2.2.3')

    # Live Kodi has requests 2.26.0 requiring urllib3 >= 1.26.0, and urllib3 1.26.5 installed
    write_addon(live, 'script.module.requests', '2.26.0',
                requires=({'addon': 'script.module.urllib3', 'version': '1.26.0'},))
    write_addon(live, 'script.module.urllib3', '1.26.5')

    plan = plan_dependencies(
        live,
        stage,
        managed=MANAGED,
        details=lambda aid: {'version': {'script.module.requests': '2.26.0', 'script.module.urllib3': '1.26.5'}.get(aid), 'enabled': True}
        if aid in ('script.module.requests', 'script.module.urllib3') else None,
    )
    assert plan['items']['script.module.requests']['manifest_source'] == 'installed'
    assert plan['items']['script.module.urllib3']['minimum'] == '1.26.0'
    assert plan['items']['script.module.urllib3']['state'] == SATISFIED


def test_needs_upgrade_never_calls_fake_install_addon_and_supports_native_recheck(tmp_path, monkeypatch, signing_pair):
    """N3-INST-01 / DEP-08: Old requests < floor never calls InstallAddon; hands off to addons://dependencies/ cleanly."""
    stage, live = tmp_path / 'stage', tmp_path / 'addons'
    stage.mkdir()
    live.mkdir()
    for comp in FULL_COMPONENTS:
        reqs = ({'addon': 'script.module.requests', 'version': '2.31.0'},) if comp == 'plugin.video.bobbi' else ()
        write_addon(stage, comp, '1.0.0', requires=reqs)
    write_addon(live, 'script.module.requests', '2.25.1', origin='repository.xbmc.org')

    state = {'requests_ver': '2.25.1', 'enabled': True}
    commands = []
    waits = []
    enabled_rpc = []

    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(waitForAbort=lambda sec: (waits.append(sec) or False)),
        Player=lambda: SimpleNamespace(isPlaying=lambda: False),
        executebuiltin=lambda cmd, wait=False: commands.append((cmd, wait)),
        LOGINFO=1,
        LOGERROR=3,
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda p: str(live) if str(p).startswith('special://') else str(p)
    ))

    def fake_rpc(method, params=None):
        if method == 'Settings.GetSettingValue' and (params or {}).get('setting') == 'locale.language':
            return {'value': 'resource.language.en_gb'}
        if method == 'Addons.SetAddonEnabled':
            enabled_rpc.append((params['addonid'], params['enabled']))
            if params['addonid'] == 'script.module.requests':
                state['enabled'] = bool(params['enabled'])
            return 'OK'
        raise AssertionError((method, params))

    monkeypatch.setattr(ui, 'rpc', fake_rpc)

    def live_details(aid):
        if aid == 'script.module.pycryptodome':
            return {'version': '3.4.3', 'enabled': True}
        if aid == 'script.module.requests':
            return {'version': state['requests_ver'], 'enabled': state['enabled']}
        return None

    # 1) No dialog -> DEPENDENCY_NEEDS_UPGRADE, zero InstallAddon, zero ActivateWindow
    host_no_dlg = KodiHost()
    host_no_dlg.dialog = None
    monkeypatch.setattr(host_no_dlg, 'details', live_details)
    with pytest.raises(UpdateError, match=r'^DEPENDENCY_NEEDS_UPGRADE:script\.module\.requests:2\.25\.1->2\.31\.0$'):
        host_no_dlg.dependencies(stage)
    assert commands == []
    assert waits == []

    # 2) User declines yesno -> DEPENDENCY_NEEDS_UPGRADE, zero ActivateWindow, zero InstallAddon
    prompts = []
    host_decline = KodiHost()
    host_decline.dialog = SimpleNamespace(yesno=lambda title, body: (prompts.append((title, body)) and False))
    monkeypatch.setattr(host_decline, 'details', live_details)
    with pytest.raises(UpdateError, match=r'^DEPENDENCY_NEEDS_UPGRADE:script\.module\.requests:2\.25\.1->2\.31\.0$'):
        host_decline.dependencies(stage)
    assert len(prompts) == 1
    assert 'script.module.requests' in prompts[0][1]
    assert '2.25.1' in prompts[0][1] and '2.31.0' in prompts[0][1]
    assert 'addons://dependencies/' in prompts[0][1]
    assert commands == []

    # 3) User accepts yesno -> opens AddonBrowser at addons://dependencies/ (wait=False) & releases modal flow immediately!
    prompts.clear()
    host_accept = KodiHost()
    host_accept.dialog = SimpleNamespace(yesno=lambda title, body: (prompts.append((title, body)) or True))
    monkeypatch.setattr(host_accept, 'details', live_details)
    with pytest.raises(UpdateError, match=r'^DEPENDENCY_HANDOFF_OPENED:script\.module\.requests:2\.25\.1->2\.31\.0$'):
        host_accept.dependencies(stage)
    assert len(prompts) == 1  # Never pops a second yesno on top of AddonBrowser!
    assert commands == [('ActivateWindow(AddonBrowser,addons://dependencies/,return)', False)]
    assert not any('InstallAddon' in cmd for cmd, _ in commands)

    # 3b) In ce_install_ui.main(), DEPENDENCY_HANDOFF_OPENED logs INFO and exits cleanly without dialog.ok covering AddonBrowser
    key, trust = signing_pair
    real_bundle = build_signed_bundle(tmp_path / 'script.bobbi.start-test.zip', key, trust, sequence=1, requests_min='2.31.0')
    work_dir = tmp_path / 'start_profile'
    work_dir.mkdir(parents=True, exist_ok=True)
    logs = []
    ok_modals = []
    commands.clear()
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(waitForAbort=lambda _: False, abortRequested=lambda: False),
        Player=lambda: SimpleNamespace(isPlaying=lambda: False),
        executebuiltin=lambda cmd, wait=False: commands.append((cmd, wait)),
        log=lambda msg, level=1: logs.append((msg, level)),
        LOGINFO=1,
        LOGERROR=3,
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Dialog=lambda: SimpleNamespace(
            yesno=lambda *a: True,
            textviewer=lambda *a: None,
            ok=lambda *a: ok_modals.append(a),
            select=lambda *a, **kw: 1,
        ),
    ))
    monkeypatch.setattr('bobbi_platform.android_ui.bundled_host', lambda: False)
    monkeypatch.setattr(ui, 'profile', lambda *a, **kw: work_dir)
    monkeypatch.setattr(ui, 'readable_text', lambda *a, **kw: True)
    monkeypatch.setattr(ui, 'ensure_host_language', lambda *a, **kw: {'action': 'already_initialized'})
    monkeypatch.setattr(ui, 'Installer', lambda addons_p, work_p, host_obj: Installer(addons_p, work_p, host_obj, trust=trust))
    monkeypatch.setattr(KodiHost, 'details', lambda self, aid: live_details(aid))
    ui.main(payload=str(real_bundle))
    assert ok_modals == []
    assert commands == [('ActivateWindow(AddonBrowser,addons://dependencies/,return)', False)]
    assert any('DEPENDENCY_HANDOFF_OPENED' in msg and lvl == 1 for msg, lvl in logs)
    assert not (work_dir / 'installation.json').exists()

    # 4) User re-runs dependencies(stage) while Kodi still reports 2.25.1 -> prompts again (never bypassed!)
    commands.clear()
    prompts.clear()
    with pytest.raises(UpdateError, match=r'^DEPENDENCY_HANDOFF_OPENED:script\.module\.requests:2\.25\.1->2\.31\.0$'):
        host_accept.dependencies(stage)
    assert len(prompts) == 1
    assert commands == [('ActivateWindow(AddonBrowser,addons://dependencies/,return)', False)]

    # 5) User upgrades script.module.requests in Kodi to 2.31.0 (even if currently disabled) and re-runs dependencies(stage)
    commands.clear()
    prompts.clear()
    state['requests_ver'] = '2.31.0'
    state['enabled'] = False
    (live / 'script.module.requests/addon.xml').write_text(
        '<addon id="script.module.requests" version="2.31.0"><requires/></addon>', encoding='utf-8'
    )
    host_recheck = KodiHost()
    host_recheck.dialog = SimpleNamespace(yesno=lambda *a: (prompts.append(a) or True))
    monkeypatch.setattr(host_recheck, 'details', live_details)
    host_recheck.dependencies(stage)
    assert prompts == []
    assert commands == []
    assert enabled_rpc == [('script.module.requests', True)]
    assert state['enabled'] is True


def test_topological_seeding_disabled_enable_and_directory_conflict_protection(tmp_path, monkeypatch):
    """DEP-07/09/10/11: Seed in dependency order, enable disabled required dep, never delete residual dir."""
    stage, live = tmp_path / 'stage', tmp_path / 'addons'
    stage.mkdir()
    live.mkdir()
    for comp in FULL_COMPONENTS:
        reqs = ()
        if comp == 'plugin.video.bobbi':
            reqs = ({'addon': 'script.module.requests', 'version': '2.31.0'},)
        elif comp == 'script.module.requests':
            reqs = (
                {'addon': 'script.module.urllib3', 'version': '2.2.3'},
                {'addon': 'script.module.idna', 'version': '3.0.0'},
            )
        elif comp == 'script.module.urllib3':
            reqs = ({'addon': 'script.module.certifi', 'version': '2023.5.7'},)
        write_addon(stage, comp, '2.31.0' if comp == 'script.module.requests' else '2.2.3' if comp == 'script.module.urllib3' else '2023.5.7', requires=reqs)

    # Disabled required idna on disk, plus unregistered residual skinvariables (not in closure -> ignored)
    write_addon(live, 'script.module.idna', '3.10.0')
    write_addon(live, 'script.skinvariables', '2.1.0', extra_files={'residual.txt': 'keep'})

    enabled_log = []
    enabled_set = set()
    seed_order = []
    orig_copytree = ui.shutil.copytree

    def tracked_copytree(source, dest, *a, **kw):
        seed_order.append(Path(source).name)
        return orig_copytree(source, dest, *a, **kw)

    def details(aid):
        if aid == 'script.module.pycryptodome':
            return {'version': '3.4.3', 'enabled': True}
        if aid == 'script.skinvariables':
            return None  # Residual unregistered folder outside closure!
        xml_path = live / aid / 'addon.xml'
        if not xml_path.exists():
            return None
        ver = ET.parse(xml_path).getroot().get('version')
        return {'version': ver, 'enabled': aid in enabled_set}

    properties = {}
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(waitForAbort=lambda _: False),
        executebuiltin=lambda cmd, wait=False: properties.__setitem__(
            cmd.split('(', 1)[1].split(',', 1)[0], 'ready'
        ) if cmd.startswith('SetProperty(') else None,
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(
        Window=lambda _: SimpleNamespace(
            getProperty=lambda k: properties.get(k, ''),
            clearProperty=lambda k: properties.pop(k, None),
        ),
    ))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda p: str(live) if str(p).startswith('special://') else str(p)
    ))
    monkeypatch.setattr(ui.shutil, 'copytree', tracked_copytree)
    monkeypatch.setattr(ui, 'rpc', lambda method, params: (
        enabled_log.append(params['addonid']) or enabled_set.add(params['addonid'])
    ))

    host = KodiHost()
    monkeypatch.setattr(host, 'details', details)
    host.dependencies(stage)

    assert seed_order == ['script.module.certifi', 'script.module.urllib3', 'script.module.requests']
    assert 'script.module.idna' in enabled_log
    assert (live / 'script.skinvariables/residual.txt').read_text(encoding='utf-8') == 'keep'

    # Now create an unregistered residual directory for a REQUIRED addon -> DIRECTORY_CONFLICT, never deleted!
    stage2, live2 = tmp_path / 'stage2', tmp_path / 'live2'
    stage2.mkdir()
    live2.mkdir()
    for comp in FULL_COMPONENTS:
        reqs = ({'addon': 'script.module.routing', 'version': '0.2.3'},) if comp == 'plugin.video.bobbi' else ()
        write_addon(stage2, comp, '1.0.0', requires=reqs)
    write_addon(live2, 'script.module.routing', '0.2.3', extra_files={'user_file.txt': 'do-not-delete'})
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(live2)))

    host2 = KodiHost()
    monkeypatch.setattr(host2, 'details', lambda aid: {'version': '3.4.3', 'enabled': True} if aid == 'script.module.pycryptodome' else None)
    with pytest.raises(UpdateError, match=r'DEPENDENCY_DIRECTORY_CONFLICT:script\.module\.routing'):
        host2.dependencies(stage2)
    assert (live2 / 'script.module.routing/user_file.txt').read_text(encoding='utf-8') == 'do-not-delete'


def test_rpc_detail_fallback_to_list_and_unknown_state_safety(tmp_path, monkeypatch):
    """DEP-13/14: GetAddonDetails failure falls back to GetAddons; total RPC failure stays STATE_UNKNOWN."""
    stage, live = tmp_path / 'stage', tmp_path / 'addons'
    stage.mkdir()
    live.mkdir()
    for comp in FULL_COMPONENTS:
        reqs = ({'addon': 'script.module.requests', 'version': '2.31.0'},) if comp == 'plugin.video.bobbi' else ()
        write_addon(stage, comp, '2.31.0', requires=reqs)
    write_addon(live, 'script.module.requests', '2.31.0', extra_files={'keep.txt': 'untouched'})

    def rpc_fallback(method, params=None):
        if method == 'Addons.GetAddonDetails':
            raise RuntimeError('RPC detail timeout')
        if method == 'Addons.GetAddons':
            return {'addons': [
                {'addonid': 'script.module.requests', 'version': '2.31.0', 'enabled': True},
                {'addonid': 'script.module.pycryptodome', 'version': '3.4.3', 'enabled': True},
            ]}
        raise AssertionError(method)

    monkeypatch.setattr(ui, 'rpc', rpc_fallback)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(waitForAbort=lambda _: False)))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda p: str(live) if str(p).startswith('special://') else str(p)
    ))
    host = KodiHost()
    assert host.details('script.module.requests') == {'addonid': 'script.module.requests', 'version': '2.31.0', 'enabled': True}
    host.dependencies(stage)

    # Both detail and list fail -> STATE_UNKNOWN, zero seeding or overwrite
    def rpc_dead(method, params=None):
        raise RuntimeError('RPC offline')

    monkeypatch.setattr(ui, 'rpc', rpc_dead)
    with pytest.raises(UpdateError, match=r'ADDON_STATE_UNKNOWN'):
        host.dependencies(stage)
    assert (live / 'script.module.requests/keep.txt').read_text(encoding='utf-8') == 'untouched'


@pytest.mark.parametrize('kind', ['cycle', 'bad_id', 'bad_version', 'id_mismatch'])
def test_prewrite_validation_rejects_malformed_graphs_before_any_write(tmp_path, kind):
    """DEP-17: Cycles, illegal IDs/versions, or mismatched folder/manifest IDs fail pre-write."""
    stage, live = tmp_path / 'stage', tmp_path / 'live'
    stage.mkdir()
    live.mkdir()
    for comp in MANAGED:
        write_addon(stage, comp, '1.0.0')
    if kind == 'cycle':
        write_addon(stage, 'plugin.video.bobbi', '1.0.0', requires=({'addon': 'script.module.requests', 'version': '1.0.0'},))
        write_addon(stage, 'script.module.requests', '1.0.0', requires=({'addon': 'script.module.urllib3', 'version': '1.0.0'},))
        write_addon(stage, 'script.module.urllib3', '1.0.0', requires=({'addon': 'script.module.requests', 'version': '1.0.0'},))
    elif kind == 'bad_id':
        write_addon(stage, 'plugin.video.bobbi', '1.0.0', requires=({'addon': '../escape', 'version': '1.0.0'},))
    elif kind == 'bad_version':
        write_addon(stage, 'plugin.video.bobbi', '1.0.0', requires=({'addon': 'script.module.requests', 'version': 'bad ver!'},))
    elif kind == 'id_mismatch':
        (stage / 'plugin.video.bobbi/addon.xml').write_text('<addon id="other.addon" version="1.0.0"/>', encoding='utf-8')

    with pytest.raises(UpdateError):
        plan_dependencies(live, stage, managed=MANAGED)
    assert list(live.iterdir()) == []


def test_space_budget_and_recovery_store_respect_per_bundle_closure(tmp_path, signing_pair):
    """DEP-20: Space budget ignores retired upstreams; old recovery bundle uses its own real closure."""
    key, trust = signing_pair
    addons = tmp_path / 'addons'
    work = tmp_path / 'work'
    addons.mkdir()
    work.mkdir()
    for dep in ACTIVE_SEEDABLE_UPSTREAMS:
        write_addon(addons, dep, '2.0.0')
    # Notice: script.skinvariables / jurialmunkey / infotagger are completely absent from addons/!

    new_bundle = build_signed_bundle(tmp_path / 'new.zip', key, trust, sequence=20, version='2.0.0',
                                     skin_requires_skinvariables=False)

    # Historical recovery bundle where old skin DID require script.skinvariables >= 2.2.2
    old_bundle = build_signed_bundle(tmp_path / 'old.zip', key, trust, sequence=19, version='1.9.0',
                                     skin_requires_skinvariables=True)
    old_sha_before = hashlib.sha256(old_bundle.read_bytes()).hexdigest()

    enabled_vec = set()
    host = SimpleNamespace(
        dependencies=lambda stage: None,
        skin=lambda: 'skin.estuary',
        enabled=lambda: sorted(enabled_vec),
        quiesce=lambda: None,
        refresh=lambda: None,
        verify=lambda versions: None,
        activate=lambda versions: enabled_vec.update(versions),
        restore=lambda skin, enabled: None,
    )
    installer = Installer(addons, work, host, trust=trust)
    space = installer.plan_space(new_bundle)
    assert space['dependency_copy_bytes'] == 0
    old_space = installer.plan_space(old_bundle)
    assert old_space['dependency_copy_bytes'] > 0
    installer.apply(old_bundle)
    installer.apply(new_bundle)
    watermark_before = installer._read()['high_watermark']
    assert watermark_before == 20

    store = RecoveryStore(work, trust)
    old_point = next(p for p in store.list()['points'] if p['sequence'] == 19)
    dep_plan = store.plan_dependencies(
        old_point['name'],
        addons,
        details=lambda aid: {'version': '2.0.0', 'enabled': True} if aid in ACTIVE_SEEDABLE_UPSTREAMS else None,
    )
    assert 'script.skinvariables' in dep_plan['order']
    assert 'script.module.jurialmunkey' in dep_plan['order']
    assert dep_plan['items']['script.skinvariables']['state'] == MISSING_SEEDABLE
    assert hashlib.sha256(old_bundle.read_bytes()).hexdigest() == old_sha_before
    assert installer._read()['high_watermark'] == watermark_before

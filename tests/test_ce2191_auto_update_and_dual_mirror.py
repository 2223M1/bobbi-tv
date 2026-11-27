"""CE2191 regression suite: default-enabled idle auto-update, disable auto-update & check-updates settings."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
for rel in (
    'addons/script.module.bobbi.core/lib',
    'addons/script.module.bobbi.platform/lib',
    'addons/plugin.video.bobbi',
    'tools',
):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from bobbi_platform import ce_install_ui as ui, ce_update_notice as notice, online_updates as online
from bobbi_platform.updates import UpdateError, auto_update_enabled
from test_onboarding import setup_ui


def _write_journal(work: Path, sequence: int = 2026102190, **extra) -> None:
    work.mkdir(parents=True, exist_ok=True)
    row = dict(schema=1, tx='a' * 32, items=[], sequence=sequence, high_watermark=sequence, phase='complete')
    row.update(extra)
    (work / 'installation.json').write_text(json.dumps(row), encoding='utf-8')


def test_auto_update_enabled_by_default_even_with_legacy_muted_notice_and_can_be_disabled(tmp_path):
    work = tmp_path / 'addon_data' / 'script.bobbi.start'
    work.mkdir(parents=True)
    # Even if legacy update-notices.json was false, auto-update defaults to True
    notice.enabled(work, False)
    assert notice.enabled(work) is False
    assert auto_update_enabled(work) is True
    assert notice.auto_enabled(work) is True

    # Disabling writes auto-update.json = false
    assert notice.auto_enabled(work, False) is False
    assert (work / 'auto-update.json').read_text(encoding='utf-8').strip() == 'false'
    assert notice.auto_enabled(work) is False

    # Re-enabling writes true
    assert notice.auto_enabled(work, True) is True
    assert notice.auto_enabled(work) is True

    # Corrupt file fails closed
    (work / 'auto-update.json').write_text('{"bad": 1}', encoding='utf-8')
    with pytest.raises(UpdateError, match='AUTO_UPDATE_PREF_INVALID'):
        notice.auto_enabled(work)


def test_check_auto_update_lifecycle_cooldown_and_disabled_gate(tmp_path):
    from bobbi_platform.updates import _Lock
    notice.reset_auto_update_cooldowns()
    work = tmp_path / 'start'
    _write_journal(work, sequence=2026102190)

    dispatched, notified = [], []
    now = [1000.0]
    offer = {'tag': 'ce2191', 'sequence': 2026102191}

    # Simulate CoreELEC post-install steady state: installation.lock file stays on disk!
    # While actively held -> returns 'deferred'; once released -> file still exists and dispatches!
    with _Lock(work / 'installation.lock'):
        assert notice.check_auto_update(
            work,
            lambda: False,
            dispatched.append,
            lookup=lambda *_a, **_k: pytest.fail('network called while install lock held'),
        ) == 'deferred'
    assert (work / 'installation.lock').exists()

    # 1. Default enabled + released installation.lock inode on disk -> discovers & dispatches!
    res = notice.check_auto_update(
        work,
        lambda: False,
        dispatched.append,
        notify=notified.append,
        lookup=lambda _c, *, track: offer,
        cooldown_seconds=300,
        clock=lambda: now[0],
    )
    assert res == 'dispatched'
    assert dispatched == ['CE2191'] and notified == ['CE2191']

    # 2. Immediate repeat within cooldown -> returns 'cooldown' without re-dispatching
    now[0] += 30.0
    assert notice.check_auto_update(
        work,
        lambda: False,
        dispatched.append,
        lookup=lambda _c, *, track: offer,
        cooldown_seconds=300,
        clock=lambda: now[0],
    ) == 'cooldown'
    assert len(dispatched) == 1

    # 3. Disable auto-update -> returns 'disabled' with zero network lookups
    notice.auto_enabled(work, False)
    assert notice.check_auto_update(
        work,
        lambda: False,
        dispatched.append,
        lookup=lambda *_a, **_k: pytest.fail('network called while disabled'),
    ) == 'disabled'

    # 4. Re-enable and advance journal to 2026102191 -> returns 'current'
    notice.auto_enabled(work, True)
    _write_journal(work, sequence=2026102191)
    assert notice.check_auto_update(
        work,
        lambda: False,
        dispatched.append,
        lookup=lambda _c, *, track: offer,
        clock=lambda: now[0] + 500.0,
    ) == 'current'


def test_settings_xml_and_setup_expose_check_updates_and_disable_auto_update(setup_ui, tmp_path, monkeypatch):
    # 1. Settings.xml system_maint category exposes check_updates (#32380) and auto_update_policy (#32381)
    settings_xml = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/Settings.xml').getroot()
    maint_items = [
        it for it in settings_xml.findall('.//control[@id="9010"]/content/item')
        if 'system_maint' in (it.findtext('visible') or '')
    ]
    clicks = [it.findtext('onclick') for it in maint_items]
    assert 'RunScript(script.bobbi.setup,check_updates)' in clicks
    assert 'RunScript(script.bobbi.setup,auto_update_policy)' in clicks
    assert clicks.index('RunScript(script.bobbi.setup,check_updates)') == 0
    assert clicks.index('RunScript(script.bobbi.setup,auto_update_policy)') == 1

    # 2. run_check_updates dispatches online check when idle, refuses during playback
    setup_ui.playing = True
    assert setup_ui.module.run_check_updates(setup_ui.dialog) is False
    assert setup_ui.builtins == []
    setup_ui.playing = False
    setup_ui.dialogs.clear()
    assert setup_ui.module.run_check_updates(setup_ui.dialog) is True
    assert setup_ui.builtins == ['RunScript(script.bobbi.start,online)']

    # 3. show_updates option 6 toggles auto_update_policy (default preselect=0 -> disable=1 -> preselect=1)
    setup_ui.builtins.clear()
    work = tmp_path / 'profile_a'
    monkeypatch.setattr(sys.modules['xbmcvfs'], 'translatePath', lambda _: str(work))
    _write_journal(work, sequence=2026102190)

    seen_preselects = []
    choices = iter([6, 1])  # Open auto-update policy (6) -> Disable automatic updates (1)

    def select_disable(title, rows, **kw):
        if 'preselect' in kw:
            seen_preselects.append(kw['preselect'])
        return next(choices)

    setup_ui.dialog.select = select_disable
    assert setup_ui.module.show_updates(setup_ui.dialog) is True
    assert seen_preselects == [0]  # Default is enabled (0)
    assert notice.auto_enabled(work) is False

    # Re-open -> preselect is now 1 (Disabled); choose 0 (Enable)
    seen_preselects.clear()
    choices2 = iter([6, 0])

    def select_enable(title, rows, **kw):
        if 'preselect' in kw:
            seen_preselects.append(kw['preselect'])
        return next(choices2)

    setup_ui.dialog.select = select_enable
    monkeypatch.setattr(notice, 'coreelec', lambda: True)
    assert setup_ui.module.show_updates(setup_ui.dialog) is True
    assert seen_preselects == [1]
    assert notice.auto_enabled(work) is True
    # Must wake background AutoUpdateCheck worker rather than bypassing 20s idle via immediate RunScript(...,auto)
    assert 'RunScript(script.bobbi.start,auto)' not in setup_ui.builtins
    assert 'NotifyAll(bobbi.setup,AutoUpdatePolicyChanged)' in setup_ui.builtins


from test_ce_general_installer import environment, signing  # noqa: F401
from test_online_updates import Response, entry  # noqa: F401


def test_unattended_auto_online_installs_signed_update_without_modal_prompts(entry, signing, monkeypatch):
    import build_ce_entry
    assert set(ui._ENTRY_BOOTSTRAP_FILES) == set(build_ce_entry.BOOTSTRAP)

    # Seed initial generation 1 so box is an active managed install
    from test_ce_general_installer import package
    base_pkg = package(entry.env.root / 'base.zip', signing, 1, '1.0.0', channel='private-stable')
    entry.env.installer.apply(base_pkg)
    assert entry.env.installer._read()['sequence'] == 1

    # 1. When auto-update is disabled -> ui.main(auto=True) makes zero network calls & zero changes
    notice.auto_enabled(entry.env.work, False)
    monkeypatch.setattr(online, '_open', lambda _: pytest.fail('network called when auto-update disabled'))
    assert ui.main(auto=True) is False
    assert entry.env.installer._read()['sequence'] == 1

    # 2. Re-enable auto-update, but active playback -> aborts silently with zero modal error popups
    notice.auto_enabled(entry.env.work, True)
    entry.playing = True
    entry.dialogs.clear()
    assert ui.main(auto=True) is False
    assert entry.dialogs == []
    assert entry.env.installer._read()['sequence'] == 1

    # 3. Idle < 20s (remote just pressed) -> refuses unattended update before network/apply!
    from test_ce_update_continuity import make_offer
    entry.playing = False
    idle_seconds = [0]
    sys.modules['xbmc'].getGlobalIdleTime = lambda: idle_seconds[0]
    next_pkg = package(entry.env.root / 'next.zip', signing, 2, '2.0.0', channel='private-stable')
    next_raw = next_pkg.read_bytes()
    next_offer = make_offer(next_pkg, 'ce2055')
    monkeypatch.setattr(online, 'latest', lambda *_a, **_kw: pytest.fail('network called while idle < 20s'))
    assert ui.main(auto=True) is False
    assert entry.env.installer._read()['sequence'] == 1

    # 4. Idle drops below 20s mid-download -> cancels cleanly with zero apply and cleans partial staging!
    idle_seconds[0] = 25
    monkeypatch.setattr(online, 'latest', lambda *_a, **_kw: next_offer)

    class WakeDuringDownload(Response):
        def read1(self, size):
            idle_seconds[0] = 2
            return super().read1(size)

    monkeypatch.setattr(online, '_open', lambda _u: WakeDuringDownload(next_raw))
    assert ui.main(auto=True) is False
    assert entry.env.installer._read()['sequence'] == 1

    # 5. Idle >= 20s + auto-update enabled -> installs next_pkg (sequence=2) with zero modal dialogs!
    idle_seconds[0] = 25
    monkeypatch.setattr(online, '_open', lambda _u: Response(next_raw))
    assert ui.main(auto=True) is True
    assert entry.env.installer._read()['sequence'] == 2
    assert entry.dialogs == [] and not entry.confirmations

    # 6. Simulate legacy launcher (0.0.1) on disk -> ensure_entry_synced_from_recovery self-heals from recovery-v1!
    start_xml = entry.env.addons / 'script.bobbi.start' / 'addon.xml'
    start_xml.parent.mkdir(parents=True, exist_ok=True)
    start_xml.write_text('<addon id="script.bobbi.start" version="0.0.1"/>', encoding='utf-8')
    assert ui.ensure_entry_synced_from_recovery(entry.env.work, entry.env.addons, trust=signing[1]) is True
    assert ET.fromstring(start_xml.read_bytes()).get('version') == '2.0.0'
    # Idempotent when already synced and all bootstrap files match byte-for-byte
    assert ui.ensure_entry_synced_from_recovery(entry.env.work, entry.env.addons, trust=signing[1]) is False

    # 7. Same-version addon.xml (2.0.0) with missing/corrupt bootstrap module -> detected & repaired!
    boot_target = entry.env.addons / 'script.bobbi.start' / 'bootstrap' / 'bobbi_platform' / 'online_updates.py'
    orig_boot = boot_target.read_bytes()
    boot_target.write_bytes(b'# corrupted bootstrap')
    assert ui.ensure_entry_synced_from_recovery(entry.env.work, entry.env.addons, trust=signing[1]) is True
    assert boot_target.read_bytes() == orig_boot

    # 8. Newer offline script.bobbi.start (9.9.9) with embedded complete.bobbi-update.zip -> NEVER downgraded!
    embedded = entry.env.addons / 'script.bobbi.start' / 'resources' / 'complete.bobbi-update.zip'
    embedded.parent.mkdir(parents=True, exist_ok=True)
    embedded.write_bytes(b'offline-full-bundle')
    start_xml.write_text('<addon id="script.bobbi.start" version="9.9.9"/>', encoding='utf-8')
    out = {}
    assert ui.sync_entry_from_bundle(
        next_pkg, entry.env.addons, trust=signing[1], work=entry.env.work, report_outcome=out,
    ) is False
    assert out['status'] == 'kept_newer'
    assert ET.fromstring(start_xml.read_bytes()).get('version') == '9.9.9'
    assert embedded.read_bytes() == b'offline-full-bundle'

    # 9. Simulated os.replace failure on publish -> original script.bobbi.start is restored, NEVER deleted!
    start_xml.write_text('<addon id="script.bobbi.start" version="1.0.0"/>', encoding='utf-8')
    real_replace = ui.os.replace
    live_entry_dir = entry.env.addons / 'script.bobbi.start'

    def fail_stage_publish(src, dst):
        if Path(dst) == live_entry_dir and '.bobbi-entry-stage-' in Path(src).name:
            raise OSError('simulated publish failure')
        return real_replace(src, dst)

    monkeypatch.setattr(ui.os, 'replace', fail_stage_publish)
    fail_out = {}
    assert ui.sync_entry_from_bundle(
        next_pkg, entry.env.addons, trust=signing[1], work=entry.env.work, report_outcome=fail_out,
    ) is False
    monkeypatch.setattr(ui.os, 'replace', real_replace)
    assert fail_out['status'] == 'failed'
    assert live_entry_dir.is_dir() and ET.fromstring(start_xml.read_bytes()).get('version') == '1.0.0'

    # 10. Held installation.lock & phase='restored' skip recovery entry sync cleanly
    from bobbi_platform.updates import _Lock
    with _Lock(entry.env.work / 'installation.lock'):
        locked_out = {}
        assert ui.ensure_entry_synced_from_recovery(
            entry.env.work, entry.env.addons, trust=signing[1], report_outcome=locked_out,
        ) is False
        assert locked_out['status'] == 'failed'
    st = json.loads((entry.env.work / 'installation.json').read_text(encoding='utf-8'))
    st['phase'] = 'restored'
    (entry.env.work / 'installation.json').write_text(json.dumps(st), encoding='utf-8')
    restored_out = {}
    assert ui.ensure_entry_synced_from_recovery(
        entry.env.work, entry.env.addons, trust=signing[1], report_outcome=restored_out,
    ) is False
    assert restored_out['status'] == 'skipped_inactive'


def test_v4_gitcode_http_418_fails_over_to_github_while_tls_and_conflict_fail_closed(monkeypatch):
    from email.message import Message
    from io import BytesIO
    from urllib.error import HTTPError, URLError
    import ssl
    from test_online_updates import Response, tracked_offer

    valid_offer = tracked_offer(b'valid', sequence=2026102195, track='stable')
    raw_offer = json.dumps(valid_offer).encode('utf-8')

    def open_418_then_ok(url):
        if 'gitcode.com' in url:
            raise HTTPError(url, 418, "I'm a teapot", Message(), BytesIO(b'waf'))
        return Response(raw_offer)

    monkeypatch.setattr(online, '_open', open_418_then_ok)
    rep = {}
    got = online.latest(track='stable', report=rep)
    assert got['sequence'] == 2026102195
    assert rep['mirrors'] == 'unavailable'

    # TLS SSLError on primary mirror MUST still fail closed without silent downgrade/fallback
    monkeypatch.setattr(
        online,
        '_open',
        lambda u: (_ for _ in ()).throw(URLError(ssl.SSLError('certificate verify failed')))
        if 'gitcode.com' in u else Response(raw_offer),
    )
    with pytest.raises(URLError):
        online.latest(track='stable')


def test_rls01_isolated_bootstrap_auto_executes_without_missing_modules_and_rejects_incomplete_bundle(tmp_path, signing, monkeypatch):
    import shutil
    import subprocess
    import zipfile
    from io import BytesIO
    import build_ce_entry
    import test_ce_general_installer as fixtures

    # 1. Exact 24-file BOOTSTRAP copied into fresh python -I -B interpreter with full platform/lib on sys.path[1]
    boot_dir = tmp_path / 'bootstrap' / 'bobbi_platform'
    boot_dir.mkdir(parents=True)
    plat_lib = ROOT / 'addons/script.module.bobbi.platform/lib'
    for fname in build_ce_entry.BOOTSTRAP:
        shutil.copyfile(plat_lib / 'bobbi_platform' / fname, boot_dir / fname)

    work_dir = tmp_path / 'work'
    work_dir.mkdir()
    (work_dir / 'auto-update.json').write_text('false', encoding='utf-8')

    child_code = (
        "import importlib.util, json, sys, types\n"
        "from pathlib import Path\n"
        "sys.path[:0] = [sys.argv[1], sys.argv[2]]\n"
        "sys.modules['xbmc'] = types.SimpleNamespace(\n"
        "    Player=lambda: types.SimpleNamespace(isPlaying=lambda: False),\n"
        "    getCondVisibility=lambda _c: False,\n"
        "    getGlobalIdleTime=lambda: 60,\n"
        ")\n"
        "sys.modules['xbmcgui'] = types.SimpleNamespace(Dialog=lambda: types.SimpleNamespace())\n"
        "sys.modules['xbmcvfs'] = types.SimpleNamespace(translatePath=lambda _p: sys.argv[3])\n"
        "import bobbi_platform\n"
        "from bobbi_platform import ce_install_ui as ui\n"
        "inst = types.SimpleNamespace(work=Path(sys.argv[3]))\n"
        "host = types.SimpleNamespace(xbmc=sys.modules['xbmc'], monitor=types.SimpleNamespace(abortRequested=lambda: False), check_idle=lambda: None)\n"
        "ret = ui.install_auto_online(inst, host)\n"
        "print(json.dumps({'ret': ret, 'ui_file': ui.__file__, 'notice_in_boot': importlib.util.find_spec('bobbi_platform.ce_update_notice') is not None}))\n"
    )
    proc = subprocess.run(
        [sys.executable, '-I', '-B', '-c', child_code, str(tmp_path / 'bootstrap'), str(plat_lib), str(work_dir)],
        capture_output=True, text=True, check=True,
    )
    obs = json.loads(proc.stdout)
    assert obs['ret'] is False
    assert obs['notice_in_boot'] is False
    assert Path(obs['ui_file']).resolve() == (boot_dir / 'ce_install_ui.py').resolve()

    # 2. Signed bundle missing a required bootstrap file is rejected BEFORE touching live script.bobbi.start
    addons = tmp_path / 'addons'
    addons.mkdir()
    good_one = fixtures.package(tmp_path / 'one.zip', signing, 1, '1.0.0', channel='private-stable')
    assert ui.sync_entry_from_bundle(good_one, addons, trust=signing[1]) is True
    live_start = addons / 'script.bobbi.start'
    assert ET.parse(live_start / 'addon.xml').getroot().get('version') == '1.0.0'

    orig_archive = fixtures.archive

    def omit_ui_archive(name, version='2.0.0'):
        raw = orig_archive(name, version)
        if name != 'script.module.bobbi.platform':
            return raw
        buf = BytesIO()
        with zipfile.ZipFile(BytesIO(raw)) as src, zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if not item.filename.endswith('/ce_install_ui.py'):
                    dst.writestr(item, src.read(item.filename))
        return buf.getvalue()

    monkeypatch.setattr(fixtures, 'archive', omit_ui_archive)
    bad_two = fixtures.package(tmp_path / 'bad_two.zip', signing, 2, '2.0.0', channel='private-stable')
    monkeypatch.setattr(fixtures, 'archive', orig_archive)

    _write_journal(work_dir, sequence=2)
    bad_out = {}
    assert ui.sync_entry_from_bundle(
        bad_two, addons, trust=signing[1], work=work_dir, expected_sequence=2, report_outcome=bad_out,
    ) is False
    assert bad_out['status'] == 'failed' and 'ENTRY_BOOTSTRAP_INCOMPLETE' in bad_out['error']
    assert ET.parse(live_start / 'addon.xml').getroot().get('version') == '1.0.0'
    assert (live_start / 'bootstrap/bobbi_platform/ce_install_ui.py').is_file()

    # 3. Real online/offline entry ZIPs built via build_ce_entry.build() execute `default.py auto` (seq 1 -> 2) in isolated `python -I -B`
    import vendor_licenses
    base_pkg = fixtures.package(tmp_path / 'real_base.zip', signing, 1, '1.0.0', channel='private-stable')
    next_pkg = fixtures.package(tmp_path / 'real_next.zip', signing, 2, '2.0.0', channel='private-stable')
    expected_inv = json.loads((ROOT / 'release/source-inventory.json').read_text(encoding='utf-8'))['components']
    monkeypatch.setattr(build_ce_entry, 'files', lambda root_p: expected_inv[Path(root_p).name])
    monkeypatch.setattr(build_ce_entry, 'load_trust', lambda: signing[1])
    monkeypatch.setattr(vendor_licenses, 'verify_bundle_notices', lambda _sb: None)
    for online_mode in (True, False):
        mode_dir = tmp_path / ('entry_online' if online_mode else 'entry_offline')
        mode_addons = mode_dir / 'addons'
        mode_addons.mkdir(parents=True)
        entry_zip = mode_dir / f'script.bobbi.start-1.0.0-{"online" if online_mode else "offline"}.zip'
        entry_meta = build_ce_entry.build(base_pkg, entry_zip, online=online_mode)
        assert entry_meta['complete_offline_payload'] is (not online_mode)
        with zipfile.ZipFile(entry_zip) as zin:
            zin.extractall(mode_addons)

        run_auto_child = (
            "import hashlib, importlib.util, io, json, sys, types\n"
            "from pathlib import Path\n"
            "mode_dir = Path(sys.argv[1])\n"
            "plat_lib = Path(sys.argv[2])\n"
            "base_zip = Path(sys.argv[3])\n"
            "next_zip = Path(sys.argv[4])\n"
            "trust_doc = json.loads(Path(sys.argv[5]).read_text(encoding='utf-8'))\n"
            "addons_dir = mode_dir / 'addons'\n"
            "work_dir = mode_dir / 'userdata/addon_data/script.bobbi.start'\n"
            "work_dir.mkdir(parents=True, exist_ok=True)\n"
            "# Put full platform_lib on sys.path BEFORE default.py prepends bootstrap at sys.path[0]!\n"
            "sys.path.insert(0, str(plat_lib))\n"
            "sys.modules['xbmc'] = types.SimpleNamespace(\n"
            "    LOGERROR=4, LOGWARNING=2, LOGINFO=1,\n"
            "    log=lambda *a: None, executebuiltin=lambda *a: None,\n"
            "    getInfoLabel=lambda _k: '21.2',\n"
            "    getCondVisibility=lambda _c: False,\n"
            "    getGlobalIdleTime=lambda: 60,\n"
            "    Player=lambda: types.SimpleNamespace(isPlaying=lambda: False),\n"
            "    Monitor=lambda: types.SimpleNamespace(abortRequested=lambda: False, waitForAbort=lambda _d: False),\n"
            ")\n"
            "notices = []\n"
            "sys.modules['xbmcgui'] = types.SimpleNamespace(\n"
            "    Dialog=lambda: types.SimpleNamespace(notification=lambda *a, **k: notices.append(a)),\n"
            ")\n"
            "sys.modules['xbmcvfs'] = types.SimpleNamespace(\n"
            "    translatePath=lambda p: str(addons_dir) if 'home/addons' in p else str(work_dir),\n"
            ")\n"
            "sys.modules['xbmcaddon'] = types.SimpleNamespace(\n"
            "    Addon=lambda aid='script.bobbi.start': types.SimpleNamespace(\n"
            "        getAddonInfo=lambda k: str(addons_dir / aid) if k == 'path' else '1.0.0',\n"
            "    ),\n"
            ")\n"
            "# Import bootstrap package exactly as default.py does\n"
            "sys.path.insert(0, str(addons_dir / 'script.bobbi.start/bootstrap'))\n"
            "from bobbi_platform import ce_install_ui as boot_ui, ce_installer as boot_inst, online_updates as boot_online\n"
            "assert importlib.util.find_spec('bobbi_platform.ce_update_notice') is None\n"
            "vector = set()\n"
            "host = types.SimpleNamespace(\n"
            "    xbmc=sys.modules['xbmc'], monitor=sys.modules['xbmc'].Monitor(),\n"
            "    check_idle=lambda: None, dependencies=lambda _s: None,\n"
            "    skin=lambda: 'skin.estuary', enabled=lambda: sorted(vector),\n"
            "    quiesce=lambda: None, refresh=lambda: None, verify=lambda _v: None,\n"
            "    activate=lambda v: vector.update(v), restore=lambda _s, e: (vector.clear(), vector.update(e)),\n"
            "    close=lambda: None,\n"
            ")\n"
            "inst = boot_inst.Installer(addons_dir, work_dir, host, trust_doc)\n"
            "inst.apply(base_zip)\n"
            "boot_ui.KodiHost = lambda **_kw: host\n"
            "boot_ui.Installer = lambda *_a: inst\n"
            "boot_ui.profile = lambda *_a, **_kw: work_dir\n"
            "raw_next = next_zip.read_bytes()\n"
            "with boot_ui.SignedBundle(next_zip, trust_doc, 'coreelec') as sb:\n"
            "    next_mf = sb.check_all()\n"
            "offer = {'schema': 2, 'tag': 'ce2055', 'sequence': 2, 'size': len(raw_next),\n"
            "         'sha256': hashlib.sha256(raw_next).hexdigest(), 'track': 'stable', 'prerelease': False,\n"
            "         'manifest_channel': 'private-stable',\n"
            "         'versions': {r['id']: r['version'] for r in next_mf['components']},\n"
            "         'url': 'https://github.com/2223M1/bobbi-tv/releases/download/ce2055/BobbiTV-CE2055.bobbi-update.zip'}\n"
            "class _R(io.BytesIO):\n"
            "    status = 200\n"
            "    def __init__(self, b): super().__init__(b); self.headers = {'Content-Length': str(len(b))}\n"
            "    def read1(self, n): return self.read(n)\n"
            "boot_online.latest = lambda *_a, **_k: offer\n"
            "boot_online._open = lambda _u: _R(raw_next)\n"
            "sys.argv = ['default.py', 'auto']\n"
            "exec(compile((addons_dir / 'script.bobbi.start/default.py').read_text(encoding='utf-8'), 'default.py', 'exec'), {'__name__': '__main__'})\n"
            "print(json.dumps({'seq': inst._read()['sequence'], 'notices': notices, 'ui_file': boot_ui.__file__}))\n"
        )
        trust_file = mode_dir / 'trust.json'
        trust_file.write_text(json.dumps(signing[1]), encoding='utf-8')
        res_proc = subprocess.run(
            [sys.executable, '-I', '-B', '-c', run_auto_child, str(mode_dir), str(plat_lib), str(base_pkg), str(next_pkg), str(trust_file)],
            capture_output=True, text=True, check=True,
        )
        res_json = json.loads(res_proc.stdout)
        assert res_json['seq'] == 2
        assert res_json['notices'] and 'CE2055' in res_json['notices'][-1][1]
        assert 'bootstrap' in res_json['ui_file']


def test_rls02_rls03_pre_handoff_idle_recheck_sequence_binding_and_entry_pending_notices(tmp_path, signing):
    from test_ce_general_installer import environment, package
    from test_online_updates import Response, entry as entry_fixture
    from test_ce_update_continuity import make_offer

    for scenario in ('nav_in_prep', 'modal_in_prep', 'own_ui_in_prepare_skin', 'entry_fail_notice'):
        case_dir = tmp_path / scenario
        case_dir.mkdir()
        with pytest.MonkeyPatch.context() as mp:
            env = environment.__wrapped__(case_dir, signing)
            st = entry_fixture.__wrapped__(env, signing, mp)
            env.installer.apply(package(case_dir / 'base.zip', signing, 1, '1.0.0', channel='private-stable'))
            cand = package(case_dir / 'cand.zip', signing, 2, '2.0.0', channel='private-stable')
            cand_raw = cand.read_bytes()
            offer = make_offer(cand, 'ce2195')

            idle_val = [60]
            modal_val = [False]
            effects, notices, logs = [], [], []
            kodi = sys.modules['xbmc']
            kodi.Player = lambda: SimpleNamespace(isPlaying=lambda: False)
            kodi.getCondVisibility = lambda c: modal_val[0] if c == 'System.HasModalDialog' else False
            kodi.getGlobalIdleTime = lambda: idle_val[0]
            kodi.log = lambda line, *_a: logs.append(line)
            env.host.xbmc = kodi
            st.dialog.notification = lambda *a, **kw: notices.append(a)
            mp.setattr(sys.modules['xbmcvfs'], 'translatePath', lambda _p: str(env.work))
            mp.setattr(online, 'latest', lambda *_a, **_k: offer)
            mp.setattr(online, '_open', lambda _u: Response(cand_raw))

            real_deps = env.host.dependencies

            def deps_hook(stage):
                res = real_deps(stage)
                if scenario == 'nav_in_prep':
                    idle_val[0] = 0
                elif scenario == 'modal_in_prep':
                    modal_val[0] = True
                return res

            env.host.dependencies = deps_hook

            def prep_skin():
                effects.append('prepare_skin')
                if scenario == 'own_ui_in_prepare_skin':
                    idle_val[0] = 0
                    modal_val[0] = True

            env.host.prepare_install_skin = prep_skin
            orig_quiesce = env.host.quiesce
            env.host.quiesce = lambda: effects.append('quiesce') or orig_quiesce()

            if scenario == 'entry_fail_notice':
                live_entry = env.addons / 'script.bobbi.start'
                assert ui.sync_entry_from_bundle(case_dir / 'base.zip', env.addons, trust=signing[1]) is True
                real_rep = ui.os.replace
                mp.setattr(
                    ui.os,
                    'replace',
                    lambda s, d: (_ for _ in ()).throw(OSError('publish fail'))
                    if Path(d) == live_entry and Path(s).name.startswith('.bobbi-entry-stage-')
                    else real_rep(s, d),
                )

            ret = ui.main(auto=True)
            final_seq = env.installer._read()['sequence']
            if scenario in ('nav_in_prep', 'modal_in_prep'):
                assert ret is False and final_seq == 1 and effects == []
            elif scenario == 'own_ui_in_prepare_skin':
                assert ret is True and final_seq == 2 and 'prepare_skin' in effects
                assert notices and '已自动升级至 CE2195' in notices[-1][1]
            else:
                assert ret is True and final_seq == 2
                assert any('ENTRY_SYNC_FAILED' in ln for ln in logs)
                assert notices and '启动器待同步' in notices[-1][1] and '已自动升级至' not in notices[-1][1]
                assert ET.parse(env.addons / 'script.bobbi.start/addon.xml').getroot().get('version') == '1.0.0'

    # Manual online & offline paths bind applied['sequence'] and surface entry_pending in dialog.ok!
    manual_dir = tmp_path / 'manual_seq_and_dialog'
    manual_dir.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        env = environment.__wrapped__(manual_dir, signing)
        st = entry_fixture.__wrapped__(env, signing, mp)
        b1 = package(manual_dir / 'm1.zip', signing, 1, '1.0.0', channel='private-stable')
        b2 = package(manual_dir / 'm2.zip', signing, 2, '2.0.0', channel='private-stable')
        b3 = package(manual_dir / 'm3.zip', signing, 3, '3.0.0', channel='private-stable')
        env.installer.apply(b1)
        assert ui.sync_entry_from_bundle(b1, env.addons, trust=signing[1], work=env.work, expected_sequence=1) is True

        # Simulate race where journal already advanced to sequence=3 before manual online sync_entry_from_bundle acquires lock
        orig_apply = env.installer.apply

        def apply_then_advance_to_3(bundle):
            applied_manifest = orig_apply(bundle)
            orig_apply(b3)
            return applied_manifest

        mp.setattr(env.installer, 'apply', apply_then_advance_to_3)
        b2_raw = b2.read_bytes()
        mp.setattr(online, 'latest', lambda *_a, **_k: make_offer(b2, 'ce2055'))
        mp.setattr(online, '_open', lambda _u: Response(b2_raw))
        st.dialogs.clear()
        ui.main(online=True)
        # Stale candidate b2 (seq=2 vs journal seq=3) was skipped cleanly, AND dialog informed user launcher sync is pending!
        assert ET.parse(env.addons / 'script.bobbi.start/addon.xml').getroot().get('version') == '1.0.0'
        assert st.dialogs and '启动器入口尚未同步' in st.dialogs[-1][1]

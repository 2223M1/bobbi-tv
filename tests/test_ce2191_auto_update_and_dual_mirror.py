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

    # 7. Same-version addon.xml (2.0.0) with missing/corrupt entry payload file -> detected & repaired!
    entry_code = entry.env.addons / 'script.bobbi.start' / 'code.py'
    orig_code = entry_code.read_bytes()
    entry_code.write_bytes(b'# corrupted payload')
    assert ui.ensure_entry_synced_from_recovery(entry.env.work, entry.env.addons, trust=signing[1]) is True
    assert entry_code.read_bytes() == orig_code

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

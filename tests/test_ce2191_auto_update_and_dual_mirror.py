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
    notice.reset_auto_update_cooldowns()
    work = tmp_path / 'start'
    _write_journal(work, sequence=2026102190)

    dispatched, notified = [], []
    now = [1000.0]
    offer = {'tag': 'ce2191', 'sequence': 2026102191}

    # 1. Default enabled -> discovers 2026102191 & dispatches RunScript(script.bobbi.start,auto)
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
    assert 'RunScript(script.bobbi.start,auto)' in setup_ui.builtins


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

    # 3. Idle + auto-update enabled -> installs next_pkg (sequence=2) with zero modal dialogs!
    from test_ce_update_continuity import make_offer
    entry.playing = False
    next_pkg = package(entry.env.root / 'next.zip', signing, 2, '2.0.0', channel='private-stable')
    next_raw = next_pkg.read_bytes()
    next_offer = make_offer(next_pkg, 'ce2055')
    monkeypatch.setattr(online, 'latest', lambda *_a, **_kw: next_offer)
    monkeypatch.setattr(online, '_open', lambda _u: Response(next_raw))
    assert ui.main(auto=True) is True
    assert entry.env.installer._read()['sequence'] == 2
    assert entry.dialogs == [] and not entry.confirmations


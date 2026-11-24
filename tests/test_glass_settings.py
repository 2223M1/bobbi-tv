"""First-use consent, host ownership and the sealed stock launcher."""
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.platform/lib'))
from bobbi_platform import glass_settings as s


class Dialog:
    def __init__(self, yes):
        self.yes, self.questions = yes, []

    def yesno(self, *args):
        self.questions.append(args)
        return self.yes


@pytest.mark.parametrize('yes', [False, True])
@pytest.mark.parametrize('mode', ['live', 'stock', 'material'])
def test_only_confirming_an_enable_can_arm_stock(yes, mode):
    dialog, events = Dialog(yes), []
    class Host:
        def mode(self): return mode
        def enable(self): events.append('arm')
        def disable(self): events.append('disarm')
    s.toggle(dialog, Host(), lambda:False, events.append, lambda:True)
    assert len(dialog.questions) == 1
    assert events == ([] if not yes else ['arm', True] if mode == 'stock' else [True])
    assert ('可撤销' in dialog.questions[0][1]) == (mode == 'stock')
    s.toggle(dialog, Host(), lambda:True, events.append, lambda:True)
    assert len(dialog.questions) == 1 and events[-2:] == [False, 'disarm']


def test_profile_or_support_changing_during_prompt_cannot_enable():
    for current, modes in (([True,False], ['stock']), ([True,True], ['stock','material'])):
        host = type('Host', (), {'mode': lambda _:modes.pop(0)})()
        s.toggle(Dialog(True), host, lambda:False, pytest.fail, lambda:current.pop(0))


def test_failed_arm_never_changes_skin():
    class Host:
        def mode(self): return 'stock'
        def enable(self): raise OSError('full')
    with pytest.raises(OSError):
        s.toggle(Dialog(True), Host(), lambda:False, pytest.fail, lambda:True)


def test_owned_files_are_exclusive_revocable_and_match_shipped_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(s.HostOptics,'storage',tmp_path)
    monkeypatch.setattr(s,'coreelec',lambda:True)
    host = s.HostOptics(True)
    monkeypatch.setattr(host,'available',lambda:True)
    host.enable()
    assert host.drop.read_bytes() == s.UNIT
    assert hashlib.sha256(host.snapshot.read_bytes()).hexdigest() == s.GUARD_HASH
    host.enable()
    host.disable()
    assert not host.drop.exists() and not host.snapshot.exists()
    host.drop.write_text('administrator')
    with pytest.raises(ValueError):
        host.enable()
    host.disable()
    assert host.drop.read_text() == 'administrator'
    assert b'ExecStartPre=-' in s.UNIT and b'--stock-opt-in' in s.UNIT


@pytest.mark.parametrize('old,consent,eligible,changed', [(True, True, True, True), (False, True, True, False), (True, False, True, False), (True, True, False, False)])
@pytest.mark.parametrize('old_unit', tuple(s.OLD_UNITS.values()))
def test_upgrade_only_refreshes_previously_owned_opt_in(tmp_path, monkeypatch, old, consent, eligible, changed, old_unit):
    from bobbi_platform import paths
    monkeypatch.setattr(paths, 'profile_root', lambda: Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform'))
    monkeypatch.setattr(s, 'coreelec', lambda: True)
    monkeypatch.setattr(s.HostOptics, 'storage', tmp_path)
    monkeypatch.setattr(s.HostOptics, 'available', lambda self: eligible)
    monkeypatch.setattr(s.boot, 'opted_in', lambda _: consent)
    host = s.HostOptics(True)
    original = old_unit if old else b'local owner'
    host.drop.parent.mkdir(parents=True)
    host.drop.write_bytes(original)
    s.refresh_owned()
    assert host.drop.read_bytes() == (s.UNIT if changed else original)
    assert host.snapshot.exists() == changed


def test_guard_requires_explicit_persisted_preference(tmp_path):
    settings=tmp_path/'addon_data/skin.bobbi.cinema/settings.xml'
    settings.parent.mkdir(parents=True)
    assert not s.boot.opted_in(tmp_path)
    for xml, expected in [('',False), ('<settings/>',False),
        ('<settings><setting id="BobbiGlassPrerendered">false</setting></settings>',False),
        ('<settings><setting id="bobbiliquidglassenabled">false</setting></settings>',False),
        ('<settings><setting id="bobbiliquidglassenabled">true</setting></settings>',True)]:
        settings.write_text(xml)
        assert s.boot.opted_in(tmp_path) == expected


def test_positive_switch_is_the_only_skin_action_and_is_not_run_on_load():
    folder=ROOT/'addons/skin.bobbi.cinema/1080p'
    skin=ET.parse(folder/'SkinSettings.xml')
    row=next(c for c in skin.iter('include') if c.findtext("param[@name='id']")=='9106')
    assert row.findtext("param[@name='setting']")==s.SETTING and row.findtext("param[@name='glass']")=='true'
    control=ET.parse(folder/'Includes_Dialogs.xml').find("include[@name='SkinToggle']/definition/control")
    assert [(a.get('condition'),a.text) for a in control.findall('onclick')][:2] == [
        ('!$PARAM[glass]', 'Skin.ToggleSetting($PARAM[setting])'),
        ('$PARAM[glass]', 'RunScript(script.bobbi.setup,liquid_glass)')]
    for xml in [*folder.glob('*.xml'),*(ROOT/'addons/plugin.video.bobbi/resources/skins/Default/1080i').glob('*.xml')]:
        raw=xml.read_text(encoding='utf-8')
        assert 'BobbiGlassPrerendered' not in raw and 'Skin.SetBool(BobbiLiquidGlassEnabled)' not in raw

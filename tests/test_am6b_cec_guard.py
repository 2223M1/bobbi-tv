"""CEC guard must reject power/route risks before Kodi starts or a box reboots."""
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

spec = importlib.util.spec_from_file_location('cec_guard', Path(__file__).parents[1] / 'tools/am6b_cec_test_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.fixture
def box(tmp_path, monkeypatch):
    mask, boot, backup = (tmp_path / name for name in ('fun_cfg', 'config.ini', 'prior.json'))
    mask.write_text('0x7d')
    boot.write_text("cec_func_config='7d'\n")
    profile = tmp_path / 'home'
    xml = profile / guard.ADAPTER
    xml.parent.mkdir(parents=True)
    document = ET.Element('settings')
    for key, value in guard.OFF.items():
        ET.SubElement(document, 'setting', id=key, value=value)
    ET.ElementTree(document).write(xml)
    for name, path in [('REG', mask), ('BOOT_CONFIG', boot), ('BACKUP', backup), ('FAMILY', profile)]:
        monkeypatch.setattr(guard, name, path)
    monkeypatch.setattr(guard, 'device_mask', lambda: int(mask.read_text().strip(), 16))
    monkeypatch.setattr(guard, 'open_processes', lambda: 0)
    monkeypatch.setattr(guard.time, 'sleep', lambda seconds: None)
    return profile, mask, boot, backup


def test_guard_preserves_original_mask_and_family_settings_and_blocks_reboot(box):
    profile, mask, boot, backup = box
    original = (profile / guard.ADAPTER).read_bytes()
    assert guard.disable()['before'] == '0x7d'
    assert int(mask.read_text(), 16) == 0
    assert guard.disable()['before'] == '0x0'
    assert json.loads(backup.read_text())['mask'] == '0x7d'
    assert (profile / guard.ADAPTER).read_bytes() == original
    with pytest.raises(RuntimeError, match='do not reboot'):
        guard.verify(profile, before_box_reboot=True)
    assert boot.read_text() == "cec_func_config='7d'\n"
    boot.write_text("# cec_func_config='7d'\ncec_func_config='00' # test boot\n")
    assert guard.verify(profile, before_box_reboot=True)['configured_boot_mask'] == '0x0'


@pytest.mark.parametrize('risk', ['activate_source', 'standby_devices', 'enabled', 'open_adapter'])
def test_guard_refuses_to_change_an_unsafe_active_profile(box, monkeypatch, risk):
    profile, mask, _, backup = box
    if risk == 'open_adapter':
        monkeypatch.setattr(guard, 'open_processes', lambda: 1)
    else:
        xml = profile / guard.ADAPTER
        tree = ET.parse(xml)
        tree.find(f".//setting[@id='{risk}']").set('value', '1')
        tree.write(xml)
    with pytest.raises(RuntimeError, match='test blocked'):
        guard.disable()
    assert int(mask.read_text(), 16) == 0x7d and not backup.exists()


@pytest.mark.parametrize('setting', ['# cec_func_config=0', 'cec_func_config=0\ncec_func_config=7d', 'cec_func_config=$default'])
def test_ambiguous_boot_config_rejects_hardware_reboot(box, setting):
    profile, mask, boot, _ = box
    mask.write_text('0')
    boot.write_text(setting)
    with pytest.raises(RuntimeError, match='do not reboot'):
        guard.verify(profile, before_box_reboot=True)

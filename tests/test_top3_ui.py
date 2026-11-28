"""Settings destinations and shared row drift are contracts across two windows."""
import importlib.util
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / 'addons/skin.bobbi.cinema/1080p'


def test_settings_shortcuts_focus_existing_controls_without_toggling_and_name_full_dialog():
    settings = ET.parse(SKIN / 'Settings.xml')
    target = ET.parse(SKIN / 'SkinSettings.xml')
    rows = settings.findall(".//control[@id='9010']/content/item")
    for n in (9106, 9105, 9102):
        item, = [r for r in rows if r.findtext('onclick') == f'ActivateWindowAndFocus(SkinSettings,{n},0)']
        # An included SkinToggle takes its id/label as params. A regular control owns them directly.
        matches = [c.findtext('label') for c in target.findall(f".//control[@id='{n}']")]
        matches += [c.findtext("param[@name='label']") for c in target.findall(".//include[@content='SkinToggle']")
                    if c.findtext("param[@name='id']") == str(n)]
        assert matches == [item.findtext('label')]
    general = [r for r in rows if r.findtext('onclick') == 'Addon.OpenSettings(plugin.video.bobbi)']
    cats = {item.findtext('property'):item.findtext('label') for item in
            settings.findall(".//control[@id='9000']/content/item")}
    assert len(general) == 4
    for row in general:
        cat = next(k for k in cats if row.findtext('visible').endswith(',' + k + ')'))
        assert row.findtext('label') == cats[cat]
        assert row.findtext("property[@name='Bobbi.Value']") == '$LOCALIZE[32400]'


def test_stale_shared_rows_fail_check_and_rebuild_without_overwriting_window_navigation(tmp_path):
    spec = importlib.util.spec_from_file_location('source_rows', ROOT / 'tools/generate_source_rows.py')
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    gen.sync_source_rows(ROOT)
    dest = tmp_path / gen.WINDOWS
    dest.mkdir(parents=True)
    for name in ('source_select.xml', 'source_select_direct.xml'):
        shutil.copyfile(ROOT / gen.WINDOWS / name, dest / name)
    master, direct = dest / 'source_select.xml', dest / 'source_select_direct.xml'
    # A new badge in the authored layout must reach the direct window only inside its list row.
    master.write_bytes(master.read_bytes().replace(b'Property(seeders)', b'Property(new_badge)'))
    before, _, after = gen._parts(direct)
    with pytest.raises(ValueError, match='Source rows are stale'):
        gen.sync_source_rows(tmp_path)
    gen.sync_source_rows(tmp_path, check=False)
    gen.sync_source_rows(tmp_path)
    actual_before, _, actual_after = gen._parts(direct)
    assert (actual_before, actual_after) == (before, after)
    def list_layout(path):
        ctl = ET.parse(path).find(".//control[@id='1000']")
        return [ET.tostring(ctl.find(tag)) for tag in ('itemlayout', 'focusedlayout')]
    assert list_layout(direct) == list_layout(master)

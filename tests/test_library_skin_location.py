from pathlib import Path
import xml.etree.ElementTree as ET

SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'


def test_actual_source_tile_uses_location_after_kodi_clears_label2():
    home = ET.parse(SKIN / 'Includes_Home.xml').getroot()
    hint = home.find("variable[@name='LibraryTileHint']")
    values = hint.findall('value')
    assert values[0].attrib['condition'] == '$EXP[BobiIsManage]'
    assert values[1].text == '$VAR[BobiLibraryLocation]'
    assert 'ListItem.Property(Bobi.Library.Location)' in values[1].attrib['condition']
    assert 'ListItem.Label2' in values[1].attrib['condition']
    tile = home.find("include[@name='LibraryTile']")
    assert sum(n.text == '$VAR[LibraryTileHint]' for n in tile.iter('label')) == 2
    variables = ET.parse(SKIN / 'Variables.xml').getroot()
    location = variables.find("variable[@name='BobiLibraryLocation']")
    assert [v.text for v in location.findall('value')] == [
        '$INFO[ListItem.Property(Bobi.Library.Location)]', '$INFO[ListItem.Label2]']


def test_cast_role_remains_generic_not_library_specific():
    root = ET.parse(SKIN / 'Includes_Views.xml').getroot()
    labels = [n.text for n in root.find("include[@name='CastTile']").iter('label')]
    assert '$INFO[ListItem.Label2]' in labels
    assert '$VAR[BobiLibraryLocation]' not in labels

"""Directory export uses the real skin's active and inactive focus colors."""
from pathlib import Path
import xml.etree.ElementTree as ET

SKIN = Path(__file__).resolve().parents[1]/'addons/skin.bobbi.cinema'


def test_file_browser_focused_labels_keep_contrast_in_both_panels():
    root = ET.parse(SKIN/'1080p/FileBrowser.xml')
    for panel in ('450', '451'):
        labels = root.findall(".//control[@id='"+panel+"']/focusedlayout/control[@type='label']")
        assert labels
        for label in labels:
            assert label.findtext('textcolor') == '$VAR[BobiFileBrowserFocusText]'
            assert label.findtext('selectedcolor') == '$VAR[BobiFileBrowserFocusText]'
    variable = ET.parse(SKIN/'1080p/Variables.xml').find("variable[@name='BobiFileBrowserFocusText']")
    assert [(value.get('condition'), value.text) for value in variable] == [
        ('Control.HasFocus(450) | Control.HasFocus(451)', 'black'), (None, 'text')]

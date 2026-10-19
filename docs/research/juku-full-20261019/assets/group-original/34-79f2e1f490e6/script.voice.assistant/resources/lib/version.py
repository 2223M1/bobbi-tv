"""The addon manifest is the single source for UI and client version labels."""
from pathlib import Path
import xml.etree.ElementTree as ET

VERSION = ET.parse(Path(__file__).resolve().parents[2] / 'addon.xml').getroot().get('version')

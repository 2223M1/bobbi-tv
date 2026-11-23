"""Check real skin windows and transitive include references, not unused legacy stubs."""
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

SKIN = Path(__file__).resolve().parents[1] / 'addons/skin.bobbi.cinema/1080p'


def active_markup():
    documents = {p.name: ET.parse(p).getroot() for p in SKIN.glob('*.xml')}
    loaded, pending = set(), ['Includes.xml']
    definitions = defaultdict(list)
    while pending:
        name = pending.pop()
        if name in loaded:
            continue
        loaded.add(name)
        for child in documents[name].findall('include'):
            if child.get('file'):
                pending.append(child.get('file'))
            elif child.get('name'):
                definitions[child.get('name')].append((name, child))

    pending = [(name, None, root) for name, root in documents.items() if root.tag == 'window']
    seen = set()
    while pending:
        path, name, node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield path, name, node
        for item in node.iter('include'):
            ref = item.get('content') or (item.text or '').strip()
            pending.extend((file, ref, child) for file, child in definitions.get(ref, ()))


def test_all_reachable_effects_and_list_artwork_timings_share_motion_policy():
    missed = []
    for path, name, node in active_markup():
        for animation in node.iter('animation'):
            if any(part.get('time') not in (None, '0') for part in animation.iter()):
                if 'Skin.HasSetting(BobbiReduceMotion)' not in animation.get('condition', ''):
                    missed.append((path, name, 'animation'))
        for tag, owner in [('scrolltime', 'MotionListTravel'), ('fadetime', 'MotionArtBlend')]:
            if name != owner and any((part.text or '').strip() != '0' for part in node.iter(tag)):
                missed.append((path, name, tag))
    # Textbox auto-reading, image display duration and instant state offsets
    # are not decorative transition lengths; disabling them can hide content.
    assert not missed, missed

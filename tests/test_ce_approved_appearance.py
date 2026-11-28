"""The approved artwork is a release input, independent of Kodi's addon version."""
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from build_release import files
from approved_xbt import approved_digest, rekey, MIXED
import pytest


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def visual_rows(root, rows, addon=None):
    # Baselines computed from the signed CE2174 user ZIP (4349d5c8…).
    # Keep every image, font, script, XML value and layout; XML comments do
    # not render. New license notices are still pinned by the raw package hash.
    result = dict(rows)
    for name in rows:
        if name in {'licenses/fontawesome.txt', 'licenses/roboto.txt', 'licenses/misans-apache.txt', 'licenses/noto-ofl.txt'}:
            del result[name]
        elif name.endswith('.xml'):
            raw = addon if name == 'addon.xml' and addon is not None else (root/name).read_bytes()
            result[name] = hashlib.sha256(ET.canonicalize(raw, with_comments=False).encode()).hexdigest()
    return result

def test_stable_uses_approved_opt_in_skin_and_plugin_dialogs():
    skin = ROOT/'addons/skin.bobbi.cinema'
    rows = files(skin)
    # Ignore only the root addon's numeric version; dependency versions and
    # every visual byte must still match the approved archive.
    data, count = re.subn(rb'(<addon id="skin\.bobbi\.cinema" version=")[0-9.]+(")',
                          rb'\g<1>0.1.34\g<2>', (skin/'addon.xml').read_bytes(), count=1)
    assert count == 1
    rows['addon.xml'] = hashlib.sha256(data).hexdigest()
    # Both freeze checks still cover the entire original archive, including
    # frame offsets, pixels and padding. Only the two new lookup keys differ.
    rows['media/Textures.xbt'] = approved_digest((skin/'media/Textures.xbt').read_bytes())
    # Reviewed settings destinations, right-pane focus, source-row generator output and dependency floor.
    # Both complete freezes still cover all other windows and textures. See test_top3_ui.py.
    assert fingerprint(visual_rows(skin, rows, data)) == '9a4c7bdc047d8bf1d99a6d9ea32d3602ce6c146614811b66cd4db7fe8166d4b8'
    assert fingerprint(rows) == 'd7c99a0e687ea64e8a4787561d0e8a4ed635923f87f2879743a85df5ed0a12c4'
    mirror = ROOT/'addons/plugin.video.bobbi/resources/skins/Default'
    mirrored = files(mirror)
    visual = visual_rows(mirror, mirrored)
    # CE2201: reviewed both picker windows with recommendation/edition labels
    # and separate diagnostics. Pin the exact shipped XML, including those labels;
    # the complete mirror still covers every other pixel, control and texture.
    assert mirrored['1080i/source_select.xml'] == 'f54142d3544f92b1c22a01a0633785d0d7500edc364c6b7f8f8c6e0c445baf8e'
    assert mirrored['1080i/source_select_direct.xml'] == 'aa6fdb8ca77c4e9d7f2bc1d1c2bedafac7ab4ac087f8e0a39a61fc4260ad97f3'
    assert fingerprint(visual) == 'f5dc3c648e02aadc8ebd5b3bb9eaad18c26be45ba6934df4710ad586e6a1670a'
    assert fingerprint(mirrored) == '522f304bfe46540a9030dfb9a1171a3185289137f0c5212b70c05363e238afb2'


def test_new_texture_keys_cannot_hide_a_pixel_change_or_a_mixed_case_key():
    raw = (ROOT/'addons/skin.bobbi.cinema/media/Textures.xbt').read_bytes()
    with pytest.raises(ValueError, match='differs beyond'):
        approved_digest(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(ValueError, match='Missing approved rename'):
        approved_digest(rekey(raw, {v: k for k, v in MIXED.items()}))

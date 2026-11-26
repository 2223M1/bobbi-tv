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
    # CE2188: MyFavourites binding, Settings IA consolidation, VS10/OSD capability expressions, and Liquid Glass state sync.
    assert fingerprint(visual_rows(skin, rows, data)) == 'c8f58fd898dab9cc022984bb5a9239a37a26fc7e3981cf44a330d5fa5c83ec96'
    assert fingerprint(rows) == 'b329cc8dd872c3e56f085a9fea02fe8980908f89382a897a58d541d46e75b189'
    mirror = ROOT/'addons/plugin.video.bobbi/resources/skins/Default'
    mirrored = files(mirror)
    assert fingerprint(visual_rows(mirror, mirrored)) == '4a20833ad30cf0f1b304389a0bc34d0b907c213491211200602a4cfe4332149d'
    assert fingerprint(mirrored) == 'a80106d547c45b179c546408f70e53a1892d5351e769ca0a9d835254304aa576'


def test_new_texture_keys_cannot_hide_a_pixel_change_or_a_mixed_case_key():
    raw = (ROOT/'addons/skin.bobbi.cinema/media/Textures.xbt').read_bytes()
    with pytest.raises(ValueError, match='differs beyond'):
        approved_digest(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(ValueError, match='Missing approved rename'):
        approved_digest(rekey(raw, {v: k for k, v in MIXED.items()}))

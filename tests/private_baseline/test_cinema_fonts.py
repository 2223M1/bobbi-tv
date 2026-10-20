import hashlib
import struct

import pytest

from lib.cinema.fonts import ass_font_requirements, cache_eviction_candidates, inspect_font, select_fonts


def font(names=("Test Font", "测试字体"), weight=400, italic=False, offset=0):
    strings = b""
    records = []
    for name in names:
        text = name.encode("utf-16-be")
        records.append(struct.pack(">HHHHHH", 3, 1, 0x409, 1, len(text), len(strings)))
        strings += text
    name = struct.pack(">HHH", 0, len(records), 6 + 12 * len(records)) + b"".join(records) + strings
    os2 = bytearray(64)
    struct.pack_into(">H", os2, 4, weight)
    struct.pack_into(">H", os2, 62, int(italic))
    header = b"\0\1\0\0" + struct.pack(">HHHH", 2, 0, 0, 0)
    tables = struct.pack(">4sIII", b"name", 0, offset + 44, len(name))
    tables += struct.pack(">4sIII", b"OS/2", 0, offset + 44 + len(name), len(os2))
    return header + tables + name + bytes(os2)


ASS = r"""[Script Info]
ScriptType: v4.00+
[V4+ Styles]
Format: Name,Fontname,Fontsize,Bold,Italic
Style: Default,测试字体,30,-1,0
[Events]
Format: Layer,Start,End,Style,Text
Dialogue: 0,0:00:00.00,0:00:10.00,Default,{\fnOther Font}中文字幕{\b1\i1\fnItalic Face}测试
""".encode("utf-8")


def test_actual_names_weight_and_italic_not_filename():
    result = inspect_font(font(weight=700, italic=True))
    face = result["faces"][0]
    assert face["families"] == ["Test Font", "测试字体"]
    assert face["weight"] == 700 and face["italic"] is True
    assert result["bytes"] == len(font(weight=700, italic=True))


def test_ttc_reads_all_face_internal_names():
    first = font(("Regular Face",), offset=20)
    second_offset = 20 + len(first)
    second = font(("Bold Face",), weight=700, offset=second_offset)
    collection = b"ttcf" + struct.pack(">IIII", 0x10000, 2, 20, second_offset) + first + second
    result = inspect_font(collection)
    assert result["extension"] == ".ttc"
    assert [face["families"] for face in result["faces"]] == [["Regular Face"], ["Bold Face"]]


@pytest.mark.parametrize("data", [b"", b"not font" * 10, font()[:20], b"ttcf" + struct.pack(">II", 0x10000, 1000)])
def test_corrupt_and_unbounded_fonts_rejected(data):
    with pytest.raises(ValueError):
        inspect_font(data)


def test_ass_requires_style_and_inline_families_without_rewriting():
    result = ass_font_requirements(ASS)
    assert result["fonts"] == [{"family": "测试字体", "weight": 700, "italic": False},
                               {"family": "Other Font", "weight": 700, "italic": False},
                               {"family": "Italic Face", "weight": 700, "italic": True}]
    assert not result["style_override"]
    assert ass_font_requirements(ASS.decode().encode("utf-16"))["fonts"] == result["fonts"]


def test_inline_font_inherits_style_and_later_weight_changes():
    raw = ASS.replace(br'{\fnOther Font}', br'{\fnOther Font\b600\i1}')
    required = ass_font_requirements(raw)['fonts']
    assert {'family': 'Other Font', 'weight': 600, 'italic': True} in required
    assert {'family': 'Other Font', 'weight': 400, 'italic': False} not in required


def test_reset_and_empty_font_restore_active_style_without_ui_override():
    raw = ASS.replace(b'[Events]', b'Style: Alternate,Second Family,30,0,-1\n[Events]')
    raw = raw.replace(br'{\fnOther Font}', br'{\rAlternate\fnOther Font\b600}one{\fn}two{\r}')
    required = ass_font_requirements(raw)['fonts']
    assert {'family': 'Other Font', 'weight': 600, 'italic': True} in required
    assert {'family': 'Second Family', 'weight': 600, 'italic': True} in required
    assert {'family': '测试字体', 'weight': 700, 'italic': False} in required


def test_unknown_style_and_animated_font_do_not_claim_exact_readiness():
    for raw in (ASS.replace(b',Default,{', b',Missing,{'),
                ASS.replace(br'{\fnOther Font}', br'{\t(0,100,\fnOther Font)}')):
        with pytest.raises(ValueError): ass_font_requirements(raw)


@pytest.mark.parametrize('style', [b'*Default', b'***Default', b'default', b'*dEfAuLt'])
def test_event_default_alias_matches_libass_without_rewriting(style):
    from bobbi_core.subtitle_cues import parse
    raw = ASS.replace(b',Default,{', b',' + style + b',{')
    result = ass_font_requirements(raw)
    assert result['fonts'] == ass_font_requirements(ASS)['fonts']
    assert result['subtitle_sha256'] == hashlib.sha256(raw).hexdigest()
    assert not result['style_override']
    assert parse(raw, '.ass', 60) == parse(ASS, '.ass', 60)
    assert b',' + style + b',{' in raw


def test_event_non_default_style_keeps_case_and_strips_only_stars():
    raw = ASS.replace(b'Style: Default,', b'Style: Alternate,')
    raw = raw.replace(b',Default,{', b',**Alternate,{')
    assert ass_font_requirements(raw)['fonts'] == ass_font_requirements(ASS)['fonts']
    for style in (b'alternate', b'*alternate', b'*Missing', b''):
        with pytest.raises(ValueError, match='unknown style'):
            ass_font_requirements(raw.replace(b',**Alternate,{', b',' + style + b',{'))


@pytest.mark.parametrize('reset', [br'\r*Default', br'\rdefault', br'\rMissing'])
def test_reset_style_lookup_stays_strict(reset):
    raw = ASS.replace(b',Default,{', b',*Default,{')
    raw = raw.replace(br'{\fnOther Font}', b'{' + reset + b'}')
    with pytest.raises(ValueError, match='reset style'):
        ass_font_requirements(raw)


def test_empty_reset_uses_canonical_event_default_style():
    raw = ASS.replace(b',Default,{', b',*Default,{')
    raw = raw.replace(br'{\fnOther Font}', br'{\fnOther Font}one{\r}two')
    assert ass_font_requirements(raw)['fonts'] == ass_font_requirements(ASS)['fonts']


def test_ordinary_transform_before_font_does_not_hide_font_requirement():
    raw = ASS.replace(br'{\fnOther Font}', br'{\t(0,100,\fscx120)\fnOther Font}')
    assert {'family': 'Other Font', 'weight': 700, 'italic': False} in ass_font_requirements(raw)['fonts']


def test_font_selection_prefers_attachment_then_same_release_then_exact_local():
    required = {"subtitle_sha256": "a" * 64, "fonts": [{"family": "测试字体", "weight": 700, "italic": False}]}
    local = dict(inspect_font(font(weight=700)), origin="local_exact")
    release = dict(inspect_font(font(weight=600)), origin="same_release_pack")
    attached = dict(inspect_font(font(weight=400)), origin="media_attachment")
    result = select_fonts(required, [local, release, attached])
    assert result["selected"][0]["origin"] == "media_attachment"
    assert result["selected"][0]["synthetic_style_may_be_needed"]
    assert select_fonts(required, [local, release])["selected"][0]["origin"] == "same_release_pack"
    assert select_fonts(required, [local])["status"] == "EXACT_FONTS_READY_NOT_VISUAL_PROOF"


def test_missing_family_is_not_replaced_by_harmony_ui_font():
    required = {"subtitle_sha256": "a" * 64, "fonts": [{"family": "Missing Font", "weight": 400, "italic": False}]}
    result = select_fonts(required, [dict(inspect_font(font(("HarmonyOS Sans SC",))), origin="local_exact")])
    assert result["status"] == "MISSING_FONTS"
    assert not result["selected"]


@pytest.mark.parametrize('change', [dict(weight=700), dict(weight=400, italic=True)])
def test_synthetic_weight_or_italic_is_not_reported_as_exact(change):
    required = dict(subtitle_sha256='a' * 64, fonts=[dict(family='Test Font', italic=False, **change)]) if 'italic' not in change else dict(subtitle_sha256='a' * 64, fonts=[dict(family='Test Font', **change)])
    result = select_fonts(required, [dict(inspect_font(font()), origin='media_attachment')])
    assert result['selected'][0]['synthetic_style_may_be_needed']
    assert result['status'] == 'SYNTHETIC_STYLE_REQUIRED_NOT_VISUAL_PROOF'


def test_cache_only_evicts_managed_unpinned_font_objects():
    entries = [{"sha256": str(index), "bytes": 100, "last_used": index, "managed": index != 2} for index in range(4)]
    result = cache_eviction_candidates(entries, {"0", "3"}, extra_bytes=100, limit=200)
    assert result["hashes"] == ["1"]
    assert result["soft_limit_exceeded_by_protected_items"]


def test_corrupt_name_offset_cannot_read_another_table():
    data = bytearray(font())
    struct.pack_into(">H", data, 44 + 6 + 10, 65530)
    with pytest.raises(ValueError):
        inspect_font(bytes(data))

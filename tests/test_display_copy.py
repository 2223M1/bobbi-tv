"""Branding projections must not change transport or configuration contracts."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def test_owned_component_display_metadata_is_project_facing():
    for name in ('plugin.video.bobbi', 'skin.bobbi.cinema'):
        addon = ET.parse(ROOT / 'addons' / name / 'addon.xml').getroot()
        assert addon.get('id') == name
        assert addon.get('provider-name') == 'bobbi TV'
        meta = addon.find("extension[@point='xbmc.addon.metadata']")
        for node in meta:
            if node.tag in {'summary', 'description', 'news'}:
                assert not re.search(r'Jacktook|Sam-Max|Minsk|明斯克|Confluence', node.text or '', re.I)


def test_retired_catalog_has_no_switch_or_bundled_endpoint():
    settings = ET.parse(ROOT / 'addons/plugin.video.bobbi/resources/settings.xml')
    catalog = settings.find(".//setting[@id='juku_enabled']")
    assert catalog is None
    assert settings.find(".//setting[@id='auto_start_jacktook']") is not None
    assert settings.find(".//setting[@id='donate']") is None
    api = ast.parse((ROOT / 'addons/script.module.bobbi.core/lib/bobbi_core/juku_api.py').read_text(encoding='utf-8'))
    base = next(node.value for node in api.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'BASE' for target in node.targets))
    assert ast.literal_eval(base) == ''


def test_no_legacy_support_popup_or_recipient_route_is_rebranded():
    nav = ast.parse((ROOT / 'addons/plugin.video.bobbi/lib/navigation.py').read_text(encoding='utf-8'))
    functions = {node.name for node in nav.body if isinstance(node, ast.FunctionDef)}
    assert not {'donate', 'maybe_show_donation_prompt'} & functions
    router = ast.parse((ROOT / 'addons/plugin.video.bobbi/lib/router.py').read_text(encoding='utf-8'))
    assert 'donate' not in {node.value for node in ast.walk(router) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def test_legacy_skin_variants_are_mapped_without_brand_specific_rules():
    spec = importlib.util.spec_from_file_location('display_skin_sanitizer', ROOT / 'tools/sanitize_skin.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.remap('skin.confluence.legacy') == 'skin.bobbi.cinema'
    assert module.remap('Player.BobiNextReady') == 'Player.BobiNextReady'


def test_repository_display_index_keeps_valid_checksums():
    raw = (ROOT / 'repository/addons.xml').read_bytes()
    assert (ROOT / 'repository/addons.xml.md5').read_text() == hashlib.md5(raw).hexdigest()
    assert (ROOT / 'repository/addons.xml.sha256').read_text() == hashlib.sha256(raw).hexdigest()
    ET.fromstring(raw)

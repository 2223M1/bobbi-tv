"""R3-NAV-POWER-01, S01..S06, and DS01..DS10 contract tests for Spaces, Control Center, Power, VS10, and Display Fit."""
from __future__ import annotations

import importlib.util
from itertools import product
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / 'addons/skin.bobbi.cinema'
for rel in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib'):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

SPEC_MOD = importlib.util.spec_from_file_location('home_rails_gen_r3', ROOT / 'tools/generate_home_rails.py')
generator = importlib.util.module_from_spec(SPEC_MOD)
SPEC_MOD.loader.exec_module(generator)


def _parse_po(path: Path) -> dict[int, str]:
    entries: dict[int, str] = {}
    raw = path.read_text(encoding='utf-8')
    for m in re.finditer(
        r'msgctxt\s+"#(\d+)"\s+msgid\s+"((?:[^"\\]|\\.)*)"\s+msgstr\s+"((?:[^"\\]|\\.)*)"',
        raw,
    ):
        cid = int(m.group(1))
        msgid = bytes(m.group(2), 'utf-8').decode('unicode_escape')
        msgstr = bytes(m.group(3), 'utf-8').decode('unicode_escape')
        entries[cid] = msgstr if msgstr else msgid
    return entries


def _eval_bool(expr: str, expressions: dict[str, str], bools: set[str], strings: dict[str, str], conds: dict[str, bool] | None = None) -> bool:
    s = expr.strip()

    def split_top(text: str, sep: str) -> list[str]:
        parts, depth, cur = [], 0, []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in '([':
                depth += 1
            elif ch in ')]':
                depth -= 1
            if depth == 0 and text.startswith(sep, i):
                parts.append(''.join(cur).strip())
                cur = []
                i += len(sep)
                continue
            cur.append(ch)
            i += 1
        parts.append(''.join(cur).strip())
        return parts

    or_parts = split_top(s, ' | ')
    if len(or_parts) > 1:
        return any(_eval_bool(p, expressions, bools, strings, conds) for p in or_parts)
    and_parts = split_top(s, ' + ')
    if len(and_parts) > 1:
        return all(_eval_bool(p, expressions, bools, strings, conds) for p in and_parts)
    if s.startswith('!'):
        return not _eval_bool(s[1:], expressions, bools, strings, conds)
    if s.startswith('[') and s.endswith(']'):
        return _eval_bool(s[1:-1], expressions, bools, strings, conds)
    if s == 'true':
        return True
    if s == 'false':
        return False
    m = re.fullmatch(r'\$EXP\[(\w+)\]', s)
    if m:
        return _eval_bool(expressions[m.group(1)], expressions, bools, strings, conds)
    m = re.fullmatch(r'Skin\.HasSetting\((\w+)\)', s)
    if m:
        return m.group(1) in bools
    m = re.fullmatch(r'String\.IsEqual\(Skin\.String\((\w+)\),([\w_]+)\)', s)
    if m:
        return strings.get(m.group(1), '') == m.group(2)
    if conds is not None and s in conds:
        return bool(conds[s])
    raise AssertionError(f'Unhandled Kodi boolean atom: {s}')


def test_skin_bilingual_po_has_zero_orphans_and_complete_english_coverage():
    en_po = _parse_po(SKIN / 'language/resource.language.en_gb/strings.po')
    zh_po = _parse_po(SKIN / 'language/resource.language.zh_cn/strings.po')
    assert set(en_po) == set(zh_po)
    assert 31967 in en_po and 32399 in en_po
    assert en_po[32399] == 'en' and zh_po[32399] == 'zh'
    # Every active $LOCALIZE[31xxx/32xxx] reference in 1080p/*.xml must exist in both POs
    missing = set()
    for xml_path in (SKIN / '1080p').glob('*.xml'):
        text = xml_path.read_text(encoding='utf-8')
        for m in re.finditer(r'\$LOCALIZE\[(3[12]\d{3})\]', text):
            cid = int(m.group(1))
            if cid not in en_po or cid not in zh_po:
                missing.add((xml_path.name, cid))
    assert not missing
    # English PO entries for 32001..32399 must not leak CJK characters
    cjk_leaks = [
        (cid, val) for cid, val in en_po.items()
        if 32001 <= cid <= 32399 and re.search(r'[\u4e00-\u9fff]', val)
    ]
    assert not cjk_leaks


def test_static_space_slot_algebra_produces_zero_duplicates_and_zero_dropped_spaces():
    _, _, nav, _ = generator.full_outputs(ROOT)
    nav_tree = ET.fromstring(nav)
    expressions = {e.get('name'): (e.text or '') for e in nav_tree.findall('expression')}
    items = nav_tree.find("include[@name='HomeSpaceItems']/content").findall('item')

    def render_visible_spaces(bools: set[str], strings: dict[str, str]) -> list[str]:
        out = []
        for item in items:
            vis = item.findtext('visible')
            if vis is None or _eval_bool(vis, expressions, bools, strings):
                out.append(item.findtext("property[@name='space_key']"))
        return out

    # 1. Default state: 7 visible spaces in exact default order
    assert render_visible_spaces(set(), {}) == [
        'home', 'tv', 'movie', 'anime', 'mine', 'search', 'settings'
    ]

    # 2. All optional spaces hidden: only fixed 'home' remains
    hide_all = {f'BobbiHideSpace_{k}' for k in ('tv', 'movie', 'anime', 'mine', 'search', 'settings')}
    assert render_visible_spaces(hide_all, {}) == ['home']

    # 3. All 13 spaces enabled + custom reversed slot order -> exact 13 unique spaces, 'home' first
    show_all = {
        f'BobbiShowSpace_{k}'
        for k in ('continue_watching', 'personal_catalog', 'saved_views', 'sources', 'media_servers', 'favourites')
    }
    opt_keys = [
        'settings', 'search', 'favourites', 'media_servers', 'sources', 'saved_views',
        'personal_catalog', 'continue_watching', 'mine', 'anime', 'movie', 'tv',
    ]
    rev_slots = {f'BobbiSpaceSlot{i}': k for i, k in enumerate(opt_keys, start=1)}
    assert render_visible_spaces(show_all, rev_slots) == ['home'] + opt_keys

    # 4. Corrupted / duplicate / unknown slot strings NEVER duplicate or drop any visible space!
    corrupt_slots = {
        'BobbiSpaceSlot1': 'mine',
        'BobbiSpaceSlot2': 'mine',  # duplicate!
        'BobbiSpaceSlot3': 'nonexistent_space',  # unknown -> falls back to slot 3 default ('anime')
        'BobbiSpaceSlot4': 'tv',
    }
    rendered = render_visible_spaces(show_all, corrupt_slots)
    assert rendered[0] == 'home'
    assert len(rendered) == 13
    assert len(set(rendered)) == 13


def test_home_short_back_and_fixed_tools_button_contracts():
    includes = ET.parse(SKIN / '1080p/Includes.xml').getroot()
    for form in ('SideNav', 'TopNav'):
        node = includes.find(f"include[@name='{form}']")
        nav_list = node.find(".//control[@id='9701']")
        tools = node.find(".//control[@id='9730']")
        assert tools is not None and tools.findtext('onclick') == 'ActivateWindow(ShutdownMenu)'
        # Fuse3 short-Back on Home main nav only when Home is active and ShutdownMenu is not already visible
        expected_cond = '$PARAM[home_nav] + Window.IsActive(home) + !Window.IsVisible(shutdownmenu)'
        for ctrl in (nav_list, tools):
            backs = [(b.get('condition'), b.text) for b in ctrl.findall('onback')]
            assert (expected_cond, 'ActivateWindow(ShutdownMenu)') in backs

    # VideoOSD and custom_OptionsDialog (1114) yield visibility when ShutdownMenu opens, and 1114 offers Tools & Power
    osd_vis = ET.parse(SKIN / '1080p/VideoOSD.xml').getroot().findtext(".//control[@type='group']/visible")
    assert 'Window.IsVisible(shutdownmenu)' in osd_vis and osd_vis.startswith('![')
    opt_root = ET.parse(SKIN / '1080p/custom_OptionsDialog.xml').getroot()
    assert '!Window.IsVisible(shutdownmenu)' in opt_root.findtext(".//control[@type='group']/visible")
    assert any(item.findtext('onclick') == 'ActivateWindow(ShutdownMenu)' for item in opt_root.findall('.//content/item'))

    # custom_1116_VS10 narrows Dialog.Close(all) -> Dialog.Close(1116) and has a fallback item when VS10 is unavailable
    vs10_raw = (SKIN / '1080p/custom_1116_VS10.xml').read_text(encoding='utf-8')
    assert 'Dialog.Close(all)' not in vs10_raw
    assert 'Dialog.Close(1116)' in vs10_raw
    vs10_items = ET.fromstring(vs10_raw).findall('.//content/item')
    expected_vs10_fallback = 'String.IsEmpty(Player.Process(video.source.hdr.type)) | String.IsEqual(Player.Process(video.source.hdr.type.raw),2)'
    assert any(item.findtext('visible') == expected_vs10_fallback and item.findtext('onclick') == 'Dialog.Close(1116)'
               for item in vs10_items)


@pytest.mark.parametrize('can_power,can_reboot,show_exit', list(product([False, True], repeat=3)))
def test_control_center_focus_graph_is_closed_across_all_8_capability_combinations(can_power, can_reboot, show_exit):
    cc = ET.parse(SKIN / '1080p/DialogButtonMenu.xml').getroot()
    conds = {
        'System.CanPowerDown': can_power,
        'System.CanReboot': can_reboot,
        'System.ShowExitButton': show_exit,
    }
    visible_buttons = {}
    for group in cc.find(".//control[@id='9000']").findall("control[@type='group']"):
        btn = group.find("control[@type='button']")
        if btn is None:
            continue
        g_vis = group.findtext('visible')
        if g_vis is None or _eval_bool(g_vis, {}, set(), {}, conds):
            visible_buttons[btn.get('id')] = btn

    assert '9012' in visible_buttons  # Default safe return button is ALWAYS visible
    assert {'9011', '9014', '9015', '9021', '9022', '9023', '9024'} <= set(visible_buttons)

    # Every directional move from any visible button must land on 'noop' or another visible button!
    for bid, btn in visible_buttons.items():
        for direction in ('onup', 'ondown', 'onleft', 'onright'):
            matched_target = None
            for edge in btn.findall(direction):
                ec = edge.get('condition')
                if ec is None or _eval_bool(ec, {}, set(), {}, conds):
                    matched_target = edge.text
                    break
            assert matched_target is not None, (bid, direction, conds)
            assert matched_target == 'noop' or matched_target in visible_buttons, (
                f'Dead focus edge {bid}.{direction} -> {matched_target} under {conds}'
            )


def test_power_menu_capability_gate_cancel_safety_and_single_builtin_dispatch():
    from bobbi_platform import power_menu

    # 1. Unsupported capability -> 0 power builtins, clear dialog.ok
    ok_calls, yesno_calls, builtins = [], [], []
    dialog = SimpleNamespace(
        ok=lambda t, m: ok_calls.append((t, m)),
        yesno=lambda t, m: (yesno_calls.append((t, m)) or True),
    )
    res = power_menu.execute_power_action(
        'powerdown',
        dialog=dialog,
        get_cond=lambda _c: False,
        is_playing=lambda: True,
        execute=builtins.append,
    )
    assert res == 'UNSUPPORTED'
    assert len(ok_calls) == 1 and yesno_calls == [] and builtins == []

    # 2. Active playback + user cancels confirmation -> 0 builtins, NEVER calls PlayerControl(Stop)!
    ok_calls.clear()
    dialog_cancel = SimpleNamespace(
        ok=lambda t, m: ok_calls.append((t, m)),
        yesno=lambda t, m: (yesno_calls.append((t, m)) or False),
    )
    res_cancel = power_menu.execute_power_action(
        'reboot',
        dialog=dialog_cancel,
        get_cond=lambda c: c in ('System.CanReboot', 'Window.IsVisible(shutdownmenu)'),
        is_playing=lambda: True,
        execute=builtins.append,
        english=True,
    )
    assert res_cancel == 'CANCELLED'
    assert 'Playback is currently active' in yesno_calls[-1][1]
    assert builtins == []

    # 3. Confirmed powerdown, reboot, quit -> exact mapped native builtin
    for action, cap, expected_cmd in [
        ('powerdown', 'System.CanPowerDown', 'Powerdown()'),
        ('reboot', 'System.CanReboot', 'Reset()'),
        ('quit', 'System.ShowExitButton', 'Quit()'),
    ]:
        builtins.clear()
        res_ok = power_menu.execute_power_action(
            action,
            dialog=SimpleNamespace(ok=lambda *_a: None, yesno=lambda *_a: True),
            get_cond=lambda c, cap=cap: c in (cap, 'Window.IsVisible(shutdownmenu)'),
            is_playing=lambda: False,
            execute=builtins.append,
        )
        assert res_ok == 'EXECUTED'
        assert builtins == ['Dialog.Close(shutdownmenu)', expected_cmd]


def test_display_adaptation_is_strictly_read_only_and_deep_links_native_windows(tmp_path):
    from bobbi_platform import power_menu

    (tmp_path / 'amhdmitx/amhdmitx0').mkdir(parents=True)
    (tmp_path / 'amhdmitx/amhdmitx0/disp_mode').write_text('1080p60hz\n', encoding='utf-8')
    (tmp_path / 'graphics/fb0').mkdir(parents=True)
    (tmp_path / 'graphics/fb0/window_axis').write_text('0 0 1919 1079\n', encoding='utf-8')

    rpc_calls = []

    def fake_rpc(method, params):
        rpc_calls.append((method, params))
        assert method == 'Settings.GetSettingValue'  # Never SetSettingValue!
        if params['setting'] == 'lookandfeel.skinzoom':
            return {'value': 0}
        return {'value': 'DESKTOP'}

    summary = power_menu.collect_display_summary(
        get_info=lambda _k: '1920x1080 @ 60.00',
        rpc_call=fake_rpc,
        sysfs_root=tmp_path,
    )
    assert summary == {
        'gui_resolution': '1920x1080 @ 60.00',
        'hdmi_mode': '1080p60hz',
        'fb0_window_axis': '0 0 1919 1079',
        'skin_zoom': '0%',
        'screen_mode': 'DESKTOP',
    }

    # Inspect status (0) -> overscan guide (1) -> cancel (-1) => CANCELLED, zero execute calls
    ok_msgs, executed = [], []
    picks = iter([0, 1, -1])
    out = power_menu.show_display_adaptation(
        SimpleNamespace(select=lambda _h, _r: next(picks), ok=lambda t, m: ok_msgs.append((t, m))),
        get_info=lambda _k: 'Chinese (Simple)',
        rpc_call=fake_rpc,
        execute=executed.append,
        is_current=lambda: True,
    )
    assert out == 'CANCELLED' and executed == []
    assert any('Just Scan' in m for _, m in ok_msgs)

    # Choosing ScreenCalibration (4) => NAVIGATED + ActivateWindow(ScreenCalibration)
    out_nav = power_menu.show_display_adaptation(
        SimpleNamespace(select=lambda _h, _r: 4, ok=lambda *_a: None),
        get_info=lambda _k: 'English',
        rpc_call=fake_rpc,
        execute=executed.append,
        is_current=lambda: True,
    )
    assert out_nav == 'NAVIGATED'
    assert executed == ['ActivateWindow(ScreenCalibration)']

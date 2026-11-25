"""Stage 4A regression suite: Home Emby rails, slot visibility/order, OSD next capsule, and phone job capsule."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
for rel in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib'):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

SPEC_MOD = importlib.util.spec_from_file_location('home_rails_gen_s4', ROOT / 'tools/generate_home_rails.py')
generator = importlib.util.module_from_spec(SPEC_MOD)
SPEC_MOD.loader.exec_module(generator)


def _eval_kodi_bool(expr: str, expressions: dict[str, str], state: dict) -> bool:
    """Deterministic evaluator for the boolean expression subset emitted by generate_home_rails.py."""
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
        return any(_eval_kodi_bool(part, expressions, state) for part in or_parts)

    and_parts = split_top(s, ' + ')
    if len(and_parts) > 1:
        return all(_eval_kodi_bool(part, expressions, state) for part in and_parts)

    if s.startswith('!'):
        return not _eval_kodi_bool(s[1:], expressions, state)
    if s.startswith('[') and s.endswith(']'):
        return _eval_kodi_bool(s[1:-1], expressions, state)
    if s == 'true':
        return True
    if s == 'false':
        return False

    m = re.fullmatch(r'\$EXP\[(\w+)\]', s)
    if m:
        return _eval_kodi_bool(expressions[m.group(1)], expressions, state)

    m = re.fullmatch(r'Skin\.HasSetting\((\w+)\)', s)
    if m:
        return bool(state.get('bools', {}).get(m.group(1), False))

    m = re.fullmatch(r'String\.IsEqual\(Skin\.String\((\w+)\),([\w_]+)\)', s)
    if m:
        return state.get('strings', {}).get(m.group(1), '') == m.group(2)

    m = re.fullmatch(r'String\.IsEqual\(Window\(Home\)\.Property\(BobbiRail\),(\d+)\)', s)
    if m:
        return str(state.get('remembered', '')) == m.group(1)

    m = re.fullmatch(r'String\.IsEqual\(Control\.GetLabel\(9791\),(\d+)\)', s)
    if m:
        return str(state.get('current_9791', '')) == m.group(1)

    m = re.fullmatch(r'Integer\.IsGreater\(Container\((\d+)\)\.NumItems,0\)', s)
    if m:
        return int(state.get('counts', {}).get(int(m.group(1)), 0)) > 0

    m = re.fullmatch(r'Container\((\d+)\)\.IsUpdating', s)
    if m:
        return bool(state.get('updating', {}).get(int(m.group(1)), False))

    m = re.fullmatch(r'Control\.HasFocus\((\d+)\)', s)
    if m:
        return int(state.get('focused', -1)) == int(m.group(1))

    raise AssertionError(f'Unhandled Kodi boolean atom: {s}')


def _eval_var(tree: ET.Element, name: str, expressions: dict[str, str], state: dict) -> str:
    var = tree.find(f"variable[@name='{name}']")
    assert var is not None, name
    for val in var.findall('value'):
        cond = val.get('condition')
        if cond is None or _eval_kodi_bool(cond, expressions, state):
            return val.text or ''
    return ''


def test_home_rails_spec_aligns_with_glass_settings_and_compiles_emby_routes():
    from bobbi_platform import glass_settings as gs
    from bobbi_platform import home_rails_meta as meta

    loaded = generator.load_spec(ROOT / generator.SPEC)
    assert loaded['slot_preferences'] is True
    pairs = tuple((r['key'], r['title']) for r in loaded['rails'])
    assert pairs == meta.HOME_RAILS == gs.HOME_RAILS
    assert gs.HOME_RAIL_SPECS is meta.HOME_RAIL_SPECS
    assert gs.HOME_RAIL_CONTROL_IDS == {r['key']: r['control_id'] for r in loaded['rails']}
    # Confirm glass_settings.py has no second handwritten rail declaration
    gs_text = (ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform/glass_settings.py').read_text(encoding='utf-8')
    assert "('continue_watching'" not in gs_text and "('emby_resume'" not in gs_text
    by_key = {r['key']: r for r in loaded['rails']}
    assert by_key['emby_resume']['control_id'] == 9815
    assert by_key['emby_resume']['layout'] == 'wide'
    assert generator.route_path(by_key['emby_resume']) == 'plugin://plugin.video.bobbi/?action=emby_rail&section=resume'
    assert by_key['emby_recent']['control_id'] == 9825
    assert by_key['emby_recent']['layout'] == 'poster'
    assert generator.route_path(by_key['emby_recent']) == 'plugin://plugin.video.bobbi/?action=emby_rail&section=recent'


def test_slot_reordering_hiding_corrupt_fallback_and_all_hidden_recovery():
    raw, hero = generator.outputs(ROOT)
    rails_tree = ET.fromstring(raw)
    hero_tree = ET.fromstring(hero)
    expressions = {
        e.get('name'): (e.text or '')
        for tree in (rails_tree, hero_tree)
        for e in tree.findall('expression')
    }

    # Populate 4 rails: continue_watching (9810), emby_resume (9815), popular_tv (9830), personal_library (9820)
    base_counts = {9810: 3, 9815: 2, 9830: 10, 9820: 4}

    # 1. Default slot order: 9810 -> 9815 -> 9830 -> 9820
    st = {'counts': base_counts, 'bools': {}, 'strings': {}}
    assert _eval_var(rails_tree, 'HomeContentFocus', expressions, st) == '9810'
    st['current_9791'] = '9810'
    st['focused'] = 9810
    assert _eval_var(hero_tree, 'HomeNextRail', expressions, st) == '9815'
    assert _eval_var(rails_tree, 'HomeRailDown', expressions, st) == '9815'
    assert _eval_var(rails_tree, 'HomeRailUp', expressions, st) == '9701'

    # 2. Custom slot order: swap Slot 1 = personal_library (9820), Slot 2 = emby_resume (9815), Slot 8 = continue_watching (9810)
    custom_strings = {
        'BobbiRailSlot1': 'personal_library',
        'BobbiRailSlot2': 'emby_resume',
        'BobbiRailSlot3': 'emby_recent',
        'BobbiRailSlot4': 'popular_tv',
        'BobbiRailSlot5': 'popular_movies',
        'BobbiRailSlot6': 'current_anime',
        'BobbiRailSlot7': 'anime_movies',
        'BobbiRailSlot8': 'continue_watching',
    }
    st2 = {'counts': base_counts, 'bools': {}, 'strings': custom_strings}
    assert _eval_var(rails_tree, 'HomeContentFocus', expressions, st2) == '9820'
    st2['current_9791'] = '9820'
    st2['focused'] = 9820
    assert _eval_var(hero_tree, 'HomeNextRail', expressions, st2) == '9815'
    assert _eval_var(rails_tree, 'HomeRailDown', expressions, st2) == '9815'
    st2['focused'] = 9815
    assert _eval_var(rails_tree, 'HomeRailUp', expressions, st2) == '9820'
    assert _eval_var(rails_tree, 'HomeRailDown', expressions, st2) == '9830'
    st2['focused'] = 9830
    assert _eval_var(rails_tree, 'HomeRailDown', expressions, st2) == '9810'
    st2['focused'] = 9810
    assert _eval_var(rails_tree, 'HomeRailUp', expressions, st2) == '9830'

    # 3. Hide emby_resume (9815): navigation from 9820 skips 9815 directly to 9830!
    st2['bools'] = {'BobbiHideRail_emby_resume': True}
    st2['focused'] = 9820
    st2['current_9791'] = '9820'
    assert _eval_var(rails_tree, 'HomeRailDown', expressions, st2) == '9830'
    assert _eval_var(hero_tree, 'HomeNextRail', expressions, st2) == '9830'

    # 4. Corrupt/unknown slot value safely falls back to default rail
    st_corrupt = {'counts': base_counts, 'bools': {}, 'strings': {'BobbiRailSlot1': 'retired_nonexistent_rail'}}
    assert _eval_var(rails_tree, 'HomeContentFocus', expressions, st_corrupt) == '9810'

    # 5. Hide ALL rails -> BobbiHomeHasItems=False, BobbiHomeUpdating=False, BobbiHomeAnyRailHidden=True, focus -> 9870, button 9871 present in Home.xml
    all_hidden = {f'BobbiHideRail_{r["key"]}': True for r in generator.load_spec(ROOT / generator.SPEC)['rails']}
    st_all_hidden = {'counts': base_counts, 'updating': {9810: True}, 'bools': all_hidden, 'strings': {}}
    assert _eval_kodi_bool('$EXP[BobbiHomeHasItems]', expressions, st_all_hidden) is False
    assert _eval_kodi_bool('$EXP[BobbiHomeUpdating]', expressions, st_all_hidden) is False
    assert _eval_kodi_bool('$EXP[BobbiHomeAnyRailHidden]', expressions, st_all_hidden) is True
    assert _eval_var(rails_tree, 'HomeContentFocus', expressions, st_all_hidden) == '9870'

    home_xml = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/Home.xml').getroot()
    reset_btn = home_xml.find(".//control[@id='9871']")
    assert reset_btn is not None
    assert reset_btn.findtext('label') == '$LOCALIZE[32044]'
    assert reset_btn.findtext('onclick') == 'RunScript(script.bobbi.setup,home_rails_reset)'


def test_glass_settings_home_rail_manager_persists_only_skin_settings():
    from bobbi_platform import glass_settings as gs

    bools: dict[str, bool] = {}
    strings: dict[str, str] = {}

    def set_bool(k, on):
        if on:
            bools[k] = True
        else:
            bools.pop(k, None)

    def set_string(k, v):
        strings[k] = v

    def reset_setting(k):
        bools.pop(k, None)
        strings.pop(k, None)

    # Sequence: pick index 1 (emby_resume) -> move up (index 1) -> pick index 1 (continue_watching) -> hide (index 0) -> save & exit (len + 1 = 9)
    choices = iter([1, 1, 1, 0, 9])
    dialog = SimpleNamespace(select=lambda _title, _rows: next(choices))
    changed = gs.manage_home_rails(
        dialog,
        lambda k: bools.get(k, False),
        lambda k: strings.get(k, ''),
        set_bool,
        set_string,
        reset_setting,
    )
    assert changed is True
    assert strings['BobbiRailSlot1'] == 'emby_resume'
    assert strings['BobbiRailSlot2'] == 'continue_watching'
    assert bools == {'BobbiHideRail_continue_watching': True}

    # Reset restores clean empty defaults
    gs.apply_home_rail_prefs(list(gs.HOME_RAIL_KEYS), set(), set_bool, set_string, reset_setting)
    assert bools == {} and strings == {}


def test_emby_home_rail_zero_network_when_unconfigured_and_multi_account_isolated(tmp_path, monkeypatch):
    from bobbi_platform import emby_dynamic, paths
    from bobbi_platform.libraries import Registry, Source

    monkeypatch.setattr(paths, 'profile_root', lambda addon_id='script.module.bobbi.platform': tmp_path)
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _p: str(tmp_path)))

    class FakeItem:
        def __init__(self, label=''):
            self.label = label
            self.label2 = ''
            self.props = {}
            self.info = {}
            self.art = {}

        def setLabel2(self, v):
            self.label2 = v

        def setProperty(self, k, v):
            self.props[k] = v

        def setInfo(self, _kind, info):
            self.info = dict(info)

        def setContentLookup(self, _v):
            pass

        def setArt(self, art):
            self.art = dict(art)

    added, ended = [], []
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(abortRequested=lambda: False),
        getInfoLabel=lambda _k: 'Master user',
    ))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(ListItem=FakeItem))
    monkeypatch.setitem(sys.modules, 'xbmcplugin', SimpleNamespace(
        setContent=lambda *a: None,
        addDirectoryItems=lambda h, rows, n: added.append((h, rows, n)),
        endOfDirectory=lambda h, **kw: ended.append((h, kw)),
    ))

    network_calls = []

    class ForbiddenClient:
        def __init__(self, *_a, **_kw):
            network_calls.append('constructed')

    monkeypatch.setattr(emby_dynamic, 'Client', ForbiddenClient)

    # Case 1: No libraries.sqlite3 -> 0 network calls, empty directory
    emby_dynamic.execute_home_rail(11, {'action': 'emby_rail', 'section': 'resume'})
    assert network_calls == []
    assert added[-1] == (11, [], 0)
    assert ended[-1][1]['succeeded'] is True

    # Case 2: libraries.sqlite3 exists with WebDAV only (no Emby) -> 0 network calls
    reg = Registry(tmp_path / 'libraries.sqlite3')
    reg.close()
    emby_dynamic.execute_home_rail(12, {'action': 'emby_rail', 'section': 'recent'})
    assert network_calls == []
    assert added[-1] == (12, [], 0)

    # Case 3: Two Emby accounts with identical ItemId '9001' -> isolated routes & server resume authority
    reg = Registry(tmp_path / 'libraries.sqlite3')
    id_a, id_b = 'a' * 32, 'b' * 32
    reg.save(Source(
        id=id_a,
        name='客厅 Emby',
        kind='media_server',
        location='https://emby-a.example.test:8920',
        username='',
        password='tok-a',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srvA01', 'user_id': 'usrA01'},
    ), activate_emby=reg.emby_binding()[1])
    reg.save(Source(
        id=id_b,
        name='书房 Emby',
        kind='media_server',
        location='https://emby-b.example.test:8920',
        username='',
        password='tok-b',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srvB02', 'user_id': 'usrB02'},
    ), activate_emby=reg.emby_binding()[1])
    reg.close()

    class MockSession:
        def budget(self, _sec):
            from contextlib import nullcontext
            return nullcontext()

    class MockClient:
        def __init__(self, _prov, saved):
            self.saved = saved
            self.session = MockSession()

        def _identity(self, **_kw):
            network_calls.append(self.saved['server_id'])

        def page_rows(self, query, page, size, display=True):
            assert query == 'view:resume'
            pos = 900 * 10_000_000 if self.saved['server_id'] == 'srvA01' else 1800 * 10_000_000
            return ([{
                'Id': '9001',
                'Name': 'Severance S01E01',
                'Type': 'Episode',
                'SeriesName': 'Severance',
                'ParentIndexNumber': 1,
                'IndexNumber': 1,
                'RunTimeTicks': 3600 * 10_000_000,
                'UserData': {'PlaybackPositionTicks': pos, 'Played': False, 'IsFavorite': True},
            }], 1)

    monkeypatch.setattr(emby_dynamic, 'Client', MockClient)
    emby_dynamic.execute_home_rail(13, {'action': 'emby_rail', 'section': 'resume'})
    assert network_calls == ['srvA01', 'srvB02']
    _, rows, count = added[-1]
    assert count == 2
    url_a, item_a, folder_a = rows[0]
    url_b, item_b, folder_b = rows[1]
    assert not folder_a and not folder_b
    assert f'source={id_a}' in url_a and 'resume_mode=resume' in url_a
    assert f'source={id_b}' in url_b and 'resume_mode=resume' in url_b
    assert item_a.props['PercentPlayed'] == '25'
    assert item_b.props['PercentPlayed'] == '50'
    assert item_a.props['Bobbi.Emby.Authority'] == 'emby_server'
    assert '客厅 Emby' in item_a.label2 and '书房 Emby' in item_b.label2


def test_osd_next_episode_capsule_and_emby_summary_projection():
    from bobbi_core.next_episode_summary import checked, label, project

    cur = {
        'mode': 'tv',
        '_emby_season_ref': '0123456789abcdef',
        'tv_data': {'season': 1, 'episode': 1},
        'selection_policy': 'exact',
        'url': 'https://emby-secret.example/Videos/1/stream?api_key=SECRET',
    }
    nxt = {
        'mode': 'tv',
        '_emby_season_ref': '0123456789abcdef',
        'tv_data': {'season': 1, 'episode': 2},
        'selection_policy': 'exact',
        'prepared_version_key': 'b' * 64,
        '_next_cloud_verified': True,
    }
    proj = checked(project(cur, nxt))
    assert proj['state'] == 'ready'
    assert proj['current_media_ref'] == 'emby:season:0123456789abcdef:s1:e1'
    assert proj['next_media_ref'] == 'emby:season:0123456789abcdef:s1:e2'
    assert 'SECRET' not in str(proj) and 'emby-secret' not in str(proj)
    assert '同版下一集已就绪' in label(proj) and 'S01E02' in label(proj)

    osd_xml = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/VideoOSD.xml').getroot()
    capsule = osd_xml.find(".//control[@id='9650']")
    assert capsule is not None
    assert capsule.findall('.//onclick') == []
    assert '$INFO[Window(Home).Property(Bobbi.Next.Label)]' in ET.tostring(capsule, encoding='unicode')

    # Check pure DOM invariant on manage.html and manage.js
    forbidden = 'inner' + 'HTML'
    for web_name in ('manage.html', 'manage.js'):
        content = (ROOT / 'addons/plugin.video.bobbi/resources/web' / web_name).read_text(encoding='utf-8')
        assert forbidden not in content, web_name
    assert 'id="jobCapsule"' in (ROOT / 'addons/plugin.video.bobbi/resources/web/manage.html').read_text(encoding='utf-8')

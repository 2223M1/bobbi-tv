"""glass (on-device) home/navigation sample: asset, brand and id contracts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / 'addons/skin.bobbi.cinema'
MIRROR = ROOT / 'addons/plugin.video.bobbi/resources/skins/Default/media/bobbi/glass'
GLASS = SKIN / 'media/bobbi/glass'
SPEC = importlib.util.spec_from_file_location('home_rails_generator_atv', ROOT / 'tools/generate_home_rails.py')
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)
PROTECTED = {'9000', '9700', '9701', '9711', '9712', '9713', '9714', '9715', '9721', '9722',
             '9790', '9791', '9810', '9820', '9830', '9840', '9850', '9860', '9870'}


def test_generated_textures_are_manifested_and_mirrored_byte_for_byte():
    manifest = json.loads((ROOT / 'ui/glass_assets.json').read_text(encoding='utf-8'))['files']
    actual = {p.relative_to(GLASS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in GLASS.rglob('*.png')}
    assert actual == manifest
    mirrored = {p.relative_to(MIRROR).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in MIRROR.rglob('*.png')}
    assert mirrored == manifest


def test_every_referenced_atv_texture_exists():
    missing = set()
    for path in (SKIN / '1080p').glob('*.xml'):
        for name in re.findall(r'bobbi/glass/[A-Za-z0-9_./-]+\.png', path.read_text(encoding='utf-8')):
            if not (SKIN / 'media' / name).is_file():
                missing.add((path.name, name))
    assert not missing


def test_composite_fonts_exist_and_existing_fonts_are_untouched():
    fonts = ET.parse(SKIN / '1080p/Font.xml').getroot()
    files = {node.text for node in fonts.iter('filename')}
    for weight in ('Regular', 'Medium', 'Semibold', 'Bold'):
        assert f'BobbiTV-{weight}.ttf' in files
        assert (SKIN / f'fonts/BobbiTV-{weight}.ttf').stat().st_size > 1_000_000


@pytest.mark.parametrize('name', ['Home.xml', 'Includes_Home.xml'])
def test_home_and_navigation_carry_no_brand_artwork(name):
    assert 'logo-bobbi' not in (SKIN / '1080p' / name).read_text(encoding='utf-8')
    includes = ET.parse(SKIN / '1080p/Includes.xml').getroot()
    for include in ('TopBar', 'SideNav', 'TopNav', 'NavRow', 'GlassCapsule'):
        node = includes.find(f"include[@name='{include}']")
        assert node is not None
        text = ET.tostring(node, encoding='unicode')
        assert 'logo-bobbi' not in text and 'Kodi' not in text
    sidenav = ET.tostring(includes.find("include[@name='SideNav']"), encoding='unicode')
    assert '<label>波比TV</label>' in sidenav
    assert '$VAR[BobbiTimeAMPM]' in sidenav
    assert 'bobbi/glass/avatar-disc.png' in sidenav
    assert 'bobbi/glass/icon-disc-44.png' in ET.tostring(includes.find("include[@name='NavGlyph']"), encoding='unicode')


@pytest.mark.parametrize('topbar', [False, True])
def test_both_navigation_forms_keep_every_bound_home_id(topbar):
    raw, hero = generator.outputs(ROOT)
    # expanded_home expands every include-condition configuration and rejects
    # duplicates or missing focus targets in each; the default form is returned.
    expanded = generator.expanded_home(ROOT, raw, hero)
    ids = {node.get('id') for node in expanded.iter('control') if node.get('id')}
    assert PROTECTED <= ids
    includes = ET.parse(ROOT / generator.SKIN / 'Includes.xml').getroot()
    name = 'TopNav' if topbar else 'SideNav'
    body = ET.tostring(includes.find(f"include[@name='{name}']"), encoding='unicode')
    for control_id in ('9700', '9701', '9711', '9712', '9713', '9714', '9715', '9721', '9722'):
        assert f'"{control_id}"' in body, (name, control_id)


def test_motion_is_gpu_only_reversible_and_reduce_motion_gated():
    for name in ('Includes.xml', 'Includes_Home.xml'):
        root = ET.parse(SKIN / '1080p' / name).getroot()
        for include in ('SideNav', 'HomeRailMotion', 'NavFade', 'HomeDotsIndicator', 'HomePageStep',
                        'PageOpen', 'PanelOpen', 'Lift', 'FadeVisible'):
            node = root.find(f"include[@name='{include}']")
            if node is None:
                continue
            for animation in node.iter('animation'):
                effects = [animation] if animation.get('effect') else list(animation.iter('effect'))
                for effect in effects:
                    assert (effect.get('effect') or effect.get('type')) in ('slide', 'fade', 'zoom')
                    if effect.get('time', '0') != '0':
                        assert 'Skin.HasSetting(BobbiReduceMotion)' in animation.get('condition', ''), include
                    assert effect.get('loop') is None and animation.get('loop') is None


def test_legacy_fades_disc_art_and_pvr_layout_respect_reduced_motion():
    folder = SKIN / '1080p'
    legacy = ET.parse(folder / 'Includes_Compatibility.xml')
    for name in ('Animation_FadeIn', 'Animation_FadeOut'):
        for a in legacy.find(f"include[@name='{name}']").iter('animation'):
            assert '!Skin.HasSetting(BobbiReduceMotion)' in a.get('condition', '')
            assert all(int(effect.get('time')) <= 180 for effect in a)
    lyrics = ET.parse(folder / 'script-cu-lrclyrics-main.xml')
    assert all('!Skin.HasSetting(BobbiReduceMotion)' in a.get('condition', '')
               for a in lyrics.iter('animation') if a.get('loop') == 'true')
    assert lyrics.find(".//include[.='ListMotion']") is not None
    # These instantaneous offsets/dims are layout and state, not decorative motion.
    for path in [*folder.glob('*PVR*.xml'), folder / 'script-cu-lrclyrics-main.xml']:
        root = ET.parse(path).getroot()
        if root.tag == 'window':
            for a in root.iter('animation'):
                if a.get('time') == '0' and (a.text or '').strip().lower() == 'conditional':
                    assert '+ !Skin.HasSetting(BobbiReduceMotion)' not in a.get('condition', ''), path.name


def test_sidebar_hides_by_motion_not_visibility_so_focus_can_enter():
    root = ET.parse(SKIN / '1080p/Includes.xml').getroot()
    group = root.find("include[@name='SideNav']//control[@id='9700']")
    assert group.find('visible') is None
    grouplist = group.find("control[@id='9701']")
    assert grouplist.get('type') == 'grouplist' and grouplist.findtext('onright') == '$PARAM[down]'
    # A decorative direct child with ID zero breaks both Kodi directions.
    # It should occupy space but never become a stop on a remote.
    assert all(c.get('id') for c in grouplist.findall('control'))
    raw, hero = generator.outputs(ROOT)
    home = generator.expanded_home(ROOT, raw, hero)
    children = home.find(".//control[@id='9701']").findall('control')
    assert len({c.get('id') for c in children}) == len(children)
    assert [c.get('id') for c in children if c.get('type') == 'togglebutton'] == [
        '9721', '9711', '9712', '9713', '9714', '9715', '9722']


def test_page_geometry_from_expanded_ui_covers_every_absolute_selection():
    raw, hero = generator.outputs(ROOT)
    selectors = ET.fromstring(hero)
    rails = generator.load_spec(ROOT / generator.SPEC)['rails']
    for name, field in [('BobbiPageItem', 'CurrentItem'), ('BobbiPageCount', 'NumItems')]:
        values = selectors.find(f"variable[@name='{name}']").findall('value')
        assert [(v.get('condition'), v.text) for v in values] == [
            (generator._current(r['control_id']), f"$INFO[Container({r['control_id']}).{field}]")
            for r in rails] + [(None, '0')]
    home = generator.expanded_home(ROOT, raw, hero)
    thumb = next(c for c in home.iter('control') if c.findtext('texture') == 'bobbi/glass/dot-active-pill.png')
    conveyor = next(c for c in home.iter('control') if thumb in list(c))
    group = next(c for c in home.iter('control') if conveyor in list(c))
    assert 'Integer.IsGreater(Control.GetLabel(9795),1)' in group.findtext('visible')
    # Original glass page-indicator pill style restored: no 2px scrollbar line
    assert 'bobbi/white.png' not in ET.tostring(group, encoding='unicode')
    assert (thumb.findtext('width'), thumb.findtext('height')) == ('30', '9')

    centers = {int(a.get('condition').split(',')[-1][:-1]): int(a.get('end').split(',')[0])
               for a in group.findall('animation') if a.get('effect') == 'slide'}
    tracks = {int(re.search(r'GetLabel\(9795\),(\d+)\)', g.findtext('visible'))[1]):
              int(g.find('control/width').text)
              for g in group.findall("control[@type='group']") if g.findtext('visible')}
    assert tracks[20] == 206 and (960 + centers[20] - 15) == 857

    dot_groups = [g for g in conveyor.findall("control[@type='group']")
                  if g.find("control[@type='image']") is not None
                  and g.findtext("control[@type='image']/texture") == 'bobbi/glass/dot-9.png']
    assert len(dot_groups) == 19

    def eval_dot_vis(m: int, k: int, n: int) -> bool:
        ok = (n > m) and ((k <= m + 5) or (n <= m + 7))
        if m >= 8:
            ok = ok and (k > m - 2)
        return ok

    for size in range(2, max(r['limit'] for r in rails) + 1):
        vis_slots = min(size, 8)
        for reduced in (False, True):
            prev_state = None
            thumb_xs = []
            for index in range(1, size + 1):
                win_dx = 0
                for motion in conveyor.findall('animation'):
                    cond = motion.get('condition')
                    m_it = int(re.search(r'GetLabel\(9794\),(\d+)\)', cond)[1])
                    m_ct = int(re.search(r'GetLabel\(9795\),(\d+)\)', cond)[1])
                    if index > m_it and size > m_ct and reduced == ('!Skin.HasSetting' not in cond):
                        assert (motion.get('time') == '0') == reduced
                        win_dx += int(motion.get('end').split(',')[0])
                expected_w = min(max(index - 6, 0), max(size - 8, 0))
                assert win_dx == -21 * expected_w

                tx = centers[size] + win_dx
                for motion in thumb.findall('animation'):
                    cond = motion.get('condition')
                    threshold = int(re.search(r'GetLabel\(9794\),(\d+)\)', cond)[1])
                    if index > threshold and reduced == ('!Skin.HasSetting' not in cond):
                        assert (motion.get('time') == '0') == reduced
                        tx += int(motion.get('end').split(',')[0])
                slot_idx = (index - 1) - expected_w
                assert tx == centers[size] + 21 * slot_idx
                thumb_xs.append(tx)

                # Verify parting 9x9 dots fill the remaining vis_slots - 1 slots with zero overlap
                dot_xs = []
                for m_idx, dg in enumerate(dot_groups, start=1):
                    if eval_dot_vis(m_idx, index, size):
                        dx = centers[size] + win_dx + int(dg.findtext('left'))
                        if index <= m_idx:
                            dx += 42
                        dot_xs.append(dx)
                assert len(dot_xs) == vis_slots - 1
                state = (tx, tuple(conveyor_raw_x := [
                    (m_idx, win_dx + (42 if index <= m_idx else 0))
                    for m_idx in range(1, size)
                ]))
                if prev_state is not None:
                    assert state != prev_state
                prev_state = state

            # Last two cards (N-1 and N) MUST slide onto the 2nd-from-last and very last slots!
            assert thumb_xs[0] == centers[size]
            assert thumb_xs[-1] == centers[size] + 21 * (vis_slots - 1)
            if size >= 3:
                assert thumb_xs[-2] == centers[size] + 21 * (vis_slots - 2)
                assert thumb_xs[-1] - thumb_xs[-2] == 21
            if size >= 8:
                assert thumb_xs[-2] - thumb_xs[-3] == 21


def test_glass26_concentric_corners_and_liquid_glass_translucency():
    includes = ET.parse(SKIN / '1080p/Includes.xml').getroot()
    sidenav = includes.find("include[@name='SideNav']/definition")
    # Outside stage whisper dim (<= 10% alpha, never 50% blackout)
    dim = sidenav.find("control[@type='image']/texture")
    assert int(dim.get('colordiffuse')[:2], 16) <= 0x20
    # Concentric 10 px inset: 320x72 focus capsule @ x=45 inside 340x1010 sidebar @ (35, 35)
    fills = [c for c in sidenav.findall("control[@id='9700']/control[@type='image']")
             if c.findtext('texture') in ('bobbi/glass/sidebar-fill.png', 'bobbi/glass/sidebar-classic.png')]
    assert len(fills) == 2
    for fill in fills:
        assert (fill.findtext('left'), fill.findtext('top'),
                fill.findtext('width'), fill.findtext('height')) == ('35', '35', '340', '1010')
    grouplist = sidenav.find("control[@id='9700']/control[@id='9701']")
    assert (grouplist.findtext('left'), grouplist.findtext('width')) == ('45', '320')
    row = includes.find("include[@name='NavRow']/definition/control[@type='togglebutton']")
    assert (row.findtext('width'), row.findtext('height')) == ('320', '72')
    assert row.findtext('texturefocus') == 'bobbi/glass/pill-320x72.png'
    # The GPU now samples the actual scene. No duplicate background image job.
    timers = ET.parse(SKIN / '1080p/Timers.xml').getroot()
    assert timers.find("timer[name='BobbiStageBlurSync']") is None
    assert fills[0].find('texture').get('diffuse') == 'bobbi/glass/lg-sidebar.png'
    assert 'BobbiLiquidGlassEnabled' in fills[0].findtext('visible')
    for name in ('Home.xml', 'Includes.xml', 'Includes_Home.xml', 'DialogButtonMenu.xml'):
        raw = (SKIN / '1080p' / name).read_text(encoding='utf-8')
        assert 'blur_image=' not in raw and 'TMDbHelper.EnableBlur' not in raw
    # Without the CE renderer, the fullscreen soften layer must not paint white.
    cc = ET.parse(SKIN / '1080p/DialogButtonMenu.xml')
    assert cc.find(".//texture[@diffuse='bobbi/glass/lg-cc-soften.png']").text == 'am6b/transparent.png'
    palette = {n.get('name'): n.text for n in ET.parse(SKIN / 'colors/defaults.xml').getroot()}
    assert 0x80 <= int(palette['glass_blur'][:2], 16) <= 0xBA
    assert palette['classic_panel'].startswith('FF')
    assert fills[1].findtext('texture') == 'bobbi/glass/sidebar-classic.png'
    assert fills[1].findtext('visible') == '!Skin.HasSetting(BobbiLiquidGlassEnabled)'


def test_tvapp_card_grid_on_card_progress_bar_and_caption_typography():
    home_inc = ET.parse(SKIN / '1080p/Includes_Home.xml').getroot()
    # 5-up 320x180 wide cards @ x=80,440,800,1160,1520 (+ 40 px right peek @ x=1880..1920), y=793..973
    wide_list = home_inc.find("include[@name='HomeRailWide']//control[@type='list']")
    assert (wide_list.findtext('left'), wide_list.findtext('top'),
            wide_list.findtext('width')) == ('60', '193', '1860')
    assert wide_list.find('itemlayout').get('width') == '360'
    assert wide_list.find('focusedlayout').get('width') == '360'
    assert wide_list.find('itemlayout/control/left').text == '20'
    assert wide_list.find('itemlayout/control/top').text == '20'
    # On-card progress bar uses rounded capsule track + fill + min nub, and no % text under cards
    progress = ET.tostring(home_inc.find("include[@name='ATVProgress']"), encoding='unicode')
    assert 'bobbi/glass/progress-track.png' in progress
    assert 'bobbi/glass/progress-fill.png' in progress
    assert 'bobbi/glass/progress-nub.png' in progress
    caption = ET.tostring(home_inc.find("include[@name='WideCaption']"), encoding='unicode')
    assert 'PercentPlayed' not in caption and '%' not in caption
    # Hero stage buttons, [TV-MA]-style outlined badge, animated dots pill, and top-left back pill
    stage = ET.tostring(home_inc.find("include[@name='HomeStage']"), encoding='unicode')
    assert 'bobbi/glass/hero-play-pill.png' in stage
    assert 'bobbi/glass/hero-circle-66.png' in stage
    assert 'bobbi/glass/badge-outline-26.png' in stage
    assert 'HomeDotsIndicator' in stage
    dots = ET.tostring(home_inc.find("include[@name='HomeDotsIndicator']"), encoding='unicode')
    assert 'bobbi/glass/dots-pill-bg.png' in ET.tostring(home_inc.find("include[@name='HomePageTrack']"), encoding='unicode')
    assert 'bobbi/glass/dot-active-pill.png' in dots
    includes = ET.parse(SKIN / '1080p/Includes.xml').getroot()
    sidenav = ET.tostring(includes.find("include[@name='SideNav']"), encoding='unicode')
    assert 'bobbi/glass/back-pill-180x60.png' in sidenav


def test_hud_and_popup_dismissal_are_interruptible_and_do_not_own_visibility_timers():
    controls = SKIN / '1080p'
    includes = ET.parse(controls / 'Includes.xml').getroot()
    consumers = {
        'HudFade': ('DialogSeekBar', 'DialogVolumeBar', 'DialogExtendedProgressBar'),
        'MenuPop': ('DialogContextMenu', 'DialogButtonMenu'),
        'PanelOpen': ('DialogPlayerProcessInfo', 'DialogNotification', 'DialogSlider'),
    }
    for name, windows in consumers.items():
        animations = includes.find(f"include[@name='{name}']").findall('.//animation')
        assert len(animations) == 2
        assert {a.get('type') or (a.text or '').strip() for a in animations} == {'WindowOpen', 'WindowClose'}
        for a in animations:
            assert a.get('reversible') == 'true' and a.get('condition') == '!Skin.HasSetting(BobbiReduceMotion)'
            effects = a.findall('effect') or [a]
            assert all(e.get('tween')=='cubic' and int(e.get('delay','0'))==0 for e in effects)
            if (a.get('type') or a.text.strip())=='WindowClose':
                assert all(int(e.get('time'))<=120 for e in effects)
        for window in windows:
            root = ET.parse(controls / (window+'.xml')).getroot()
            assert any(i.get('content')==name or (i.text or '').strip()==name for i in root.iter('include'))
            assert not any((a.get('type') or (a.text or '').strip()) in ('WindowOpen','WindowClose')
                           for a in root.iter('animation'))
    # The busy indicator's distinct debounce suppresses flashes on cheap operations.
    assert ET.parse(controls/'DialogBusy.xml').getroot().find("animation[@delay='350']") is not None


def test_secondary_pages_align_with_glass26_design_system():
    plugin_skins = ROOT / 'addons/plugin.video.bobbi/resources/skins/Default'
    missing = set()
    for path in plugin_skins.glob('1080i/*.xml'):
        for name in re.findall(r'bobbi/glass/[A-Za-z0-9_./-]+\.png', path.read_text(encoding='utf-8')):
            if not (plugin_skins / 'media' / name).is_file():
                missing.add((path.name, name))
    assert not missing

    skin_secondary = (
        'Includes_Views.xml', 'Includes_Dialogs.xml', 'Includes_OSD.xml',
        'DialogVideoInfo.xml', 'Custom_1197_BobbiPersonal.xml', 'Settings.xml',
        'SkinSettings.xml', 'SettingsCategory.xml', 'DialogSettings.xml',
        'DialogAddonSettings.xml', 'Custom_1196_BobbiSearch.xml', 'Custom_1198_BobbiAnime.xml',
        'AddonBrowser.xml', 'MyFavourites.xml', 'FileManager.xml', 'SettingsSystemInfo.xml',
        'VideoOSD.xml', 'DialogSeekBar.xml', 'DialogVolumeBar.xml',
    )
    for name in skin_secondary:
        raw = (SKIN / '1080p' / name).read_text(encoding='utf-8')
        assert 'BobbiCompactWordmark' not in raw, name
        assert 'CinemaTopNav' not in raw, name
        assert not re.search(r'FF(?:8A3D|B27F|D9601A)', raw, re.I), name

    plugin_dialogs = (
        'extras.xml', 'source_select.xml', 'source_select_direct.xml', 'source_pack_select.xml',
        'playing_next.xml', 'skip_intro.xml', 'resume_dialog.xml', 'resolver.xml',
        'filter_items.xml', 'filter_type.xml', 'search_status.xml',
        'customdialog.xml', 'custom_progress_dialog.xml', 'download_manager.xml',
        'qr_dialog.xml', 'terminal-actions.xml',
    )
    for name in plugin_dialogs:
        raw = (plugin_skins / '1080i' / name).read_text(encoding='utf-8')
        assert 'BobbiCompactWordmark' not in raw, name
        assert not re.search(r'FF(?:8A3D|B27F|D9601A|E50914|E50924)', raw, re.I), name
        assert 'bobbi/glass/' in raw, name

    # Verify x=80..1840 symmetric grid on DirectoryPanel (7-up 256=1792, 4-up 448=1792) & Settings (4-up 448=1792)
    views = ET.parse(SKIN / '1080p/Includes_Views.xml').getroot()
    panel = views.find("include[@name='DirectoryPanel']/control[@id='50']")
    assert (panel.findtext('left'), panel.findtext('width')) == ('64', '1792')
    settings = ET.parse(SKIN / '1080p/Settings.xml').getroot()
    s_panel = settings.find(".//control[@id='9000']")
    assert (s_panel.findtext('left'), s_panel.findtext('width')) == ('1036', '828')
    skin_settings = ET.parse(SKIN / '1080p/SkinSettings.xml').getroot()
    ss_list = skin_settings.find(".//control[@id='9000']")
    assert (ss_list.findtext('left'), ss_list.findtext('top'), ss_list.findtext('width')) == ('1060', '189', '780')


def test_personal_page_replicates_glass_library_1to1_and_migrates_settings_out():
    personal = ET.parse(SKIN / '1080p/Custom_1197_BobbiPersonal.xml').getroot()
    raw = (SKIN / '1080p/Custom_1197_BobbiPersonal.xml').read_text(encoding='utf-8')
    rail = personal.find(".//control[@id='9100']")
    assert (rail.findtext('left'), rail.findtext('top'), rail.findtext('width')) == ('46', '161', '318')
    # Right 6-column 200x300 poster grid starts at x=420+20=440..1840, y=142+18=160
    dialogs = ET.parse(SKIN / '1080p/Includes_Dialogs.xml').getroot()
    p_panel = dialogs.find("include[@name='PersonalPosterPanel']/definition/control")
    assert (p_panel.findtext('left'), p_panel.findtext('top'), p_panel.findtext('width')) == ('420', '142', '1440')
    assert p_panel.find('itemlayout').attrib == {'width': '240', 'height': '364'}
    # Top-left Library capsule enabled (< [stack 我的])
    assert personal.find(".//include[@content='TopBar']/param[@name='library_pill']").get('value') == 'true'
    # System/admin items migrated out of Personal into Settings.xml
    for migrated in ('SkinSettings', 'SystemInfo', 'FileManager', 'shutdownmenu', 'bobbi_setup'):
        assert migrated not in raw
    settings_raw = (SKIN / '1080p/Settings.xml').read_text(encoding='utf-8')
    assert 'RunScript(script.bobbi.setup)' in settings_raw
    assert 'RunScript(script.bobbi.setup,libraries)' in settings_raw


def _decode_png_rgba(raw_png: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    import struct
    import zlib

    assert raw_png[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8
    w = h = 0
    idat = bytearray()
    while pos < len(raw_png):
        length, ctype = struct.unpack('>I4s', raw_png[pos:pos + 8])
        cdata = raw_png[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b'IHDR':
            w, h, bit_depth, color_type, _, _, _ = struct.unpack('>IIBBBBB', cdata)
            assert (bit_depth, color_type) == (8, 6)
        elif ctype == b'IDAT':
            idat.extend(cdata)
        elif ctype == b'IEND':
            break
    decomp = zlib.decompress(bytes(idat))
    stride = w * 4
    rows: list[bytearray] = []
    idx = 0
    for r in range(h):
        ftype = decomp[idx]
        scan = bytearray(decomp[idx + 1:idx + 1 + stride])
        idx += 1 + stride
        prev = rows[r - 1] if r > 0 else bytearray(stride)
        if ftype == 1:
            for i in range(4, stride):
                scan[i] = (scan[i] + scan[i - 4]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                scan[i] = (scan[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = scan[i - 4] if i >= 4 else 0
                scan[i] = (scan[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = scan[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                scan[i] = (scan[i] + pr) & 0xFF
        rows.append(scan)
    pixels = []
    for row in rows:
        for x in range(w):
            pixels.append((row[x * 4], row[x * 4 + 1], row[x * 4 + 2], row[x * 4 + 3]))
    return w, h, pixels


def test_classic_controls_have_a_matte_face_and_antialiased_silhouette():
    names = ['sidebar-classic.png', 'back-pill-164x60.png', 'back-pill-180x60.png',
             'dots-pill-bg.png', 'hero-circle-66.png', 'osd-disc-64.png',
             'glass-modal.png', 'glass-orb-128.png', 'cc-pill-251x110.png',
             'cc-power-251x242.png', 'cc-pill-251x112.png', 'cc-orb-115.png']
    names += [p.name for p in GLASS.glob('glass-pill-*.png')]
    for name in names:
        w, h, pixels = _decode_png_rgba((GLASS / name).read_bytes())
        at = lambda x, y: pixels[y*w+x]
        assert at(0, 0)[3] == 0 and any(0 < p[3] < 255 for p in pixels), name
        assert all(at(w*x//4, h*y//4)[3] == 255 for x in (1,2,3) for y in (1,2,3)), name
        centre = at(w//2, h//2)
        if name == 'sidebar-classic.png':
            assert (w, h) == (340, 1010)
            for x,y,ref in [(15,115,(77,79,86)), (15,515,(63,67,74)),
                            (325,515,(66,67,73)), (325,990,(59,60,67))]:
                assert max(abs(a-b) for a,b in zip(at(x,y),ref)) <= 3
        else:
            # Keep the matte controls lighter than the sidebar, and distinguish
            # a large sheet, a regular action, and its selected state.
            lo, hi = ((95, 110) if name.startswith('cc-') else (100, 116) if '-active.' in name
                      else (76, 94) if name in ('glass-modal.png', 'dots-pill-bg.png', 'osd-disc-64.png')
                      else (85, 102))
            assert lo <= min(centre[:3]) <= max(centre[:3]) <= hi, name


def test_classic_sheets_lighten_scrims_without_changing_liquid_defaults():
    mode = '!Skin.HasSetting(BobbiLiquidGlassEnabled)'
    palette = {c.get('name'):c.text for c in ET.parse(SKIN/'colors/defaults.xml').iter('color')}
    values = ET.parse(SKIN/'1080p/Variables.xml')
    def branches(name):
        return [(v.get('condition'),palette.get(v.text,v.text)) for v in values.find(f"variable[@name='{name}']")]
    assert branches('BobbiSheetScrim') == [(mode, '59191B20'), (None, '66000000')]
    assert branches('BobbiPanelCaption') == [(mode, 'E6EBEBF5'), (None, '9CEBEBF5')]
    assert branches('BobbiPanelHint') == [(mode, 'DCEBEBF5'), (None, '73EBEBF5')]
    scrim = ET.parse(SKIN/'1080p/Includes.xml').find("include[@name='DialogScrim']")
    assert {(c.findtext('visible'),c.find('texture').get('colordiffuse')) for c in scrim.findall('control')} == {
        (mode,'classic_scrim'),(mode[1:],'4D000000')}
    checked = set()
    for path in (MIRROR.parents[2]/'1080i').glob('*.xml'):
        for c in ET.parse(path).iter('control'):
            for anim in c.findall("animation[@time='0']"):
                if anim.text != 'Conditional' or anim.get('condition','').lstrip('!') != mode[1:]:
                    continue
                if anim.get('condition') == mode:
                    assert c.get('type') == 'image' and c.findtext('texture') == 'bobbi/white.png', path
                    alpha = int(c.find('texture').get('colordiffuse')[:2],16)
                    assert 78 <= alpha * int(anim.get('end')) / 100 <= 82, path
                    checked.add(path.stem)
                else:
                    assert c.get('type') in ('label', 'textbox'), path
    assert {'resume_dialog', 'search_status'} <= checked


def test_classic_browse_canvas_reuses_settings_without_tinting_media():
    folder = SKIN/'1080p'
    mode = '!Skin.HasSetting(BobbiLiquidGlassEnabled)'
    include = ET.parse(folder/'Includes.xml').find("include[@name='BobbiBrowseCanvas']")
    layers = {c.findtext('visible'): c.find('texture') for c in include.findall('definition/control')}
    settings = ET.parse(folder/'Settings.xml').find('controls/control/texture').text
    assert layers[mode].text == settings and not layers[mode].get('colordiffuse')
    assert layers[mode[1:]].text == '$PARAM[liquid]'
    assert include.find("param[@name='liquid']").text == 'bobbi/glass/stage-ambient.png'
    pages = set()
    for path in folder.glob('*.xml'):
        root = ET.parse(path).getroot()
        if any(n.text == 'BobbiBrowseCanvas' or n.get('content') == 'BobbiBrowseCanvas' for n in root.iter('include')):
            pages.add(path.stem)
    assert pages == {'Custom_1195_AM6BStreamingHub','Custom_1196_BobbiSearch','Custom_1197_BobbiPersonal',
                     'Custom_1198_BobbiAnime','AddonBrowser','MyFavourites'}
    mine = ET.parse(folder/'Custom_1197_BobbiPersonal.xml').find("controls/include[@content='BobbiBrowseCanvas']")
    assert {p.get('name'):p.text for p in mine} == {'liquid':'bobbi/white.png','tint':'FF1A1A1B'}


def test_classic_preference_disarms_optical_materials_except_control_center_background():
    files = list((SKIN/'1080p').glob('*.xml')) + list((MIRROR.parents[2]/'1080i').glob('*.xml'))
    barriers = set()
    for path in files:
        for control in ET.parse(path).iter('control'):
            for tex in control.findall('texture'):
                if 'lg-barrier-' not in (tex.text or ''):
                    continue
                barriers.add(tex.text)
                if tex.text.endswith('/lg-barrier-cc-backdrop.png'):
                    assert path.name=='DialogButtonMenu.xml' and control.findtext('visible')=='!Skin.HasSetting(BobbiLiquidGlassEnabled)'
                else:
                    assert 'Skin.HasSetting(BobbiLiquidGlassEnabled)' in control.findtext('visible',''), path
    assert any('sidebar' in name for name in barriers) and any('cc' in name for name in barriers)


def test_control_center_reference_geometry_and_isolated_materials():
    cc = ET.parse(SKIN/'1080p/DialogButtonMenu.xml')
    inc = ET.parse(SKIN/'1080p/Includes.xml')
    group = cc.find(".//control[@id='9000']")
    assert (group.findtext('left'), group.findtext('top'), group.findtext('width')) == ('1421','52','437')
    clock, = (n for n in group.findall('control') if n.findtext('label','')=='$VAR[BobbiTimeAMPM]')
    assert clock.findtext('font')=='CCClock24' and (clock.findtext('left'), clock.findtext('top'), clock.findtext('height'))==('55','0','56')
    cc_disc, = (n for n in group.findall('control') if n.findtext('texture','')=='bobbi/glass/circle-128.png')
    assert (cc_disc.findtext('left'), cc_disc.findtext('width'), cc_disc.findtext('height'), cc_disc.findtext('top')) == ('333','56','56','0')
    avatar, = (n for n in group.findall('control') if n.findtext('texture','')=='bobbi/glass/cc-avatar-34.png')
    assert (avatar.findtext('left'), avatar.findtext('top'), avatar.findtext('width'), avatar.findtext('height')) == ('403','11','34','34')
    assert not any('glass-pill-' in (t.text or '') for t in group.findall('control/texture'))
    power_labels = [c for c in cc.iter('control') if c.findtext('label')=='关机']
    assert len(power_labels)==2 and all(c.findtext('font')=='CCLabel24' for c in power_labels)
    idle = inc.find("include[@name='CCIdleFace']/definition")
    matte, optic = idle.findall('control')
    assert matte.find('texture').get('diffuse') is None and optic.find('texture').get('diffuse')=='$PARAM[optics]'
    assert '+ !Skin.HasSetting(BobbiLiquidGlassEnabled)' in matte.findtext('visible')
    assert '+ Skin.HasSetting(BobbiLiquidGlassEnabled)' in optic.findtext('visible')
    faces = cc.findall(".//include[@content='CCIdleFace']")
    assert len(faces)==len(cc.findall(".//control[@type='button']"))==9
    moving = [c for c in cc.iter('control') if c.find("include[@content='Lift']") is not None]
    assert len(moving)==9
    for c in moving:
        x,y,w,h=(int(c.findtext(k)) for k in ('left','top','width','height'))
        assert c.findtext("include[@content='Lift']/param[@name='center']")==f'{x+w//2},{y+h//2}'
    for include in faces:
        v={n.get('name'):n.get('value') for n in include.findall('param')}
        b=cc.find(".//control[@id='"+v['id']+"']")
        assert b.findtext('texturefocus')==v['face'].replace('.png','-focus.png')
        assert (b.findtext('width'),b.findtext('height'))==(v['width'],v['height'])
        assert not b.find('texturenofocus').get('diffuse')
        if v['id'] in ('9010','9012','9013','9011','9014'):
            w,h,pixels = _decode_png_rgba((GLASS/Path(v['face']).name).read_bytes())
            assert (w,h)==(int(v['width']),int(v['height']))
            assert w==208 and h==(208 if v['id']=='9010' else 96)
            # Boundary check away from the bounding box: the cap must transition
            # along its contour, not be a clipped/stretched rounded rectangle.
            at_y=[next(x for x in range(w) if pixels[y*w+x][3]>=128) for y in (4,12,24,40)]
            assert all(abs(a-e)<=2 for a,e in zip(at_y,(28,16,6,1))), (v,at_y)


def test_control_center_action_label_pairs_share_weight_in_both_focus_states():
    folder = SKIN / '1080p'
    cc = ET.parse(folder / 'DialogButtonMenu.xml')
    template = ET.parse(folder / 'Includes.xml').find("include[@name='CCActionContent']/definition")
    fonts = {e.findtext('name'):e for e in ET.parse(folder / 'Font.xml').findall('.//font')}
    rows = {}
    for group in cc.iter('control'):
        inc = group.find("include[@content='CCActionContent']")
        if inc is None:
            continue
        args = {p.get('name'):p.get('value') for p in inc.findall('param')}
        assert group.find("control[@type='button']").get('id') == args['id']
        assert not group.findall("control[@type='label']")  # No local font overrides.
        rows[args['id']] = args['title'], args['subtitle']
        w,h,rgba = _decode_png_rgba((GLASS / 'icons' / (args['glyph']+'.png')).read_bytes())
        ix = [i for i,v in enumerate(rgba) if v[3]>=128]
        xx,yy = [i%w for i in ix],[i//w for i in ix]
        size = int(args['size'])
        bw,bh=(max(xx)+1-min(xx))*size/w,(max(yy)+1-min(yy))*size/h
        cx=int(args['x'])+(max(xx)+1+min(xx))*size/(2*w)
        cy=int(args['y'])+(max(yy)+1+min(yy))*size/(2*h)
        assert abs(cx-48)<=1 and abs(cy-48)<=1 and abs(bh-34)<=1 and bw<=48
    assert rows == {'9012':('返回影院','继续观看'), '9013':('重启系统','CoreELEC'),
                    '9011':('重载界面','波比TV'), '9014':('系统信息','硬件与网络')}
    labels = template.findall("control[@type='label']")
    assert len(labels)==4
    icons=template.findall("control[@type='image']")
    assert len(icons)==2 and all(c.findtext('width')==c.findtext('height')=='$PARAM[size]' for c in icons)
    for polarity in ('!', ''):
        active = {c.findtext('label'):c for c in labels
                  if c.findtext('visible') == polarity + 'Control.HasFocus($PARAM[id])'}
        front, sub = (active['$PARAM['+part+']'] for part in ('title','subtitle'))
        ft, fs = (fonts[c.findtext('font')] for c in (front,sub))
        assert (front.findtext('left'),sub.findtext('left'),front.findtext('top'),sub.findtext('top'))==('86','86','19','47')
        assert ft.findtext('filename') == fs.findtext('filename') == 'BobbiTV-CCMedium.ttf'
        assert tuple(int(f.findtext('size')) for f in (ft,fs)) == (23,23)
        title_ink, sub_ink = (c.findtext('textcolor') for c in (front,sub))
        assert title_ink[2:] == sub_ink[2:] and (title_ink[:2],sub_ink[:2]) == ('FF','A3')


def test_plugin_dialogs_use_the_classic_panel_colour_without_requiring_bobbi_skin():
    palette = ET.parse(SKIN / 'colors/defaults.xml')
    colour = palette.find("color[@name='classic_panel']").text
    assert colour.startswith('FF')
    covered = set()
    mode = '!Skin.HasSetting(BobbiLiquidGlassEnabled)'
    v = ET.parse(SKIN/'1080p/Variables.xml').find("variable[@name='BobbiMattePanelColor']")
    assert [(n.get('condition'), n.text) for n in v] == [(mode, 'classic_panel'), (None, 'FF25252C')]
    for path in (MIRROR.parents[2] / '1080i').glob('*.xml'):
        faces = [(c.findtext('visible'), c.find('texture').get('colordiffuse'),
                  tuple(c.findtext(k) for k in ('left','top','width','height')))
                 for c in ET.parse(path).iter('control') if c.findtext('texture') == 'bobbi/glass/modal-glass.png']
        if faces:
            assert {(cond, tint) for cond,tint,_ in faces} == {(mode,colour),(mode[1:],'FF25252C')}, path
            assert len(faces) == 2 and faces[0][2] == faces[1][2], path
            covered.add(path.stem)
    assert {'resume_dialog', 'search_status', 'qr_dialog', 'playing_next'} <= covered


def _crc8_bobbilg(payload: bytes) -> int:
    crc = 0x5A
    for b_val in payload:
        crc ^= b_val
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def test_gles2_liquid_glass_steganographic_tags_and_barriers():
    glass_dir = SKIN / 'media/bobbi/glass'
    mirror_dir = ROOT / 'addons/plugin.video.bobbi/resources/skins/Default/media/bobbi/glass'
    lg_pngs = sorted(glass_dir.glob('lg-*.png'))
    assert len(lg_pngs) >= 19

    decoded_tags = {}
    kinds_seen = set()
    for p in lg_pngs:
        raw = p.read_bytes()
        assert (mirror_dir / p.name).read_bytes() == raw
        w, h, pixels = _decode_png_rgba(raw)
        # 16x4 aligns to Kodi CTextureBase::Allocate 16-pixel stride with zero row padding
        assert (w, h) == (16, 4), f'{p.name} must be 16x4'
        msg = bytearray(16)
        for idx, (r, g, b, a) in enumerate(pixels):
            assert (r, b, a) == (255, 255, 255) and 252 <= g <= 255, f'{p.name} fallback pixel out of >=98.8% white range'
            msg[idx >> 2] |= ((g & 0x03) << ((3 - (idx & 3)) * 2))
        assert bytes(msg[:6]) == b'BOBILG', f'{p.name} missing BOBILG magic'
        assert _crc8_bobbilg(bytes(msg[:15])) == msg[15], f'{p.name} CRC8 mismatch'
        kinds_seen.add(msg[6])
        decoded_tags[p.name] = msg
    assert kinds_seen == {1, 2}

    # Verify 4-layer isolation & exact native UI kit continuous corner radii
    assert (decoded_tags['lg-barrier-nav1.png'][7] & 0x03) == 1
    assert (decoded_tags['lg-barrier-sidebar.png'][7] & 0x03) == 2
    assert (decoded_tags['lg-barrier-cc.png'][7] & 0x03) == 3
    assert (decoded_tags['lg-sidebar.png'][7] & 0x03, decoded_tags['lg-sidebar.png'][8]) == (2, 41)
    # A clear 22-px meniscus used to repeat hero lettering inside the panel.
    # Check the shipped bytes, not just the texture generator defaults.
    for name in ('lg-sidebar.png', 'lg-nav-pill.png', 'lg-nav-pill-active.png',
                 'lg-pill.png', 'lg-pill-active.png'):
        bevel, refraction, clarity = decoded_tags[name][9:12]
        assert 2 <= bevel <= 6 and 0 < refraction <= bevel and 0 < clarity <= 100
    skin_xml = ET.parse(ROOT / 'addons/skin.bobbi.cinema/1080p/Includes.xml')
    shadow, = (t for t in skin_xml.iter('texture') if t.text == 'bobbi/glass/sidebar-shadow.png')
    assert 0 < int(shadow.attrib['colordiffuse'][:2], 16) <= 0x50
    # The control center borrows more wallpaper colour; sheets prioritise
    # reading over texture detail. A video overlay must not become a CC tile.
    for name, shape in [('lg-cc-tile.png', 54), ('lg-cc-pill.png', 0),
                        ('lg-modal-panel.png', 38), ('lg-modal-pill.png', 0),
                        ('lg-card-r24.png', 24), ('lg-osd-pill.png', 0)]:
        tag = decoded_tags[name]
        assert tag[8] == shape and 0 < tag[10] <= tag[9] <= 7
    assert (decoded_tags['lg-osd-pill.png'][12] < decoded_tags['lg-cc-tile.png'][12]
            < decoded_tags['lg-modal-panel.png'][12])
    assert decoded_tags['lg-cc-soften.png'][8] == 255
    assert decoded_tags['lg-cc-matte-soften.png'][7:9] == bytes([1,255])
    assert decoded_tags['lg-barrier-cc-backdrop.png'][6:9] == bytes([1,1,255])
    assert decoded_tags['lg-cc-power-r56.png'][7:9] == bytes([3,56])
    assert (decoded_tags['lg-cc-tile.png'][7] & 0x03, decoded_tags['lg-cc-tile.png'][8]) == (3, 54)

    c_src = (ROOT / 'ui/liquid_glass/bobbi_liquid_glass_gles2.c').read_text(encoding='utf-8')
    assert '#version 100' in c_src
    assert 'unsetenv("LD_PRELOAD")' in c_src
    assert 'sqrt(max(2.0 * t - t * t, 0.0))' in c_src
    assert '1.0 - smoothstep(0.0, 2.2, depth)' in c_src
    assert 'tls_unicol[3] = 1.0f;' in c_src
    assert '1.5286648' in c_src
    assert 'bgAlpha < 0.05' in c_src
    assert 'end_internal_gl_pass' in c_src

    # native HIG scope: barriers precede genuine glass chrome; Settings, SourceSelect & content cards are NOT forced glass
    views_raw = (SKIN / '1080p/Includes_Views.xml').read_text(encoding='utf-8')
    assert '<include>LGBarrierNav</include>' in views_raw
    assert 'diffuse="bobbi/glass/lg-nav-pill.png"' in views_raw
    for non_glass_xml in ('Settings.xml', 'SkinSettings.xml'):
        assert 'lg-' not in (SKIN / '1080p' / non_glass_xml).read_text(encoding='utf-8')
    for src_xml in ('source_select.xml', 'source_select_direct.xml', 'source_pack_select.xml'):
        assert 'lg-' not in (ROOT / 'addons/plugin.video.bobbi/resources/skins/Default/1080i' / src_xml).read_text(encoding='utf-8')
    wall_tile = ET.parse(SKIN / '1080p/Includes_Views.xml').getroot().find("include[@name='WallTile']")
    assert 'lg-' not in ET.tostring(wall_tile, encoding='unicode')
    home_inc = ET.parse(SKIN / '1080p/Includes_Home.xml').getroot()
    for tile_inc in ('HomeRailWide', 'MoreTile', 'LibraryTile'):
        assert 'lg-card-r24' not in ET.tostring(home_inc.find(f"include[@name='{tile_inc}']"), encoding='unicode')

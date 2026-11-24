"""Compile reviewed, bounded home rail data to static Kodi 21 XML.

This is a build tool, never an addon service. The only write target is OUTPUT;
--check validates without repairing it. Paths/actions come from code, not JSON.
"""
import argparse
from collections import Counter
from itertools import product
import copy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
SKIN = Path('addons/skin.bobbi.cinema/1080p')
SPEC = Path('ui/rails/home_rails.json')
OUTPUT = SKIN / 'Includes_HomeRails.generated.xml'
HERO_OUTPUT = SKIN / 'Includes_HomeHero.generated.xml'
TITLES = ('TitlePrimary', 'TitleSecondary', 'SeasonLabel', 'EpisodeLabel',
          'EpisodeTitle', 'EpisodeTitleSep')
FIELDS = {'key', 'control_id', 'title', 'layout', 'route', 'params', 'limit', 'preloaditems'}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate RailSpec field: ' + key)
        result[key] = value
    return result


def load_spec(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_object))


def route_path(rail):
    """Closed route registry. No URL, builtin or template can be provided by data."""
    route, params = rail['route'], rail['params']
    if type(params) is not dict:
        raise ValueError('Rail params must be an object')
    if route == 'continue_watching' and not params:
        query = [('action', 'continue_watching_menu')]
    elif route == 'personal_catalog' and params == {'mode': 'rail'}:
        query = [('action', 'personal_catalog'), ('mode', 'rail')]
    elif (route == 'emby_rail' and set(params) == {'section'}
          and params['section'] in ('resume', 'recent')):
        query = [('action', 'emby_rail'), ('section', params['section'])]
    elif (route == 'catalog' and set(params) == {'section', 'page'}
          and params['section'] in ('tv', 'movie')
          and type(params['page']) is int and params['page'] == 1):
        query = [('action', 'am6b_streaming_catalog'), ('section', params['section']), ('page', 1)]
    elif (route == 'anime_catalog' and set(params) == {'category'}
          and params['category'] in ('current_quarter', 'movies_new')):
        series = params['category'] == 'current_quarter'
        query = [('action', 'search_item'), ('api', 'tmdb'), ('mode', 'anime'),
                 ('submode', 'tv' if series else 'movies'),
                 ('category', 'Anime_Current_Quarter' if series else 'Anime_Movies_New')]
    else:
        raise ValueError('Unknown rail route or invalid typed parameters')
    return 'plugin://plugin.video.bobbi/?' + urlencode(query)


def validate(spec):
    if (type(spec) is not dict
            or not ({'schema', 'rails'} <= set(spec) <= {'schema', 'rails', 'slot_preferences'})
            or type(spec['schema']) is not int or spec['schema'] != 1
            or ('slot_preferences' in spec and type(spec['slot_preferences']) is not bool)):
        raise ValueError('Unsupported RailSpec schema')
    rails = spec['rails']
    if type(rails) is not list or not 1 <= len(rails) <= 12:
        raise ValueError('Expected 1 to 12 home rails')
    keys, ids = set(), set()
    for rail in rails:
        if type(rail) is not dict or set(rail) != FIELDS:
            raise ValueError('Unexpected RailSpec fields')
        key, control_id, title = rail['key'], rail['control_id'], rail['title']
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', key) or key in keys:
            raise ValueError('Invalid or duplicate rail key')
        if type(control_id) is not int or not 9800 <= control_id <= 9899 or control_id in ids:
            raise ValueError('Invalid or duplicate rail control_id')
        if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 80
                or re.search(r'[\x00-\x1f\x7f$\[\]{}()<>]|(?:https?|plugin|special)://|RunScript|RunPlugin|PlayMedia|ActivateWindow', title, re.I)):
            raise ValueError('Rail title must be plain display text')
        if rail['layout'] not in ('wide', 'poster'):
            raise ValueError('Unknown rail layout')
        if type(rail['limit']) is not int or rail['limit'] != 20:
            raise ValueError('Unreviewed rail content limit')
        if type(rail['preloaditems']) is not int or rail['preloaditems'] != 2:
            raise ValueError('Unreviewed rail preload budget')
        route_path(rail)
        keys.add(key)
        ids.add(control_id)
    return spec


def _has(control_id):
    return f'Integer.IsGreater(Container({control_id}).NumItems,0)'


def _remembered(control_id):
    return f'String.IsEqual(Window(Home).Property(BobbiRail),{control_id})'


def _focus(control_id):
    return f'Control.HasFocus({control_id})'


def _any_focus(ids):
    terms = [_focus(control_id) for control_id in ids]
    return terms[0] if len(terms) == 1 else '[' + ' | '.join(terms) + ']'


def _value(variable, text, condition=None):
    node = ET.SubElement(variable, 'value', {} if condition is None else {'condition': condition})
    node.text = str(text)


def _is_resume_rail(rail):
    return rail['route'] == 'continue_watching' or (
        rail['route'] == 'emby_rail' and rail['params'].get('section') == 'resume'
    )


def _slot_at_ref(slot, rail, default_rail):
    if rail['key'] == default_rail['key']:
        return f'$EXP[BobbiSlotDefault_{slot}]'
    return f"String.IsEqual(Skin.String(BobbiRailSlot{slot}),{rail['key']})"


def render(spec, title_source):
    """Pure deterministic compiler; title fallback rules have one handwritten owner."""
    validated = validate(spec)
    rails = validated['rails']
    slot_mode = bool(validated.get('slot_preferences'))
    ids = [rail['control_id'] for rail in rails]
    root = ET.Element('includes')
    root.append(ET.Comment(' Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json. '))
    rows = ET.SubElement(root, 'include', {'name': 'HomeRails'})
    for rail in rails:
        item = ET.SubElement(rows, 'include', {'content': 'HomeRailWide' if rail['layout'] == 'wide' else 'HomeRail'})
        for key, value in [('id', rail['control_id']), ('key', rail['key']), ('title', rail['title']),
                           ('content', route_path(rail)), ('limit', rail['limit']), ('preloaditems', rail['preloaditems'])]:
            ET.SubElement(item, 'param', {'name': key, 'value': str(value)})

    if not slot_mode:
        ET.SubElement(root, 'expression', {'name': 'BobbiHomeHasItems'}).text = ' | '.join(_has(i) for i in ids)
        ET.SubElement(root, 'expression', {'name': 'BobbiHomeUpdating'}).text = ' | '.join(f'Container({i}).IsUpdating' for i in ids)
        focus = ET.SubElement(root, 'variable', {'name': 'HomeContentFocus'})
        for i in ids:
            _value(focus, i, _remembered(i) + ' + ' + _has(i))
        for i in ids:
            _value(focus, i, _has(i))
        _value(focus, 9701, '$EXP[BobbiHomeUpdating]')
        _value(focus, 9870)
        up = ET.SubElement(root, 'variable', {'name': 'HomeRailUp'})
        for index in range(len(ids) - 2, -1, -1):
            _value(up, ids[index], _any_focus(ids[index + 1:]) + ' + ' + _has(ids[index]))
        _value(up, 9701)
        down = ET.SubElement(root, 'variable', {'name': 'HomeRailDown'})
        for index in range(1, len(ids)):
            _value(down, ids[index], _any_focus(ids[:index]) + ' + ' + _has(ids[index]))
        for i in ids:
            _value(down, i, _focus(i))
        _value(down, 9701)
        next_title = ET.SubElement(root, 'variable', {'name': 'NextRailTitle'})
        for index, i in enumerate(ids):
            for following in rails[index + 1:]:
                _value(next_title, following['title'], _focus(i) + ' + ' + _has(following['control_id']))
        for name in ('StageArt', 'StageMeta', 'StagePlot'):
            variable = ET.SubElement(root, 'variable', {'name': name})
            for remembered in (True, False):
                for i in ids:
                    condition = (_remembered(i) + ' + ' if remembered else '') + _has(i)
                    item = f'Container({i}).ListItem'
                    if name == 'StageArt':
                        for field in ('fanart', 'tvshow.fanart'):
                            _value(variable, f'$INFO[{item}.Art({field})]', condition + f' + !String.IsEmpty({item}.Art({field}))')
                        _value(variable, f'$INFO[{item}.Art(thumb)]', condition)
                    elif name == 'StageMeta':
                        _value(variable, f'$INFO[{item}.Year]$INFO[{item}.Genre,   ·   ]$INFO[{item}.Rating,   ·   ★ ]', condition)
                    else:
                        _value(variable, f'$INFO[{item}.Plot]', condition)
        progress = ET.SubElement(root, 'variable', {'name': 'StageProgress'})
        for rail in rails:
            if _is_resume_rail(rail):
                i = rail['control_id']
                for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                    _value(progress, f'已看 $INFO[Container({i}).ListItem.{field}]%',
                           _remembered(i) + f' + Integer.IsGreater(Container({i}).ListItem.{field},0)')
        for i in ids:
            for name in TITLES:
                source = title_source.find(f"variable[@name='{name}']")
                if source is None:
                    raise ValueError('Missing handwritten title fallback: ' + name)
                variable = copy.deepcopy(source)
                variable.set('name', f'{name}_{i}')
                for node in variable.iter():
                    node.attrib = {key: value.replace('ListItem.', f'Container({i}).ListItem.') for key, value in node.attrib.items()}
                    if node.text:
                        node.text = node.text.replace('ListItem.', f'Container({i}).ListItem.')
                root.append(variable)
        for name in TITLES[:-1]:
            variable = ET.SubElement(root, 'variable', {'name': 'Stage' + name})
            for remembered in (True, False):
                for i in ids:
                    condition = (_remembered(i) + ' + ' if remembered else '') + _has(i)
                    _value(variable, f'$VAR[{name}_{i}]', condition)
        ET.indent(root, space='  ')
        return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='utf-8') + b'\n'

    n_slots = len(rails)
    ET.SubElement(root, 'expression', {'name': 'BobbiHomeAnyRailHidden'}).text = ' | '.join(
        f"Skin.HasSetting(BobbiHideRail_{r['key']})" for r in rails
    )
    ET.SubElement(root, 'expression', {'name': 'BobbiHomeHasItems'}).text = ' | '.join(
        f"[!Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}]" for r in rails
    )
    ET.SubElement(root, 'expression', {'name': 'BobbiHomeUpdating'}).text = ' | '.join(
        f"[!Skin.HasSetting(BobbiHideRail_{r['key']}) + Container({r['control_id']}).IsUpdating]" for r in rails
    )
    for slot in range(1, n_slots + 1):
        default_r = rails[slot - 1]
        others = [
            f"String.IsEqual(Skin.String(BobbiRailSlot{slot}),{o['key']})"
            for o in rails if o['key'] != default_r['key']
        ]
        ET.SubElement(root, 'expression', {'name': f'BobbiSlotDefault_{slot}'}).text = (
            '![' + ' | '.join(others) + ']' if others else 'true'
        )
        for r in rails:
            at_ref = _slot_at_ref(slot, r, default_r)
            ET.SubElement(root, 'expression', {'name': f"BobbiSlot_{slot}_{r['key']}"}).text = (
                f"{at_ref} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}"
            )
        ET.SubElement(root, 'expression', {'name': f'BobbiSlot{slot}Focused'}).text = ' | '.join(
            f"[{_focus(r['control_id'])} + {_slot_at_ref(slot, r, default_r)}]" for r in rails
        )

    focus = ET.SubElement(root, 'variable', {'name': 'HomeContentFocus'})
    for r in rails:
        _value(focus, r['control_id'], f"{_remembered(r['control_id'])} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}")
    for slot in range(1, n_slots + 1):
        for r in rails:
            _value(focus, r['control_id'], f"$EXP[BobbiSlot_{slot}_{r['key']}]")
    _value(focus, 9701, '$EXP[BobbiHomeUpdating]')
    _value(focus, 9870)

    up = ET.SubElement(root, 'variable', {'name': 'HomeRailUp'})
    for target_slot in range(n_slots - 1, 0, -1):
        below_terms = [f'$EXP[BobbiSlot{s}Focused]' for s in range(target_slot + 1, n_slots + 1)]
        below = below_terms[0] if len(below_terms) == 1 else '[' + ' | '.join(below_terms) + ']'
        for r in rails:
            _value(up, r['control_id'], f"{below} + $EXP[BobbiSlot_{target_slot}_{r['key']}]")
    _value(up, 9701)

    down = ET.SubElement(root, 'variable', {'name': 'HomeRailDown'})
    for target_slot in range(2, n_slots + 1):
        above_terms = [f'$EXP[BobbiSlot{s}Focused]' for s in range(1, target_slot)]
        above = above_terms[0] if len(above_terms) == 1 else '[' + ' | '.join(above_terms) + ']'
        for r in rails:
            _value(down, r['control_id'], f"{above} + $EXP[BobbiSlot_{target_slot}_{r['key']}]")
    for r in rails:
        _value(down, r['control_id'], _focus(r['control_id']))
    _value(down, 9701)

    next_title = ET.SubElement(root, 'variable', {'name': 'NextRailTitle'})
    for cur_slot in range(1, n_slots):
        for after_slot in range(cur_slot + 1, n_slots + 1):
            for r in rails:
                _value(next_title, r['title'], f"$EXP[BobbiSlot{cur_slot}Focused] + $EXP[BobbiSlot_{after_slot}_{r['key']}]")

    def _stage_targets(remembered):
        if remembered:
            return [(r['control_id'], f"{_remembered(r['control_id'])} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}") for r in rails]
        return [(r['control_id'], f"$EXP[BobbiSlot_{slot}_{r['key']}]") for slot in range(1, n_slots + 1) for r in rails]

    for name in ('StageArt', 'StageMeta', 'StagePlot'):
        variable = ET.SubElement(root, 'variable', {'name': name})
        for remembered in (True, False):
            for i, condition in _stage_targets(remembered):
                item = f'Container({i}).ListItem'
                if name == 'StageArt':
                    for field in ('fanart', 'tvshow.fanart'):
                        _value(variable, f'$INFO[{item}.Art({field})]', condition + f' + !String.IsEmpty({item}.Art({field}))')
                    _value(variable, f'$INFO[{item}.Art(thumb)]', condition)
                elif name == 'StageMeta':
                    _value(variable, f'$INFO[{item}.Year]$INFO[{item}.Genre,   ·   ]$INFO[{item}.Rating,   ·   ★ ]', condition)
                else:
                    _value(variable, f'$INFO[{item}.Plot]', condition)

    progress = ET.SubElement(root, 'variable', {'name': 'StageProgress'})
    for rail in rails:
        if _is_resume_rail(rail):
            i = rail['control_id']
            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                _value(progress, f'已看 $INFO[Container({i}).ListItem.{field}]%',
                       f"{_remembered(i)} + !Skin.HasSetting(BobbiHideRail_{rail['key']}) + Integer.IsGreater(Container({i}).ListItem.{field},0)")

    for i in ids:
        for name in TITLES:
            source = title_source.find(f"variable[@name='{name}']")
            if source is None:
                raise ValueError('Missing handwritten title fallback: ' + name)
            variable = copy.deepcopy(source)
            variable.set('name', f'{name}_{i}')
            for node in variable.iter():
                node.attrib = {key: value.replace('ListItem.', f'Container({i}).ListItem.') for key, value in node.attrib.items()}
                if node.text:
                    node.text = node.text.replace('ListItem.', f'Container({i}).ListItem.')
            root.append(variable)

    for name in TITLES[:-1]:
        variable = ET.SubElement(root, 'variable', {'name': 'Stage' + name})
        for remembered in (True, False):
            for i, condition in _stage_targets(remembered):
                _value(variable, f'$VAR[{name}_{i}]', condition)

    ET.indent(root, space='  ')
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='utf-8') + b'\n'


def _current(control_id):
    """The rail occupying the visible slot (label 9791 = $VAR[HomeContentFocus])."""
    return f'String.IsEqual(Control.GetLabel(9791),{control_id})'


def _no_art(control_id):
    item = f'Container({control_id}).ListItem'
    return ' + '.join(f'String.IsEmpty({item}.Art({field}))'
                      for field in ('fanart', 'tvshow.fanart', 'poster', 'landscape'))


def _page_control(root, rails):
    """Compile geometry for the real content limit; no runtime script or timer."""
    for name, field in [('BobbiPageItem', 'CurrentItem'), ('BobbiPageCount', 'NumItems')]:
        var = ET.SubElement(root, 'variable', name=name)
        for rail in rails:
            i = rail['control_id']
            _value(var, f'$INFO[Container({i}).{field}]', _current(i))
        _value(var, 0)

    geometry = ET.SubElement(root, 'include', name='HomePageGeometry')
    window = ET.SubElement(root, 'include', name='HomePageWindow')
    dots = ET.SubElement(root, 'include', name='HomePageDots')
    travel = ET.SubElement(root, 'include', name='HomePageTravel')
    def use(parent, template, **values):
        node = ET.SubElement(parent, 'include', content=template)
        for key, value in values.items():
            ET.SubElement(node, 'param', name=key, value=str(value))

    max_items = max(rail['limit'] for rail in rails)
    max_slots = min(8, max_items)
    for count in range(2, max_items + 1):
        vis_slots = min(count, max_slots)
        inner_w = 30 + (vis_slots - 1) * 21
        pill_w = inner_w + 29
        # Recenter only when changing shelf length (206px @ x=857..1063 for >=8 items).
        ET.SubElement(geometry, 'animation', effect='slide', start='0,0', end=f'{-(inner_w // 2)},0',
                      time='0', condition=f'Integer.IsEqual(Control.GetLabel(9795),{count})').text = 'Conditional'
        use(geometry, 'HomePageTrack', count=count, width=pill_w)

    # Sliding window W = clamp(k - 6, 0, max(0, N - 8)): shifts conveyor -21px per step
    # while holding slot 5 on middle items, then clamps so k=N-1 and k=N glide onto slots 6 & 7.
    for w in range(1, max(1, max_items - max_slots + 1)):
        use(window, 'HomePageStep',
            when=f'Integer.IsGreater(Control.GetLabel(9794),{5 + w}) + Integer.IsGreater(Control.GetLabel(9795),{7 + w})',
            dx=-21)

    for m in range(1, max_items):
        vis = (f'Integer.IsGreater(Control.GetLabel(9795),{m}) + '
               f'[!Integer.IsGreater(Control.GetLabel(9794),{m + 5}) | !Integer.IsGreater(Control.GetLabel(9795),{m + 7})]')
        if m >= max_slots:
            vis += f' + Integer.IsGreater(Control.GetLabel(9794),{m - 2})'
        part = f'!Integer.IsGreater(Control.GetLabel(9794),{m})'
        left_ov = (f'[Integer.IsEqual(Control.GetLabel(9794),{m + 5}) + Integer.IsGreater(Control.GetLabel(9795),{m + 7})] | '
                   f'[Integer.IsEqual(Control.GetLabel(9795),{m + 7}) + Integer.IsGreater(Control.GetLabel(9794),{m + 4})]') if m >= 2 else None
        if m == 7:
            right_ov = '!Integer.IsGreater(Control.GetLabel(9794),6) + Integer.IsGreater(Control.GetLabel(9795),8)'
        elif m >= 8:
            right_ov = f'Integer.IsEqual(Control.GetLabel(9794),{m - 1}) + Integer.IsGreater(Control.GetLabel(9795),{m + 1})'
        else:
            right_ov = None
        if left_ov and right_ov:
            taper = f'[{left_ov}] | [{right_ov}]'
        else:
            taper = left_ov or right_ov or 'false'
        use(dots, 'HomePageDot', index=m, left=(m - 1) * 21, visible=vis, part=part, taper=taper)

    for after in range(1, max_items):
        use(travel, 'HomePageStep', when=f'Integer.IsGreater(Control.GetLabel(9794),{after})', dx=21)


def render_hero(spec):
    """native glass stage selectors kept apart from the frozen rail selector set.

    HomeNextRail  the next populated rail under the visible one (1.5-rail peek)
    HeroArt       sticky full-bleed art: the visible card's art, else the
                  selected card of the nearest rail that has art (never an icon)
    HeroLogo      ClearLogo of the visible card
    HeroCaption   art-less cards (library sources, raw files) read as a quiet caption
    """
    validated = validate(spec)
    rails = validated['rails']
    slot_mode = bool(validated.get('slot_preferences'))
    ids = [rail['control_id'] for rail in rails]
    root = ET.Element('includes')
    root.append(ET.Comment(' Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json. '))

    if slot_mode:
        n_slots = len(rails)
        for slot in range(1, n_slots + 1):
            default_r = rails[slot - 1]
            ET.SubElement(root, 'expression', {'name': f'BobbiSlot{slot}Current'}).text = ' | '.join(
                f"[{_current(r['control_id'])} + {_slot_at_ref(slot, r, default_r)}]" for r in rails
            )
        following = ET.SubElement(root, 'variable', {'name': 'HomeNextRail'})
        for cur_slot in range(1, n_slots):
            for after_slot in range(cur_slot + 1, n_slots + 1):
                for r in rails:
                    _value(following, r['control_id'], f"$EXP[BobbiSlot{cur_slot}Current] + $EXP[BobbiSlot_{after_slot}_{r['key']}]")
        hero_targets = lambda current: (
            [(r, f"{_current(r['control_id'])} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}") for r in rails]
            if current
            else [(r, f"$EXP[BobbiSlot_{slot}_{r['key']}]") for slot in range(1, n_slots + 1) for r in rails]
        )
    else:
        following = ET.SubElement(root, 'variable', {'name': 'HomeNextRail'})
        for index, i in enumerate(ids):
            for after in ids[index + 1:]:
                _value(following, after, _current(i) + ' + ' + _has(after))
        hero_targets = lambda current: [
            (r, (_current(r['control_id']) + ' + ' if current else '') + _has(r['control_id']))
            for r in rails
        ]

    art = ET.SubElement(root, 'variable', {'name': 'HeroArt'})
    for current in (True, False):
        for rail, condition in hero_targets(current):
            i = rail['control_id']
            item = f'Container({i}).ListItem'
            for field in ('fanart', 'tvshow.fanart'):
                _value(art, f'$INFO[{item}.Art({field})]', condition + f' + !String.IsEmpty({item}.Art({field}))')
            if rail['layout'] == 'wide' and _is_resume_rail(rail):
                _value(art, f'$INFO[{item}.Art(thumb)]', condition + f' + !String.IsEmpty({item}.Art(thumb))')
    # still nothing (raw files, library sources): the first cards that do carry art
    for position in range(8):
        for rail, base_cond in hero_targets(False):
            i = rail['control_id']
            item = f'Container({i}).ListItemAbsolute({position})'
            _value(art, f'$INFO[{item}.Art(fanart)]', base_cond + f' + !String.IsEmpty({item}.Art(fanart))')
    logo = ET.SubElement(root, 'variable', {'name': 'HeroLogo'})
    has_logo = []
    for i in ids:
        item = f'Container({i}).ListItem'
        for field in ('clearlogo', 'tvshow.clearlogo'):
            condition = _current(i) + f' + !String.IsEmpty({item}.Art({field}))'
            _value(logo, f'$INFO[{item}.Art({field})]', condition)
            has_logo.append('[' + condition + ']')
    ET.SubElement(root, 'expression', {'name': 'BobbiHeroHasLogo'}).text = ' | '.join(has_logo)
    caption = ET.SubElement(root, 'variable', {'name': 'HeroCaption'})
    hint = ET.SubElement(root, 'variable', {'name': 'HeroCaptionHint'})
    quiet = []
    for rail in rails:
        i = rail['control_id']
        condition = _current(i) + ' + ' + _has(i) + ' + ' + _no_art(i)
        _value(caption, f'{rail["title"]}  ·  $INFO[Container({i}).ListItem.Label]', condition)
        if rail['route'] == 'personal_catalog':
            _value(hint, '按确定打开  ·  网盘与 NAS 在「我的」里添加或管理', condition)
        elif _is_resume_rail(rail):
            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                _value(hint, f'按确定继续播放  ·  已看 $INFO[Container({i}).ListItem.{field}]%',
                       condition + f' + Integer.IsGreater(Container({i}).ListItem.{field},0)')
            _value(hint, '按确定继续播放', condition)
        else:
            _value(hint, '按确定查看', condition)
        quiet.append('[' + condition + ']')
    ET.SubElement(root, 'expression', {'name': 'BobbiHeroQuiet'}).text = ' | '.join(quiet)

    # glass (on-device) Hero metadata line, [TV-MA]-style outlined badge, Play label & page-indicator dots
    meta_line = ET.SubElement(root, 'variable', {'name': 'HeroMetaLine'})
    badge_lbl = ET.SubElement(root, 'variable', {'name': 'HeroBadgeLabel'})
    play_lbl = ET.SubElement(root, 'variable', {'name': 'HeroPlayLabel'})
    for current in (True, False):
        for rail, cond in hero_targets(current):
            i = rail['control_id']
            item = f'Container({i}).ListItem'
            _value(meta_line,
                   f'剧集 · 第$INFO[{item}.Season]季第$INFO[{item}.Episode]集$INFO[{item}.Genre, · ]',
                   cond + f' + !String.IsEmpty({item}.Season) + !String.IsEmpty({item}.Episode)')
            _value(meta_line,
                   f'剧集$INFO[{item}.Year, · ]$INFO[{item}.Genre, · ]',
                   cond + f' + [String.IsEqual({item}.DBType,tvshow) | !String.IsEmpty({item}.Season)]')
            _value(meta_line,
                   f'电影$INFO[{item}.Year, · ]$INFO[{item}.Genre, · ]',
                   cond + f' + [!String.IsEmpty({item}.Year) | !String.IsEmpty({item}.Genre)]')
            _value(meta_line, f'{rail["title"]} · $INFO[{item}.Label]', cond)

            _value(badge_lbl, f'★ $INFO[{item}.Rating]', cond + f' + !String.IsEmpty({item}.Rating)')
            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                _value(badge_lbl, f'已看 $INFO[{item}.{field}]%',
                       cond + f' + Integer.IsGreater({item}.{field},0)')

            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                _value(play_lbl, '继续', cond + f' + Integer.IsGreater({item}.{field},0)')
            if rail['route'] == 'personal_catalog':
                _value(play_lbl, '打开', cond + f' + {item}.IsFolder')
            _value(play_lbl, '播放', cond)

    _page_control(root, rails)

    ET.indent(root, space='  ')
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='utf-8') + b'\n'


def _include_settings(definitions, tree):
    pattern = re.compile(r'^(!?)Skin\.HasSetting\((\w+)\)$')
    found = set()
    for node in [*definitions.values(), tree]:
        for include in node.iter('include'):
            match = pattern.match((include.get('condition') or '').strip())
            if match:
                found.add(match[2])
    return sorted(found)


def expanded_home(root, generated, hero=None):
    """Expand the actual Home include closure, with Kodi include parameters.

    Other windows may reuse IDs. Only controls instantiated under Home count.
    Control visibility conditions are retained, not evaluated, so mutually
    hidden controls still cannot acquire duplicate IDs when data changes at
    runtime.  Include conditions are different: Kodi resolves them once when
    the window loads, so every Skin.HasSetting() combination they use is
    expanded and checked as its own window.
    """
    skin, definitions, loaded = Path(root) / SKIN, {}, set()

    def load(path):
        if path in loaded:
            return
        loaded.add(path)
        if path.name == OUTPUT.name:
            tree = ET.fromstring(generated)
        elif path.name == HERO_OUTPUT.name and hero is not None:
            tree = ET.fromstring(hero)
        else:
            tree = ET.parse(path).getroot()
        for node in tree:
            if node.tag == 'include' and node.get('file'):
                child = (path.parent / node.get('file')).resolve()
                if not child.is_relative_to(skin.resolve()):
                    raise ValueError('Include escapes skin directory')
                load(child)
            elif node.tag == 'include' and node.get('name'):
                definitions[node.get('name')] = node

    load(skin / 'Includes.xml')
    home = ET.parse(skin / 'Home.xml').getroot()

    def substitute(value, params):
        return re.sub(r'\$PARAM\[([^]]+)\]', lambda m: params.get(m[1], m[0]), value)

    def expand(node, params, stack, config):
        node = copy.deepcopy(node)
        node.attrib = {key: substitute(value, params) for key, value in node.attrib.items()}
        if node.text:
            node.text = substitute(node.text, params)
        if node.tag == 'include' and not node.get('file'):
            condition = re.match(r'^(!?)Skin\.HasSetting\((\w+)\)$', (node.get('condition') or '').strip())
            if condition and (condition[1] == '!') == config.get(condition[2], False):
                return []
            name = node.get('content') or (node.text or '').strip()
            if name not in definitions or name in stack:
                raise ValueError('Unresolved/cyclic Home include: ' + name)
            definition = definitions[name]
            arguments = {p.get('name'): substitute(p.get('default', p.text or ''), params)
                         for p in definition.findall('param')}
            arguments.update({p.get('name'): substitute(p.get('value', p.text or ''), params)
                              for p in node.findall('param')})
            body = definition.find('definition')
            if body is None:
                body = definition
            return [result for child in body if child.tag != 'param'
                    for result in expand(child, arguments, stack + (name,), config)]
        children = [result for child in node for result in expand(child, params, stack, config)]
        node[:] = children
        return [node]

    settings = _include_settings(definitions, home)
    configs = [dict(zip(settings, bits)) for bits in product((False, True), repeat=len(settings))]
    expanded_default = None
    for config in configs:
        expanded = expand(home, {}, (), config)[0]
        ids = [node.get('id') for node in expanded.iter('control') if node.get('id')]
        if any(not value.isdecimal() for value in ids):
            raise ValueError('Unresolved Home control ID')
        duplicates = [value for value, count in Counter(ids).items() if count > 1]
        if duplicates:
            raise ValueError('Duplicate expanded Home control ID: ' + ', '.join(duplicates))
        for name in ('HomeContentFocus', 'HomeRailUp', 'HomeRailDown'):
            variable = ET.fromstring(generated).find(f"variable[@name='{name}']")
            if any(value.text not in ids for value in variable):
                raise ValueError('Missing Home focus target: ' + name)
        if expanded_default is None:
            expanded_default = expanded
    return expanded_default


def outputs(root=ROOT):
    root = Path(root)
    spec = load_spec(root / SPEC)
    raw = render(spec, ET.parse(root / SKIN / 'Includes_Titles.xml').getroot())
    hero = render_hero(spec)
    expanded_home(root, raw, hero)
    return raw, hero


def expected(root=ROOT):
    return outputs(root)[0]


def check_generated(root=ROOT):
    root = Path(root)
    raw, hero = outputs(root)
    path = root / OUTPUT
    if not path.is_file() or path.read_bytes() != raw:
        raise ValueError('Home rail XML is stale; run tools/generate_home_rails.py explicitly')
    hero_path = root / HERO_OUTPUT
    if not hero_path.is_file() or hero_path.read_bytes() != hero:
        raise ValueError('Home hero XML is stale; run tools/generate_home_rails.py explicitly')
    inputs = (SPEC, Path('tools/generate_home_rails.py'), SKIN / 'Includes_Titles.xml')
    return {'schema': 1, 'inputs': {path.as_posix(): hashlib.sha256((root / path).read_bytes()).hexdigest()
                                  for path in inputs},
            'output': OUTPUT.as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'hero_output': HERO_OUTPUT.as_posix(), 'hero_sha256': hashlib.sha256(hero).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only stale output and Home closure check')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check_generated(), ensure_ascii=False, sort_keys=True))
    else:
        raw, hero = outputs()
        for output, data in ((OUTPUT, raw), (HERO_OUTPUT, hero)):
            target = ROOT / output
            if target.is_symlink() or target.parent.resolve() != (ROOT / SKIN).resolve():
                raise ValueError('Unsafe generated output target')
            target.write_bytes(data)
            print('Generated ' + output.as_posix())


if __name__ == '__main__':
    main()

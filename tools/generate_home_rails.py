"""Compile reviewed, bounded home rail and space data to static Kodi 21 XML.

This is a build tool, never an addon service. The only write targets are OUTPUT,
HERO_OUTPUT, NAV_OUTPUT and META_OUTPUT; --check validates without repairing them.
Paths and actions come from closed compiler tables, never arbitrary JSON strings.
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
ICONS = Path('addons/skin.bobbi.cinema/media/bobbi/glass/icons')
SPEC = Path('ui/rails/home_rails.json')
OUTPUT = SKIN / 'Includes_HomeRails.generated.xml'
HERO_OUTPUT = SKIN / 'Includes_HomeHero.generated.xml'
NAV_OUTPUT = SKIN / 'Includes_HomeNav.generated.xml'
META_OUTPUT = Path('addons/script.module.bobbi.platform/lib/bobbi_platform/home_rails_meta.py')
TITLES = ('TitlePrimary', 'TitleSecondary', 'SeasonLabel', 'EpisodeLabel',
          'EpisodeTitle', 'EpisodeTitleSep')
RAIL_FIELDS_V1 = {'key', 'control_id', 'title', 'layout', 'route', 'params', 'limit', 'preloaditems'}
RAIL_FIELDS_V2 = RAIL_FIELDS_V1 | {'label_id', 'title_en'}
SPACE_FIELDS = {'key', 'label_id', 'title', 'title_en', 'icon', 'disc', 'fixed', 'default_visible', 'route', 'params'}
DISCS = {'none', 'focus', 'always'}
UNSAFE_TEXT_RE = re.compile(
    r'[\x00-\x1f\x7f$\[\]{}()<>]|(?:https?|plugin|special)://|RunScript|RunPlugin|PlayMedia|ActivateWindow',
    re.I,
)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate RailSpec field: ' + key)
        result[key] = value
    return result


def _plain_text(value, what):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80 or UNSAFE_TEXT_RE.search(value):
        raise ValueError(f'{what} must be plain display text')


def load_spec(path, *, root=ROOT):
    return validate(json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_object), root=root)


def route_path(rail):
    """Closed route registry for Home rails. No URL, builtin or template can be provided by data."""
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


def space_dispatch(space):
    """Closed route registry for top-level navigation spaces.

    Returns (kind, target, set_section) where kind is one of:
      - 'window': target is exact ActivateWindow(...) builtin
      - 'directory': target is exact plugin:// directory URL (mutually exclusive
                     Container.Update(...,replace) vs ActivateWindow(Videos,...,return))
      - 'plugin': target is exact RunPlugin(...) builtin
    """
    route, params = space['route'], space['params']
    if type(params) is not dict:
        raise ValueError('Space params must be an object')
    if route == 'window_home' and not params:
        return ('window', 'ActivateWindow(Home)', True)
    if route == 'window_personal' and not params:
        return ('window', 'ActivateWindow(1197)', True)
    if route == 'window_favourites' and not params:
        return ('window', 'ActivateWindow(favouritesbrowser)', True)
    if route == 'window_settings' and not params:
        return ('window', 'ActivateWindow(Settings)', True)
    if (route == 'search_prompt' and set(params) == {'section'}
            and params['section'] in ('multi', 'tv', 'movie', 'anime_tv', 'anime_movie')):
        url = 'plugin://plugin.video.bobbi/?' + urlencode([
            ('action', 'bobbi_search_prompt'), ('section', params['section'])
        ])
        return ('plugin', f'RunPlugin("{url}")', False)
    if (route == 'catalog' and set(params) == {'section', 'page'}
            and params['section'] in ('tv', 'movie')
            and type(params['page']) is int and params['page'] == 1):
        url = 'plugin://plugin.video.bobbi/?' + urlencode([
            ('action', 'am6b_streaming_catalog'), ('section', params['section']), ('page', 1)
        ])
        return ('directory', url, True)
    if (route == 'anime_catalog' and set(params) == {'category'}
            and params['category'] == 'current_quarter'):
        url = 'plugin://plugin.video.bobbi/?' + urlencode([
            ('action', 'search_item'), ('api', 'tmdb'), ('mode', 'anime'),
            ('submode', 'tv'), ('category', 'Anime_Current_Quarter')
        ])
        return ('directory', url, True)
    if route == 'continue_watching' and not params:
        url = 'plugin://plugin.video.bobbi/?' + urlencode([('action', 'continue_watching_menu')])
        return ('directory', url, True)
    if route == 'personal_catalog_root' and not params:
        url = 'plugin://plugin.video.bobbi/?' + urlencode([('action', 'personal_catalog')])
        return ('directory', url, True)
    if route == 'saved_views' and not params:
        url = 'plugin://plugin.video.bobbi/?' + urlencode([('action', 'personal_catalog'), ('mode', 'views')])
        return ('directory', url, True)
    if route == 'library_root' and not params:
        return ('directory', 'plugin://plugin.video.bobbi.library/', True)
    if route == 'media_servers' and not params:
        url = 'plugin://plugin.video.bobbi.library/?' + urlencode([('action', 'root'), ('kind', 'media_server')])
        return ('directory', url, True)
    raise ValueError('Unknown space route or invalid typed parameters')


def validate(spec, *, root=ROOT):
    if type(spec) is not dict or 'schema' not in spec or type(spec['schema']) is not int:
        raise ValueError('Unsupported RailSpec schema')
    schema = spec['schema']
    if schema == 1:
        if (not ({'schema', 'rails'} <= set(spec) <= {'schema', 'rails', 'slot_preferences'})
                or ('slot_preferences' in spec and type(spec['slot_preferences']) is not bool)):
            raise ValueError('Unsupported RailSpec schema 1 fields')
        rail_fields = RAIL_FIELDS_V1
    elif schema == 2:
        if (set(spec) != {'schema', 'rails', 'spaces', 'slot_preferences'}
                or spec['slot_preferences'] is not True):
            raise ValueError('Unsupported RailSpec schema 2 fields')
        rail_fields = RAIL_FIELDS_V2
    else:
        raise ValueError('Unsupported RailSpec schema')

    rails = spec['rails']
    if type(rails) is not list or not 1 <= len(rails) <= 12:
        raise ValueError('Expected 1 to 12 home rails')
    keys, ids, label_ids = set(), set(), set()
    for rail in rails:
        valid_rail_sets = (RAIL_FIELDS_V1,) if schema == 1 else (RAIL_FIELDS_V1, RAIL_FIELDS_V2)
        if type(rail) is not dict or set(rail) not in valid_rail_sets:
            raise ValueError('Unexpected RailSpec fields')
        key, control_id, title = rail['key'], rail['control_id'], rail['title']
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', key) or key in keys:
            raise ValueError('Invalid or duplicate rail key')
        if type(control_id) is not int or not 9800 <= control_id <= 9899 or control_id in ids:
            raise ValueError('Invalid or duplicate rail control_id')
        _plain_text(title, 'Rail title')
        if 'label_id' in rail:
            _plain_text(rail['title_en'], 'Rail English title')
            lid = rail['label_id']
            if type(lid) is not int or not 32000 <= lid <= 32999 or lid in label_ids:
                raise ValueError('Invalid or duplicate rail label_id')
            label_ids.add(lid)
        if rail['layout'] not in ('wide', 'poster'):
            raise ValueError('Unknown rail layout')
        if type(rail['limit']) is not int or rail['limit'] != 20:
            raise ValueError('Unreviewed rail content limit')
        if type(rail['preloaditems']) is not int or rail['preloaditems'] != 2:
            raise ValueError('Unreviewed rail preload budget')
        route_path(rail)
        keys.add(key)
        ids.add(control_id)

    if schema == 2:
        spaces = spec['spaces']
        if type(spaces) is not list or not 1 <= len(spaces) <= 16:
            raise ValueError('Expected 1 to 16 home spaces')
        space_keys = set()
        icon_dir = Path(root) / ICONS
        for idx, space in enumerate(spaces):
            if type(space) is not dict or set(space) != SPACE_FIELDS:
                raise ValueError('Unexpected SpaceSpec fields')
            skey = space['key']
            if not isinstance(skey, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', skey) or skey in space_keys:
                raise ValueError('Invalid or duplicate space key')
            _plain_text(space['title'], 'Space title')
            _plain_text(space['title_en'], 'Space English title')
            lid = space['label_id']
            if type(lid) is not int or not 32000 <= lid <= 32999 or lid in label_ids:
                raise ValueError('Invalid or duplicate space label_id')
            label_ids.add(lid)
            icon = space['icon']
            if not isinstance(icon, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}', icon):
                raise ValueError('Invalid space icon name')
            if icon_dir.is_dir() and not (icon_dir / f'{icon}.png').is_file():
                raise ValueError('Missing space icon asset: ' + icon)
            if space['disc'] not in DISCS:
                raise ValueError('Unknown space disc style')
            if type(space['fixed']) is not bool or type(space['default_visible']) is not bool:
                raise ValueError('Space booleans must be bool')
            if idx == 0:
                if skey != 'home' or not space['fixed'] or not space['default_visible']:
                    raise ValueError('Home must be fixed first and default visible')
            elif space['fixed'] or skey == 'home':
                raise ValueError('Only the leading home space may be fixed')
            space_dispatch(space)
            space_keys.add(skey)
    return spec


def _rail_label_expr(rail):
    return f"$LOCALIZE[{rail['label_id']}]" if 'label_id' in rail else rail['title']


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


def render(spec, title_source, *, root=ROOT):
    """Pure deterministic compiler; title fallback rules have one handwritten owner."""
    validated = validate(spec, root=root)
    localized = validated['schema'] >= 2
    rails = validated['rails']
    slot_mode = bool(validated.get('slot_preferences'))
    ids = [rail['control_id'] for rail in rails]
    doc = ET.Element('includes')
    doc.append(ET.Comment(' Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json. '))
    rows = ET.SubElement(doc, 'include', {'name': 'HomeRails'})
    for rail in rails:
        item = ET.SubElement(rows, 'include', {'content': 'HomeRailWide' if rail['layout'] == 'wide' else 'HomeRail'})
        for key, value in [('id', rail['control_id']), ('key', rail['key']), ('title', _rail_label_expr(rail)),
                           ('content', route_path(rail)), ('limit', rail['limit']), ('preloaditems', rail['preloaditems'])]:
            ET.SubElement(item, 'param', {'name': key, 'value': str(value)})

    if not slot_mode:
        ET.SubElement(doc, 'expression', {'name': 'BobbiHomeHasItems'}).text = ' | '.join(_has(i) for i in ids)
        ET.SubElement(doc, 'expression', {'name': 'BobbiHomeUpdating'}).text = ' | '.join(f'Container({i}).IsUpdating' for i in ids)
        focus = ET.SubElement(doc, 'variable', {'name': 'HomeContentFocus'})
        for i in ids:
            _value(focus, i, _remembered(i) + ' + ' + _has(i))
        for i in ids:
            _value(focus, i, _has(i))
        _value(focus, 9701, '$EXP[BobbiHomeUpdating]')
        _value(focus, 9870)
        up = ET.SubElement(doc, 'variable', {'name': 'HomeRailUp'})
        for index in range(len(ids) - 2, -1, -1):
            _value(up, ids[index], _any_focus(ids[index + 1:]) + ' + ' + _has(ids[index]))
        _value(up, 9701)
        down = ET.SubElement(doc, 'variable', {'name': 'HomeRailDown'})
        for index in range(1, len(ids)):
            _value(down, ids[index], _any_focus(ids[:index]) + ' + ' + _has(ids[index]))
        for i in ids:
            _value(down, i, _focus(i))
        _value(down, 9701)
        next_title = ET.SubElement(doc, 'variable', {'name': 'NextRailTitle'})
        for index, i in enumerate(ids):
            for following in rails[index + 1:]:
                _value(next_title, _rail_label_expr(following), _focus(i) + ' + ' + _has(following['control_id']))

        def _stage_targets(remembered):
            return [(i, (_remembered(i) + ' + ' if remembered else '') + _has(i)) for i in ids]

        def _progress_guard(rail):
            return _remembered(rail['control_id'])
    else:
        n_slots = len(rails)
        ET.SubElement(doc, 'expression', {'name': 'BobbiHomeAnyRailHidden'}).text = ' | '.join(
            f"Skin.HasSetting(BobbiHideRail_{r['key']})" for r in rails
        )
        ET.SubElement(doc, 'expression', {'name': 'BobbiHomeHasItems'}).text = ' | '.join(
            f"[!Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}]" for r in rails
        )
        ET.SubElement(doc, 'expression', {'name': 'BobbiHomeUpdating'}).text = ' | '.join(
            f"[!Skin.HasSetting(BobbiHideRail_{r['key']}) + Container({r['control_id']}).IsUpdating]" for r in rails
        )
        for slot in range(1, n_slots + 1):
            default_r = rails[slot - 1]
            others = [
                f"String.IsEqual(Skin.String(BobbiRailSlot{slot}),{o['key']})"
                for o in rails if o['key'] != default_r['key']
            ]
            ET.SubElement(doc, 'expression', {'name': f'BobbiSlotDefault_{slot}'}).text = (
                '![' + ' | '.join(others) + ']' if others else 'true'
            )
            for r in rails:
                at_ref = _slot_at_ref(slot, r, default_r)
                ET.SubElement(doc, 'expression', {'name': f"BobbiSlot_{slot}_{r['key']}"}).text = (
                    f"{at_ref} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}"
                )
            ET.SubElement(doc, 'expression', {'name': f'BobbiSlot{slot}Focused'}).text = ' | '.join(
                f"[{_focus(r['control_id'])} + {_slot_at_ref(slot, r, default_r)}]" for r in rails
            )

        focus = ET.SubElement(doc, 'variable', {'name': 'HomeContentFocus'})
        for r in rails:
            _value(focus, r['control_id'], f"{_remembered(r['control_id'])} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}")
        for slot in range(1, n_slots + 1):
            for r in rails:
                _value(focus, r['control_id'], f"$EXP[BobbiSlot_{slot}_{r['key']}]")
        _value(focus, 9701, '$EXP[BobbiHomeUpdating]')
        _value(focus, 9870)

        up = ET.SubElement(doc, 'variable', {'name': 'HomeRailUp'})
        for target_slot in range(n_slots - 1, 0, -1):
            below_terms = [f'$EXP[BobbiSlot{s}Focused]' for s in range(target_slot + 1, n_slots + 1)]
            below = below_terms[0] if len(below_terms) == 1 else '[' + ' | '.join(below_terms) + ']'
            for r in rails:
                _value(up, r['control_id'], f"{below} + $EXP[BobbiSlot_{target_slot}_{r['key']}]")
        _value(up, 9701)

        down = ET.SubElement(doc, 'variable', {'name': 'HomeRailDown'})
        for target_slot in range(2, n_slots + 1):
            above_terms = [f'$EXP[BobbiSlot{s}Focused]' for s in range(1, target_slot)]
            above = above_terms[0] if len(above_terms) == 1 else '[' + ' | '.join(above_terms) + ']'
            for r in rails:
                _value(down, r['control_id'], f"{above} + $EXP[BobbiSlot_{target_slot}_{r['key']}]")
        for r in rails:
            _value(down, r['control_id'], _focus(r['control_id']))
        _value(down, 9701)

        next_title = ET.SubElement(doc, 'variable', {'name': 'NextRailTitle'})
        for cur_slot in range(1, n_slots):
            for after_slot in range(cur_slot + 1, n_slots + 1):
                for r in rails:
                    _value(next_title, _rail_label_expr(r), f"$EXP[BobbiSlot{cur_slot}Focused] + $EXP[BobbiSlot_{after_slot}_{r['key']}]")

        def _stage_targets(remembered):
            if remembered:
                return [(r['control_id'], f"{_remembered(r['control_id'])} + !Skin.HasSetting(BobbiHideRail_{r['key']}) + {_has(r['control_id'])}") for r in rails]
            return [(r['control_id'], f"$EXP[BobbiSlot_{slot}_{r['key']}]") for slot in range(1, n_slots + 1) for r in rails]

        def _progress_guard(rail):
            return f"{_remembered(rail['control_id'])} + !Skin.HasSetting(BobbiHideRail_{rail['key']})"

    for name in ('StageArt', 'StageMeta', 'StagePlot'):
        variable = ET.SubElement(doc, 'variable', {'name': name})
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

    progress = ET.SubElement(doc, 'variable', {'name': 'StageProgress'})
    for rail in rails:
        if _is_resume_rail(rail):
            i = rail['control_id']
            guard = _progress_guard(rail)
            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                cond = f'{guard} + Integer.IsGreater(Container({i}).ListItem.{field},0)'
                if localized:
                    _value(progress, f'$INFO[Container({i}).ListItem.{field}]% $LOCALIZE[32048]',
                           f'String.IsEqual($LOCALIZE[32399],en) + {cond}')
                    _value(progress, f'$LOCALIZE[32048] $INFO[Container({i}).ListItem.{field}]%', cond)
                else:
                    _value(progress, f'已看 $INFO[Container({i}).ListItem.{field}]%', cond)

    for i in ids:
        for name in TITLES:
            source = title_source.find(f"variable[@name='{name}']")
            if source is None:
                raise ValueError('Missing handwritten title fallback: ' + name)
            variable = copy.deepcopy(source)
            variable.set('name', f'{name}_{i}')
            if not localized:
                for child in list(variable):
                    if (child.get('condition') or '').startswith('String.IsEqual($LOCALIZE[32399],en)'):
                        variable.remove(child)
                    elif child.text == '$LOCALIZE[32057]':
                        child.text = '特别篇'
            for node in variable.iter():
                node.attrib = {key: value.replace('ListItem.', f'Container({i}).ListItem.') for key, value in node.attrib.items()}
                if node.text:
                    node.text = node.text.replace('ListItem.', f'Container({i}).ListItem.')
            doc.append(variable)

    for name in TITLES[:-1]:
        variable = ET.SubElement(doc, 'variable', {'name': 'Stage' + name})
        for remembered in (True, False):
            for i, condition in _stage_targets(remembered):
                _value(variable, f'$VAR[{name}_{i}]', condition)

    ET.indent(doc, space='  ')
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(doc, encoding='utf-8') + b'\n'


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
        ET.SubElement(geometry, 'animation', effect='slide', start='0,0', end=f'{-(inner_w // 2)},0',
                      time='0', condition=f'Integer.IsEqual(Control.GetLabel(9795),{count})').text = 'Conditional'
        use(geometry, 'HomePageTrack', count=count, width=pill_w)

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


def render_hero(spec, *, root=ROOT):
    """Native glass stage selectors kept apart from the frozen rail selector set."""
    validated = validate(spec, root=root)
    localized = validated['schema'] >= 2
    rails = validated['rails']
    slot_mode = bool(validated.get('slot_preferences'))
    ids = [rail['control_id'] for rail in rails]
    doc = ET.Element('includes')
    doc.append(ET.Comment(' Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json. '))

    if slot_mode:
        n_slots = len(rails)
        for slot in range(1, n_slots + 1):
            default_r = rails[slot - 1]
            ET.SubElement(doc, 'expression', {'name': f'BobbiSlot{slot}Current'}).text = ' | '.join(
                f"[{_current(r['control_id'])} + {_slot_at_ref(slot, r, default_r)}]" for r in rails
            )
        following = ET.SubElement(doc, 'variable', {'name': 'HomeNextRail'})
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
        following = ET.SubElement(doc, 'variable', {'name': 'HomeNextRail'})
        for index, i in enumerate(ids):
            for after in ids[index + 1:]:
                _value(following, after, _current(i) + ' + ' + _has(after))
        hero_targets = lambda current: [
            (r, (_current(r['control_id']) + ' + ' if current else '') + _has(r['control_id']))
            for r in rails
        ]

    art = ET.SubElement(doc, 'variable', {'name': 'HeroArt'})
    for current in (True, False):
        for rail, condition in hero_targets(current):
            i = rail['control_id']
            item = f'Container({i}).ListItem'
            for field in ('fanart', 'tvshow.fanart'):
                _value(art, f'$INFO[{item}.Art({field})]', condition + f' + !String.IsEmpty({item}.Art({field}))')
            if rail['layout'] == 'wide' and _is_resume_rail(rail):
                _value(art, f'$INFO[{item}.Art(thumb)]', condition + f' + !String.IsEmpty({item}.Art(thumb))')
    for position in range(8):
        for rail, base_cond in hero_targets(False):
            i = rail['control_id']
            item = f'Container({i}).ListItemAbsolute({position})'
            _value(art, f'$INFO[{item}.Art(fanart)]', base_cond + f' + !String.IsEmpty({item}.Art(fanart))')
    logo = ET.SubElement(doc, 'variable', {'name': 'HeroLogo'})
    has_logo = []
    for i in ids:
        item = f'Container({i}).ListItem'
        for field in ('clearlogo', 'tvshow.clearlogo'):
            condition = _current(i) + f' + !String.IsEmpty({item}.Art({field}))'
            _value(logo, f'$INFO[{item}.Art({field})]', condition)
            has_logo.append('[' + condition + ']')
    ET.SubElement(doc, 'expression', {'name': 'BobbiHeroHasLogo'}).text = ' | '.join(has_logo)
    caption = ET.SubElement(doc, 'variable', {'name': 'HeroCaption'})
    hint = ET.SubElement(doc, 'variable', {'name': 'HeroCaptionHint'})
    quiet = []
    for rail in rails:
        i = rail['control_id']
        rtitle = _rail_label_expr(rail)
        condition = _current(i) + ' + ' + _has(i) + ' + ' + _no_art(i)
        _value(caption, f'{rtitle}  ·  $INFO[Container({i}).ListItem.Label]', condition)
        if rail['route'] == 'personal_catalog':
            _value(hint, '$LOCALIZE[32045]' if localized else '按确定打开  ·  网盘与 NAS 在「我的」里添加或管理', condition)
        elif _is_resume_rail(rail):
            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                p_cond = condition + f' + Integer.IsGreater(Container({i}).ListItem.{field},0)'
                if localized:
                    _value(hint, f'$LOCALIZE[32046]  ·  $INFO[Container({i}).ListItem.{field}]% $LOCALIZE[32048]',
                           f'String.IsEqual($LOCALIZE[32399],en) + {p_cond}')
                    _value(hint, f'$LOCALIZE[32046]  ·  $LOCALIZE[32048] $INFO[Container({i}).ListItem.{field}]%', p_cond)
                else:
                    _value(hint, f'按确定继续播放  ·  已看 $INFO[Container({i}).ListItem.{field}]%', p_cond)
            _value(hint, '$LOCALIZE[32046]' if localized else '按确定继续播放', condition)
        else:
            _value(hint, '$LOCALIZE[32047]' if localized else '按确定查看', condition)
        quiet.append('[' + condition + ']')
    ET.SubElement(doc, 'expression', {'name': 'BobbiHeroQuiet'}).text = ' | '.join(quiet)

    meta_line = ET.SubElement(doc, 'variable', {'name': 'HeroMetaLine'})
    badge_lbl = ET.SubElement(doc, 'variable', {'name': 'HeroBadgeLabel'})
    play_lbl = ET.SubElement(doc, 'variable', {'name': 'HeroPlayLabel'})
    for current in (True, False):
        for rail, cond in hero_targets(current):
            i = rail['control_id']
            rtitle = _rail_label_expr(rail)
            item = f'Container({i}).ListItem'
            ep_cond = cond + f' + !String.IsEmpty({item}.Season) + !String.IsEmpty({item}.Episode)'
            if localized:
                _value(meta_line,
                       f'$LOCALIZE[32052] · S$INFO[{item}.Season]E$INFO[{item}.Episode]$INFO[{item}.Genre, · ]',
                       f'String.IsEqual($LOCALIZE[32399],en) + {ep_cond}')
                _value(meta_line,
                       f'$LOCALIZE[32052] · 第$INFO[{item}.Season]季第$INFO[{item}.Episode]集$INFO[{item}.Genre, · ]',
                       ep_cond)
                _value(meta_line,
                       f'$LOCALIZE[32052]$INFO[{item}.Year, · ]$INFO[{item}.Genre, · ]',
                       cond + f' + [String.IsEqual({item}.DBType,tvshow) | !String.IsEmpty({item}.Season)]')
                _value(meta_line,
                       f'$LOCALIZE[32053]$INFO[{item}.Year, · ]$INFO[{item}.Genre, · ]',
                       cond + f' + [!String.IsEmpty({item}.Year) | !String.IsEmpty({item}.Genre)]')
            else:
                _value(meta_line,
                       f'剧集 · 第$INFO[{item}.Season]季第$INFO[{item}.Episode]集$INFO[{item}.Genre, · ]',
                       ep_cond)
                _value(meta_line,
                       f'剧集$INFO[{item}.Year, · ]$INFO[{item}.Genre, · ]',
                       cond + f' + [String.IsEqual({item}.DBType,tvshow) | !String.IsEmpty({item}.Season)]')
                _value(meta_line,
                       f'电影$INFO[{item}.Year, · ]$INFO[{item}.Genre, · ]',
                       cond + f' + [!String.IsEmpty({item}.Year) | !String.IsEmpty({item}.Genre)]')
            _value(meta_line, f'{rtitle} · $INFO[{item}.Label]', cond)

            _value(badge_lbl, f'★ $INFO[{item}.Rating]', cond + f' + !String.IsEmpty({item}.Rating)')
            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                p_cond = cond + f' + Integer.IsGreater({item}.{field},0)'
                if localized:
                    _value(badge_lbl, f'$INFO[{item}.{field}]% $LOCALIZE[32048]',
                           f'String.IsEqual($LOCALIZE[32399],en) + {p_cond}')
                    _value(badge_lbl, f'$LOCALIZE[32048] $INFO[{item}.{field}]%', p_cond)
                else:
                    _value(badge_lbl, f'已看 $INFO[{item}.{field}]%', p_cond)

            for field in ('Property(PercentPlayed)', 'PercentPlayed'):
                _value(play_lbl, '$LOCALIZE[32049]' if localized else '继续', cond + f' + Integer.IsGreater({item}.{field},0)')
            if rail['route'] == 'personal_catalog':
                _value(play_lbl, '$LOCALIZE[32050]' if localized else '打开', cond + f' + {item}.IsFolder')
            _value(play_lbl, '$LOCALIZE[32051]' if localized else '播放', cond)

    _page_control(doc, rails)

    ET.indent(doc, space='  ')
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(doc, encoding='utf-8') + b'\n'


def _append_space_item(content_node, space, visible_expr=None):
    kind, target, set_section = space_dispatch(space)
    item = ET.SubElement(content_node, 'item')
    ET.SubElement(item, 'label').text = f"$LOCALIZE[{space['label_id']}]"
    ET.SubElement(item, 'icon').text = f"bobbi/glass/icons/{space['icon']}.png"
    ET.SubElement(item, 'property', {'name': 'section'}).text = space['key'] if set_section else 'none'
    ET.SubElement(item, 'property', {'name': 'space_key'}).text = space['key']
    ET.SubElement(item, 'property', {'name': 'disc'}).text = space['disc']
    if visible_expr is not None:
        ET.SubElement(item, 'visible').text = visible_expr
    if set_section:
        ET.SubElement(item, 'onclick').text = f"SetProperty(BobbiSection,{space['key']},Home)"
    if kind in ('window', 'plugin'):
        ET.SubElement(item, 'onclick').text = target
    elif kind == 'directory':
        ET.SubElement(item, 'onclick', {'condition': 'Window.IsActive(videos)'}).text = f'Container.Update("{target}",replace)'
        ET.SubElement(item, 'onclick', {'condition': '!Window.IsActive(videos)'}).text = f'ActivateWindow(Videos,"{target}",return)'


def render_nav(spec, *, root=ROOT):
    """Compile deduplicated static space slot expressions and unified SideNav/TopNav <content>."""
    validated = validate(spec, root=root)
    doc = ET.Element('includes')
    doc.append(ET.Comment(' Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json. '))
    if validated['schema'] < 2:
        ET.indent(doc, space='  ')
        return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(doc, encoding='utf-8') + b'\n'

    spaces = validated['spaces']
    home_space = spaces[0]
    optional = spaces[1:]
    n_opt = len(optional)

    any_hidden_terms = []
    for sp in optional:
        key = sp['key']
        if sp['default_visible']:
            vis_expr = f'!Skin.HasSetting(BobbiHideSpace_{key})'
            any_hidden_terms.append(f'Skin.HasSetting(BobbiHideSpace_{key})')
        else:
            vis_expr = f'Skin.HasSetting(BobbiShowSpace_{key})'
        ET.SubElement(doc, 'expression', {'name': f'BobbiSpaceVis_{key}'}).text = vis_expr

    ET.SubElement(doc, 'expression', {'name': 'BobbiAnyDefaultSpaceHidden'}).text = (
        ' | '.join(any_hidden_terms) if any_hidden_terms else 'false'
    )

    for slot in range(1, n_opt + 1):
        default_sp = optional[slot - 1]
        others = [
            f"String.IsEqual(Skin.String(BobbiSpaceSlot{slot}),{o['key']})"
            for o in optional if o['key'] != default_sp['key']
        ]
        ET.SubElement(doc, 'expression', {'name': f'BobbiSpaceDefault_{slot}'}).text = (
            '![' + ' | '.join(others) + ']' if others else 'true'
        )
        for sp in optional:
            key = sp['key']
            raw_expr = (
                f'$EXP[BobbiSpaceDefault_{slot}]'
                if key == default_sp['key']
                else f'String.IsEqual(Skin.String(BobbiSpaceSlot{slot}),{key})'
            )
            ET.SubElement(doc, 'expression', {'name': f'BobbiSpaceRaw_{slot}_{key}'}).text = raw_expr

    for slot in range(1, n_opt + 1):
        for sp in optional:
            key = sp['key']
            if slot == 1:
                seen_expr = f'$EXP[BobbiSpaceRaw_1_{key}]'
                slot_expr = f'$EXP[BobbiSpaceVis_{key}] + $EXP[BobbiSpaceRaw_1_{key}]'
            else:
                seen_expr = f'$EXP[BobbiSpaceSeen_{slot - 1}_{key}] | $EXP[BobbiSpaceRaw_{slot}_{key}]'
                slot_expr = f'$EXP[BobbiSpaceVis_{key}] + $EXP[BobbiSpaceRaw_{slot}_{key}] + !$EXP[BobbiSpaceSeen_{slot - 1}_{key}]'
            ET.SubElement(doc, 'expression', {'name': f'BobbiSpaceSeen_{slot}_{key}'}).text = seen_expr
            ET.SubElement(doc, 'expression', {'name': f'BobbiSpaceSlot_{slot}_{key}'}).text = slot_expr

    for sp in optional:
        key = sp['key']
        ET.SubElement(doc, 'expression', {'name': f'BobbiSpaceFallback_{key}'}).text = (
            f'$EXP[BobbiSpaceVis_{key}] + !$EXP[BobbiSpaceSeen_{n_opt}_{key}]'
        )

    inc = ET.SubElement(doc, 'include', {'name': 'HomeSpaceItems'})
    content = ET.SubElement(inc, 'content')
    _append_space_item(content, home_space, visible_expr=None)
    for slot in range(1, n_opt + 1):
        for sp in optional:
            _append_space_item(content, sp, visible_expr=f"$EXP[BobbiSpaceSlot_{slot}_{sp['key']}]")
    for sp in optional:
        _append_space_item(content, sp, visible_expr=f"$EXP[BobbiSpaceFallback_{sp['key']}]")

    sec_lbl = ET.SubElement(doc, 'variable', {'name': 'BobbiSectionLabel'})
    sec_ico = ET.SubElement(doc, 'variable', {'name': 'BobbiSectionIcon'})
    for sp in optional:
        cond = f"String.IsEqual(Window(Home).Property(BobbiSection),{sp['key']})"
        _value(sec_lbl, f"$LOCALIZE[{sp['label_id']}]", cond)
        _value(sec_ico, f"bobbi/glass/icons/{sp['icon']}.png", cond)
    _value(sec_lbl, '$LOCALIZE[32165]', 'String.IsEqual(Window(Home).Property(BobbiSection),library)')
    _value(sec_ico, 'bobbi/glass/icons/stack.png', 'String.IsEqual(Window(Home).Property(BobbiSection),library)')
    _value(sec_lbl, f"$LOCALIZE[{home_space['label_id']}]")
    _value(sec_ico, f"bobbi/glass/icons/{home_space['icon']}.png")

    ET.indent(doc, space='  ')
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(doc, encoding='utf-8') + b'\n'


def _include_settings(definitions, tree):
    pattern = re.compile(r'^(!?)Skin\.HasSetting\((\w+)\)$')
    found = set()
    for node in [*definitions.values(), tree]:
        for include in node.iter('include'):
            match = pattern.match((include.get('condition') or '').strip())
            if match:
                found.add(match[2])
    return sorted(found)


def expanded_home(root, generated, hero=None, nav=None):
    """Expand the actual Home include closure, with Kodi include parameters."""
    skin, definitions, loaded = Path(root) / SKIN, {}, set()

    def load(path):
        if path in loaded:
            return
        loaded.add(path)
        if path.name == OUTPUT.name:
            tree = ET.fromstring(generated)
        elif path.name == HERO_OUTPUT.name and hero is not None:
            tree = ET.fromstring(hero)
        elif path.name == NAV_OUTPUT.name and nav is not None:
            tree = ET.fromstring(nav)
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


def render_python(spec, *, root=ROOT):
    """Compile pure constants-only Python projection from home_rails.json."""
    validated = validate(spec, root=root)
    lines = [
        '"""Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json."""',
        '',
        'HOME_RAIL_SPECS = (',
    ]
    for rail in validated['rails']:
        lines.append(
            f"    ({rail['key']!r}, {rail['control_id']}, {rail['title']!r}, {rail['layout']!r}),"
        )
    lines.extend([
        ')',
        'HOME_RAIL_I18N_SPECS = (',
    ])
    for rail in validated['rails']:
        title_en = rail.get('title_en', rail['title'])
        label_id = rail.get('label_id', 0)
        lines.append(
            f"    ({rail['key']!r}, {rail['title']!r}, {title_en!r}, {label_id}),"
        )
    lines.extend([
        ')',
        'HOME_RAILS = tuple((key, title) for key, _, title, _ in HOME_RAIL_SPECS)',
        'HOME_RAIL_KEYS = tuple(key for key, _, _, _ in HOME_RAIL_SPECS)',
        'HOME_RAIL_TITLES = {key: title for key, _, title, _ in HOME_RAIL_SPECS}',
        'HOME_RAIL_TITLES_EN = {key: title_en for key, _, title_en, _ in HOME_RAIL_I18N_SPECS}',
        'HOME_RAIL_LABEL_IDS = {key: label_id for key, _, _, label_id in HOME_RAIL_I18N_SPECS}',
        'HOME_RAIL_CONTROL_IDS = {key: control_id for key, control_id, _, _ in HOME_RAIL_SPECS}',
        '',
        'HOME_SPACE_SPECS = (',
    ])
    for space in validated.get('spaces', ()):
        kind, target, _ = space_dispatch(space)
        lines.append(
            f"    ({space['key']!r}, {space['label_id']}, {space['title']!r}, {space['title_en']!r}, "
            f"{space['icon']!r}, {space['fixed']!r}, {space['default_visible']!r}, {kind!r}, {target!r}),"
        )
    lines.extend([
        ')',
        'HOME_SPACES = tuple((key, title) for key, _, title, _, _, _, _, _, _ in HOME_SPACE_SPECS)',
        'HOME_SPACE_KEYS = tuple(key for key, _, _, _, _, _, _, _, _ in HOME_SPACE_SPECS)',
        'HOME_OPTIONAL_SPACE_KEYS = tuple(key for key, _, _, _, _, fixed, _, _, _ in HOME_SPACE_SPECS if not fixed)',
        'HOME_DEFAULT_VISIBLE_SPACE_KEYS = frozenset(key for key, _, _, _, _, _, def_vis, _, _ in HOME_SPACE_SPECS if def_vis)',
        'HOME_SPACE_TITLES = {key: title for key, _, title, _, _, _, _, _, _ in HOME_SPACE_SPECS}',
        'HOME_SPACE_TITLES_EN = {key: title_en for key, _, _, title_en, _, _, _, _, _ in HOME_SPACE_SPECS}',
        'HOME_SPACE_LABEL_IDS = {key: label_id for key, label_id, _, _, _, _, _, _, _ in HOME_SPACE_SPECS}',
        '',
        '',
        'def rail_title(key: str, *, english: bool = False) -> str:',
        '    table = HOME_RAIL_TITLES_EN if english else HOME_RAIL_TITLES',
        '    return table.get(key) or HOME_RAIL_TITLES.get(key, key)',
        '',
        '',
        'def space_title(key: str, *, english: bool = False) -> str:',
        '    table = HOME_SPACE_TITLES_EN if english else HOME_SPACE_TITLES',
        '    return table.get(key) or HOME_SPACE_TITLES.get(key, key)',
        '',
    ])
    return '\n'.join(lines).encode('utf-8')


def full_outputs(root=ROOT):
    root = Path(root)
    spec = load_spec(root / SPEC, root=root)
    raw = render(spec, ET.parse(root / SKIN / 'Includes_Titles.xml').getroot(), root=root)
    hero = render_hero(spec, root=root)
    nav = render_nav(spec, root=root)
    py_raw = render_python(spec, root=root)
    expanded_home(root, raw, hero, nav)
    return raw, hero, nav, py_raw


def all_outputs(root=ROOT):
    raw, hero, _, py_raw = full_outputs(root)
    return raw, hero, py_raw


def outputs(root=ROOT):
    raw, hero, _, _ = full_outputs(root)
    return raw, hero


def expected(root=ROOT):
    return outputs(root)[0]


def check_generated(root=ROOT):
    root = Path(root)
    raw, hero, nav, py_raw = full_outputs(root)
    path = root / OUTPUT
    if not path.is_file() or path.read_bytes() != raw:
        raise ValueError('Home rail XML is stale; run tools/generate_home_rails.py explicitly')
    hero_path = root / HERO_OUTPUT
    if not hero_path.is_file() or hero_path.read_bytes() != hero:
        raise ValueError('Home hero XML is stale; run tools/generate_home_rails.py explicitly')
    nav_path = root / NAV_OUTPUT
    if not nav_path.is_file() or nav_path.read_bytes() != nav:
        raise ValueError('Home navigation XML is stale; run tools/generate_home_rails.py explicitly')
    py_path = root / META_OUTPUT
    if not py_path.is_file() or py_path.read_bytes() != py_raw:
        raise ValueError('Home rail Python metadata is stale; run tools/generate_home_rails.py explicitly')
    inputs = (SPEC, Path('tools/generate_home_rails.py'), SKIN / 'Includes_Titles.xml')
    return {
        'schema': 2,
        'inputs': {
            inp.as_posix(): hashlib.sha256((root / inp).read_bytes()).hexdigest()
            for inp in inputs
        },
        'output': OUTPUT.as_posix(),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'hero_output': HERO_OUTPUT.as_posix(),
        'hero_sha256': hashlib.sha256(hero).hexdigest(),
        'nav_output': NAV_OUTPUT.as_posix(),
        'nav_sha256': hashlib.sha256(nav).hexdigest(),
        'python_output': META_OUTPUT.as_posix(),
        'python_sha256': hashlib.sha256(py_raw).hexdigest(),
    }


def _safe_target(root, rel_output):
    base = Path(root).resolve()
    cur = Path(root)
    for part in rel_output.parts[:-1]:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError('Unsafe generated output target')
    cur.mkdir(parents=True, exist_ok=True)
    target = cur / rel_output.parts[-1]
    if target.is_symlink() or not target.parent.resolve().is_relative_to(base):
        raise ValueError('Unsafe generated output target')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only stale output and Home closure check')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check_generated(), ensure_ascii=False, sort_keys=True))
    else:
        raw, hero, nav, py_raw = full_outputs()
        for output, data in ((OUTPUT, raw), (HERO_OUTPUT, hero), (NAV_OUTPUT, nav), (META_OUTPUT, py_raw)):
            target = _safe_target(ROOT, output)
            target.write_bytes(data)
            print('Generated ' + output.as_posix())


if __name__ == '__main__':
    main()

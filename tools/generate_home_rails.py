"""Compile reviewed, bounded home rail data to static Kodi 21 XML.

This is a build tool, never an addon service. The only write target is OUTPUT;
--check validates without repairing it. Paths/actions come from code, not JSON.
"""
import argparse
from collections import Counter
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
    if type(spec) is not dict or set(spec) != {'schema', 'rails'} or type(spec['schema']) is not int or spec['schema'] != 1:
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
    return f'String.IsEqual(Window(Home).Property(BobiRail),{control_id})'


def _focus(control_id):
    return f'Control.HasFocus({control_id})'


def _any_focus(ids):
    terms = [_focus(control_id) for control_id in ids]
    return terms[0] if len(terms) == 1 else '[' + ' | '.join(terms) + ']'


def _value(variable, text, condition=None):
    node = ET.SubElement(variable, 'value', {} if condition is None else {'condition': condition})
    node.text = str(text)


def render(spec, title_source):
    """Pure deterministic compiler; title fallback rules have one handwritten owner."""
    rails = validate(spec)['rails']
    ids = [rail['control_id'] for rail in rails]
    root = ET.Element('includes')
    root.append(ET.Comment(' Generated by tools/generate_home_rails.py; edit ui/rails/home_rails.json. '))
    rows = ET.SubElement(root, 'include', {'name': 'HomeRails'})
    for rail in rails:
        item = ET.SubElement(rows, 'include', {'content': 'HomeRailWide' if rail['layout'] == 'wide' else 'HomeRail'})
        for key, value in [('id', rail['control_id']), ('key', rail['key']), ('title', rail['title']),
                           ('content', route_path(rail)), ('limit', rail['limit']), ('preloaditems', rail['preloaditems'])]:
            ET.SubElement(item, 'param', {'name': key, 'value': str(value)})
    ET.SubElement(root, 'expression', {'name': 'BobiHomeHasItems'}).text = ' | '.join(_has(i) for i in ids)
    ET.SubElement(root, 'expression', {'name': 'BobiHomeUpdating'}).text = ' | '.join(f'Container({i}).IsUpdating' for i in ids)
    focus = ET.SubElement(root, 'variable', {'name': 'HomeContentFocus'})
    for i in ids:
        _value(focus, i, _remembered(i) + ' + ' + _has(i))
    for i in ids:
        _value(focus, i, _has(i))
    _value(focus, 9701, '$EXP[BobiHomeUpdating]')
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
        if rail['route'] == 'continue_watching':
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


def expanded_home(root, generated):
    """Expand the actual Home include closure, with Kodi include parameters.

    Other windows may reuse IDs. Only controls instantiated under Home count.
    Conditions are retained, not evaluated, so mutually hidden controls still
    cannot acquire duplicate IDs when data changes at runtime.
    """
    skin, definitions, loaded = Path(root) / SKIN, {}, set()

    def load(path):
        if path in loaded:
            return
        loaded.add(path)
        tree = ET.fromstring(generated) if path.name == OUTPUT.name else ET.parse(path).getroot()
        for node in tree:
            if node.tag == 'include' and node.get('file'):
                child = (path.parent / node.get('file')).resolve()
                if not child.is_relative_to(skin.resolve()):
                    raise ValueError('Include escapes skin directory')
                load(child)
            elif node.tag == 'include' and node.get('name'):
                definitions[node.get('name')] = node

    load(skin / 'Includes.xml')

    def substitute(value, params):
        return re.sub(r'\$PARAM\[([^]]+)\]', lambda m: params.get(m[1], m[0]), value)

    def expand(node, params, stack):
        node = copy.deepcopy(node)
        node.attrib = {key: substitute(value, params) for key, value in node.attrib.items()}
        if node.text:
            node.text = substitute(node.text, params)
        if node.tag == 'include' and not node.get('file'):
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
                    for result in expand(child, arguments, stack + (name,))]
        children = [result for child in node for result in expand(child, params, stack)]
        node[:] = children
        return [node]

    expanded = expand(ET.parse(skin / 'Home.xml').getroot(), {}, ())[0]
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
    return expanded


def expected(root=ROOT):
    root = Path(root)
    raw = render(load_spec(root / SPEC), ET.parse(root / SKIN / 'Includes_Titles.xml').getroot())
    expanded_home(root, raw)
    return raw


def check_generated(root=ROOT):
    root = Path(root)
    raw = expected(root)
    path = root / OUTPUT
    if not path.is_file() or path.read_bytes() != raw:
        raise ValueError('Home rail XML is stale; run tools/generate_home_rails.py explicitly')
    inputs = (SPEC, Path('tools/generate_home_rails.py'), SKIN / 'Includes_Titles.xml')
    return {'schema': 1, 'inputs': {path.as_posix(): hashlib.sha256((root / path).read_bytes()).hexdigest()
                                  for path in inputs},
            'output': OUTPUT.as_posix(), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only stale output and Home closure check')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check_generated(), ensure_ascii=False, sort_keys=True))
    else:
        raw = expected()
        target = ROOT / OUTPUT
        if target.is_symlink() or target.parent.resolve() != (ROOT / SKIN).resolve():
            raise ValueError('Unsafe generated output target')
        target.write_bytes(raw)
        print('Generated ' + OUTPUT.as_posix())


if __name__ == '__main__':
    main()

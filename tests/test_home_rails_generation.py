"""RailSpec safety, 35591f5 semantic preservation and one-declaration expansion."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = importlib.util.spec_from_file_location('home_rails_generator', ROOT / 'tools/generate_home_rails.py')
generator = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(generator)

# Independent pre-migration receipt, captured from the handwritten 35591f5 XML.
# Covers all 45 generated selector/title variables and expressions, including
# condition ordering and leading spaces in the episode-title separator.
BASELINE_SELECTORS_SHA256 = '92d06a2ba538bcc1601d0c6e6844662bd738de9a78d8b426834047cb730cc3ff'
BASELINE_ROWS = (
    (9810, '继续观看', 'HomeRailWide', 'plugin://plugin.video.bobbi/?action=continue_watching_menu'),
    (9830, '热门剧集', 'HomeRail', 'plugin://plugin.video.bobbi/?action=am6b_streaming_catalog&section=tv&page=1'),
    (9840, '热门电影', 'HomeRail', 'plugin://plugin.video.bobbi/?action=am6b_streaming_catalog&section=movie&page=1'),
    (9850, '当季新番', 'HomeRail', 'plugin://plugin.video.bobbi/?action=search_item&api=tmdb&mode=anime&submode=tv&category=Anime_Current_Quarter'),
    (9860, '动漫电影', 'HomeRail', 'plugin://plugin.video.bobbi/?action=search_item&api=tmdb&mode=anime&submode=movies&category=Anime_Movies_New'),
)


def spec():
    return generator.load_spec(ROOT / generator.SPEC)


def baseline_spec():
    value = spec()
    value['rails'] = [row for row in value['rails'] if row['control_id'] != 9820]
    return value


def render(value):
    return generator.render(value, ET.parse(ROOT / generator.SKIN / 'Includes_Titles.xml').getroot())


def params(node):
    return {param.get('name'): param.get('value', param.text) for param in node.findall('param')}


def test_five_rails_preserve_routes_order_labels_layout_and_budgets():
    tree = ET.fromstring(render(baseline_spec()))
    rows = tree.find("include[@name='HomeRails']").findall('include')
    actual = tuple((int(params(row)['id']), params(row)['title'], row.get('content'), params(row)['content']) for row in rows)
    assert actual == BASELINE_ROWS
    assert [params(row)['key'] for row in rows] == [
        'continue_watching', 'popular_tv', 'popular_movies', 'current_anime', 'anime_movies']
    assert all(params(row)['limit'] == '20' and params(row)['preloaditems'] == '2' for row in rows)


def test_all_generated_selectors_are_exactly_equivalent_to_handwritten_baseline():
    tree = ET.fromstring(render(baseline_spec()))
    canonical = {node.get('name'): (node.tag, node.attrib,
                 node.text if node.tag == 'expression' else [(child.attrib, child.text or '') for child in node])
                 for node in tree if node.tag in ('expression', 'variable')}
    assert len(canonical) == 45
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode()).hexdigest()
    assert digest == BASELINE_SELECTORS_SHA256


def test_generation_is_repeatable_utf8_lf_and_matches_committed_output():
    first, second = render(spec()), render(spec())
    assert first == second == (ROOT / generator.OUTPUT).read_bytes()
    assert b'\r' not in first
    assert str(ROOT).encode() not in first
    receipt = generator.check_generated(ROOT)
    assert receipt['sha256'] == hashlib.sha256(first).hexdigest()
    assert set(receipt['inputs']) == {'ui/rails/home_rails.json', 'tools/generate_home_rails.py',
                                     'addons/skin.bobbi.cinema/1080p/Includes_Titles.xml'}


def test_expanded_home_has_unique_ids_real_focus_targets_and_same_layout_limits():
    expanded = generator.expanded_home(ROOT, render(spec()))
    ids = [node.get('id') for node in expanded.iter('control') if node.get('id')]
    assert len(ids) == len(set(ids))
    for control_id, *_ in BASELINE_ROWS:
        control = expanded.find(f".//control[@id='{control_id}']")
        assert control.get('type') == 'list'
        assert control.findtext('preloaditems') == '2'
        assert control.find('content').get('limit') == '20'
        assert control.findtext('enable') == f'Integer.IsGreater(Container({control_id}).NumItems,0)'
    assert {'9701', '9870'} <= set(ids)


def test_one_new_declaration_generates_sixth_rail_navigation_titles_and_stage():
    value = baseline_spec()
    value['rails'].insert(1, dict(value['rails'][1], key='sixth_fixture', control_id=9820, title='新增 & 片单'))
    raw = render(value)
    tree = ET.fromstring(raw)
    rows = tree.find("include[@name='HomeRails']").findall('include')
    assert len(rows) == 6 and params(rows[1])['title'] == '新增 & 片单'
    assert b'&amp;' in raw
    expanded = generator.expanded_home(ROOT, raw)
    assert expanded.find(".//control[@id='9820']") is not None
    for name in ('BobiHomeHasItems', 'BobiHomeUpdating', 'HomeContentFocus', 'HomeRailUp',
                 'HomeRailDown', 'NextRailTitle', 'StageArt', 'StageMeta', 'StagePlot',
                 'StageTitlePrimary', 'StageTitleSecondary', 'StageSeasonLabel',
                 'StageEpisodeLabel', 'StageEpisodeTitle'):
        node = next(node for node in tree if node.get('name') == name)
        assert '9820' in ET.tostring(node, encoding='unicode'), name
    # Removing a declaration updates the same closure; no residual index/ID table.
    value['rails'] = [rail for rail in value['rails'] if rail['control_id'] != 9830]
    reduced = render(value)
    assert b'9830' not in reduced
    generator.expanded_home(ROOT, reduced)


@pytest.mark.parametrize('field,value', [
    ('key', 'duplicate'), ('control_id', 9810), ('control_id', True), ('control_id', '9810'),
    ('control_id', -1), ('control_id', 10000), ('layout', 'arbitrary'), ('limit', 21),
    ('limit', True), ('preloaditems', 1000), ('route', 'https://example.com'),
    ('route', 'RunScript(evil)'), ('route', 'plugin://external/'), ('route', 'PlayMedia'),
    ('title', '$INFO[System.FriendlyName]'), ('title', '[COLOR red]title'),
    ('title', 'ActivateWindow(1)'), ('title', 'special://profile/'),
    ('title', '${python}'), ('title', 'x\x00y'), ('title', 'x' * 81),
    ('params', {'url': 'http://example.com'}), ('params', {'page': '1', 'section': 'tv'}),
    ('params', {'page': True, 'section': 'tv'}), ('params', {'page': 1, 'section': 'all'}),
    ('params', {'page': 1, 'section': 'tv', 'cookie': 'never'}),
])
def test_restricted_schema_rejects_unknown_unsafe_or_unbounded_values(field, value):
    document = spec()
    document['rails'][0]['key'] = 'duplicate'
    document['rails'][1][field] = value
    with pytest.raises(ValueError):
        render(document)


@pytest.mark.parametrize('change', [
    lambda value: value.update(schema=2),
    lambda value: value.update(schema=True),
    lambda value: value.update(output='elsewhere'),
    lambda value: value['rails'][0].update(onclick='PlayMedia(evil)'),
    lambda value: value['rails'][0]['params'].update(category='current_quarter'),
    lambda value: value['rails'][3]['params'].update(category='unknown'),
])
def test_schema_fields_and_route_specific_parameters_fail_closed(change):
    value = spec()
    change(value)
    with pytest.raises(ValueError):
        render(value)


def test_json_duplicate_fields_are_rejected(tmp_path):
    path = tmp_path / 'duplicate.json'
    path.write_text('{"schema": 1, "schema": 1, "rails": []}', encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate'):
        generator.load_spec(path)


def test_id_collision_is_checked_in_expanded_home_not_other_windows():
    value = spec()
    value['rails'][0]['control_id'] = 9870  # Existing actionable empty-state button.
    with pytest.raises(ValueError, match='Duplicate expanded Home control ID'):
        generator.expanded_home(ROOT, render(value))
    # Shared IDs used by other windows don't invalidate the current home closure.
    generator.expanded_home(ROOT, render(spec()))


def test_readonly_check_detects_manual_output_edits_without_repair(tmp_path):
    shutil.copytree(ROOT / generator.SKIN, tmp_path / generator.SKIN)
    for relative in (generator.SPEC, Path('tools/generate_home_rails.py')):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    target = tmp_path / generator.OUTPUT
    damaged = target.read_bytes() + b'<!-- manual change -->\n'
    target.write_bytes(damaged)
    with pytest.raises(ValueError, match='stale'):
        generator.check_generated(tmp_path)
    assert target.read_bytes() == damaged
    result = subprocess.run([sys.executable, str(tmp_path / 'tools/generate_home_rails.py'), '--check'],
                            capture_output=True, text=True)
    assert result.returncode != 0 and 'stale' in result.stderr
    assert target.read_bytes() == damaged


def test_cli_regenerates_twice_and_invalid_spec_never_overwrites_output(tmp_path):
    shutil.copytree(ROOT / generator.SKIN, tmp_path / generator.SKIN)
    for relative in (generator.SPEC, Path('tools/generate_home_rails.py')):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    command = [sys.executable, str(tmp_path / 'tools/generate_home_rails.py')]
    target = tmp_path / generator.OUTPUT
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert target.read_bytes() == (ROOT / generator.OUTPUT).read_bytes()
    verified = subprocess.run(command + ['--check'], capture_output=True, text=True)
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)['sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    before = target.read_bytes()
    value = spec()
    value['rails'][0]['route'] = 'PlayMedia(untrusted)'
    (tmp_path / generator.SPEC).write_text(json.dumps(value), encoding='utf-8')
    rejected = subprocess.run(command, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert target.read_bytes() == before
    # The tool has no arbitrary output-path argument, even for valid input.
    rejected = subprocess.run(command + ['--output', str(tmp_path / 'elsewhere.xml')],
                              capture_output=True, text=True)
    assert rejected.returncode != 0 and not (tmp_path / 'elsewhere.xml').exists()


def test_build_checks_generated_sources_before_refresh_or_output(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / 'tools'))
    import build_release
    monkeypatch.setattr(build_release, 'check_generated',
                        lambda root: (_ for _ in ()).throw(ValueError('stale generated XML')))
    destination = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match='stale generated XML'):
        build_release.build(destination, source_check=True)
    assert not destination.exists()
    with pytest.raises(ValueError, match='stale generated XML'):
        build_release.refresh()


def test_only_committed_static_xml_is_loaded_at_runtime():
    includes = ET.parse(ROOT / generator.SKIN / 'Includes.xml').getroot()
    assert len(includes.findall("include[@file='Includes_HomeRails.generated.xml']")) == 1
    for name in ('Home.xml', 'Includes.xml', 'Includes_Home.xml', 'Includes_Titles.xml'):
        text = (ROOT / generator.SKIN / name).read_text(encoding='utf-8')
        assert 'generate_home_rails.py' not in text
        assert 'home_rails.json' not in text
    for name in ('Includes_Home.xml', 'Includes_Titles.xml'):
        tree = ET.parse(ROOT / generator.SKIN / name).getroot()
        assert not any(node.get('name', '').startswith('Stage') for node in tree if node.tag == 'variable')
        assert not any(node.get('name', '').endswith('_9810') for node in tree)

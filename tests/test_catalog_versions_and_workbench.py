"""B01/B02: bounded file descriptions, one TV browser and original-ID recovery."""
from pathlib import Path
import json
import tracemalloc
import time
from types import SimpleNamespace
import sys
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.platform'):
    sys.path.insert(0, str(ROOT/'addons'/addon/'lib'))

from bobbi_core.catalog_query import opaque, wire
from bobbi_platform import catalog_ui
from test_catalog_query import index, confirm
from test_media_library_index import insert, ref, scope, command
from test_personal_catalog import catalog, card, plugin
from test_catalog_tv_candidates import tv, writes


@pytest.mark.parametrize('kind', ['movie', 'tv'])
def test_three_versions_keep_original_file_details_only_at_file_layer(index, kind):
    files = [dict(ref(n, name='Original.%d.mkv' % n), size=1000 + n) for n in range(3)]
    insert(index, files)
    for number, file in enumerate(files):
        cmd = command(file)
        cmd['mapping'] = dict(kind=kind, title='Same work', tmdb_id=123,
            season=1 if kind == 'tv' else None, episode=2 if kind == 'tv' else None, version='版本%d' % number)
        index.apply(scope(), uuid4().hex, [cmd])
    works = index.query(scope())['items']
    assert len(works) == 1 and works[0]['variant_count'] == 3
    assert not {'file_size', 'file_name', 'version_label', 'sources', 'history_key'} & set(works[0])
    parent = works[0]['entity_id']
    if kind == 'tv':
        season = index.query(scope(), query=dict(view='seasons', parent_entity_id=parent))['items'][0]
        parent = index.query(scope(), query=dict(view='episodes', parent_entity_id=season['entity_id']))['items'][0]['entity_id']
    rows = index.query(scope(), query=dict(view='files', parent_entity_id=parent), source_names={'a'*32: '我的收藏'})['items']
    assert len(rows) == 3
    by_id = {row['entity_id']: row for row in rows}
    for number, file in enumerate(files):
        row = by_id[file['id']]
        assert row['file_name'] == file['name'] and row['file_size'] == file['size']
        assert row['version_label'] == '版本%d' % number
        assert row['sources'] == [dict(id='a'*32, name='我的收藏')]
        assert row['history_key'] == opaque(file['id'], file['size'], file['fingerprint'])


def test_long_file_version_pages_still_fit_wire_budget_and_cursor(index):
    files = [ref(n, name='长中文名称'*100 + str(n) + '.mkv') for n in range(35)]
    task = index.start('a'*32, scope());index.begin(task)
    for start in (0, 20):
        index.batch(task, files[start:start+20], dict(page=start), len(files[start:start+20]))
    index.finish(task, 'completed')
    for file in files:
        confirm(index, file)
    query, cursor, seen = dict(view='files'), None, []
    while True:
        result = index.query(scope(), query=query, cursor=cursor, limit=32, source_names={'a'*32: '来源'*80})
        assert len(wire(result)) <= 15000 and len(result['items']) <= 32
        assert all(row['truncated'] and len(row['file_name']) == 160 and len(row['sources'][0]['name']) == 80 for row in result['items'])
        seen.extend(row['entity_id'] for row in result['items'])
        cursor = result['next_cursor']
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 35


def test_legacy_oversized_version_is_explicitly_truncated_without_rewriting_mapping(index):
    file = ref();insert(index, [file]);confirm(index, file)
    saved = json.loads(index.db.execute('SELECT mapping FROM reviews WHERE file=?', (file['id'],)).fetchone()[0])
    saved['version'] = '中文版本备注'*20
    raw = json.dumps(saved)
    index.db.execute('UPDATE reviews SET mapping=? WHERE file=?', (raw, file['id']))
    row = index.query(scope(), query=dict(view='files'))['items'][0]
    assert row['version_label'] == saved['version'][:80] and row['truncated']
    assert index.db.execute('SELECT mapping FROM reviews WHERE file=?', (file['id'],)).fetchone()[0] == raw


def test_many_retired_sources_do_not_multiply_presence_work_or_detail_memory(index):
    file = ref();insert(index, [file])
    with index.transaction():
        index.db.executemany('INSERT INTO memberships VALUES(?,?,?,0)',
            (('%032x' % number, file['id'], 'old') for number in range(10000)))
    tracemalloc.start()
    began = time.monotonic()
    result = index.query(scope(), query=dict(view='files'), source_names={'a'*32: 'Active source'})
    elapsed = time.monotonic() - began
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    row = result['items'][0]
    assert len(row['sources']) == 3 and row['source_total'] == 10001 and row['truncated']
    assert dict(id='a'*32, name='Active source') in row['sources']
    assert peak < 512 * 1024 and len(wire(row)) <= 15000
    assert row['availability'] == 'observed_present' and row['source_count'] == 1
    assert elapsed < 5  # The prior membership-expanded query took about 58 s here.
    print('CATALOG_RETIRED_SOURCE_BENCHMARK ' + json.dumps(dict(memberships=10001,
        query_seconds=elapsed, python_peak_bytes=peak, displayed_sources=len(row['sources']))))


def test_workbench_explicit_states_share_query_renderer_and_source_filter(catalog):
    params = dict(catalog.params, mode='review', source_id='a'*32)
    params.pop('view')
    catalog.catalog.execute(params, 17, catalog.rpc)
    routes = [dict(parse_qsl(urlsplit(url).query)) for url, _, _ in catalog.rows]
    states = [row for row in routes if row.get('review_state')]
    assert {row['review_state'] for row in states} == {'unmatched', 'ambiguous', 'proposed', 'ignored'}
    assert all(row['mode'] == 'review' and row['source_id'] == 'a'*32 and row['view'] == 'files' for row in states)
    assert not any(action == 'catalog_items' for action, _ in catalog.query_calls)


def test_workbench_selection_reviews_exact_file_and_pagination_keeps_mode(catalog, monkeypatch):
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(KEY='history',
        FileHistory=lambda: SimpleNamespace(database=SimpleNamespace(get_key_checked=lambda key: {}))))
    catalog.page.update(items=[card('file')], next_cursor='b'*32)
    catalog.catalog.execute(dict(catalog.params, mode='review', view='files', review_state='ambiguous', source_id='c'*32), 17, catalog.rpc)
    routes = [dict(parse_qsl(urlsplit(url).query)) for url, _, _ in catalog.rows]
    assert routes[0]['action'] == 'personal_catalog_manage' and routes[0]['object_id'] == 'a'*64
    assert routes[0]['source_id'] == 'c'*32 and routes[0]['scope'] == catalog.params['scope']
    assert routes[1]['mode'] == 'review' and routes[1]['review_state'] == 'ambiguous'
    assert not catalog.resolved


@pytest.mark.parametrize('kind', ['work', 'episode'])
def test_private_detail_version_action_preserves_scope_and_filters(catalog, kind):
    descriptor = card(kind)
    catalog.page['items'] = [descriptor]
    catalog.catalog.execute(dict(catalog.params, source_id='b'*32, text='work', sort='recent_added'), 17, catalog.rpc)
    item = catalog.rows[0][1]
    values = dict(parse_qsl(urlsplit(item.properties['Bobi.Catalog.Variants']).query))
    assert values['view'] == 'files' and values['parent_entity_id'] == descriptor['entity_id']
    assert values['scope'] == catalog.params['scope'] and values['source_id'] == 'b'*32
    assert values['text'] == 'work' and values['sort'] == 'recent_added'
    import xml.etree.ElementTree as ET
    tree = ET.parse(Path(__file__).resolve().parents[1]/'addons/skin.bobbi.cinema/1080p/DialogVideoInfo.xml')
    button = tree.find(".//control[@id='985']")
    assert button.findtext('label') == '选择文件版本'
    assert 'Bobi.Catalog.Variants' in button.findtext('visible')
    assert any('Bobi.Catalog.Variants' in row.text for row in button.findall('onclick'))
    native_version = [row for row in tree.findall(".//include[@content='TextPill']")
                      if any(param.attrib.get('name') == 'id' and param.text == '14' for param in row)]
    assert len(native_version) == 1 and 'ListItem.DBID' in ET.tostring(native_version[0], encoding='unicode')
    assert tree.findtext('defaultcontrol') == '981'
    primary = tree.find(".//control[@id='981']")
    assert 'Control.IsVisible(985)' in primary.find('onright').attrib['condition']
    assert button.findtext('onleft') == '981' and button.findtext('ondown') == '50'
    actions = primary.findall('onclick')
    assert any(row.text.startswith('ActivateWindow(Videos,') and 'ListItem.IsFolder' in row.attrib['condition'] for row in actions)
    assert any(row.text.startswith('RunPlugin(') and '!ListItem.IsFolder' in row.attrib['condition'] for row in actions)
    assert not any('play_movie' in row.text or 'search' in row.text for row in actions)
    assert item.properties['Bobi.Catalog.ActionLabel'] == ('选择文件版本' if kind == 'episode' else '选择季集')


@pytest.mark.parametrize('changed', ['', 'directory', 'account'])
def test_review_result_refreshes_only_its_original_directory_and_scope(catalog, monkeypatch, changed):
    origin = ['plugin://plugin.video.bobbi/?action=personal_catalog&scope=original']
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: origin[0], raising=False)
    def review(*args, **kwargs):
        if changed == 'directory':
            origin[0] = 'plugin://other/'
        elif changed == 'account':
            catalog.account['epoch'] += 1
        return dict(complete=True, pending_request_id=None)
    monkeypatch.setattr(catalog_ui, 'review_item', review)
    def rpc(action, body):
        if action == 'catalog_item':
            return dict(file=dict(id='a'*64))
        return catalog.rpc(action, body)
    catalog.catalog.manage(dict(catalog.params, object_id='a'*64), rpc=rpc)
    refreshes = [row for row in catalog.calls if row == ('builtin', 'Container.Refresh')]
    assert len(refreshes) == (0 if changed else 1)


def test_known_replacement_hides_old_file_progress_without_moving_it(catalog, monkeypatch):
    file = ref(1)
    row = dict(version=1, id=file['id'], file_ref=file, position=42, duration=100,
        completion_reason='STOP', updated_at=1, generation=1, session_id='a'*32, sequence=1)
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('_version_history', Path(__file__).resolve().parents[1]/'addons/plugin.video.bobbi/lib/db/file_history.py')
    history = module_from_spec(spec);spec.loader.exec_module(history)
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history)
    catalog.account = scope()
    old = card('file', file['id'], file_size=file['size'], history_key=opaque(file['id'], file['size'], file['fingerprint']))
    new = dict(old, file_size=file['size']+1, history_key=opaque(file['id'], file['size']+1, file['fingerprint']))
    assert catalog.catalog.file_progress([old], catalog.account, {file['id']: row}) == {file['id']: 42}
    assert catalog.catalog.file_progress([new], catalog.account, {file['id']: row}) == {}
    assert row['file_ref'] == file and row['position'] == 42


def test_three_file_versions_render_three_independent_history_observations(catalog, monkeypatch):
    from bobbi_core.file_ref import from_selected
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('_three_version_history', ROOT/'addons/plugin.video.bobbi/lib/db/file_history.py')
    history = module_from_spec(spec);spec.loader.exec_module(history)
    files = [from_selected(catalog.account, dict(file_id=str(number), directory=False,
        name='Movie.version%d.mkv' % number, size=1024*(number+1)), 'folder') for number in range(3)]
    positions = (10, 42, 90)
    records = {file['id']: dict(version=1, id=file['id'], file_ref=file, position=position, duration=100,
        completion_reason='STOP', updated_at=1, generation=1, session_id='a'*32, sequence=1)
        for file, position in zip(files, positions)}
    history.FileHistory = lambda: SimpleNamespace(database=SimpleNamespace(get_key_checked=lambda _: records))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', history)
    catalog.page['items'] = [dict(card('file', file['id']), display_title=file['name'],
        file_name=file['name'], file_size=file['size'], version_label='版本%d' % number,
        sources=[dict(id='a'*32, name='我的收藏')], source_total=1,
        history_key=opaque(file['id'], file['size'], file['fingerprint'])) for number, file in enumerate(files)]
    catalog.catalog.execute(dict(catalog.params, view='files'), 17, catalog.rpc)
    for number, (url, item, folder) in enumerate(catalog.rows):
        assert not folder and item.properties['PercentPlayed'] == str(positions[number])
        assert '版本%d' % number in item.label2 and '我的收藏' in item.label2
        assert '本文件已观看 %d%%' % positions[number] in item.label2
        assert files[number]['id'] in url and item.properties['Bobi.Catalog.ActionLabel'] == '继续播放本文件'
    assert [row['position'] for row in records.values()] == list(positions) and not catalog.resolved


def test_legacy_navigation_is_a_scope_bound_adapter_without_item_io(catalog):
    catalog_ui._open_catalog(catalog.account, mode='review', source_id='a'*32)
    action, command_text = catalog.calls[-1]
    assert action == 'builtin' and command_text.startswith('ActivateWindow(Videos,"')
    values = dict(parse_qsl(urlsplit(command_text.split('"')[1]).query))
    assert values['action'] == 'personal_catalog' and values['mode'] == 'review'
    assert values['source_id'] == 'a'*32 and values['scope'] == catalog.params['scope']
    assert not hasattr(catalog_ui, '_items') and not catalog.query_calls


def test_source_status_never_turns_cancel_request_or_partial_scan_into_completion():
    description = catalog_ui.source_status(dict(observation=dict(coverage='partial',
        availability='observed_present', recheck_required=True, latest_state='cancel_requested',
        indexed_count=8, counts=dict(scanned=11, discovered=8, pages=2))))
    assert '等待后台确认' in description and '仅已提交部分' in description and '11 项 / 发现 8 文件' in description
    assert '已取消' not in description and '完整扫描' not in description and '挂载已变化' not in description


def test_tv_receipt_survives_redraw_and_queries_original_id_only(tv, monkeypatch):
    properties = {}
    window = SimpleNamespace(getProperty=lambda key: properties.get(key, ''), setProperty=properties.__setitem__)
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Window=lambda _: window))
    original = catalog_ui.call
    blocked = [True]
    def call(action, body, timeout):
        if action == 'catalog_receipt' and blocked[0]:
            raise OSError('receipt response unavailable')
        return original(action, body, timeout)
    monkeypatch.setattr(catalog_ui, 'call', call)
    tv.lose_reply = True
    result = catalog_ui.review_entries(tv.dialog, tv.expected, tv.entries[:5])
    request_id = writes(tv)[0]['request_id']
    assert result['pending_request_id'] == request_id and not result['complete']
    assert catalog_ui._pending_receipts(tv.expected) == [dict(request_id=request_id, count=5)]
    assert not catalog_ui._pending_receipts(dict(tv.expected, epoch=2))
    blocked[0] = False
    receipt = catalog_ui.query_receipt(tv.dialog, tv.expected, request_id)
    assert len(receipt['items']) == 5 and all(row['status'] == 'applied' for row in receipt['items'])
    assert len(writes(tv)) == 1 and not catalog_ui._pending_receipts(tv.expected)
    assert [body['request_id'] for action, body in tv.calls if action == 'catalog_receipt'] == [request_id]


def test_overlapping_tv_group_requires_explicit_trusted_source(tv, monkeypatch):
    insert(tv.index, tv.files, source='b'*32)
    original = catalog_ui.call
    def call(action, body, timeout):
        if action == 'catalog_sources':
            return dict(items=[dict(id='a'*32, name='宽目录'), dict(id='b'*32, name='可信子目录')])
        return original(action, body, timeout)
    monkeypatch.setattr(catalog_ui, 'call', call)
    choices = []
    tv.dialog.select = lambda title, labels: (choices.append((title, labels)) or 1)
    anchor = tv.index.item(tv.expected, tv.files[0]['id'])
    result = catalog_ui.review_group(tv.dialog, tv.expected, anchor, dict(media_kind='tv', title='Show', tmdb_id=123, year=2020))
    assert result['complete'] and len(choices) == 1
    calls = [body for action, body in tv.calls if action == 'catalog_group']
    assert 'source_id' not in calls[0]
    assert all(row['source_id'] == 'b'*32 for row in calls[1:])

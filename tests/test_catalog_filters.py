"""Reachable TV query controls: real SQLite results, stable hierarchy and scope."""
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
import sys

import pytest

from test_catalog_query import index
from test_media_library_index import command, insert, ref, scope
from test_personal_catalog import catalog, card, plugin


def targets(catalog):
    commands = [value for kind, value in catalog.calls if kind == 'builtin']
    assert len(commands) == 1
    assert commands[0].startswith('Container.Update("') and ',replace)' not in commands[0]
    return dict(parse_qsl(urlsplit(commands[0][len('Container.Update("'):-2]).query))


def dialog_steps(catalog, monkeypatch, steps, text='', after=None):
    selected = iter(steps)
    def choose(title, labels):
        desired = next(selected)
        if after:
            after(desired)
        if desired is None:
            return -1
        return next(i for i, label in enumerate(labels) if label.startswith(desired))
    dialog = SimpleNamespace(select=choose, input=lambda *a, **kw: text,
                             ok=lambda *args: catalog.notices.append(args))
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: dialog)
    return dialog


def test_filter_native_source_type_state_availability_sort_and_text_reach_real_query(index, catalog, monkeypatch):
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(KEY='history',
        FileHistory=lambda: SimpleNamespace(database=SimpleNamespace(get_key_checked=lambda _: {}))))
    catalog.account = scope()
    params = dict(provider=catalog.account['provider'], scope=catalog.catalog.scope_key(catalog.account), mode='filters')
    files = [ref(n, name='Movie.%d.mkv' % n) for n in (1, 2)]
    for number, file in enumerate(files):
        insert(index, [file], source=('a' if number == 0 else 'b') * 32)
        change = command(file)
        change['mapping'].update(kind='movie', title='春宵', tmdb_id=123, season=None, episode=None)
        index.apply(catalog.account, str(number + 1) * 32, [change])
    sources = [dict(id='a'*32, name='来源 A'), dict(id='b'*32, name='来源 B')]
    def rpc(action, body):
        if action == 'catalog_sources':
            assert body['expected'] == catalog.account
            return dict(items=sources)
        if action == 'catalog_query':
            catalog.query_calls.append((action, body))
            return index.query(body['expected'], query=body['query'], cursor=body['cursor'], limit=body['limit'])
        return catalog.rpc(action, body)
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: 'plugin://origin/')
    dialog_steps(catalog, monkeypatch, ['目录来源', '来源 B', '作品类型', '电影', '整理状态', '人工确认',
        '来源观察', '已收录', '排序', '最近整理', '关键词', '应用筛选'], text='春宵')
    catalog.catalog.manage(params, rpc)
    stable = targets(catalog)
    assert stable['source_id'] == 'b'*32 and stable['media_kind'] == 'movie'
    assert stable['review_state'] == 'confirmed' and stable['availability'] == 'observed_present'
    assert stable['sort'] == 'recent_edited' and stable['text'] == '春宵' and stable['view'] == 'works'
    assert stable['scope'] == params['scope'] and not {'mode', 'cursor', 'parent_entity_id'} & stable.keys()
    catalog.catalog.execute(stable, 17, rpc)
    assert len(catalog.rows) == 1
    child = dict(parse_qsl(urlsplit(catalog.rows[0][0]).query))
    assert child['source_id'] == 'b'*32 and child['sort'] == 'recent_edited'
    catalog.rows.clear()
    catalog.catalog.execute(child, 17, rpc)
    assert len(catalog.rows) == 1 and files[1]['id'] in catalog.rows[0][0]
    assert '电影' in catalog.category and '已选来源' in catalog.category
    assert not catalog.resolved


@pytest.mark.parametrize('mounted', [False, True])
def test_context_filter_keeps_parent_scope_and_review_mode_but_resets_cursor(catalog, monkeypatch, mounted):
    expected = dict(reference_kind='mounted_path', source_id='d'*32, namespace='e'*64)
    account = expected if mounted else catalog.account
    params = dict(catalog.catalog.scope_params(account), mode='filters', view='files', parent_entity_id='b'*64,
        cursor='stale', source_id='d'*32, text='old', review_state='ambiguous', review='true')
    def rpc(action, body):
        if mounted:
            assert action == 'catalog_mount_scope' and body['source_id'] == expected['source_id']
            return dict(expected)
        return catalog.rpc(action, body)
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: 'plugin://origin/')
    dialog_steps(catalog, monkeypatch, ['清除筛选', '排序', '最近加入', '应用筛选'])
    catalog.catalog.manage(params, rpc)
    stable = targets(catalog)
    assert stable['view'] == 'files' and stable['parent_entity_id'] == 'b'*64
    assert stable['source_id'] == 'd'*32 and stable['scope'] == params['scope']
    assert stable['mode'] == 'review' and stable['sort'] == 'recent_added'
    assert 'cursor' not in stable and stable.get('text', '') == '' and 'review_state' not in stable
    if mounted:
        assert stable['source'] == expected['source_id'] and stable['namespace'] == expected['namespace']


@pytest.mark.parametrize('change', ['cancel', 'directory', 'account'])
def test_filter_cancel_or_changed_origin_keeps_existing_directory(catalog, monkeypatch, change):
    origin = ['plugin://origin/']
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: origin[0])
    def after(choice):
        if choice == '应用筛选':
            if change == 'directory':
                origin[0] = 'plugin://other/'
            elif change == 'account':
                catalog.account['epoch'] += 1
    dialog_steps(catalog, monkeypatch, [None] if change == 'cancel' else ['排序', '最近整理', '应用筛选'], after=after)
    catalog.catalog.manage(dict(catalog.params, mode='filters'), catalog.rpc)
    assert not catalog.calls and not catalog.rows


def test_filter_controls_are_reachable_from_root_card_and_empty_directory(catalog, monkeypatch):
    root = dict(catalog.params); root.pop('view')
    catalog.catalog.execute(root, 17, catalog.rpc)
    target, _, folder = next(row for row in catalog.rows if row[1].label == '筛选与排序')
    assert not folder and 'mode=filters' in target
    catalog.rows.clear()
    item_type = sys.modules['xbmcgui'].ListItem
    monkeypatch.setattr(item_type, 'addContextMenuItems', lambda item, rows: setattr(item, 'menu', getattr(item, 'menu', []) + rows), raising=False)
    catalog.page['items'] = [card('episode', season=1, episode=2)]
    params = dict(catalog.params, view='episodes', parent_entity_id='b'*64, source_id='c'*32)
    catalog.catalog.execute(params, 17, catalog.rpc)
    menu = dict(catalog.rows[0][1].menu)
    stable = dict(parse_qsl(urlsplit(menu['筛选与排序'][len('RunPlugin('):-1]).query))
    assert stable['view'] == 'episodes' and stable['parent_entity_id'] == 'b'*64
    assert stable['source_id'] == 'c'*32 and stable['scope'] == params['scope']
    catalog.rows.clear();catalog.page['items'] = []
    catalog.catalog.execute(dict(catalog.params, availability='observed_absent'), 17, catalog.rpc)
    assert catalog.rows[0][1].label == '当前筛选没有作品 · 调整筛选'
    assert 'mode=filters' in catalog.rows[0][0]


def test_oversized_filter_keyword_keeps_previous_text(catalog, monkeypatch):
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: 'plugin://origin/')
    dialog_steps(catalog, monkeypatch, ['关键词', '应用筛选'], text='中' * 161)
    catalog.catalog.manage(dict(catalog.params, mode='filters', text='原关键词'), catalog.rpc)
    assert targets(catalog)['text'] == '原关键词' and catalog.notices[0][0] == '关键词过长或含控制字符'


def test_mounted_filter_rechecks_fixed_namespace_before_navigating(catalog, monkeypatch):
    expected = dict(reference_kind='mounted_path', source_id='d'*32, namespace='e'*64)
    params = dict(catalog.catalog.scope_params(expected), mode='filters')
    checks = []
    def rpc(action, body):
        assert action == 'catalog_mount_scope'
        checks.append(body)
        return dict(expected)
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: 'plugin://origin/')
    def replace(choice):
        if choice == '应用筛选':
            expected['namespace'] = 'f'*64
    dialog_steps(catalog, monkeypatch, ['排序', '最近整理', '应用筛选'], after=replace)
    catalog.catalog.manage(params, rpc)
    assert len(checks) == 2 and not catalog.calls and not catalog.rows
    assert catalog.notices[0][0] == '片库范围已变化'

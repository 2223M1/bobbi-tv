"""Declaration/orchestration regressions; native dialog behavior needs device QA."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
import xml.etree.ElementTree as ET

import pytest

from test_personal_catalog import catalog, card, plugin

ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT/'addons/skin.bobbi.cinema/1080p'


def detail_actions(identifier):
    """Expand the real small action include, preserving button action order."""
    button = ET.parse(SKIN/'DialogVideoInfo.xml').find(".//control[@id='%s']" % identifier)
    definition = ET.parse(SKIN/'Includes.xml').find("include[@name='DetailFolderNavigation']")
    actions = []
    for node in button:
        if node.tag == 'onclick':
            actions.append((node.get('condition', 'true'), node.text))
        elif node.tag == 'include' and node.get('content') == 'DetailFolderNavigation':
            params = {row.get('name'): row.text or '' for row in definition.findall('param')}
            params.update({row.get('name'): row.text or '' for row in node.findall('param')})
            for row in definition.find('definition').findall('onclick'):
                condition, action = row.get('condition', 'true'), row.text
                for key, value in params.items():
                    condition = condition.replace('$PARAM[' + key + ']', value)
                    action = action.replace('$PARAM[' + key + ']', value)
                actions.append((condition, action))
    return actions


def selected_actions(identifier, *, videos, folder=True, bobbi=True):
    values = {'true': True, 'Window.IsVisible(videos)': videos, 'ListItem.IsFolder': folder,
              'String.StartsWith(ListItem.FilenameAndPath,plugin://plugin.video.bobbi/)': bobbi}
    def matches(condition):
        return all(not values[part[1:]] if part.startswith('!') else values[part]
                   for part in condition.split(' + '))
    return [action for condition, action in detail_actions(identifier) if matches(condition)]


@pytest.mark.parametrize('identifier,source', [
    ('981', '$INFO[ListItem.FilenameAndPath]'),
    ('985', '$INFO[ListItem.Property(Bobi.Catalog.Variants)]'),
    ('984', '$INFO[ListItem.Property(Bobi.Relationships)]')])
@pytest.mark.parametrize('videos', [True, False])
def test_detail_navigation_captures_then_closes_then_navigates_without_replacing_history(identifier, source, videos):
    # Kodi selects conditions before dispatch; it resolves each action's labels
    # later. Deliberately replace ListItem after close to model that boundary.
    actions = selected_actions(identifier, videos=videos)
    assert len(actions) == 4
    assert source in actions[0]
    assert actions[1] == 'Dialog.Close(movieinformation,true)'
    target = 'plugin://plugin.video.bobbi/?action=personal_catalog&scope=original&view=files'
    current, captured, modal, visited = target, '', True, []
    executed = []
    for action in actions:
        action = action.replace(source, current).replace(
            '$INFO[Window(Home).Property(Bobi.Detail.Target)]', captured)
        executed.append(action)
        if action.startswith('SetProperty('):
            assert modal
            captured = action.split(',"', 1)[1].rsplit('",home)', 1)[0]
        elif action.startswith('Dialog.Close('):
            modal, current = False, 'plugin://other/?scope=changed'
        elif action.startswith(('Container.Update(', 'ActivateWindow(')):
            assert not modal and 'replace' not in action
            visited.append(action)
        elif action == 'ClearProperty(Bobi.Detail.Target,home)':
            captured = ''
        else:
            pytest.fail('Unexpected navigation action: ' + action)
    assert visited == [('Container.Update("' + target + '")') if videos else
                       ('ActivateWindow(Videos,"' + target + '",return)')]
    assert not captured and executed[-1] == 'ClearProperty(Bobi.Detail.Target,home)'


def test_detail_nonfolder_and_native_play_paths_remain_unchanged():
    assert selected_actions('981', videos=True, folder=False) == [
        'RunPlugin("$INFO[ListItem.FilenameAndPath]")', 'Dialog.Close(movieinformation)']
    assert selected_actions('981', videos=False, folder=True, bobbi=False) == ['SendClick(8)']


def scenario(catalog, monkeypatch, mounted):
    origin = ['plugin://plugin.video.bobbi/?action=personal_catalog&scope=original']
    monkeypatch.setattr(sys.modules['xbmc'], 'getInfoLabel', lambda _: origin[0], raising=False)
    expected = dict(reference_kind='mounted_path', source_id='d'*32, namespace='e'*64)
    params, rpc = dict(catalog.params), catalog.rpc
    if mounted:
        params = dict(catalog.catalog.scope_params(expected), view='works')
        def rpc(action, body):
            catalog.query_calls.append((action, deepcopy(body)))
            if action == 'catalog_mount_scope':
                return dict(expected)
            if action == 'catalog_mount_query':
                return deepcopy(catalog.page)
            pytest.fail('Unexpected source operation: ' + action)
    params['source_id'] = 'a'*32
    return params, rpc, origin, expected


def builtin_target(catalog):
    kind, command = catalog.calls[-1]
    assert kind == 'builtin'
    assert command.startswith('Container.Update("') and command.endswith('")')
    assert ',replace)' not in command
    return dict(parse_qsl(urlsplit(command[len('Container.Update("'):-2]).query))


@pytest.mark.parametrize('mounted', [False, True])
def test_search_is_one_shot_and_back_refresh_use_stable_text_url(catalog, monkeypatch, mounted):
    params, rpc, origin, expected = scenario(catalog, monkeypatch, mounted)
    params.pop('view')
    catalog.catalog.execute(params, 17, rpc)
    target, _, folder = next(row for row in catalog.rows if row[1].label == '搜索片库')
    search = dict(parse_qsl(urlsplit(target).query))
    assert not folder and search['action'] == 'personal_catalog_manage' and search['mode'] == 'search'
    assert search['source_id'] == 'a'*32 and 'search' not in search
    catalog.rows.clear(); catalog.ended.clear(); catalog.query_calls.clear()
    inputs = []
    sys.modules['xbmcgui'].Dialog = lambda: SimpleNamespace(input=lambda *a, **k: (inputs.append(a) or ' 剧 "集", (1) '))
    catalog.catalog.manage(search, rpc)
    stable = builtin_target(catalog)
    assert stable['text'] == '剧 "集", (1)' and stable['view'] == 'works'
    assert stable['scope'] == params['scope'] and stable['source_id'] == 'a'*32
    assert not {'search', 'mode', 'cursor'} & set(stable)
    assert not catalog.rows and not catalog.ended
    assert not any(action.endswith('_query') for action, _ in catalog.query_calls)
    catalog.page.update(items=[card()], next_cursor='b'*32)
    for _ in range(2):  # A Back / Refresh opens the same URL without another prompt.
        catalog.rows.clear()
        catalog.catalog.execute(stable, 17, rpc)
        child = dict(parse_qsl(urlsplit(catalog.rows[0][0]).query))
        next_page = dict(parse_qsl(urlsplit(catalog.rows[-1][0]).query))
        assert child['text'] == next_page['text'] == stable['text']
        assert child['scope'] == next_page['scope'] == stable['scope']
    assert len(inputs) == 1


@pytest.mark.parametrize('mounted', [False, True])
@pytest.mark.parametrize('change', ['cancel', 'directory', 'authority'])
def test_search_cancellation_or_context_change_never_navigates(catalog, monkeypatch, mounted, change):
    params, rpc, origin, expected = scenario(catalog, monkeypatch, mounted)
    def enter(*args, **kwargs):
        if change == 'directory':
            origin[0] = 'plugin://other/'
        elif change == 'authority':
            if mounted:
                expected['namespace'] = 'f'*64
            else:
                catalog.account['epoch'] += 1
        return '' if change == 'cancel' else 'work'
    sys.modules['xbmcgui'].Dialog = lambda: SimpleNamespace(input=enter, ok=lambda *a: catalog.notices.append(a))
    catalog.catalog.manage(dict(params, mode='search'), rpc)
    assert not catalog.calls and not catalog.rows and not catalog.ended
    assert not any(action.endswith('_query') for action, _ in catalog.query_calls)


@pytest.mark.parametrize('mounted', [False, True])
def test_search_rechecks_original_directory_after_slow_authority_check(catalog, monkeypatch, mounted):
    params, rpc, origin, _ = scenario(catalog, monkeypatch, mounted)
    checks = []
    def slow(action, body):
        result = rpc(action, body)
        if action in ('pan_status', 'catalog_mount_scope'):
            checks.append(action)
            if len(checks) == 2:
                origin[0] = 'plugin://other/'
        return result
    catalog.catalog.manage(dict(params, mode='search'), slow)
    assert len(checks) == 2 and not catalog.calls and not catalog.rows


@pytest.mark.parametrize('handle', [17, -1])
def test_legacy_search_url_redirects_without_rendering_a_search_directory(catalog, monkeypatch, handle):
    params, rpc, _, _ = scenario(catalog, monkeypatch, False)
    catalog.catalog.execute(dict(params, search='true', cursor='stale'), handle, rpc)
    stable = builtin_target(catalog)
    assert stable['text'] == '测试' and 'search' not in stable and 'cursor' not in stable
    assert not catalog.rows and not any(action == 'catalog_query' for action, _ in catalog.query_calls)
    assert catalog.ended == ([((17,), dict(succeeded=False, cacheToDisc=False))] if handle >= 0 else [])


@pytest.mark.parametrize('mounted', [False, True])
def test_empty_old_group_has_only_explicit_same_scope_recovery(catalog, monkeypatch, mounted):
    params, rpc, _, _ = scenario(catalog, monkeypatch, mounted)
    catalog.catalog.execute(dict(params, view='files', parent_entity_id='b'*64,
        text='old work', review_state='unmatched', media_kind='unknown'), 17, rpc)
    assert [row[1].label for row in catalog.rows] == ['返回当前来源作品', '继续整理当前来源']
    targets = [dict(parse_qsl(urlsplit(url).query)) for url, _, _ in catalog.rows]
    for row in targets:
        assert row['scope'] == params['scope'] and row['source_id'] == 'a'*32
        assert not {'parent_entity_id', 'text', 'review_state', 'media_kind'} & set(row)
        if mounted:
            assert row['source'] == params['source'] and row['namespace'] == params['namespace']
        else:
            assert row['provider'] == params['provider']
    assert targets[0]['view'] == 'works' and targets[1]['mode'] == 'review'
    assert all(folder for _, _, folder in catalog.rows) and not catalog.calls

"""TV orchestration uses existing directory/review/player boundaries only."""
from copy import deepcopy
import sys
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import pytest

from test_personal_catalog import catalog, card, plugin
from test_ce2096_pan_playback import entry


@pytest.mark.parametrize('parent_kind', ['shared', 'version', 'custom', 'unnamed'])
def test_tv_supplement_relation_has_explicit_parent_and_cas(catalog, monkeypatch, parent_kind):
    from lib.utils.views import catalog_supplement_ui as ui
    from bobbi_platform import catalog_ui
    calls, reviewed, notices = [], [], []
    native = parent_kind in ('shared', 'version')
    choices = iter([0, 0] + ([int(parent_kind == 'version')] if native else []) + [0])
    inputs = iter(['', '制作花絮'])
    dialog = SimpleNamespace(select=lambda *args: next(choices), input=lambda *args, **kw: next(inputs),
                             ok=lambda *args: notices.append(args))
    def rpc(action, body):
        calls.append((action, deepcopy(body)))
        if action == 'catalog_query':
            return dict(items=[dict(entity_id='a'*64, display_title='主作品',
                metadata_key='tmdb:movie:1' if native else None, review_revision=7, observation_key='b'*64)], next_cursor=None)
        assert action == 'catalog_item'
        return dict(file=dict(id='a'*64, observation_key='b'*64), revision=7, state='unmatched',
                    provenance='manual', mapping=dict(kind='custom') if parent_kind == 'custom' else None)
    monkeypatch.setattr(catalog_ui, 'review_entries', lambda dialog, expected, entries: reviewed.extend(entries))
    ui.edit(dialog, catalog.account, dict(file=dict(id='c'*64, name='extra.mkv'), revision=3), rpc)
    if parent_kind == 'unnamed':
        assert not reviewed and notices
        return
    command = reviewed[0]['command']
    assert command['file_id'] == 'c'*64 and command['expected_revision'] == 3
    relation = command['mapping']
    assert relation['title'] == '制作花絮' and relation['kind'] == 'bonus'
    assert relation['metadata_key'] == ('tmdb:movie:1' if native else None)
    assert relation['parent_file_id'] == (None if parent_kind == 'shared' else 'a'*64)
    assert relation['parent_revision'] == (None if parent_kind == 'shared' else 7)
    assert relation['parent_evidence'] == (None if parent_kind == 'shared' else 'b'*64)
    assert all(action in ('catalog_query', 'catalog_item') for action, _ in calls)


@pytest.mark.parametrize('accept,abort', [(True, False), (False, False), (True, True)])
def test_failed_resume_recovery_only_navigates_with_explicit_confirmation(entry, monkeypatch, accept, abort):
    navigated, prompts, reads = [], [], []
    monkeypatch.setattr(sys.modules['xbmc'], 'executebuiltin', navigated.append, raising=False)
    monkeypatch.setattr(sys.modules['xbmc'], 'Monitor', lambda: SimpleNamespace(abortRequested=lambda: abort))
    monkeypatch.setattr(sys.modules['xbmcgui'], 'Dialog', lambda: SimpleNamespace(
        yesno=lambda *args: (prompts.append(args) or accept)))
    def rpc(action, body):
        reads.append((action, body))
        return dict(items=[dict(entity_id='c'*64, parent_entity_id='d'*64, expected=entry.expected)])
    monkeypatch.setattr(entry.module, 'call', rpc)
    entry.module._offer_history_versions('c'*64)
    assert reads == [('catalog_history_links', dict(history_ids=['c'*64]))]
    assert bool(navigated) is (accept and not abort)
    assert bool(prompts) is (not abort)
    if navigated:
        assert navigated[0].startswith('ActivateWindow(Videos,"plugin://plugin.video.bobbi/')
        assert 'parent_entity_id=' + 'd'*64 in navigated[0] and 'view=files' in navigated[0]
    assert not entry.played and not entry.calls


@pytest.mark.parametrize('mode', ['saved', 'rail'])
def test_saved_query_reuses_existing_renderer_and_default_home_rail(catalog, monkeypatch, mode):
    from lib.utils.views import catalog_saved_views as ui
    opened = []
    record = dict(id='c'*32, title='最近收藏')
    def current(identifier):
        opened.append(identifier)
        return record
    monkeypatch.setattr(ui, 'current', current)
    monkeypatch.setattr(ui, 'resolve', lambda row, rpc: (catalog.account,
        dict(view='files', text='导演', sort='recent_added')))
    monkeypatch.setitem(sys.modules, 'lib.db.file_history', SimpleNamespace(KEY='files',
        FileHistory=lambda: SimpleNamespace(database=SimpleNamespace(get_key_checked=lambda key: {}))))
    catalog.page['items'] = [card('file')]
    catalog.catalog.execute(dict(mode=mode, view_id=record['id']), 17, catalog.rpc)
    assert opened == [record['id'] if mode == 'saved' else None]
    reads = [body for action, body in catalog.query_calls if action == 'catalog_query']
    assert len(reads) == 1 and reads[0]['query']['text'] == '导演'
    assert reads[0]['query']['view'] == 'files' and reads[0]['query']['sort'] == 'recent_added'
    target = dict(parse_qsl(urlsplit(catalog.rows[0][0]).query))
    assert target['action'] == 'personal_catalog_play' and target['object_id'] == 'a'*64
    assert not catalog.resolved


def test_explicit_scope_rail_is_not_overridden_by_active_saved_view(catalog, monkeypatch):
    from lib.utils.views import catalog_saved_views as ui
    monkeypatch.setattr(ui, 'current', lambda *args: pytest.fail('Scoped rail must not read the Home default'))
    catalog.page['items'] = [card()]
    catalog.catalog.execute(dict(catalog.params, mode='rail'), 17, catalog.rpc)
    assert len(catalog.rows) == 1

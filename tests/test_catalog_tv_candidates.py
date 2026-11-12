"""Real MediaIndex + TV dialog events for candidate-derived bounded reviews."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from bobbi_platform import catalog_ui
from test_media_library_index import index, insert, ref, scope

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tv(index, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi'))
    expected = scope()
    files = [ref(number+1, name='Show.2020.S00E%02d.mkv'%(number+1)) for number in range(12)]
    insert(index, files)
    entries = [dict(name=file['name'], command=dict(file_id=file['id'], expected_revision=0, action='confirm',
        mapping=dict(kind='tv', title='Show', tmdb_id=123, season=0, episode=number+1, version=None)))
        for number, file in enumerate(files)]
    state = SimpleNamespace(index=index, expected=expected, files=files, entries=entries, calls=[], views=[], messages=[],
                            confirm=None, after_apply=None, lose_reply=False, multi=None)
    def call(action, body, timeout):
        assert timeout == 2 and body['expected'] == expected
        state.calls.append((action, deepcopy(body)))
        params = dict(body);params.pop('expected')
        method = {'catalog_preview': index.preview, 'catalog_apply': index.apply,
                  'catalog_receipt': index.receipt, 'catalog_group': index.group}[action]
        result = method(expected, **params)
        if action == 'catalog_apply':
            if state.after_apply:
                state.after_apply()
            if state.lose_reply:
                state.lose_reply = False
                raise OSError('response dropped after the real database commit')
        return result
    def yesno(title, message):
        if state.confirm:
            return state.confirm(title, message)
        return title != '需要逐项调整季集？'
    def multiselect(title, labels, preselect):
        state.multi = (title, labels, preselect)
        return preselect
    state.dialog = SimpleNamespace(yesno=yesno, textviewer=lambda title, message:state.views.append((title,message)),
                                   ok=lambda title,message:state.messages.append((title,message)), multiselect=multiselect)
    monkeypatch.setattr(catalog_ui, 'call', call)
    # The production review now binds profile/runtime ownership at admission;
    # this fixture supplies the same in-memory RPC through that exact seam.
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(index.path.parent)))
    binding = SimpleNamespace(root=lambda: index.path.parent, require_current=lambda: None)
    monkeypatch.setattr(catalog_ui, '_review_context', lambda expected:
        (binding, lambda action, **body: catalog_ui._call(action, expected, **body)))
    return state


def writes(tv):
    return [body for action, body in tv.calls if action == 'catalog_apply']


def test_tv_previews_12_real_files_then_5_5_2_and_keeps_special_season(tv):
    original = deepcopy(tv.entries)
    catalog_ui.review_entries(tv.dialog, tv.expected, tv.entries)
    assert [len(body['commands']) for body in writes(tv)] == [5, 5, 2]
    assert len({body['request_id'] for body in writes(tv)}) == 3
    assert tv.views[0][0] == '逐项预览（尚未保存）'
    assert tv.views[0][1].count('修改后描述 Show') == 12
    assert '原描述 未设置' in tv.views[0][1]
    assert 'S00E01 · 版本备注 未填写' in tv.views[0][1]
    assert '操作 保存描述 · 修改后状态 人工确认' in tv.views[0][1]
    assert not any(raw in tv.views[0][1] for raw in ('None', 'confirm', "{'kind'"))
    assert tv.entries == original
    assert [command for body in writes(tv) for command in body['commands']] == [row['command'] for row in original]
    assert '已保存 12/12' in tv.views[-1][0]
    assert all(tv.index._item(file['id'], tv.expected)['mapping']['season'] == 0 for file in tv.files)


@pytest.mark.parametrize('kind,season,episode,expected', [
    ('tv', 1, 1, '剧集 · TMDb 123 · S01E01'),
    ('tv', 0, 101, '剧集 · TMDb 123 · S00E101'),
    ('movie', None, None, '电影 · TMDb 123'),
    ('custom', None, None, '自定义名称'),
])
def test_preview_mapping_is_readable_without_changing_values(kind, season, episode, expected):
    value = dict(kind=kind, title='作品名称', tmdb_id=None if kind == 'custom' else 123,
                 season=season, episode=episode, version='导演剪辑版')
    original = deepcopy(value)
    text = catalog_ui._mapping_description(value)
    assert text == '作品名称 · ' + expected + ' · 版本备注 导演剪辑版'
    assert value == original
    assert 'None' not in text


@pytest.mark.parametrize('action,label,state', [
    ('unbind', '解除绑定', '待匹配'),
    ('ignore', '忽略此项', '已忽略'),
    ('undo', '撤回上次修改', '待确认建议'),
])
def test_review_removal_preview_translates_real_before_after_and_preserves_command(tv, action, label, state):
    initial = deepcopy(tv.entries[0]['command'])
    initial['mapping'].update(season=1, episode=1, version='原版')
    tv.index.apply(tv.expected, 'f' * 32, [initial])
    entry = dict(name=tv.entries[0]['name'], command=dict(initial, expected_revision=1, action=action, mapping=None))
    original = deepcopy(entry)
    tv.confirm = lambda title, message: False
    catalog_ui.review_entries(tv.dialog, tv.expected, [entry])
    text = tv.views[0][1]
    assert '记录修订 1' in text
    assert '原描述 Show · 剧集 · TMDb 123 · S01E01 · 版本备注 原版' in text
    assert '修改后描述 未设置' in text
    assert '操作 %s · 修改后状态 %s' % (label, state) in text
    assert not any(raw in text for raw in ('None', action, "{'kind'"))
    assert entry == original and not writes(tv)
    assert tv.calls[0][1]['commands'] == [original['command']]
    assert tv.index._item(tv.files[0]['id'], tv.expected)['revision'] == 1


def test_tv_mid_plan_stop_preserves_first_commit_and_unstarted_revisions(tv):
    tv.confirm = lambda title, message:title != '继续下一批？'
    catalog_ui.review_entries(tv.dialog, tv.expected, tv.entries)
    assert len(writes(tv)) == 1
    assert '已保存 5/12' in tv.views[-1][0]
    assert [tv.index._item(file['id'], tv.expected)['revision'] for file in tv.files] == [1]*5+[0]*7


def test_tv_lost_apply_reply_queries_original_id_without_a_second_write(tv):
    tv.lose_reply = True
    catalog_ui.review_entries(tv.dialog, tv.expected, tv.entries[:5])
    applied = writes(tv)
    assert len(applied) == 1
    receipts = [body for action, body in tv.calls if action == 'catalog_receipt']
    assert receipts == [dict(expected=tv.expected, request_id=applied[0]['request_id'])]
    assert '已保存 5/5' in tv.views[-1][0]


def test_tv_later_revision_conflict_cannot_roll_back_or_overwrite_previous_chunk(tv):
    def concurrent_change():
        tv.after_apply = None
        command = deepcopy(tv.entries[5]['command']);command['mapping']['title'] = 'Newer manual title'
        tv.index.apply(tv.expected, 'f'*32, [command])
    tv.after_apply = concurrent_change
    catalog_ui.review_entries(tv.dialog, tv.expected, tv.entries)
    assert len(writes(tv)) == 1
    assert '已保存 5/12' in tv.views[-1][0] and '后续批次出现冲突' in tv.views[-1][1]
    assert tv.index._item(tv.files[5]['id'], tv.expected)['mapping']['title'] == 'Newer manual title'
    assert tv.index._item(tv.files[11]['id'], tv.expected)['revision'] == 0


def test_tv_group_uses_real_same_parent_source_and_manual_selection_before_cas(tv):
    candidate = dict(media_kind='tv', title='Show', tmdb_id=123, year=2020)
    anchor = tv.index._public(tv.index._item(tv.files[0]['id'], tv.expected))
    catalog_ui.review_group(tv.dialog, tv.expected, anchor, candidate)
    assert tv.multi[0] == '逐项选择：同目录不证明同作品；排除合集 / 重制版 / 多集文件'
    assert len(tv.multi[1]) == 12 and len(tv.multi[2]) == 12
    group_calls = [body for action, body in tv.calls if action == 'catalog_group']
    assert len(group_calls) == 3
    assert group_calls[1]['source_id'] == 'a'*32 and isinstance(group_calls[1]['projection_revision'], int)
    assert [len(body['commands']) for body in writes(tv)] == [5, 5, 2]


def test_tv_group_does_not_derive_episodes_for_movie_candidate(tv):
    candidate = dict(media_kind='movie', title='Show', tmdb_id=123, year=2020)
    anchor = tv.index._public(tv.index._item(tv.files[0]['id'], tv.expected))
    catalog_ui.review_group(tv.dialog, tv.expected, anchor, candidate)
    assert tv.messages[0][0] == '请先选择剧集候选'
    assert not tv.calls


def test_tv_group_over_100_uses_explicit_rounds_and_preserves_prior_real_receipts(tv):
    files = [ref(number+1, name='Show.2020.S00E%03d.mkv' % (number+1)) for number in range(105)]
    task = tv.index.start('a' * 32, tv.expected)
    tv.index.begin(task)
    for offset in range(0, len(files), 20):
        tv.index.batch(task, files[offset:offset + 20], dict(page=offset // 20 + 1), len(files[offset:offset + 20]))
    tv.index.finish(task, 'completed')
    anchor = tv.index.item(tv.expected, files[0]['id'])
    catalog_ui.review_group(tv.dialog, tv.expected, anchor, dict(media_kind='tv', title='Show', tmdb_id=123, year=2020))
    assert [len(body['commands']) for body in writes(tv)] == [5] * 21
    assert all(tv.index.item(tv.expected, row['id'])['revision'] == 1 for row in files)
    assert [title for title, _ in tv.views if title.startswith('真实回执')] == [
        '真实回执 · 已保存 100/100', '真实回执 · 已保存 5/5']

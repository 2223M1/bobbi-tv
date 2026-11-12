"""TV catalog review preserves preview, revision and task-state boundaries."""
from copy import deepcopy
from types import SimpleNamespace
import sys

import pytest

from bobbi_platform import catalog_ui


@pytest.fixture
def ui(monkeypatch):
    state = SimpleNamespace(choices=[], inputs=[], confirmations=[], responses=[],
                            events=[], calls=[], menus=[], messages=[], prompts=[], views=[])
    state.expected = dict(provider='baidu', account_id='baidu:' + 'a' * 64, epoch=7)

    def select(title, labels):
        state.events.append(('select', title))
        state.menus.append((title, list(labels)))
        return state.choices.pop(0)

    def input_value(title, **kwargs):
        state.events.append(('input', title))
        return state.inputs.pop(0)

    def yesno(title, message):
        state.events.append(('confirm', title))
        state.prompts.append((title, message))
        return state.confirmations.pop(0)

    def ok(title, message):
        state.events.append(('message', title))
        state.messages.append((title, message))

    def call(action, body, timeout):
        assert timeout == 2 and body['expected'] == state.expected
        state.events.append(('call', action))
        state.calls.append((action, deepcopy(body)))
        expected_action, result = state.responses.pop(0)
        assert action == expected_action
        return deepcopy(result)

    state.dialog = SimpleNamespace(select=select, input=input_value, yesno=yesno, ok=ok,
                                   textviewer=lambda title,body:state.views.append((title,body)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: state.dialog))
    monkeypatch.setattr(catalog_ui, 'call', call)
    return state


@pytest.fixture
def item():
    return dict(file=dict(id='f' * 64, name='Original.S01E02.mkv', parent='parent'),
                revision=4, state='confirmed', available=True,
                mapping=dict(kind='custom', title='Current title'), reason='manual', candidates=[])


def preview(title='Preview title', status='ready'):
    return dict(items=[dict(status=status, after=dict(kind='custom', title=title),
                            after_state='confirmed')])


def test_preview_precedes_confirmation_and_same_revision_apply(ui, item):
    ui.choices, ui.inputs, ui.confirmations = [5, 0], ['Requested title'], [True]
    ui.responses = [('catalog_preview', preview()),
                    ('catalog_preview', preview()),
                    ('catalog_apply', dict(items=[dict(status='applied')]))]
    catalog_ui.review_item(ui.dialog, ui.expected, item)

    assert [event for event in ui.events if event[0] in ('call', 'confirm')] == [
        ('call', 'catalog_preview'), ('confirm', '确认分批保存？'), ('call', 'catalog_preview'), ('call', 'catalog_apply')]
    first, refreshed, second = (body for _, body in ui.calls)
    assert first['commands'] == refreshed['commands'] == second['commands'] == [dict(
        file_id=item['file']['id'], expected_revision=4, action='confirm',
        mapping=dict(kind='custom', title='Requested title', tmdb_id=None,
                     season=None, episode=None, version=None))]
    assert len(second['request_id']) == 32 and int(second['request_id'], 16) >= 0
    assert 'Preview title' in ui.views[0][1]
    assert '已保存 1/1' in ui.views[-1][0]


def test_stale_preview_refuses_confirmation_and_write(ui, item):
    ui.choices = [2]
    ui.responses = [('catalog_preview', preview(status='conflict'))]
    catalog_ui.review_item(ui.dialog, ui.expected, item)
    assert [action for action, _ in ui.calls] == ['catalog_preview']
    assert not ui.prompts
    assert ui.messages[0][0] == '预览包含冲突'
    assert '未提交任何批次' in ui.messages[0][1]


def test_cancelled_confirmation_does_not_apply(ui, item):
    ui.choices, ui.confirmations = [3], [False]
    ui.responses = [('catalog_preview', dict(items=[dict(
        status='ready', after=None, after_state='ignored')]))]
    catalog_ui.review_item(ui.dialog, ui.expected, item)
    assert [action for action, _ in ui.calls] == ['catalog_preview']
    assert ui.calls[0][1]['commands'][0]['action'] == 'ignore'
    assert len(ui.prompts) == 1 and not ui.messages


def test_undo_confirmation_displays_actual_restored_preview_title(ui, item):
    ui.choices, ui.confirmations = [4], [True]
    ui.responses = [('catalog_preview', preview('Earlier restored title')),
                    ('catalog_preview', preview('Earlier restored title')),
                    ('catalog_apply', dict(items=[dict(status='applied')]))]
    catalog_ui.review_item(ui.dialog, ui.expected, item)
    assert ui.calls[0][1]['commands'][0]['action'] == 'undo'
    assert ui.calls[0][1]['commands'][0]['mapping'] is None
    message = ui.views[0][1]
    assert 'Earlier restored title' in message and 'Current title' not in message
    assert '解除描述' not in message
    assert '已保存 1/1' in ui.views[-1][0]


def test_revision_change_after_preview_is_not_reported_as_saved(ui, item):
    ui.choices, ui.confirmations = [2], [True]
    ui.responses = [('catalog_preview', dict(items=[dict(
        status='ready', after=None, after_state='unmatched')])),
        ('catalog_preview', dict(items=[dict(status='ready', after=None, after_state='unmatched')])),
        ('catalog_apply', dict(items=[dict(status='conflict', revision=5)]))]
    catalog_ui.review_item(ui.dialog, ui.expected, item)
    assert ui.calls[1][1]['commands'][0]['expected_revision'] == item['revision']
    assert '已保存 0/1' in ui.views[-1][0] and '版本冲突' in ui.views[-1][1]


def test_version_note_edit_uses_same_preview_and_cas_writer(ui, item):
    item['mapping'].update(tmdb_id=None, season=None, episode=None, version='Old note')
    ui.choices, ui.inputs, ui.confirmations = [7], ['影院加长版'], [True]
    ui.responses = [('catalog_preview', preview()), ('catalog_preview', preview()),
                    ('catalog_apply', dict(items=[dict(status='applied')]))]
    catalog_ui.review_item(ui.dialog, ui.expected, item)
    commands = [body['commands'][0] for _, body in ui.calls]
    assert all(row['mapping']['version'] == '影院加长版' and row['expected_revision'] == 4 for row in commands)
    assert all(row['mapping']['title'] == 'Current title' for row in commands)


def test_legacy_offset_browser_is_retired():
    assert not hasattr(catalog_ui, '_items')


def test_cancel_task_remains_request_state_until_backend_confirms(ui):
    running = dict(task_id='task-1', state='running', cancel_requested=False,
                   counts=dict(scanned=2, discovered=8), result_summary='')
    requested = dict(running, cancel_requested=True)
    ui.choices, ui.confirmations = [0, -1], [True]
    ui.responses = [
        ('catalog_jobs', dict(items=[running], next_offset=None)),
        ('catalog_cancel', dict(accepted=True)),
        ('catalog_jobs', dict(items=[requested], next_offset=None)),
    ]
    catalog_ui._jobs(ui.dialog, ui.expected)
    assert [action for action, _ in ui.calls] == ['catalog_jobs', 'catalog_cancel', 'catalog_jobs']
    assert ui.calls[1][1] == dict(expected=ui.expected, task_id='task-1')
    assert '正在取消' not in ui.menus[0][1][0]
    assert '扫描中' in ui.menus[1][1][0] and '正在取消' in ui.menus[1][1][0]
    assert '已取消' not in ui.menus[1][1][0] and not ui.messages
    assert '后台确认停止后才会显示已取消' in ui.prompts[0][1]
